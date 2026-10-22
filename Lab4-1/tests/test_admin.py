"""S3 acceptance: implemented account, ownership and survey-management routes."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from conftest import PASSWORD, register_login, unique_username


pytestmark = pytest.mark.integration


def assert_error(response, status: int) -> dict:
    assert response.status_code == status
    body = response.json()
    assert isinstance(body.get("error"), dict)
    assert isinstance(body["error"].get("code"), str)
    assert isinstance(body["error"].get("message"), str)
    assert "password_hash" not in body and "session_secret" not in body
    return body["error"]


def questions() -> list[dict]:
    return [
        {"id": "q1", "type": "single", "title": "单选", "required": True,
         "options": [{"id": "yes", "label": "是"}, {"id": "no", "label": "否"}], "validation": {}},
        {"id": "q2", "type": "multi", "title": "多选", "required": False,
         "options": [{"id": "x", "label": "甲"}, {"id": "y", "label": "乙"}, {"id": "z", "label": "丙"}],
         "validation": {"min_choices": 1, "max_choices": 2}},
        {"id": "q3", "type": "text", "title": "填空", "required": False,
         "validation": {"min_length": 0, "max_length": 100}},
        {"id": "q4", "type": "number", "title": "数字", "required": True,
         "validation": {"min_value": 0, "max_value": 120, "integer_only": True}},
    ]


def rules() -> list[dict]:
    return [{"source": "q1", "op": "eq", "value": "no", "target": "q3", "priority": 10}]


def create_draft(client, **overrides) -> dict:
    payload = {"title": "合成问卷", "description": "仅用于隔离测试", "allow_anonymous": True,
               "allow_repeat": False, "closes_at": None, **overrides}
    response = client.post("/api/surveys", json=payload)
    assert response.status_code == 201
    return response.json()


def draft_payload(survey: dict, **overrides) -> dict:
    return {
        "title": survey["title"], "description": survey.get("description", ""),
        "allow_anonymous": survey["allow_anonymous"], "allow_repeat": survey["allow_repeat"],
        "closes_at": survey.get("closes_at"), "revision": survey["revision"],
        "questions": questions(), "rules": rules(), **overrides,
    }


def ready_draft(client, **overrides) -> dict:
    survey = create_draft(client, **overrides)
    saved = client.put(f"/api/surveys/{survey['id']}", json=draft_payload(survey))
    assert saved.status_code == 200
    return saved.json()


def publish(client, survey: dict) -> dict:
    response = client.post(f"/api/surveys/{survey['id']}/publish", json={"revision": survey["revision"]})
    assert response.status_code == 200
    return response.json()


def assert_question_fields(actual: list[dict], expected: list[dict]) -> None:
    assert [question["id"] for question in actual] == [question["id"] for question in expected]
    for actual_question, expected_question in zip(actual, expected):
        for key, value in expected_question.items():
            assert actual_question[key] == value


@pytest.mark.case("TC-A01")
def test_register_login_hash_uniqueness_and_logout(client, client_factory, db):
    username = unique_username()
    registration = client.post("/api/auth/register", json={"username": username, "password": PASSWORD})
    assert registration.status_code == 201
    user = registration.json()
    assert set(user) == {"id", "username", "created_at"}
    assert user["username"] == username
    datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
    assert_error(client.get("/api/auth/me"), 401)  # registration does not log in
    stored = db.users.find_one({"_id": user["id"]})
    assert stored is not None and stored["username_key"] == username.casefold()
    # Registration time must be a real BSON date in the document, not only in the API response.
    # BSON dates carry milliseconds while the API ISO text may carry microseconds, so compare with a tolerance.
    assert isinstance(stored["created_at"], datetime) and stored["created_at"].tzinfo is not None
    api_created = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
    assert abs((stored["created_at"] - api_created).total_seconds()) < 0.001
    assert "password" not in stored and PASSWORD not in stored["password_hash"]
    assert "scrypt" in stored["password_hash"].lower()
    assert_error(client.post("/api/auth/register", json={"username": f"  {username.upper()}  ", "password": PASSWORD}), 409)
    assert_error(client.post("/api/auth/login", json={"username": username, "password": "wrong-password"}), 401)
    login = client.post("/api/auth/login", json={"username": username.upper(), "password": PASSWORD})
    assert login.status_code == 200 and login.json()["id"] == user["id"]
    cookie = login.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/auth/me").json()["id"] == user["id"]
    assert db.sessions.count_documents({"user_id": user["id"]}) == 1
    with client_factory() as other:
        other_user = register_login(other)
        other_stored = db.users.find_one({"_id": other_user["id"]})
        assert other_stored["password_hash"] != stored["password_hash"]  # independent salts
    assert client.post("/api/auth/logout").status_code == 204
    assert_error(client.get("/api/auth/me"), 401)
    assert db.sessions.count_documents({"user_id": user["id"]}) == 0


@pytest.mark.case("TC-A01")
@pytest.mark.parametrize("username,password", [("ab", PASSWORD), ("   ", PASSWORD), ("valid-user", "short")])
def test_registration_input_validation(client, username, password):
    assert_error(client.post("/api/auth/register", json={"username": username, "password": password}), 422)


@pytest.mark.case("TC-A02")
def test_unauthenticated_management_and_existing_fill_route(client, client_factory):
    with client_factory() as owner:
        register_login(owner)
        survey = ready_draft(owner)
        published = publish(owner, survey)
        code = published["share_code"]
        assert owner.get(f"/api/fill/{code}").status_code == 200  # existing implemented route
        survey_id = survey["id"]
        requests = [
            ("GET", "/api/surveys", None), ("POST", "/api/surveys", {"title": "Unauthorized"}),
            ("GET", f"/api/surveys/{survey_id}", None),
            ("PUT", f"/api/surveys/{survey_id}", draft_payload(survey)),
            ("POST", f"/api/surveys/{survey_id}/publish", {"revision": survey["revision"]}),
            ("POST", f"/api/surveys/{survey_id}/close", None),
            ("PATCH", f"/api/surveys/{survey_id}/deadline", {"closes_at": None}),
            ("GET", f"/api/fill/{code}", None),
        ]
        for method, path, body in requests:
            assert_error(client.request(method, path, **({"json": body} if body is not None else {})), 401)


@pytest.mark.case("TC-A03")
def test_owner_isolation_on_implemented_management_routes(client, client_factory, db):
    owner_user = register_login(client)
    survey = ready_draft(client)
    survey_id = survey["id"]
    assert client.get(f"/api/surveys/{survey_id}").status_code == 200
    with client_factory() as stranger:
        register_login(stranger)
        listing = stranger.get("/api/surveys")
        assert listing.status_code == 200 and isinstance(listing.json(), list)
        assert all(item["id"] != survey_id for item in listing.json())
        baseline = db.surveys.find_one({"_id": survey_id})
        assert baseline["owner_id"] == owner_user["id"]
        assert_error(stranger.get(f"/api/surveys/{survey_id}"), 404)
        assert_error(stranger.put(f"/api/surveys/{survey_id}", json=draft_payload(survey, title="Injected")), 404)
        assert_error(stranger.post(f"/api/surveys/{survey_id}/publish", json={"revision": survey["revision"]}), 404)
        assert db.surveys.find_one({"_id": survey_id}) == baseline
        published = publish(client, survey)
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        assert client.patch(f"/api/surveys/{survey_id}/deadline", json={"closes_at": future}).status_code == 200
        baseline = db.surveys.find_one({"_id": survey_id})
        assert_error(stranger.patch(f"/api/surveys/{survey_id}/deadline", json={"closes_at": None}), 404)
        assert_error(stranger.post(f"/api/surveys/{survey_id}/close"), 404)
        assert db.surveys.find_one({"_id": survey_id}) == baseline
        assert client.post(f"/api/surveys/{survey_id}/close").status_code == 200
        assert published["status"] == "published"


@pytest.mark.case("TC-Q01")
def test_create_preserves_metadata_defaults_and_ownership(client, db):
    user = register_login(client)
    deadline = (datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2))
    survey = create_draft(client, title="课程调查", description="第一行\n第二行", allow_anonymous=False,
                          allow_repeat=True, closes_at=deadline.isoformat())
    assert survey["title"] == "课程调查" and survey["description"] == "第一行\n第二行"
    assert survey["allow_anonymous"] is False and survey["allow_repeat"] is True
    assert survey["status"] == "draft" and survey["revision"] == 0
    assert survey["share_code"] and survey["share_url"]
    stored = db.surveys.find_one({"_id": survey["id"]})
    assert stored["owner_id"] == user["id"] and stored["closes_at"] == deadline
    assert stored["allow_repeat"] is True and stored["allow_anonymous"] is False
    minimal = client.post("/api/surveys", json={"title": "默认值问卷"})
    assert minimal.status_code == 201
    assert minimal.json()["description"] == ""
    assert minimal.json()["allow_anonymous"] is True and minimal.json()["allow_repeat"] is False
    listing = client.get("/api/surveys")
    assert listing.status_code == 200 and isinstance(listing.json(), list)
    assert {survey["id"], minimal.json()["id"]}.issubset({item["id"] for item in listing.json()})


@pytest.mark.case("TC-Q01")
@pytest.mark.parametrize("title", ["", "   "])
def test_empty_title_rejected_without_write(client, db, title):
    user = register_login(client)
    before = db.surveys.count_documents({"owner_id": user["id"]})
    assert_error(client.post("/api/surveys", json={"title": title}), 422)
    assert db.surveys.count_documents({"owner_id": user["id"]}) == before


@pytest.mark.case("TC-Q02")
def test_four_types_configuration_and_published_snapshot_freeze(client, db):
    register_login(client)
    survey = ready_draft(client)
    survey_id = survey["id"]
    reread = client.get(f"/api/surveys/{survey_id}")
    assert reread.status_code == 200
    assert_question_fields(reread.json()["questions"], questions())
    assert reread.json()["rules"] == rules()
    published = publish(client, survey)
    assert published["status"] == "published" and published["version"] == 1
    assert published["share_code"] == survey["share_code"] and published["share_url"] == survey["share_url"]
    snapshot = db.survey_versions.find_one({"survey_id": survey_id, "version": 1})
    assert snapshot is not None
    assert_question_fields(snapshot["questions"], questions())
    assert snapshot["rules"] == rules()
    assert "draft" not in db.surveys.find_one({"_id": survey_id})
    attempted = draft_payload(published, title="Changed", allow_anonymous=False, allow_repeat=True)
    assert_error(client.put(f"/api/surveys/{survey_id}", json=attempted), 409)
    assert_error(client.post(f"/api/surveys/{survey_id}/publish", json={"revision": published["revision"]}), 409)
    assert db.survey_versions.find_one({"survey_id": survey_id, "version": 1}) == snapshot
    assert db.survey_versions.count_documents({"survey_id": survey_id}) == 1


@pytest.mark.case("TC-Q03")
def test_draft_published_closed_and_expired_fill_links(client, db):
    register_login(client)
    survey = ready_draft(client)
    code = survey["share_code"]
    assert_error(client.get(f"/api/fill/{code}"), 409)
    published = publish(client, survey)
    fill = client.get(f"/api/fill/{code}")
    assert fill.status_code == 200 and fill.json()["version"] == 1
    assert_question_fields(fill.json()["questions"], questions())
    assert not {"owner_id", "respondent_id", "gate_seq", "last_accepted_at"}.intersection(fill.json())
    assert client.post(f"/api/surveys/{survey['id']}/close").status_code == 200
    assert_error(client.get(f"/api/fill/{code}"), 410)
    assert db.surveys.find_one({"_id": survey["id"]})["status"] == "closed"
    other = publish(client, ready_draft(client))
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    assert client.patch(f"/api/surveys/{other['id']}/deadline", json={"closes_at": past}).status_code == 200
    assert_error(client.get(f"/api/fill/{other['share_code']}"), 410)
    assert published["share_url"].endswith(code)


@pytest.mark.case("TC-Q03")
def test_stale_edit_and_publish_revision_cannot_replace_new_draft(client, db):
    register_login(client)
    original = ready_draft(client)
    edited = client.put(f"/api/surveys/{original['id']}", json=draft_payload(original, title="New revision"))
    assert edited.status_code == 200
    current = edited.json()
    assert current["revision"] > original["revision"]
    assert_error(client.put(f"/api/surveys/{original['id']}", json=draft_payload(original, title="Lost update")), 409)
    assert_error(client.post(f"/api/surveys/{original['id']}/publish", json={"revision": original["revision"]}), 409)
    assert db.survey_versions.count_documents({"survey_id": original["id"]}) == 0
    published = publish(client, current)
    assert published["title"] == "New revision"
    assert db.survey_versions.count_documents({"survey_id": original["id"]}) == 1


@pytest.mark.case("TC-Q03")
@pytest.mark.concurrency
def test_concurrent_publish_freezes_exactly_one_version(client, client_factory, db):
    register_login(client)
    survey = ready_draft(client)
    starting_line = Barrier(2)

    def attempt_publish():
        with client_factory() as concurrent_client:
            concurrent_client.cookies.update(client.cookies)
            starting_line.wait(timeout=10)
            response = concurrent_client.post(f"/api/surveys/{survey['id']}/publish", json={"revision": survey["revision"]})
            if response.status_code != 200:
                assert_error(response, 409)
            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt_publish(), range(2)))
    assert sorted(outcomes) == [200, 409]
    assert db.survey_versions.count_documents({"survey_id": survey["id"]}) == 1
    assert db.surveys.find_one({"_id": survey["id"]})["status"] == "published"


@pytest.mark.case("TC-Q03")
@pytest.mark.parametrize("corruption", ["missing_target", "self_loop", "duplicate_id", "empty_questions"])
def test_publish_revalidates_invalid_stored_configuration(client, db, corruption):
    register_login(client)
    survey = ready_draft(client)
    invalid_questions, invalid_rules = questions(), rules()
    if corruption == "missing_target":
        invalid_rules[0]["target"] = "missing"
    elif corruption == "self_loop":
        invalid_rules[0]["target"] = "q1"
    elif corruption == "duplicate_id":
        invalid_questions[1]["id"] = invalid_questions[0]["id"]
    else:
        invalid_questions, invalid_rules = [], []
    # Explicit fault injection in this test's own draft verifies the publish gate;
    # this does not claim an invalid draft was accepted through the public API.
    db.surveys.update_one({"_id": survey["id"]}, {"$set": {"draft": {"questions": invalid_questions, "rules": invalid_rules}}})
    assert_error(client.post(f"/api/surveys/{survey['id']}/publish", json={"revision": survey["revision"]}), 422)
    assert db.surveys.find_one({"_id": survey["id"]})["status"] == "draft"
    assert db.survey_versions.count_documents({"survey_id": survey["id"]}) == 0


@pytest.mark.case("TC-A02")
def test_expired_session_is_rejected_without_waiting_for_ttl(client, db):
    user = register_login(client)
    assert db.sessions.count_documents({"user_id": user["id"]}) == 1
    db.sessions.update_many({"user_id": user["id"]}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=5)}})
    assert_error(client.get("/api/auth/me"), 401)
    assert_error(client.get("/api/surveys"), 401)


@pytest.mark.case("TC-A02")
def test_cross_origin_write_is_rejected_and_same_origin_works(client, db):
    user = register_login(client)
    before = db.surveys.count_documents({"owner_id": user["id"]})
    rejected = client.post("/api/surveys", json={"title": "Forbidden origin"}, headers={"Origin": "https://untrusted.invalid"})
    assert_error(rejected, 403)
    assert db.surveys.count_documents({"owner_id": user["id"]}) == before
    allowed = client.post("/api/surveys", json={"title": "Same origin"}, headers={"Origin": "http://testserver"})
    assert allowed.status_code == 201


@pytest.mark.case("TC-Q01", "TC-Q02")
@pytest.mark.parametrize("field,value", [("owner_id", "attacker"), ("status", "published"), ("gate_seq", 999), ("unexpected", True)])
def test_unknown_and_server_owned_fields_are_rejected(client, db, field, value):
    user = register_login(client)
    before = db.surveys.count_documents({"owner_id": user["id"]})
    assert_error(client.post("/api/surveys", json={"title": "Injection", field: value}), 422)
    assert db.surveys.count_documents({"owner_id": user["id"]}) == before
    survey = ready_draft(client)
    stored = deepcopy(db.surveys.find_one({"_id": survey["id"]}))
    assert_error(client.put(f"/api/surveys/{survey['id']}", json=draft_payload(survey, **{field: value})), 422)
    assert db.surveys.find_one({"_id": survey["id"]}) == stored


@pytest.mark.case("TC-A02")
def test_malformed_origin_is_rejected_without_server_error(client, db):
    user = register_login(client)
    before = db.surveys.count_documents({"owner_id": user["id"]})
    response = client.post("/api/surveys", json={"title": "Malformed origin"}, headers={"Origin": "http://["})
    assert_error(response, 403)
    assert db.surveys.count_documents({"owner_id": user["id"]}) == before


@pytest.mark.case("TC-A01")
def test_body_larger_than_one_mib_is_rejected_with_content_length(client, db):
    username = unique_username()
    # Whitespace keeps this valid JSON with otherwise valid registration fields:
    # the size limit, rather than a field-length constraint, must reject it.
    body = b" " * (1024 * 1024) + json.dumps({"username": username, "password": PASSWORD}).encode()
    response = client.post("/api/auth/register", content=body, headers={"Content-Type": "application/json"})
    assert_error(response, 422)
    assert db.users.find_one({"username_key": username.casefold()}) is None


@pytest.mark.case("TC-A01")
def test_stream_without_content_length_stops_reading_when_limit_exceeded(app, db):
    username = unique_username()
    chunks = [b" " * (1024 * 1024), b" ", json.dumps({"username": username, "password": PASSWORD}).encode()]
    receive_count = 0
    sent = []
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/api/auth/register", "raw_path": b"/api/auth/register",
        "root_path": "", "query_string": b"", "server": ("testserver", 80), "client": ("testclient", 50000),
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")], "state": {},
    }

    async def receive():
        nonlocal receive_count
        receive_count += 1
        if receive_count > 2:
            raise AssertionError("Application continued reading after exceeding 1 MiB")
        return {"type": "http.request", "body": chunks[receive_count - 1], "more_body": True}

    async def send(message):
        sent.append(message)

    async def exchange():
        await asyncio.wait_for(app(scope, receive, send), timeout=5)

    # Direct ASGI receive events preserve chunk boundaries, unlike a client
    # transport that may combine the entire generator before delivering it.
    asyncio.run(exchange())
    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert len(starts) == 1 and starts[0]["status"] == 422
    response_body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    assert isinstance(json.loads(response_body).get("error"), dict)
    assert receive_count == 2
    assert db.users.find_one({"username_key": username.casefold()}) is None


@pytest.mark.case("TC-Q01", "TC-Q03")
@pytest.mark.parametrize("invalid", [1700000000, 1700000000.5, "1700000000", "1700000000000", True, False],
                         ids=["integer-epoch", "float-epoch", "numeric-seconds", "numeric-millis", "true", "false"])
def test_numeric_or_boolean_deadline_rejected_at_all_write_entries(client, db, invalid):
    user = register_login(client)
    before = db.surveys.count_documents({"owner_id": user["id"]})
    assert_error(client.post("/api/surveys", json={"title": "Invalid deadline", "closes_at": invalid}), 422)
    assert db.surveys.count_documents({"owner_id": user["id"]}) == before
    survey = ready_draft(client)
    stored = db.surveys.find_one({"_id": survey["id"]})
    assert_error(client.put(f"/api/surveys/{survey['id']}", json=draft_payload(survey, closes_at=invalid)), 422)
    assert db.surveys.find_one({"_id": survey["id"]}) == stored
    published = publish(client, survey)
    stored = db.surveys.find_one({"_id": survey["id"]})
    assert_error(client.patch(f"/api/surveys/{published['id']}/deadline", json={"closes_at": invalid}), 422)
    assert db.surveys.find_one({"_id": survey["id"]}) == stored


@pytest.mark.case("TC-Q01", "TC-Q03")
@pytest.mark.parametrize("kind", ["offset-iso", "utc-iso", "null"])
def test_timezone_iso_and_null_deadline_accepted_at_all_write_entries(client, db, kind):
    register_login(client)
    expected = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
    if kind == "offset-iso":
        value = expected.astimezone(timezone(timedelta(hours=8))).isoformat()
    elif kind == "utc-iso":
        value = expected.isoformat().replace("+00:00", "Z")
    else:
        value, expected = None, None
    survey = create_draft(client, closes_at=value)
    assert db.surveys.find_one({"_id": survey["id"]})["closes_at"] == expected
    saved = client.put(f"/api/surveys/{survey['id']}", json=draft_payload(survey, closes_at=value))
    assert saved.status_code == 200
    assert db.surveys.find_one({"_id": survey["id"]})["closes_at"] == expected
    published = publish(client, saved.json())
    assert client.patch(f"/api/surveys/{published['id']}/deadline", json={"closes_at": value}).status_code == 200
    assert db.surveys.find_one({"_id": survey["id"]})["closes_at"] == expected
