"""S5 real-MongoDB submission, isolation, idempotency and transaction races."""

from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import OperationFailure

from conftest import register_login


pytestmark = pytest.mark.integration
N = 10


def definition():
    return [
        {"id": "single", "type": "single", "title": "选择", "required": True, "validation": {},
         "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]},
        {"id": "multi", "type": "multi", "title": "多选", "required": True,
         "validation": {"min_choices": 1, "max_choices": 2},
         "options": [{"id": "x", "label": "X"}, {"id": "y", "label": "Y"}, {"id": "z", "label": "Z"}]},
        {"id": "text", "type": "text", "title": "建议", "required": True,
         "validation": {"min_length": 2, "max_length": 20}},
        {"id": "number", "type": "number", "title": "数字", "required": True,
         "validation": {"min_value": 0, "max_value": 120, "integer_only": True}},
    ]


def answers():
    return {"single": "a", "multi": ["y", "x"], "text": "合成回答", "number": 1.0}


def prepare(client, *, allow_repeat=False, anonymous=True, branching=False, unbounded_number=False):
    created = client.post("/api/surveys", json={"title": "S5 synthetic survey", "allow_repeat": allow_repeat,
                                              "allow_anonymous": anonymous})
    assert created.status_code == 201
    survey = created.json()
    questions = definition()
    if unbounded_number:
        questions[-1]["validation"] = {}
    rules = [{"source": "single", "op": "eq", "value": "a", "target": "number", "priority": 10}] if branching else []
    saved = client.put(f"/api/surveys/{survey['id']}", json={
        "title": survey["title"], "description": "Synthetic test data", "allow_repeat": allow_repeat,
        "allow_anonymous": anonymous, "closes_at": None, "revision": survey["revision"],
        "questions": questions, "rules": rules,
    })
    assert saved.status_code == 200
    published = client.post(f"/api/surveys/{survey['id']}/publish", json={"revision": saved.json()["revision"]})
    assert published.status_code == 200
    return published.json()


def payload(value=None, request_id=None, version=1, **extra):
    return {"version": version, "request_id": request_id or uuid4().hex,
            "answers": answers() if value is None else value, **extra}


def submit(client, survey, body=None):
    return client.post(f"/api/fill/{survey['share_code']}/submit", json=body if body is not None else payload())


def assert_error(response, status):
    assert response.status_code == status
    assert isinstance(response.json().get("error"), dict)
    assert isinstance(response.json()["error"].get("code"), str)


def reconciliation(db, survey):
    documents = list(db.responses.find({"survey_id": survey["id"]}))
    stored = db.surveys.find_one({"_id": survey["id"]})
    return {"responses": len(documents), "response_ids": sorted(document["_id"] for document in documents),
            "distinct_respondents": len({document["respondent_id"] for document in documents}),
            "request_ids": sorted(document["request_id"] for document in documents),
            "gate_seq": stored["gate_seq"], "survey_status": stored["status"]}


def evidence(pytestconfig, name, db, survey, **details):
    result = {"name": name, "survey_id": survey["id"], "database": db.name,
              "reconciliation": reconciliation(db, survey), **details}
    pytestconfig._lab4_evidence.setdefault("submission_experiments", []).append(result)
    return result


def outcome(response):
    result = {"status": response.status_code}
    if response.status_code == 200:
        result.update({key: response.json()[key] for key in ("id", "submitted_at", "replayed")})
    else:
        assert isinstance(response.json().get("error"), dict)
        result["error_code"] = response.json()["error"]["code"]
    return result


@pytest.mark.case("TC-R01")
def test_success_is_a_complete_persistent_document_readable_by_new_application_instance(client, app, settings, db, pytestconfig):
    user = register_login(client)
    survey = prepare(client)
    body = payload()
    response = submit(client, survey, body)
    assert response.status_code == 200 and response.json()["replayed"] is False
    stored = db.responses.find_one({"_id": response.json()["id"]})
    assert stored is not None and stored["survey_id"] == survey["id"] and stored["version"] == 1
    assert stored["respondent_id"] == user["id"] and stored["request_id"] == body["request_id"]
    assert stored["answers"] == {"single": "a", "multi": ["x", "y"], "text": "合成回答", "number": 1}
    assert type(stored["answers"]["number"]) is int
    assert stored["path"] == ["single", "multi", "text", "number"]
    assert stored["single_submission"] is True and stored["anonymous"] is True
    assert len(stored["payload_hash"]) == 64 and stored["schema_version"] == 1
    gate = db.surveys.find_one({"_id": survey["id"]})
    assert gate["gate_seq"] == 1 and gate["last_accepted_at"] == stored["submitted_at"]
    from survey_app.main import create_app
    # A distinct app lifespan/MongoClient reads persistent sessions and responses;
    # a separate OS-process restart is covered by the reproduction stage.
    with TestClient(create_app(settings)) as restarted:
        restarted.cookies.update(client.cookies)
        statistics = restarted.get(f"/api/surveys/{survey['id']}/statistics")
        assert statistics.status_code == 200 and statistics.json()["submissions"] == 1
    evidence(pytestconfig, "persistent_complete_response", db, survey, receipt=outcome(response), fresh_app_read=True)


@pytest.mark.case("TC-R02", "TC-V01", "TC-V02", "TC-V03", "TC-V04")
@pytest.mark.parametrize("field,value", [
    ("single", None), ("single", ["a"]), ("single", "unknown"),
    ("multi", []), ("multi", ["x", "x"]), ("multi", ["missing"]), ("multi", ["x", "y", "z"]),
    ("text", ""), ("text", "a"), ("text", "x" * 21), ("text", 12),
    ("number", True), ("number", 1.5), ("number", -1), ("number", 121), ("number", "10"),
])
def test_invalid_values_for_all_four_types_do_not_write_response_or_gate(client, db, field, value):
    register_login(client)
    survey = prepare(client)
    invalid = {**answers(), field: value}
    assert_error(submit(client, survey, payload(invalid)), 422)
    assert reconciliation(db, survey)["responses"] == 0
    assert reconciliation(db, survey)["gate_seq"] == 0


@pytest.mark.case("TC-R02", "TC-V03", "TC-V04")
@pytest.mark.parametrize("corruption", ["lone-surrogate", "oversized-integer", "nonfinite-json-number"])
def test_non_bson_or_nonfinite_json_answers_are_422_without_writes(client, db, corruption):
    register_login(client)
    survey = prepare(client, unbounded_number=True)
    body = payload()
    if corruption == "lone-surrogate":
        body["answers"]["text"] = "ok" + chr(0xD800)
    elif corruption == "oversized-integer":
        body["answers"]["number"] = 2 ** 80
    else:
        body["answers"]["number"] = "NONFINITE_SENTINEL"
    raw = json.dumps(body, ensure_ascii=True).encode("ascii")
    if corruption == "nonfinite-json-number":
        raw = raw.replace(b'"NONFINITE_SENTINEL"', b"1e309")
    response = client.post(f"/api/fill/{survey['share_code']}/submit", content=raw, headers={"Content-Type": "application/json"})
    assert_error(response, 422)
    assert reconciliation(db, survey)["responses"] == 0 and reconciliation(db, survey)["gate_seq"] == 0


@pytest.mark.case("TC-R02", "TC-J05")
@pytest.mark.parametrize("corruption", ["missing-required", "outside-path", "unknown-question", "client-path", "client-owner", "client-rules", "old-version"])
def test_submit_recomputes_path_and_rejects_tampering_without_write(client, db, corruption):
    register_login(client)
    survey = prepare(client, branching=True)
    body = payload({"single": "a", "number": 10})
    expected = 422
    if corruption == "missing-required": body["answers"] = {"single": "b", "number": 10}
    elif corruption == "outside-path": body["answers"]["text"] = "stale branch"
    elif corruption == "unknown-question": body["answers"]["unknown"] = 1
    elif corruption == "client-path": body["path"] = ["single", "number"]
    elif corruption == "client-owner": body["respondent_id"] = "injected"
    elif corruption == "client-rules": body["rules"] = []
    else: body["version"], expected = 99, 409
    assert_error(submit(client, survey, body), expected)
    assert reconciliation(db, survey)["responses"] == 0 and reconciliation(db, survey)["gate_seq"] == 0


@pytest.mark.case("TC-R01", "TC-J05")
def test_submit_accepts_skipped_required_questions_on_recomputed_valid_branch(client, db):
    register_login(client)
    survey = prepare(client, branching=True)
    response = submit(client, survey, payload({"single": "a", "number": 10}))
    assert response.status_code == 200
    stored = db.responses.find_one({"_id": response.json()["id"]})
    assert stored["path"] == ["single", "number"] and stored["answers"] == {"single": "a", "number": 10}


@pytest.mark.case("TC-R03")
@pytest.mark.parametrize("allow_repeat,second_status,count", [(False, 409, 1), (True, 200, 2)])
def test_repeat_switch_applies_to_new_requests(client, db, allow_repeat, second_status, count):
    register_login(client)
    survey = prepare(client, allow_repeat=allow_repeat)
    first, second = submit(client, survey), submit(client, survey)
    assert first.status_code == 200
    if second_status == 200: assert second.status_code == 200 and second.json()["id"] != first.json()["id"]
    else: assert_error(second, second_status)
    assert reconciliation(db, survey)["responses"] == count
    assert reconciliation(db, survey)["gate_seq"] == count


@pytest.mark.case("TC-R03")
def test_canonical_retry_replays_same_receipt_and_conflicting_payload_rejected_even_after_close(client, db):
    register_login(client)
    survey = prepare(client, allow_repeat=True)
    body = payload()
    first = submit(client, survey, body)
    assert first.status_code == 200 and first.json()["replayed"] is False
    canonical_retry = deepcopy(body)
    canonical_retry["answers"]["multi"] = ["x", "y"]
    canonical_retry["answers"]["number"] = 1
    replayed = submit(client, survey, canonical_retry)
    assert replayed.status_code == 200 and replayed.json()["replayed"] is True
    assert replayed.json()["id"] == first.json()["id"] and replayed.json()["submitted_at"] == first.json()["submitted_at"]
    conflicting = deepcopy(body)
    conflicting["answers"]["text"] = "不同回答"
    assert_error(submit(client, survey, conflicting), 409)
    assert client.post(f"/api/surveys/{survey['id']}/close").status_code == 200
    closed_replay = submit(client, survey, body)
    assert closed_replay.status_code == 200 and closed_replay.json()["id"] == first.json()["id"]
    assert closed_replay.json()["replayed"] is True
    assert_error(submit(client, survey, conflicting), 409)
    assert_error(submit(client, survey, payload()), 410)
    assert reconciliation(db, survey)["responses"] == 1 and reconciliation(db, survey)["gate_seq"] == 1


@pytest.mark.case("TC-A02", "TC-A03", "TC-R04")
def test_authenticated_filler_can_submit_but_only_owner_can_read_statistics_and_details(client, client_factory, db):
    register_login(client)
    survey = prepare(client)
    paths = [f"/api/surveys/{survey['id']}/statistics", f"/api/surveys/{survey['id']}/statistics/single",
             f"/api/surveys/{survey['id']}/responses"]
    for path in paths:
        assert client.get(path).status_code == 200  # all inspected routes really exist
    with client_factory() as other:
        assert_error(submit(other, survey), 401)
        for path in paths: assert_error(other.get(path), 401)
        filler = register_login(other)
        response = submit(other, survey)
        assert response.status_code == 200
        for path in paths: assert_error(other.get(path), 404)
        assert db.responses.find_one({"_id": response.json()["id"]})["respondent_id"] == filler["id"]
    for path in paths: assert client.get(path).status_code == 200


@pytest.mark.case("TC-R04")
@pytest.mark.parametrize("anonymous", [True, False])
def test_anonymous_projection_and_private_duplicate_identity(client, client_factory, db, anonymous):
    register_login(client)
    survey = prepare(client, anonymous=anonymous)
    with client_factory() as filler_client:
        filler = register_login(filler_client)
        first = submit(filler_client, survey)
        assert first.status_code == 200
        assert_error(submit(filler_client, survey), 409)
        assert db.responses.find_one({"_id": first.json()["id"]})["respondent_id"] == filler["id"]
    details = client.get(f"/api/surveys/{survey['id']}/responses")
    statistics = client.get(f"/api/surveys/{survey['id']}/statistics")
    assert details.status_code == statistics.status_code == 200
    public = json.dumps({"details": details.json(), "statistics": statistics.json()}, ensure_ascii=False)
    for private_field in ("respondent_id", "user_id", "password_hash", "payload_hash", "request_id"):
        assert f'"{private_field}"' not in public
    assert filler["id"] not in public
    if anonymous:
        assert filler["username"] not in public and '"username"' not in public
    else:
        assert filler["username"] in public


@pytest.mark.case("TC-R05")
@pytest.mark.concurrency
@pytest.mark.parametrize("mode", ["independent-users", "same-user-new-ids", "same-request-id", "allow-repeat-new-ids"])
def test_ten_synchronized_submissions_reconcile_receipts_and_database(client, client_factory, db, pytestconfig, mode):
    register_login(client)
    survey = prepare(client, allow_repeat=mode == "allow-repeat-new-ids")
    same_id = uuid4().hex
    starting_line = Barrier(N)
    with ExitStack() as clients_stack:
        workers = [clients_stack.enter_context(client_factory()) for _ in range(N)]
        if mode == "independent-users":
            for worker in workers: register_login(worker)
        else:
            for worker in workers: worker.cookies.update(client.cookies)

        def send(index):
            starting_line.wait(timeout=20)
            return outcome(submit(workers[index], survey, payload(request_id=same_id if mode == "same-request-id" else uuid4().hex)))

        with ThreadPoolExecutor(max_workers=N) as executor:
            outcomes = list(executor.map(send, range(N)))
    counts = Counter(item["status"] for item in outcomes)
    actual = evidence(pytestconfig, mode, db, survey, n=N, synchronization="Barrier(10)",
                      outcomes=outcomes, status_counts={str(key): value for key, value in counts.items()})["reconciliation"]
    if mode == "same-user-new-ids":
        assert counts == {200: 1, 409: 9} and actual["responses"] == actual["gate_seq"] == 1
    elif mode == "same-request-id":
        assert counts == {200: N} and actual["responses"] == actual["gate_seq"] == 1
        assert len({item["id"] for item in outcomes}) == 1
        assert sum(item["replayed"] is False for item in outcomes) == 1
    else:
        assert counts == {200: N} and actual["responses"] == actual["gate_seq"] == N
        assert len({item["id"] for item in outcomes}) == N
        assert actual["distinct_respondents"] == (N if mode == "independent-users" else 1)


def lifecycle_write(client, survey, action):
    if action == "close":
        return client.post(f"/api/surveys/{survey['id']}/close")
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    return client.patch(f"/api/surveys/{survey['id']}/deadline", json={"closes_at": past})


@pytest.mark.case("TC-R05")
@pytest.mark.concurrency
@pytest.mark.parametrize("action", ["close", "deadline"])
def test_lifecycle_write_before_actual_gate_rejects_submission(client, client_factory, db, monkeypatch, pytestconfig, action):
    register_login(client)
    survey = prepare(client, allow_repeat=True)
    collection_class = type(db.surveys)
    original = collection_class.find_one_and_update
    reached, release = Event(), Event()

    def before_gate(collection, query, update, *args, **kwargs):
        if (collection.database.name == db.name and collection.name == "surveys" and query.get("_id") == survey["id"]
                and kwargs.get("session") is not None and isinstance(update, list) and not reached.is_set()):
            reached.set()
            if not release.wait(timeout=15): raise AssertionError("Timed out waiting to release actual gate")
        return original(collection, query, update, *args, **kwargs)

    monkeypatch.setattr(collection_class, "find_one_and_update", before_gate)
    with client_factory() as filling_client:
        filling_client.cookies.update(client.cookies)
        with ThreadPoolExecutor(max_workers=1) as executor:
            submitting = executor.submit(submit, filling_client, survey, payload())
            try:
                assert reached.wait(timeout=10)
                lifecycle = lifecycle_write(client, survey, action)
                assert lifecycle.status_code == 200
            finally:
                release.set()
            response = submitting.result(timeout=20)
    actual = evidence(pytestconfig, f"{action}_before_gate", db, survey, submission=outcome(response),
                      schedule="real lifecycle write commits before real conditional gate command")
    assert_error(response, 410)
    assert actual["reconciliation"]["responses"] == actual["reconciliation"]["gate_seq"] == 0


@pytest.mark.case("TC-R05")
@pytest.mark.concurrency
@pytest.mark.parametrize("action", ["close", "deadline"])
def test_actual_gate_before_lifecycle_write_commits_accepted_response(client, client_factory, db, monkeypatch, pytestconfig, action):
    register_login(client)
    survey = prepare(client, allow_repeat=True)
    request_id = uuid4().hex
    collection_class = type(db.responses)
    original_insert = collection_class.insert_one
    original_update = collection_class.find_one_and_update
    gate_written, release, lifecycle_attempted = Event(), Event(), Event()

    def after_real_gate(collection, document, *args, **kwargs):
        if (collection.database.name == db.name and collection.name == "responses" and document.get("request_id") == request_id
                and not gate_written.is_set()):
            assert kwargs.get("session") is not None and kwargs["session"].in_transaction
            gate_written.set()  # service reached insert only after its actual gate write
            if not release.wait(timeout=15): raise AssertionError("Timed out after real gate write")
        return original_insert(collection, document, *args, **kwargs)

    def observe_lifecycle(collection, query, update, *args, **kwargs):
        if (collection.database.name == db.name and collection.name == "surveys" and query.get("_id") == survey["id"]
                and kwargs.get("session") is None and isinstance(update, dict)):
            lifecycle_attempted.set()
        return original_update(collection, query, update, *args, **kwargs)

    monkeypatch.setattr(collection_class, "insert_one", after_real_gate)
    monkeypatch.setattr(collection_class, "find_one_and_update", observe_lifecycle)
    with client_factory() as filling_client:
        filling_client.cookies.update(client.cookies)
        with ThreadPoolExecutor(max_workers=2) as executor:
            submitting = executor.submit(submit, filling_client, survey, payload(request_id=request_id))
            try:
                assert gate_written.wait(timeout=10)
                lifecycle = executor.submit(lifecycle_write, client, survey, action)
                assert lifecycle_attempted.wait(timeout=10)
            finally:
                release.set()
            response = submitting.result(timeout=20)
            lifecycle_response = lifecycle.result(timeout=20)
    actual = evidence(pytestconfig, f"gate_before_{action}", db, survey, submission=outcome(response),
                      lifecycle_status=lifecycle_response.status_code,
                      schedule="real gate write; lifecycle write attempted; real insert/transaction commits; lifecycle finishes")
    assert response.status_code == lifecycle_response.status_code == 200
    assert actual["reconciliation"]["responses"] == actual["reconciliation"]["gate_seq"] == 1
    assert_error(submit(client, survey), 410)


@pytest.mark.case("TC-R05")
@pytest.mark.parametrize("deadline_delta,expected_status", [(60, 200), (-5, 410)])
def test_deadline_before_and_after_server_time_rechecks_already_opened_link(client, db, deadline_delta, expected_status):
    register_login(client)
    survey = prepare(client)
    assert client.get(f"/api/fill/{survey['share_code']}").status_code == 200
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=deadline_delta)).isoformat()
    assert client.patch(f"/api/surveys/{survey['id']}/deadline", json={"closes_at": deadline}).status_code == 200
    response = submit(client, survey)
    if expected_status == 200: assert response.status_code == 200
    else: assert_error(response, expected_status)
    expected_count = int(expected_status == 200)
    assert reconciliation(db, survey)["responses"] == reconciliation(db, survey)["gate_seq"] == expected_count


