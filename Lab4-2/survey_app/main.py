"""FastAPI factory with MongoDB-backed authentication and owner-scoped APIs."""
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError

from .config import Settings
from .db import create_client, initialize_schema
from .errors import DomainError
from .library import LibraryService
from .models import (BankInput, BankItemInput, BankPatch, BankVersionInput, Credentials, DeadlineInput,
                     DraftInput, ImportQuestionInput, Metadata, PublishInput, QuestionInput,
                     QuestionStatusInput, NextInput, RevisionInput, ShareInput, SubmitInput)
from .security import COOKIE_NAME, new_session, public_user, session_user, token_digest
from .service import SurveyService

ROOT = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        client = create_client(settings)
        client.admin.command('ping')
        db = client[settings.database]
        initialize_schema(db)
        app.state.db, app.state.client, app.state.settings = db, client, settings
        surveys = SurveyService(db, client, settings)
        library = LibraryService(db, client, settings, surveys=surveys)
        surveys.library = library
        app.state.service, app.state.library = surveys, library
        try:
            yield
        finally:
            client.close()

    app = FastAPI(title='问卷工作台 API', version='1.0', lifespan=lifespan)
    app.mount('/static', StaticFiles(directory=ROOT / 'static', check_dir=False), name='static')

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse(exc.payload(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Do not echo input values: validation errors may otherwise disclose passwords.
        return JSONResponse({'error': {'code': 'validation', 'message': '请求字段或类型不合法',
                                      'fields': ['.'.join(str(x) for x in item['loc']) for item in exc.errors()]}}, status_code=422)

    @app.exception_handler(PyMongoError)
    async def database_error(request, exc):
        return JSONResponse({'error': {'code': 'database', 'message': '数据库暂时不可用，请稍后重试'}}, status_code=503)

    @app.middleware('http')
    async def request_boundaries(request, call_next):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            if origin:
                try:
                    parsed = urlsplit(origin)
                    valid_origin = (parsed.netloc.lower() == request.headers.get('host', '').lower()
                                    and parsed.scheme == request.url.scheme
                                    and not (parsed.path or parsed.query or parsed.fragment or parsed.username))
                except ValueError:
                    valid_origin = False
                if not valid_origin:
                    return JSONResponse({'error': {'code': 'origin', 'message': '拒绝跨站请求'}}, status_code=403)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 1024 * 1024:
                    return JSONResponse({'error': {'code': 'too_large', 'message': '请求不能超过 1 MiB'}}, status_code=422)
                chunks.append(chunk)
            # Starlette's cached request forwards the bounded body to downstream parsing.
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    def user(request):
        return session_user(request.app.state.db, settings, request.cookies.get(COOKIE_NAME))

    def service(request):
        return request.app.state.service

    def library(request):
        return request.app.state.library

    @app.get('/', include_in_schema=False)
    @app.get('/survey/{code}', include_in_schema=False)
    def page():
        return FileResponse(ROOT / 'templates/index.html')

    @app.get('/library', include_in_schema=False)
    def library_page():
        return FileResponse(ROOT / 'templates/library.html')

    @app.get('/health')
    def health(request: Request):
        request.app.state.db.command('ping')
        return {'status': 'ok', 'database': 'connected'}

    @app.post('/api/auth/register', status_code=201)
    def register(body: Credentials, request: Request):
        return service(request).register(body.username, body.password)

    @app.post('/api/auth/login')
    def login(body: Credentials, request: Request, response: Response):
        account = service(request).login(body.username, body.password)
        token = new_session(request.app.state.db, settings, account['_id'])
        response.set_cookie(COOKIE_NAME, token, max_age=settings.session_ttl_seconds, httponly=True,
                            secure=settings.cookie_secure, samesite='strict', path='/')
        return public_user(account)

    @app.get('/api/auth/me')
    def me(request: Request):
        return public_user(user(request))

    @app.post('/api/auth/logout', status_code=204)
    def logout(request: Request):
        token = request.cookies.get(COOKIE_NAME)
        if token:
            request.app.state.db.sessions.delete_one({'_id': token_digest(token, settings.session_secret)})
        response = Response(status_code=204)
        response.delete_cookie(COOKIE_NAME, path='/')
        return response

    @app.post('/api/surveys', status_code=201)
    def create_survey(body: Metadata, request: Request):
        return service(request).create_survey(user(request)['_id'], body.model_dump())

    @app.get('/api/surveys')
    def surveys(request: Request):
        return service(request).list_surveys(user(request)['_id'])

    @app.get('/api/surveys/{survey_id}')
    def detail(survey_id: str, request: Request):
        account = user(request)
        return service(request).survey_payload(service(request).owned(survey_id, account['_id']))

    @app.put('/api/surveys/{survey_id}')
    def update(survey_id: str, body: DraftInput, request: Request):
        return service(request).update_survey(survey_id, user(request)['_id'], body.model_dump())

    @app.post('/api/surveys/{survey_id}/publish')
    def publish(survey_id: str, body: PublishInput, request: Request):
        return service(request).publish(survey_id, user(request)['_id'], body.revision)

    @app.patch('/api/surveys/{survey_id}/deadline')
    def deadline(survey_id: str, body: DeadlineInput, request: Request):
        return service(request).set_deadline(survey_id, user(request)['_id'], body.closes_at)

    @app.post('/api/surveys/{survey_id}/close')
    def close(survey_id: str, request: Request):
        return service(request).close(survey_id, user(request)['_id'])

    @app.get('/api/fill/{code}')
    def fill(code: str, request: Request):
        user(request)
        return service(request).fill_view(code)

    @app.post('/api/fill/{code}/next')
    def next_question(code: str, body: NextInput, request: Request):
        user(request)
        return service(request).next_question(code, body.version, body.answers)

    @app.post('/api/fill/{code}/submit')
    def submit(code: str, body: SubmitInput, request: Request):
        account = user(request)
        return service(request).submit(code, account['_id'], body.version, body.request_id, body.answers)

    @app.get('/api/surveys/{survey_id}/statistics')
    def statistics(survey_id: str, request: Request):
        return service(request).statistics(survey_id, user(request)['_id'])

    @app.get('/api/surveys/{survey_id}/statistics/{question_id}')
    def question_statistics(survey_id: str, question_id: str, request: Request):
        return service(request).statistics(survey_id, user(request)['_id'], question_id)

    @app.get('/api/surveys/{survey_id}/responses')
    def responses(survey_id: str, request: Request):
        return service(request).responses(survey_id, user(request)['_id'])

    # ------------------------------------------------------------------ stored questions
    @app.post('/api/questions', status_code=201)
    def create_question(body: QuestionInput, request: Request):
        return library(request).create_question(user(request)['_id'], body.model_dump())

    @app.get('/api/questions')
    def questions(request: Request, type: str | None = None, q: str | None = None):
        return library(request).list_questions(user(request)['_id'], type_filter=type, search=q)

    @app.get('/api/questions/shared')
    def shared_questions(request: Request):
        return library(request).shared_with_me(user(request)['_id'])

    @app.get('/api/questions/{question_id}')
    def question_detail(question_id: str, request: Request):
        return library(request).detail(question_id, user(request)['_id'])

    @app.get('/api/questions/{question_id}/versions')
    def question_version_list(question_id: str, request: Request):
        return library(request).detail(question_id, user(request)['_id'])['versions']

    @app.post('/api/questions/{question_id}/versions', status_code=201)
    def question_new_version(question_id: str, body: QuestionInput, request: Request):
        return library(request).new_version(question_id, user(request)['_id'], body.model_dump())

    @app.post('/api/questions/{question_id}/versions/{version}/restore', status_code=201)
    def question_restore(question_id: str, version: int, request: Request):
        return library(request).restore_version(question_id, user(request)['_id'], version)

    @app.post('/api/questions/{question_id}/fork', status_code=201)
    def question_fork(question_id: str, body: QuestionInput, request: Request,
                      version: int | None = None):
        return library(request).fork(question_id, user(request)['_id'], version, body.model_dump())

    @app.patch('/api/questions/{question_id}')
    def question_status(question_id: str, body: QuestionStatusInput, request: Request):
        return library(request).set_status(question_id, user(request)['_id'], body.status)

    @app.post('/api/questions/{question_id}/share-links', status_code=201)
    def question_share_link_create(question_id: str, request: Request):
        return library(request).create_share_link(question_id, user(request)['_id'])

    @app.get('/api/questions/{question_id}/share-links')
    def question_share_link_list(question_id: str, request: Request):
        return library(request).share_links(question_id, user(request)['_id'])

    @app.delete('/api/questions/{question_id}/share-links/{link_id}')
    def question_share_link_revoke(question_id: str, link_id: str, request: Request):
        return library(request).revoke_share_link(question_id, user(request)['_id'], link_id)

    @app.get('/api/share-links/{token}')
    def share_link_preview(token: str, request: Request):
        user(request)
        return library(request).share_link_preview(token)

    @app.post('/api/share-links/{token}/claim', status_code=201)
    def share_link_claim(token: str, request: Request):
        return library(request).claim_share_link(token, user(request)['_id'])

    @app.get('/api/questions/{question_id}/usage')
    def question_usage(question_id: str, request: Request):
        return library(request).usage(question_id, user(request)['_id'])

    @app.get('/api/questions/{question_id}/statistics')
    def question_usage_statistics(question_id: str, request: Request):
        return library(request).cross_survey_statistics(question_id, user(request)['_id'])

    @app.get('/api/questions/{question_id}/shares')
    def question_shares(question_id: str, request: Request):
        return library(request).detail(question_id, user(request)['_id'])['shares']

    @app.post('/api/questions/{question_id}/shares', status_code=201)
    def question_share(question_id: str, body: ShareInput, request: Request):
        return library(request).share(question_id, user(request)['_id'], body.username)

    @app.delete('/api/questions/{question_id}/shares/{grantee_id}')
    def question_unshare(question_id: str, grantee_id: str, request: Request):
        return library(request).unshare(question_id, user(request)['_id'], grantee_id)

    # ------------------------------------------------------------------ question banks
    @app.post('/api/banks', status_code=201)
    def create_bank(body: BankInput, request: Request):
        return library(request).create_bank(user(request)['_id'], body.model_dump())

    @app.get('/api/banks')
    def banks(request: Request):
        return library(request).list_banks(user(request)['_id'])

    @app.get('/api/banks/{bank_id}')
    def bank_detail(bank_id: str, request: Request):
        return library(request).bank_detail(bank_id, user(request)['_id'])

    @app.patch('/api/banks/{bank_id}')
    def bank_update(bank_id: str, body: BankPatch, request: Request):
        return library(request).update_bank(bank_id, user(request)['_id'], body.model_dump(exclude_none=True))

    @app.post('/api/banks/{bank_id}/items', status_code=201)
    def bank_add_item(bank_id: str, body: BankItemInput, request: Request):
        return library(request).add_bank_item(bank_id, user(request)['_id'], body.question_id, body.version)

    @app.patch('/api/banks/{bank_id}/items/{question_id}')
    def bank_update_item(bank_id: str, question_id: str, request: Request,
                         body: BankVersionInput | None = None):
        version = body.version if body else None
        return library(request).update_bank_item(bank_id, user(request)['_id'], question_id, version)

    @app.delete('/api/banks/{bank_id}/items/{question_id}')
    def bank_remove_item(bank_id: str, question_id: str, request: Request):
        return library(request).remove_bank_item(bank_id, user(request)['_id'], question_id)

    # ------------------------------------------------------------------ survey integration
    @app.post('/api/surveys/{survey_id}/questions/import', status_code=201)
    def import_question(survey_id: str, body: ImportQuestionInput, request: Request):
        return library(request).import_into_survey(survey_id, user(request)['_id'],
                                                   body.question_id, body.version, body.bank_id)

    @app.post('/api/surveys/{survey_id}/questions/{question_id}/revision')
    def revise_question(survey_id: str, question_id: str, body: RevisionInput, request: Request):
        return library(request).revise_in_survey(survey_id, user(request)['_id'], question_id,
                                                 body.mode, body.question.model_dump())

    return app


app = create_app()
