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
from .models import Credentials, DeadlineInput, DraftInput, Metadata, PublishInput
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
        app.state.service = SurveyService(db, client, settings)
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

    @app.get('/', include_in_schema=False)
    @app.get('/survey/{code}', include_in_schema=False)
    def page():
        return FileResponse(ROOT / 'templates/index.html')

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

    return app


app = create_app()