@pytest.mark.case("TC-R05")
def test_exact_deadline_equality_is_rejected_by_real_gate_comparison_expression(client, db, monkeypatch, pytestconfig):
    register_login(client)
    survey = prepare(client)
    original = type(db.surveys).find_one_and_update
    observed = {}

    def replace_deadline(value):
        if isinstance(value, str): return "$$NOW" if value == "$closes_at" else value
        if isinstance(value, dict): return {key: replace_deadline(item) for key, item in value.items()}
        if isinstance(value, list): return [replace_deadline(item) for item in value]
        return value

    def equality_probe(collection, query, update, *args, **kwargs):
        if (collection.database.name == db.name and collection.name == "surveys" and query.get("_id") == survey["id"]
                and kwargs.get("session") is not None and isinstance(update, list)):
            assert "$closes_at" in json.dumps(query.get("$expr", {})) and "$$NOW" in json.dumps(query["$expr"])
            observed["original_expression"] = deepcopy(query["$expr"])
            query = deepcopy(query)
            query["$expr"] = replace_deadline(query["$expr"])
            observed["equality_expression"] = deepcopy(query["$expr"])
        return original(collection, query, update, *args, **kwargs)

    monkeypatch.setattr(type(db.surveys), "find_one_and_update", equality_probe)
    response = submit(client, survey)
    assert observed
    actual = evidence(pytestconfig, "exact_equality_db_expression", db, survey, submission=outcome(response), **observed,
                      scope="real MongoDB expression probe substitutes deadline operand with same-command $$NOW; not a cross-command clock equality claim")
    assert_error(response, 410)
    assert actual["reconciliation"]["responses"] == actual["reconciliation"]["gate_seq"] == 0


