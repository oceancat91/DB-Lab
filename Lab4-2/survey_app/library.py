"""Stored questions: entities, immutable versions, sharing, banks, usage and cross-survey stats.

Design notes (see docs/DATABASE.md):
* A question *entity* carries identity and ownership; its content lives in immutable version
  documents, so a survey that referenced v1 keeps v1 after v2 appears.
* Surrendering a question to a survey copies the version content into the survey draft and
  records ``question_version``; publishing freezes that copy in ``survey_versions``.
* Usage is derived from the two existing arrays (``surveys.draft.questions`` and
  ``survey_versions.questions``) via multikey indexes, so no second copy of the link has to be
  kept in sync.
"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from uuid import uuid4

from pymongo import ReadPreference, ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from .errors import DomainError
from .questions import check_definition, ensure_document_size
from .security import now_utc

CONTENT_FIELDS = ("type", "title", "required", "options", "validation")
MODES = {"draft_only", "new_version", "fork"}


def _content(payload: dict, question_id: str) -> dict:
    """Validate one question definition by reusing the survey definition checker."""
    candidate = {key: payload[key] for key in CONTENT_FIELDS if key in payload}
    candidate["id"] = question_id
    normalized, _ = check_definition([candidate], [])
    return normalized[0]


def _content_of(question: dict) -> dict:
    return {key: deepcopy(question[key]) for key in CONTENT_FIELDS if key in question}


class LibraryService:
    def __init__(self, db, client, settings, surveys=None):
        self.db, self.client, self.settings = db, client, settings
        self.surveys = surveys

    # ---------------------------------------------------------------- helpers
    def transaction(self, callback):
        with self.client.start_session() as session:
            return session.with_transaction(
                callback, read_concern=ReadConcern("snapshot"),
                write_concern=WriteConcern("majority"), read_preference=ReadPreference.PRIMARY)

    def _question(self, question_id: str) -> dict:
        doc = self.db.questions.find_one({"_id": question_id})
        if doc is None:
            raise DomainError(404, "not_found", "题目不存在")
        return doc

    def _accessible(self, question_id: str, user_id: str, *, owner_only: bool = False) -> dict:
        doc = self._question(question_id)
        if doc["owner_id"] == user_id:
            return doc
        if owner_only:
            raise DomainError(404, "not_found", "题目不存在或无权操作")
        if self.db.question_shares.find_one({"question_id": question_id, "grantee_id": user_id}):
            return doc
        raise DomainError(404, "not_found", "题目不存在或无权访问")

    def _version(self, question_id: str, version: int) -> dict:
        doc = self.db.question_versions.find_one({"question_id": question_id, "version": version})
        if doc is None:
            raise DomainError(404, "not_found", f"题目版本 v{version} 不存在")
        return doc

    def _version_payload(self, doc: dict) -> dict:
        return {
            "question_id": doc["question_id"], "version": doc["version"], "type": doc["type"],
            "title": doc["title"], "required": doc["required"], "options": deepcopy(doc["options"]),
            "validation": deepcopy(doc["validation"]), "note": doc.get("note", ""),
            "derived_from": deepcopy(doc.get("derived_from")), "supersedes": doc.get("supersedes"),
            "restored_from": doc.get("restored_from"), "created_at": doc["created_at"].isoformat(),
        }

    def canonical(self, version_doc: dict) -> dict:
        """Survey-shaped question object for one stored version."""
        question = {key: deepcopy(version_doc[key]) for key in CONTENT_FIELDS if key in version_doc}
        question["id"] = version_doc["question_id"]
        question["question_version"] = version_doc["version"]
        normalized, _ = check_definition([question], [])
        return normalized[0]

    def normalize_question_refs(self, user_id: str, questions: list) -> list:
        """Keep ``question_version`` only when it matches a version the user may reference.

        A client could otherwise claim version 7 while submitting different content; the marker
        is dropped instead of trusting it, which turns the question into a survey-local edit.
        """
        candidates = [question for question in questions
                      if isinstance(question, dict) and question.get("question_version")]
        if not candidates:
            return questions
        identifiers = sorted({question["id"] for question in candidates if isinstance(question.get("id"), str)})
        accessible = {doc["_id"] for doc in self.db.questions.find({"_id": {"$in": identifiers}})
                      if doc["owner_id"] == user_id
                      or self.db.question_shares.find_one({"question_id": doc["_id"], "grantee_id": user_id})}
        stored = {(doc["question_id"], doc["version"]): doc
                  for doc in self.db.question_versions.find({"question_id": {"$in": identifiers}})}
        for question in questions:
            version = question.get("question_version")
            if not version:
                continue
            doc = stored.get((question.get("id"), version))
            if doc is None or question.get("id") not in accessible:
                question.pop("question_version", None)
                continue
            if any(deepcopy(question.get(field)) != deepcopy(doc[field]) for field in CONTENT_FIELDS):
                question.pop("question_version", None)
        return questions

    def _entity_payload(self, doc: dict, *, viewer_id: str | None = None) -> dict:
        owned = viewer_id is not None and doc["owner_id"] == viewer_id
        return {
            "id": doc["_id"], "owner_id": doc["owner_id"], "type": doc["type"], "title": doc["title"],
            "current_version": doc["current_version"], "status": doc["status"], "origin": doc["origin"],
            "created_at": doc["created_at"].isoformat(), "updated_at": doc["updated_at"].isoformat(),
            "owned": owned,
            "shared_with_me": bool(viewer_id) and not owned,
            "share_count": self.db.question_shares.count_documents({"question_id": doc["_id"]}),
            "bank_count": self.db.question_bank_items.count_documents({"question_id": doc["_id"]}),
        }

    def _insert_version(self, question_id: str, content: dict, version: int, *, user_id: str,
                        note: str, derived_from: dict | None, supersedes: int | None,
                        restored_from: int | None, session=None) -> dict:
        doc = {
            "_id": str(uuid4()), "question_id": question_id, "version": version,
            "type": content["type"], "title": content["title"], "required": content["required"],
            "options": deepcopy(content["options"]), "validation": deepcopy(content["validation"]),
            "derived_from": derived_from, "supersedes": supersedes, "restored_from": restored_from,
            "note": note, "created_by": user_id, "created_at": now_utc(), "schema_version": 1,
        }
        ensure_document_size(doc)
        self.db.question_versions.insert_one(doc, session=session)
        return doc

    # ---------------------------------------------------------------- questions
    def create_question(self, user_id: str, payload: dict, *, origin: str = "created",
                        derived_from: dict | None = None, question_id: str | None = None) -> dict:
        identifier = question_id or str(uuid4())
        content = _content(payload, identifier)
        now = now_utc()
        entity = {
            "_id": identifier, "owner_id": user_id, "type": content["type"], "title": content["title"],
            "current_version": 1, "status": "active", "origin": origin,
            "created_at": now, "updated_at": now, "schema_version": 1,
        }
        ensure_document_size(entity)

        def operation(session):
            self.db.questions.insert_one(entity, session=session)
            self._insert_version(identifier, content, 1, user_id=user_id,
                                 note=payload.get("note", ""), derived_from=derived_from,
                                 supersedes=None, restored_from=None, session=session)

        try:
            self.transaction(operation)
        except DuplicateKeyError:
            raise DomainError(409, "exists", "题目已存在") from None
        return self.detail(identifier, user_id)

    def list_questions(self, user_id: str, *, type_filter: str | None = None,
                       search: str | None = None) -> list[dict]:
        query: dict = {"owner_id": user_id, "status": "active"}
        if type_filter:
            query["type"] = type_filter
        if search:
            query["title"] = {"$regex": re.escape(search), "$options": "i"}
        docs = self.db.questions.find(query).sort("updated_at", -1).limit(200)
        return [self._entity_payload(doc, viewer_id=user_id) for doc in docs]

    def shared_with_me(self, user_id: str) -> list[dict]:
        shares = self.db.question_shares.find({"grantee_id": user_id}).sort("created_at", -1).limit(200)
        rows = []
        for share in shares:
            doc = self.db.questions.find_one({"_id": share["question_id"]})
            if doc is None:
                continue
            owner = self.db.users.find_one({"_id": doc["owner_id"]}, {"username": 1})
            row = self._entity_payload(doc, viewer_id=user_id)
            row["owner_name"] = owner["username"] if owner else ""
            rows.append(row)
        return rows

    def detail(self, question_id: str, user_id: str) -> dict:
        doc = self._accessible(question_id, user_id)
        current = self._version(question_id, doc["current_version"])
        payload = self._entity_payload(doc, viewer_id=user_id)
        payload["current"] = self._version_payload(current)
        payload["versions"] = [
            {"version": version["version"], "note": version.get("note", ""),
             "created_at": version["created_at"].isoformat(),
             "derived_from": deepcopy(version.get("derived_from")),
             "restored_from": version.get("restored_from"), "supersedes": version.get("supersedes")}
            for version in self.db.question_versions.find({"question_id": question_id}).sort("version", 1)
        ]
        payload["banks"] = [
            {"id": item["bank_id"], "version": item["question_version"]}
            for item in self.db.question_bank_items.find({"question_id": question_id})
        ]
        payload["shares"] = [
            {"user_id": share["grantee_id"], "username": (self.db.users.find_one(
                {"_id": share["grantee_id"]}, {"username": 1}) or {}).get("username", "")}
            for share in self.db.question_shares.find({"question_id": question_id})
        ] if doc["owner_id"] == user_id else []
        return payload

    def new_version(self, question_id: str, user_id: str, payload: dict) -> dict:
        doc = self._accessible(question_id, user_id, owner_only=True)
        content = _content(payload, question_id)
        current = doc["current_version"]
        next_version = current + 1

        def operation(session):
            self._insert_version(question_id, content, next_version, user_id=user_id,
                                 note=payload.get("note", ""),
                                 derived_from={"question_id": question_id, "version": current},
                                 supersedes=current, restored_from=None, session=session)
            self.db.questions.update_one(
                {"_id": question_id, "current_version": current},
                {"$set": {"current_version": next_version, "title": content["title"],
                          "type": content["type"], "updated_at": now_utc()}},
                session=session)

        try:
            self.transaction(operation)
        except DuplicateKeyError:
            raise DomainError(409, "revision", "题目已被他人修改，请刷新后重试") from None
        return self.detail(question_id, user_id)

    def restore_version(self, question_id: str, user_id: str, source_version: int) -> dict:
        doc = self._accessible(question_id, user_id, owner_only=True)
        source = self._version(question_id, source_version)
        content = _content(_content_of(source), question_id)
        current = doc["current_version"]
        next_version = current + 1

        def operation(session):
            self._insert_version(question_id, content, next_version, user_id=user_id,
                                 note=f"恢复自 v{source_version}",
                                 derived_from={"question_id": question_id, "version": source_version},
                                 supersedes=current, restored_from=source_version, session=session)
            self.db.questions.update_one(
                {"_id": question_id, "current_version": current},
                {"$set": {"current_version": next_version, "title": content["title"],
                          "type": content["type"], "updated_at": now_utc()}},
                session=session)

        self.transaction(operation)
        return self.detail(question_id, user_id)

    def fork(self, question_id: str, user_id: str, source_version: int | None, payload: dict) -> dict:
        source = self._accessible(question_id, user_id)
        version = source_version or source["current_version"]
        self._version(question_id, version)
        return self.create_question(user_id, payload, origin="forked",
                                    derived_from={"question_id": question_id, "version": version})

    # ---------------------------------------------------------------- sharing
    def share(self, question_id: str, user_id: str, username: str) -> dict:
        self._accessible(question_id, user_id, owner_only=True)
        grantee = self.db.users.find_one({"username_key": username.casefold()})
        if grantee is None:
            raise DomainError(404, "not_found", "要共享的用户不存在")
        if grantee["_id"] == user_id:
            raise DomainError(422, "validation", "不能共享给自己")
        try:
            self.db.question_shares.insert_one({
                "_id": str(uuid4()), "question_id": question_id, "owner_id": user_id,
                "grantee_id": grantee["_id"], "created_at": now_utc(), "schema_version": 1})
        except DuplicateKeyError:
            raise DomainError(409, "exists", "已共享给该用户") from None
        return self.detail(question_id, user_id)

    def unshare(self, question_id: str, user_id: str, grantee_id: str) -> dict:
        self._accessible(question_id, user_id, owner_only=True)
        result = self.db.question_shares.delete_one({"question_id": question_id, "grantee_id": grantee_id})
        if result.deleted_count == 0:
            raise DomainError(404, "not_found", "该用户未被共享此题")
        return self.detail(question_id, user_id)

    # ---------------------------------------------------------------- banks
    def create_bank(self, user_id: str, payload: dict) -> dict:
        now = now_utc()
        doc = {"_id": str(uuid4()), "owner_id": user_id, "name": payload["name"].strip(),
               "description": payload.get("description", ""), "created_at": now, "updated_at": now,
               "schema_version": 1}
        try:
            self.db.question_banks.insert_one(doc)
        except DuplicateKeyError:
            raise DomainError(409, "exists", "同名题库已存在") from None
        return self.bank_detail(doc["_id"], user_id)

    def _bank(self, bank_id: str, user_id: str) -> dict:
        doc = self.db.question_banks.find_one({"_id": bank_id, "owner_id": user_id})
        if doc is None:
            raise DomainError(404, "not_found", "题库不存在或无权访问")
        return doc

    def list_banks(self, user_id: str) -> list[dict]:
        rows = []
        for doc in self.db.question_banks.find({"owner_id": user_id}).sort("created_at", 1):
            rows.append({"id": doc["_id"], "name": doc["name"], "description": doc["description"],
                         "items": self.db.question_bank_items.count_documents({"bank_id": doc["_id"]}),
                         "updated_at": doc["updated_at"].isoformat()})
        return rows

    def bank_detail(self, bank_id: str, user_id: str) -> dict:
        bank = self._bank(bank_id, user_id)
        items = []
        for item in self.db.question_bank_items.find({"bank_id": bank_id}).sort("added_at", 1):
            entity = self.db.questions.find_one({"_id": item["question_id"]})
            if entity is None:
                continue
            version = self.db.question_versions.find_one(
                {"question_id": item["question_id"], "version": item["question_version"]})
            items.append({
                "question_id": item["question_id"], "question_version": item["question_version"],
                "title": entity["title"], "type": entity["type"],
                "current_version": entity["current_version"],
                "outdated": item["question_version"] != entity["current_version"],
                "preview": (version or {}).get("title", ""),
            })
        return {"id": bank["_id"], "name": bank["name"], "description": bank["description"],
                "items": items, "created_at": bank["created_at"].isoformat()}

    def update_bank(self, bank_id: str, user_id: str, payload: dict) -> dict:
        self._bank(bank_id, user_id)
        fields = {}
        if "name" in payload:
            fields["name"] = payload["name"].strip()
        if "description" in payload:
            fields["description"] = payload["description"]
        if fields:
            fields["updated_at"] = now_utc()
            try:
                self.db.question_banks.update_one({"_id": bank_id, "owner_id": user_id}, {"$set": fields})
            except DuplicateKeyError:
                raise DomainError(409, "exists", "同名题库已存在") from None
        return self.bank_detail(bank_id, user_id)

    def add_bank_item(self, bank_id: str, user_id: str, question_id: str,
                      version: int | None = None) -> dict:
        self._bank(bank_id, user_id)
        entity = self._accessible(question_id, user_id)
        pinned = version or entity["current_version"]
        self._version(question_id, pinned)
        try:
            self.db.question_bank_items.insert_one({
                "_id": str(uuid4()), "bank_id": bank_id, "question_id": question_id,
                "question_version": pinned, "added_by": user_id, "added_at": now_utc(),
                "schema_version": 1})
        except DuplicateKeyError:
            raise DomainError(409, "exists", "该题已在题库中") from None
        return self.bank_detail(bank_id, user_id)

    def update_bank_item(self, bank_id: str, user_id: str, question_id: str,
                         version: int | None = None) -> dict:
        self._bank(bank_id, user_id)
        entity = self._accessible(question_id, user_id)
        pinned = version or entity["current_version"]
        self._version(question_id, pinned)
        result = self.db.question_bank_items.update_one(
            {"bank_id": bank_id, "question_id": question_id},
            {"$set": {"question_version": pinned, "added_at": now_utc()}})
        if result.matched_count == 0:
            raise DomainError(404, "not_found", "该题不在题库中")
        return self.bank_detail(bank_id, user_id)

    def remove_bank_item(self, bank_id: str, user_id: str, question_id: str) -> dict:
        self._bank(bank_id, user_id)
        result = self.db.question_bank_items.delete_one({"bank_id": bank_id, "question_id": question_id})
        if result.deleted_count == 0:
            raise DomainError(404, "not_found", "该题不在题库中")
        return self.bank_detail(bank_id, user_id)

    # ---------------------------------------------------------------- usage
    def usage(self, question_id: str, user_id: str) -> dict:
        entity = self._accessible(question_id, user_id)
        rows: list[dict] = []
        for doc in self.db.surveys.find({"draft.questions.id": question_id},
                                        {"title": 1, "owner_id": 1, "status": 1, "draft.questions": 1}):
            used = [q for q in doc.get("draft", {}).get("questions", []) if q.get("id") == question_id]
            rows.append({"survey_id": doc["_id"], "title": doc["title"], "status": doc["status"],
                         "version": None, "question_version": (used[0].get("question_version")
                                                               if used else None),
                         "owner_is_self": doc["owner_id"] == user_id,
                         "editable": True})
        versions = list(self.db.survey_versions.find({"questions.id": question_id},
                                                     {"survey_id": 1, "version": 1, "questions": 1}))
        survey_ids = [item["survey_id"] for item in versions]
        surveys = {doc["_id"]: doc for doc in self.db.surveys.find({"_id": {"$in": survey_ids}},
                                                                {"title": 1, "owner_id": 1, "status": 1})}
        for item in versions:
            survey = surveys.get(item["survey_id"])
            if survey is None:
                continue
            used = [q for q in item["questions"] if q.get("id") == question_id]
            rows.append({"survey_id": item["survey_id"], "title": survey["title"],
                         "status": "published", "version": item["version"],
                         "question_version": (used[0].get("question_version") if used else None),
                         "owner_is_self": survey["owner_id"] == user_id, "editable": False})
        return {"question_id": entity["_id"], "title": entity["title"], "current_version":
                entity["current_version"], "usages": rows, "usage_count": len(rows)}

    # ---------------------------------------------------------------- statistics
    def cross_survey_statistics(self, question_id: str, user_id: str) -> dict:
        entity = self._accessible(question_id, user_id)
        is_owner = entity["owner_id"] == user_id
        versions = list(self.db.survey_versions.find({"questions.id": question_id},
                                                     {"survey_id": 1, "version": 1, "questions": 1}))
        surveys = {doc["_id"]: doc for doc in self.db.surveys.find(
            {"_id": {"$in": [item["survey_id"] for item in versions]}},
            {"title": 1, "owner_id": 1})}
        buckets: dict = {}
        per_version: dict = {}
        per_survey: list[dict] = []
        for item in versions:
            survey = surveys.get(item["survey_id"])
            if survey is None:
                continue
            if not is_owner and survey["owner_id"] != user_id:
                continue  # a grantee only aggregates over their own surveys
            definition = next((q for q in item["questions"] if q.get("id") == question_id), None)
            if definition is None:
                continue
            question_version = definition.get("question_version")
            responses = self.db.responses.find(
                {"survey_id": item["survey_id"], "version": item["version"]},
                {"answers": 1, "respondent_id": 1})
            answered_here = 0
            for response in responses:
                value = (response.get("answers") or {}).get(question_id)
                if value is None:
                    continue
                answered_here += 1
                _accumulate(buckets, definition, value)
                _accumulate(per_version.setdefault(question_version, {}), definition, value)
            per_survey.append({
                "survey_id": item["survey_id"], "title": survey["title"],
                "owner_is_self": survey["owner_id"] == user_id,
                "survey_version": item["version"], "question_version": question_version,
                "answered": answered_here,
            })
        return {
            "question_id": entity["_id"], "title": entity["title"],
            "current_version": entity["current_version"],
            "scope": "all surveys" if is_owner else "own surveys only",
            "total_answered": sum(row["answered"] for row in per_survey),
            "survey_count": len(per_survey),
            "aggregate": _summary(buckets),
            "by_question_version": {str(version): _summary(bucket)
                                    for version, bucket in sorted(per_version.items())},
            "surveys": sorted(per_survey, key=lambda row: (-row["answered"], row["title"])),
        }

    # ---------------------------------------------------------------- survey integration
    def import_into_survey(self, survey_id: str, user_id: str, question_id: str,
                           version: int | None = None) -> dict:
        self._require_surveys()
        survey = self.surveys.owned(survey_id, user_id)
        if survey["status"] != "draft":
            raise DomainError(409, "immutable", "发布后不能修改题目")
        entity = self._accessible(question_id, user_id)
        pinned = version or entity["current_version"]
        version_doc = self._version(question_id, pinned)
        draft = deepcopy(survey["draft"])
        if any(question.get("id") == question_id for question in draft["questions"]):
            raise DomainError(409, "exists", "该题已在问卷中")
        if len(draft["questions"]) >= 100:
            raise DomainError(422, "validation", "每份问卷最多包含 100 道题目")
        draft["questions"].append(self.canonical(version_doc))
        return self._save_draft(survey, user_id, draft)

    def revise_in_survey(self, survey_id: str, user_id: str, question_id: str,
                         mode: str, payload: dict) -> dict:
        self._require_surveys()
        if mode not in MODES:
            raise DomainError(422, "validation", "修改方式必须是 draft_only、new_version 或 fork")
        survey = self.surveys.owned(survey_id, user_id)
        if survey["status"] != "draft":
            raise DomainError(409, "immutable", "发布后不能修改题目")
        draft = deepcopy(survey["draft"])
        index = next((position for position, question in enumerate(draft["questions"])
                      if question.get("id") == question_id), None)
        if index is None:
            raise DomainError(404, "not_found", "问卷中没有这道题")
        current = draft["questions"][index]
        new_id = question_id
        try:
            entity = self._accessible(question_id, user_id)
        except DomainError:
            entity = None
        if mode == "draft_only":
            edited = _content(payload, question_id)
            draft["questions"][index] = edited
        elif mode == "new_version":
            if entity is None:
                raise DomainError(409, "not_stored", "该题不是题库题目，请改用 draft_only 或 fork")
            if entity["owner_id"] != user_id:
                raise DomainError(403, "forbidden", "只有题目所有者可以创建新版本；他人题目请用 fork")
            detail = self.new_version(question_id, user_id, payload)
            version = detail["current_version"]
            draft["questions"][index] = self.canonical(self._version(question_id, version))
        else:  # fork
            if entity is None:
                raise DomainError(409, "not_stored", "该题不是题库题目，请改用 draft_only")
            detail = self.fork(question_id, user_id, current.get("question_version"), payload)
            new_id = detail["id"]
            draft["questions"][index] = self.canonical(self._version(new_id, 1))
            for rule in draft.get("rules", []):
                for key in ("source", "target"):
                    if rule.get(key) == question_id:
                        rule[key] = new_id
        return self._save_draft(survey, user_id, draft)

    def sync_draft_versions(self, survey: dict, user_id: str, draft: dict) -> dict:
        """Compatibility wrapper kept for callers that pass a whole draft."""
        draft["questions"] = self.normalize_question_refs(user_id, draft.get("questions", []))
        return draft

    def _require_surveys(self) -> None:
        if self.surveys is None:
            raise RuntimeError("LibraryService requires the survey service for draft integration")

    def _save_draft(self, survey: dict, user_id: str, draft: dict) -> dict:
        questions, rules = check_definition(draft.get("questions", []), draft.get("rules", []))
        draft = {"questions": questions, "rules": rules}
        fields = {"draft": draft}
        if self.surveys is not None:
            fields["updated_at"] = now_utc()
        updated = self.db.surveys.find_one_and_update(
            {"_id": survey["_id"], "owner_id": user_id, "status": "draft",
             "revision": survey["revision"]},
            {"$set": fields, "$inc": {"revision": 1}}, return_document=ReturnDocument.AFTER)
        if updated is None:
            raise DomainError(409, "revision", "问卷已被修改，请重新读取后保存")
        return self.surveys.survey_payload(updated)


def _escape(text: str) -> str:
    return re.escape(text)


def _accumulate(buckets: dict, definition: dict, value) -> None:
    question_type = definition["type"]
    bucket = buckets.setdefault(question_type, {"count": 0, "options": {}, "labels": {},
                                                "values": [], "numbers": []})
    bucket["count"] += 1
    if question_type == "single":
        bucket["options"][value] = bucket["options"].get(value, 0) + 1
    elif question_type == "multi":
        for option in value:
            bucket["options"][option] = bucket["options"].get(option, 0) + 1
    elif question_type == "number":
        bucket["numbers"].append(float(value))
    else:
        if len(bucket["values"]) < 200:
            bucket["values"].append(value)
    for option in definition.get("options", []):
        bucket["labels"][option["id"]] = option["label"]


def _summary(buckets: dict) -> dict:
    summary: dict = {"answered": sum(bucket["count"] for bucket in buckets.values()), "by_type": {}}
    for question_type, bucket in buckets.items():
        entry = {"answered": bucket["count"]}
        if question_type in {"single", "multi"}:
            entry["options"] = [{"id": option, "label": bucket["labels"].get(option, option),
                                 "count": count}
                                for option, count in sorted(bucket["options"].items(),
                                                            key=lambda item: (-item[1], item[0]))]
        elif question_type == "number":
            numbers = bucket["numbers"]
            entry["values"] = numbers[:200]
            entry["count"] = len(numbers)
            entry["mean"] = _mean(numbers) if numbers else None
        else:
            entry["values"] = bucket["values"][:200]
            entry["count"] = len(bucket["values"])
        summary["by_type"][question_type] = entry
    return summary


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    try:
        return math.fsum(value / len(values) for value in values)
    except OverflowError:
        scale = max(abs(value) for value in values)
        return scale * math.fsum(value / scale / len(values) for value in values)
