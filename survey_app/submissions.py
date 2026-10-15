"""MongoDB transaction gate, idempotent receipts and complete response storage."""
from hashlib import sha256
import json
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .errors import DomainError
from .questions import ensure_document_size, evaluate_path


def receipt(document, replayed):
    return {'id': document['_id'], 'submitted_at': document['submitted_at'].isoformat(),
            'replayed': replayed}


def _replay(document, payload_hash):
    if document['payload_hash'] != payload_hash:
        raise DomainError(409, 'idempotency', '同一请求编号对应的回答已改变，请勿复用编号')
    return receipt(document, True)


def submit(service, code, user_id, version_number, request_id, answers):
    survey = service.by_code(code)
    if survey['published_version'] is None:
        raise DomainError(409, 'not_published', '问卷尚未发布')
    if version_number != survey['published_version']:
        raise DomainError(409, 'version', '问卷版本不匹配，请重新打开链接')
    version = service.version(survey)
    evaluated = evaluate_path(version['questions'], version['rules'], answers)
    normalized = {key: value for key, value in evaluated['answers'].items() if value is not None}
    ensure_document_size({'answers': normalized})
    # Canonical option order, mathematical integers and omitted optional empties
    # make semantically identical retries stable.
    canonical = json.dumps({'version': version_number, 'answers': normalized},
                           sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    payload_hash = sha256(canonical.encode('utf-8')).hexdigest()
    key = {'survey_id': survey['_id'], 'respondent_id': user_id, 'request_id': request_id}
    response_id = str(uuid4())
    response = {'_id': response_id, **key, 'version': version_number, 'payload_hash': payload_hash,
                'answers': normalized, 'path': evaluated['path'], 'single_submission': not survey['allow_repeat'],
                'anonymous': survey['allow_anonymous'], 'schema_version': 1}
    ensure_document_size(response)

    def operation(session):
        previous = service.db.responses.find_one(key, session=session)
        if previous is not None:
            return _replay(previous, payload_hash)
        # A real write serializes this transaction with close/deadline writes.
        # Both the predicate and stored acceptance timestamp use this command's $$NOW.
        accepted = service.db.surveys.find_one_and_update(
            {'_id': survey['_id'], 'status': 'published', 'published_version': version_number,
             '$expr': {'$or': [{'$eq': ['$closes_at', None]}, {'$gt': ['$closes_at', '$$NOW']}] }},
            [{'$set': {'gate_seq': {'$add': ['$gate_seq', 1]}, 'last_accepted_at': '$$NOW'}}],
            return_document=ReturnDocument.AFTER, session=session)
        if accepted is None:
            raise DomainError(410, 'closed', '问卷已关闭或超过截止时间，未保存本次回答')
        document = {**response, 'submitted_at': accepted['last_accepted_at']}
        ensure_document_size(document)
        service.db.responses.insert_one(document, session=session)
        return receipt(document, False)

    try:
        return service.transaction(operation)
    except DuplicateKeyError:
        # A concurrent winner has committed before its unique-key conflict is seen.
        # Never infer a replay solely from a duplicate-account conflict.
        previous = service.db.responses.find_one(key)
        if previous is not None:
            return _replay(previous, payload_hash)
        raise DomainError(409, 'already_submitted', '本问卷每个账号只能成功提交一次') from None