@pytest.mark.case("TC-R02", "TC-R05")
def test_actual_mongodb_validation_failure_rolls_back_gate_and_retry_can_succeed(client, app, db, monkeypatch, pytestconfig):
    user = register_login(client)
    survey = prepare(client)
    request_id = uuid4().hex
    original = type(db.responses).insert_one
    reached = []

    def inject_invalid_document(collection, document, *args, **kwargs):
        if collection.database.name == db.name and collection.name == "responses" and document.get("request_id") == request_id:
            assert kwargs.get("session") is not None and kwargs["session"].in_transaction
            reached.append(True)
            document = {**document, "schema_version": 99}
        # The real MongoDB validator rejects this command; no successful write is mocked.
        return original(collection, document, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(type(db.responses), "insert_one", inject_invalid_document)
        with pytest.raises(OperationFailure) as caught:
            app.state.service.submit(survey["share_code"], user["id"], 1, request_id, answers())
        assert caught.value.code == 121
    before_retry = reconciliation(db, survey)
    assert reached and before_retry["responses"] == before_retry["gate_seq"] == 0
    response = submit(client, survey, payload(request_id=request_id))
    actual = evidence(pytestconfig, "real_validation_failure_transaction_rollback", db, survey,
                      injected_error_code=121, before_retry=before_retry, retry=outcome(response))
    assert response.status_code == 200
    assert actual["reconciliation"]["responses"] == actual["reconciliation"]["gate_seq"] == 1
