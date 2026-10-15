"""Owner-only statistics and response views from a MongoDB snapshot.

Each request reads the selected version's responses once in a snapshot
transaction. Python then aggregates that fixed list; no statistics are stored
as business data outside MongoDB and no mutable summary collection is used.
"""

from __future__ import annotations

import math
from copy import deepcopy

from .errors import DomainError


_RESPONSE_FIELDS = {
    "_id": 1,
    "version": 1,
    "respondent_id": 1,
    "answers": 1,
    "path": 1,
    "submitted_at": 1,
    "anonymous": 1,
}


def _snapshot(service, survey_id, user_id, question_id=None, with_usernames=False):
    def read(session):
        # Ownership is checked before reading versions, answers or identities.
        survey = service.owned(survey_id, user_id, session=session)
        if survey["status"] == "draft" or survey["published_version"] is None:
            raise DomainError(409, "not_published", "草稿问卷尚无可查看的填写结果")
        version = service.version(survey, session=session)
        if (question_id is not None
                and not any(question["id"] == question_id for question in version["questions"])):
            raise DomainError(404, "not_found", "问卷中不存在这道题目", question_id)
        rows = list(service.db.responses.find(
            {"survey_id": survey["_id"], "version": version["version"]},
            _RESPONSE_FIELDS, session=session,
        ).sort([("submitted_at", 1), ("_id", 1)]))
        usernames = {}
        if with_usernames and not survey["allow_anonymous"]:
            identifiable = {row["respondent_id"] for row in rows if not row["anonymous"]}
            if identifiable:
                users = service.db.users.find(
                    {"_id": {"$in": list(identifiable)}}, {"_id": 1, "username": 1}, session=session,
                )
                usernames = {user["_id"]: user["username"] for user in users}
        return survey, version, rows, usernames

    return service.transaction(read)


def _mean(values):
    if not values:
        return None
    count = len(values)
    try:
        return math.fsum(value / count for value in values)
    except OverflowError:
        # Rounded thirds of the largest double can still overflow fsum.
        # Rescale that exceptional case; a mean cannot exceed max(abs(value)).
        scale = max(abs(value) for value in values)
        normalized = math.fsum(value / scale for value in values) / count
        return max(-1.0, min(1.0, normalized)) * scale


def _question_statistics(question, rows):
    question_id = question["id"]
    answered = [
        (row["respondent_id"], row["answers"][question_id])
        for row in rows
        if question_id in row["answers"] and row["answers"][question_id] is not None
    ]
    result = {
        "id": question_id,
        "type": question["type"],
        "title": question["title"],
        "answered_submissions": len(answered),
        "answered_people": len({respondent for respondent, _ in answered}),
    }
    if question["type"] in {"single", "multi"}:
        options = []
        for option in question["options"]:
            selections = [
                respondent for respondent, value in answered
                if (value == option["id"] if question["type"] == "single"
                    else option["id"] in value)
            ]
            options.append({
                "id": option["id"], "label": option["label"],
                "count": len(selections), "people": len(set(selections)),
            })
        result["options"] = options
    else:
        values = [value for _, value in answered]
        result["values"] = deepcopy(values)
        if question["type"] == "number":
            result["mean"] = _mean(values)
    return result


def statistics(service, survey_id, user_id, question_id=None):
    """Return whole-survey or single-question statistics for the owner only."""
    survey, version, rows, _ = _snapshot(service, survey_id, user_id, question_id)
    if question_id is not None:
        question = next(question for question in version["questions"] if question["id"] == question_id)
        return _question_statistics(question, rows)
    return {
        "survey_id": survey["_id"],
        "version": version["version"],
        "submissions": len(rows),
        "respondents": len({row["respondent_id"] for row in rows}),
        "questions": [_question_statistics(question, rows) for question in version["questions"]],
    }


def responses(service, survey_id, user_id):
    """Return only explicitly allowed answer fields and permitted usernames."""
    survey, _, rows, usernames = _snapshot(service, survey_id, user_id, with_usernames=True)
    result = []
    for row in rows:
        anonymous = bool(survey["allow_anonymous"] or row["anonymous"])
        public = {
            "id": row["_id"],
            "version": row["version"],
            "answers": deepcopy(row["answers"]),
            "path": deepcopy(row["path"]),
            "submitted_at": row["submitted_at"].isoformat(),
            "anonymous": anonymous,
        }
        if not anonymous and row["respondent_id"] in usernames:
            public["username"] = usernames[row["respondent_id"]]
        result.append(public)
    return result
