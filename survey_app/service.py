"""Survey lifecycle and ownership. Submission is added after S4 acceptance."""
from copy import deepcopy
import secrets
from uuid import uuid4

from pymongo import ReadPreference, ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from .errors import DomainError
from .questions import check_definition, ensure_document_size
from .security import hash_password, now_utc, public_user, verify_password


class SurveyService:
    def __init__(self, db, client, settings):
        self.db, self.client, self.settings = db, client, settings

    def transaction(self, callback):
        with self.client.start_session() as session:
            return session.with_transaction(callback, read_concern=ReadConcern('snapshot'),
                                            write_concern=WriteConcern('majority'), read_preference=ReadPreference.PRIMARY)

    def register(self, username, password):
        if not username.strip() or any(ord(c) < 32 for c in username):
            raise DomainError(422, 'validation', '用户名不能包含控制字符')
        doc = {'_id': str(uuid4()), 'username': username, 'username_key': username.casefold(),
               'password_hash': hash_password(password), 'created_at': now_utc(), 'schema_version': 1}
        try:
            self.db.users.insert_one(doc)
        except DuplicateKeyError:
            raise DomainError(409, 'username_exists', '用户名已存在') from None
        return public_user(doc)

    def login(self, username, password):
        user = self.db.users.find_one({'username_key': username.casefold()})
        if user is None or not verify_password(password, user['password_hash']):
            raise DomainError(401, 'authentication', '用户名或密码错误')
        return user

    def owned(self, survey_id, user_id, session=None):
        doc = self.db.surveys.find_one({'_id': survey_id, 'owner_id': user_id}, session=session)
        if doc is None:
            raise DomainError(404, 'not_found', '问卷不存在或无权访问')
        return doc

    def version(self, survey, session=None):
        doc = self.db.survey_versions.find_one({'survey_id': survey['_id'], 'version': survey['published_version']}, session=session)
        if doc is None:
            raise DomainError(409, 'version', '问卷发布版本不可用')
        return doc

    def survey_payload(self, doc):
        content = doc.get('draft') if doc['status'] == 'draft' else self.version(doc)
        return {'id': doc['_id'], 'title': doc['title'], 'description': doc['description'],
                'allow_anonymous': doc['allow_anonymous'], 'allow_repeat': doc['allow_repeat'],
                'closes_at': doc['closes_at'].isoformat() if doc['closes_at'] else None,
                'status': doc['status'], 'revision': doc['revision'], 'version': doc['published_version'],
                'share_code': doc['share_code'], 'share_url': f"/survey/{doc['share_code']}",
                'questions': deepcopy(content['questions']), 'rules': deepcopy(content['rules']),
                'created_at': doc['created_at'].isoformat(), 'updated_at': doc['updated_at'].isoformat()}

    def create_survey(self, user_id, metadata):
        now = now_utc()
        doc = {'_id': str(uuid4()), 'owner_id': user_id, 'share_code': secrets.token_urlsafe(12),
               **metadata, 'status': 'draft', 'published_version': None, 'revision': 0, 'gate_seq': 0,
               'created_at': now, 'updated_at': now, 'draft': {'questions': [], 'rules': []}, 'schema_version': 1}
        ensure_document_size(doc)
        self.db.surveys.insert_one(doc)
        return self.survey_payload(doc)

    def list_surveys(self, user_id):
        return [self.survey_payload(doc) for doc in self.db.surveys.find({'owner_id': user_id}).sort('created_at', -1)]

    def update_survey(self, survey_id, user_id, data):
        doc = self.owned(survey_id, user_id)
        if doc['status'] != 'draft':
            raise DomainError(409, 'immutable', '发布后不能修改题目或填写策略')
        revision = data.pop('revision')
        questions, rules = check_definition(data.pop('questions'), data.pop('rules'))
        fields = {**data, 'draft': {'questions': questions, 'rules': rules}, 'updated_at': now_utc()}
        ensure_document_size({**doc, **fields})
        updated = self.db.surveys.find_one_and_update({'_id': survey_id, 'owner_id': user_id, 'status': 'draft', 'revision': revision},
            {'$set': fields, '$inc': {'revision': 1}}, return_document=ReturnDocument.AFTER)
        if updated is None:
            raise DomainError(409, 'revision', '问卷已被修改，请重新读取后保存')
        return self.survey_payload(updated)

    def publish(self, survey_id, user_id, revision):
        def operation(session):
            doc = self.owned(survey_id, user_id, session)
            if doc['status'] != 'draft' or doc['revision'] != revision:
                raise DomainError(409, 'revision', '问卷状态或版本已改变，请重新读取')
            questions, rules = check_definition(doc['draft']['questions'], doc['draft']['rules'], for_publish=True)
            snapshot = {'_id': str(uuid4()), 'survey_id': survey_id, 'version': 1,
                        'questions': questions, 'rules': rules, 'created_at': now_utc(), 'schema_version': 1}
            ensure_document_size(snapshot)
            result = self.db.surveys.update_one({'_id': survey_id, 'owner_id': user_id, 'status': 'draft', 'revision': revision},
                {'$set': {'status': 'published', 'published_version': 1, 'updated_at': now_utc()},
                 '$unset': {'draft': ''}, '$inc': {'revision': 1}}, session=session)
            if result.modified_count != 1:
                raise DomainError(409, 'revision', '发布时问卷已改变，请重试')
            self.db.survey_versions.insert_one(snapshot, session=session)
        self.transaction(operation)
        return self.survey_payload(self.owned(survey_id, user_id))

    def set_deadline(self, survey_id, user_id, closes_at):
        self.owned(survey_id, user_id)
        doc = self.db.surveys.find_one_and_update({'_id': survey_id, 'owner_id': user_id},
            {'$set': {'closes_at': closes_at, 'updated_at': now_utc()}, '$inc': {'revision': 1}}, return_document=ReturnDocument.AFTER)
        return self.survey_payload(doc)

    def close(self, survey_id, user_id):
        doc = self.owned(survey_id, user_id)
        if doc['status'] == 'closed':
            return self.survey_payload(doc)
        if doc['status'] != 'published':
            raise DomainError(409, 'state', '只有已发布问卷可以关闭')
        closed = self.db.surveys.find_one_and_update({'_id': survey_id, 'owner_id': user_id, 'status': 'published'},
            {'$set': {'status': 'closed', 'updated_at': now_utc()}, '$inc': {'revision': 1}}, return_document=ReturnDocument.AFTER)
        return self.survey_payload(closed or self.owned(survey_id, user_id))

    def by_code(self, code):
        doc = self.db.surveys.find_one({'share_code': code})
        if doc is None:
            raise DomainError(404, 'not_found', '问卷链接不存在')
        return doc

    def available(self, code):
        docs = list(self.db.surveys.aggregate([{'$match': {'share_code': code}}, {'$addFields': {'server_now': '$$NOW'}}]))
        if not docs:
            raise DomainError(404, 'not_found', '问卷链接不存在')
        doc = docs[0]
        if doc['status'] == 'draft':
            raise DomainError(409, 'not_published', '问卷尚未发布')
        if doc['status'] != 'published' or (doc['closes_at'] is not None and doc['closes_at'] <= doc['server_now']):
            raise DomainError(410, 'closed', '问卷已关闭或超过截止时间')
        return doc

    def fill_view(self, code):
        doc = self.available(code)
        version = self.version(doc)
        return {'title': doc['title'], 'description': doc['description'], 'version': version['version'],
                'allow_anonymous': doc['allow_anonymous'], 'allow_repeat': doc['allow_repeat'],
                'closes_at': doc['closes_at'].isoformat() if doc['closes_at'] else None,
                'questions': deepcopy(version['questions']), 'rules': deepcopy(version['rules'])}

    def next_question(self, code, version_number, answers):
        from .questions import evaluate_path
        doc = self.available(code)
        if version_number != doc['published_version']:
            raise DomainError(409, 'version', '问卷版本不匹配，请重新打开链接')
        version = self.version(doc)
        return evaluate_path(version['questions'], version['rules'], answers, partial=True)
