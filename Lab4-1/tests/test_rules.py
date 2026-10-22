"""Independent S4 value/path boundaries and real-MongoDB /next acceptance."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from conftest import register_login
from survey_app.errors import DomainError
from survey_app.questions import check_definition, evaluate_path, validate_answer


def question(kind: str, identifier: str = "answer", *, required: bool = True, validation: dict | None = None) -> dict:
    result = {"id": identifier, "type": kind, "title": identifier, "required": required, "validation": validation or {}}
    if kind in {"single", "multi"}:
        choices = ("a", "b") if kind == "single" else ("a", "b", "c", "d")
        result["options"] = [{"id": value, "label": value.upper()} for value in choices]
    return result


def normalized_question(kind: str, *, required: bool = True, validation: dict | None = None) -> dict:
    normalized, _ = check_definition([question(kind, required=required, validation=validation)], [])
    return normalized[0]


def invalid_call(function, *args, question_id: str | None = None, **kwargs):
    with pytest.raises(DomainError) as caught:
        function(*args, **kwargs)
    assert caught.value.status == 422
    if question_id is not None:
        assert caught.value.question_id == question_id


def branch_definition(kind="single", *, op=None, value=None, required=True):
    source = question(kind, "start", required=required)
    questions = [source, question("text", "middle", required=True), question("text", "end", required=False)]
    default_op = {"single": "eq", "multi": "any", "number": "eq"}[kind]
    default_value = {"single": "a", "multi": ["a"], "number": 10}[kind]
    rules = [{"source": "start", "op": op or default_op, "value": default_value if value is None else value,
              "target": "end", "priority": 10}]
    return check_definition(questions, rules)


def publish_definition(client, questions, rules):
    created = client.post("/api/surveys", json={"title": "S4 synthetic path", "allow_repeat": False})
    assert created.status_code == 201
    survey = created.json()
    saved = client.put(f"/api/surveys/{survey['id']}", json={
        "title": survey["title"], "description": "S4 fixture", "allow_anonymous": True, "allow_repeat": False,
        "closes_at": None, "revision": survey["revision"], "questions": questions, "rules": rules,
    })
    assert saved.status_code == 200
    published = client.post(f"/api/surveys/{survey['id']}/publish", json={"revision": saved.json()["revision"]})
    assert published.status_code == 200
    return published.json()


def assert_api_error(response, status):
    assert response.status_code == status
    assert isinstance(response.json().get("error"), dict)
    assert isinstance(response.json()["error"].get("code"), str)


@pytest.mark.unit
class TestAnswerValidation:
    @pytest.mark.case("TC-V01")
    @pytest.mark.parametrize("value", [None, "", "missing", ["a"], ["a", "b"], True, 1, {}])
    def test_required_single_rejects_empty_unknown_multiple_and_wrong_types(self, value):
        q = normalized_question("single")
        invalid_call(validate_answer, q, value, question_id=q["id"])

    @pytest.mark.case("TC-V01")
    @pytest.mark.parametrize("value", ["a", "b"])
    def test_single_accepts_only_defined_one_option(self, value):
        assert validate_answer(normalized_question("single"), value) == value

    @pytest.mark.case("TC-V01")
    @pytest.mark.parametrize("value", [None, ""])
    def test_optional_single_can_be_skipped(self, value):
        assert validate_answer(normalized_question("single", required=False), value) is None

    @pytest.mark.case("TC-V02")
    @pytest.mark.parametrize("validation,value,accepted", [
        ({"min_choices": 2}, ["a"], False), ({"min_choices": 2}, ["b", "a"], True),
        ({"max_choices": 3}, ["a", "b", "c"], True), ({"max_choices": 3}, ["a", "b", "c", "d"], False),
        ({"min_choices": 2, "max_choices": 3}, ["a", "c"], True),
        ({"exact_choices": 2}, ["a"], False), ({"exact_choices": 2}, ["b", "a"], True),
        ({"exact_choices": 2}, ["a", "b", "c"], False),
    ])
    def test_multi_count_constraints_have_inclusive_boundaries(self, validation, value, accepted):
        q = normalized_question("multi", validation=validation)
        if accepted:
            assert validate_answer(q, value) == sorted(value)
        else:
            invalid_call(validate_answer, q, value, question_id=q["id"])

    @pytest.mark.case("TC-V02")
    @pytest.mark.parametrize("value", [None, [], ["a", "a"], ["a", "unknown"], ["a", 1], "a", True, {}])
    def test_multi_rejects_duplicates_unknown_values_wrong_types_and_required_empty(self, value):
        q = normalized_question("multi")
        invalid_call(validate_answer, q, value, question_id=q["id"])

    @pytest.mark.case("TC-V02")
    def test_multi_normalizes_to_configured_order_without_mutating_input(self):
        raw = question("multi")
        raw["options"] = [raw["options"][2], raw["options"][0], raw["options"][3], raw["options"][1]]
        qs, _ = check_definition([raw], [])
        value = ["b", "c", "a"]
        assert validate_answer(qs[0], value) == ["c", "a", "b"]
        assert value == ["b", "c", "a"]

    @pytest.mark.case("TC-V02")
    @pytest.mark.parametrize("value", [None, []])
    def test_optional_multi_empty_skips_nonempty_count_constraints(self, value):
        q = normalized_question("multi", required=False, validation={"min_choices": 2, "max_choices": 3})
        assert validate_answer(q, value) is None

    @pytest.mark.case("TC-V03")
    @pytest.mark.parametrize("value", ["ab", "甲乙", "a🙂", "甲乙丙丁", " ab "])
    def test_text_preserves_raw_content_and_accepts_inclusive_lengths(self, value):
        q = normalized_question("text", validation={"min_length": 2, "max_length": 4})
        assert validate_answer(q, value) == value

    @pytest.mark.case("TC-V03")
    @pytest.mark.parametrize("value", [None, "", " ", "a", "abcde", "甲乙丙丁戊", "👨‍👩‍👧‍👦", 12, True, []])
    def test_text_rejects_required_blank_lengths_and_nontext_values(self, value):
        q = normalized_question("text", validation={"min_length": 2, "max_length": 4})
        invalid_call(validate_answer, q, value, question_id=q["id"])

    @pytest.mark.case("TC-V03")
    @pytest.mark.parametrize("value", ["e\u0301", "👍🏽"])
    def test_text_counts_unicode_codepoints_instead_of_grapheme_clusters(self, value):
        q = normalized_question("text", validation={"min_length": 2, "max_length": 2})
        assert len(value) == 2
        assert validate_answer(q, value) == value

    @pytest.mark.case("TC-V03")
    @pytest.mark.parametrize("value", [None, "", " \t\n"])
    def test_optional_text_blank_skips_length_constraints(self, value):
        q = normalized_question("text", required=False, validation={"min_length": 2, "max_length": 4})
        assert validate_answer(q, value) is None

    @pytest.mark.case("TC-V04")
    @pytest.mark.parametrize("value,expected", [(0, 0), (120, 120), (1.0, 1), (0.0, 0)])
    def test_integer_numeric_boundaries_and_normalization(self, value, expected):
        q = normalized_question("number", validation={"min_value": 0, "max_value": 120, "integer_only": True})
        result = validate_answer(q, value)
        assert result == expected and type(result) is int

    @pytest.mark.case("TC-V04")
    @pytest.mark.parametrize("value", [-1, 121, 1.5, "1", "not a number", True, False, float("nan"),
                                        float("inf"), float("-inf"), None, [], {}])
    def test_number_rejects_range_fraction_nonfinite_coercion_and_boolean(self, value):
        q = normalized_question("number", validation={"min_value": 0, "max_value": 120, "integer_only": True})
        invalid_call(validate_answer, q, value, question_id=q["id"])

    @pytest.mark.case("TC-V04")
    def test_fractional_numbers_are_preserved_when_allowed_and_zero_is_not_empty(self):
        q = normalized_question("number", validation={"min_value": -1.5, "max_value": 2.5})
        assert validate_answer(q, -1.5) == -1.5
        assert validate_answer(q, 2.5) == 2.5
        invalid_call(validate_answer, q, 2.50001, question_id=q["id"])
        optional = normalized_question("number", required=False)
        assert validate_answer(optional, None) is None
        assert validate_answer(optional, 0) == 0


@pytest.mark.unit
class TestDefinitionValidation:
    @pytest.mark.case("TC-V05")
    @pytest.mark.parametrize("kind,validation", [
        ("multi", {"min_choices": -1}), ("multi", {"min_choices": 3, "max_choices": 2}),
        ("multi", {"exact_choices": 5}), ("multi", {"exact_choices": 1, "min_choices": 2}),
        ("multi", {"exact_choices": 3, "max_choices": 2}), ("multi", {"min_choices": True}),
        ("text", {"min_length": -1}), ("text", {"min_length": 3, "max_length": 2}),
        ("text", {"max_length": 1.5}), ("text", {"unknown": 1}),
        ("number", {"min_value": 2, "max_value": 1}), ("number", {"min_value": "1"}),
        ("number", {"max_value": float("inf")}), ("number", {"min_value": float("nan")}),
        ("number", {"min_value": True}), ("number", {"integer_only": 1}),
        ("single", {"min_choices": 1}),
    ])
    def test_impossible_or_wrongly_typed_constraints_are_rejected(self, kind, validation):
        invalid_call(check_definition, [question(kind, validation=validation)], [])

    @pytest.mark.case("TC-V05")
    @pytest.mark.parametrize("kind,validation", [
        ("multi", {"max_choices": 0}), ("multi", {"exact_choices": 0}),
        ("text", {"max_length": 0}),
        ("number", {"min_value": 0.1, "max_value": 0.9, "integer_only": True}),
    ])
    def test_required_nonempty_answer_must_exist_but_optional_null_is_allowed(self, kind, validation):
        invalid_call(check_definition, [question(kind, required=True, validation=validation)], [])
        optional, _ = check_definition([question(kind, required=False, validation=validation)], [])
        assert validate_answer(optional[0], None) is None

    @pytest.mark.case("TC-V05")
    def test_integer_interval_with_exactly_zero_is_satisfiable(self):
        q = normalized_question("number", validation={"min_value": 0, "max_value": 0, "integer_only": True})
        assert validate_answer(q, 0) == 0

    @pytest.mark.case("TC-V05")
    @pytest.mark.parametrize("corruption", ["duplicate_question", "duplicate_option", "unknown_type", "unknown_field",
                                            "dot_id", "dollar_id", "one_option"])
    def test_question_and_option_structure_rejected(self, corruption):
        questions = [question("single", "first"), question("text", "second")]
        if corruption == "duplicate_question":
            questions[1]["id"] = "first"
        elif corruption == "duplicate_option":
            questions[0]["options"][1]["id"] = "a"
        elif corruption == "unknown_type":
            questions[1]["type"] = "unsupported"
        elif corruption == "unknown_field":
            questions[1]["unexpected"] = True
        elif corruption == "dot_id":
            questions[1]["id"] = "bad.id"
        elif corruption == "dollar_id":
            questions[1]["id"] = "$bad"
        else:
            questions[0]["options"] = questions[0]["options"][:1]
        invalid_call(check_definition, questions, [])

    @pytest.mark.case("TC-V05", "TC-J04")
    @pytest.mark.parametrize("corruption", ["missing_source", "missing_target", "self_loop", "backward", "duplicate_priority",
                                            "unknown_operator", "single_order_operator", "unknown_option", "text_source",
                                            "empty_multi_condition", "unknown_multi_option", "invalid_numeric_operator"])
    def test_rule_configuration_and_graph_are_checked_before_publication(self, corruption):
        questions = [question("single", "first"), question("multi", "second"), question("number", "third"), question("text", "last")]
        rules = [{"source": "first", "op": "eq", "value": "a", "target": "last", "priority": 10}]
        if corruption == "missing_source": rules[0]["source"] = "missing"
        elif corruption == "missing_target": rules[0]["target"] = "missing"
        elif corruption == "self_loop": rules[0]["target"] = "first"
        elif corruption == "backward": rules = [{"source": "third", "op": "eq", "value": 1, "target": "first", "priority": 10}]
        elif corruption == "duplicate_priority": rules.append({**rules[0], "value": "b"})
        elif corruption == "unknown_operator": rules[0]["op"] = "contains"
        elif corruption == "single_order_operator": rules[0]["op"] = "gt"
        elif corruption == "unknown_option": rules[0]["value"] = "missing"
        elif corruption == "text_source":
            questions.append(question("text", "after", required=False))
            rules = [{"source": "last", "op": "eq", "value": "x", "target": "after", "priority": 1}]
        elif corruption == "empty_multi_condition": rules = [{"source": "second", "op": "all", "value": [], "target": "last", "priority": 1}]
        elif corruption == "unknown_multi_option": rules = [{"source": "second", "op": "any", "value": ["missing"], "target": "last", "priority": 1}]
        else: rules = [{"source": "third", "op": "contains", "value": 1, "target": "last", "priority": 1}]
        invalid_call(check_definition, questions, rules)

    @pytest.mark.case("TC-V05", "TC-J04")
    def test_priority_uniqueness_is_per_source_question(self):
        questions = [question("single", "first"), question("multi", "second"), question("text", "end", required=False)]
        rules = [
            {"source": "first", "op": "eq", "value": "a", "target": "end", "priority": 10},
            {"source": "second", "op": "any", "value": ["a"], "target": "end", "priority": 10},
        ]
        normalized_questions, normalized_rules = check_definition(questions, rules)
        assert len(normalized_questions) == 3 and len(normalized_rules) == 2


@pytest.mark.unit
class TestPathEvaluation:
    @pytest.mark.case("TC-J01")
    def test_single_rule_targets_are_data_driven(self):
        questions, rules = branch_definition()
        original = deepcopy((questions, rules))
        jumped = evaluate_path(questions, rules, {"start": "a"}, partial=True)
        assert jumped["path"] == ["start", "end"] and jumped["next_question_id"] == "end"
        default = evaluate_path(questions, rules, {"start": "b"}, partial=True)
        assert default["path"] == ["start", "middle"] and default["next_question_id"] == "middle"
        new_rules = [{**rules[0], "target": "middle"}]
        new_questions, new_rules = check_definition(questions, new_rules)
        changed = evaluate_path(new_questions, new_rules, {"start": "a"}, partial=True)
        assert changed["next_question_id"] == "middle"
        assert (questions, rules) == original

    @pytest.mark.case("TC-J02")
    @pytest.mark.parametrize("op,answer,jumps", [
        ("any", ["a"], True), ("any", ["b", "c"], True), ("any", ["c"], False), ("any", [], False),
        ("all", ["a"], False), ("all", ["a", "b"], True), ("all", ["b", "a", "c"], True), ("all", [], False),
    ])
    def test_multi_any_all_and_empty_sets(self, op, answer, jumps):
        questions, rules = branch_definition("multi", op=op, value=["a", "b"], required=False)
        result = evaluate_path(questions, rules, {"start": answer}, partial=True)
        assert result["next_question_id"] == ("end" if jumps else "middle")

    @pytest.mark.case("TC-J03")
    @pytest.mark.parametrize("op,value,jumps", [
        ("eq", 9, False), ("eq", 10, True), ("eq", 11, False),
        ("lt", 9, True), ("lt", 10, False), ("lt", 11, False),
        ("lte", 9, True), ("lte", 10, True), ("lte", 11, False),
        ("gt", 9, False), ("gt", 10, False), ("gt", 11, True),
        ("gte", 9, False), ("gte", 10, True), ("gte", 11, True),
    ])
    def test_all_numeric_operators_below_equal_and_above_threshold(self, op, value, jumps):
        questions, rules = branch_definition("number", op=op, value=10)
        result = evaluate_path(questions, rules, {"start": value}, partial=True)
        assert result["next_question_id"] == ("end" if jumps else "middle")

    @pytest.mark.case("TC-J02", "TC-J04")
    def test_explicit_priority_beats_input_order_when_rules_both_match(self):
        questions, _ = branch_definition()
        rules = [
            {"source": "start", "op": "eq", "value": "a", "target": "end", "priority": 20},
            {"source": "start", "op": "eq", "value": "a", "target": "middle", "priority": 10},
        ]
        questions, rules = check_definition(questions, rules)
        result = evaluate_path(questions, rules, {"start": "a"}, partial=True)
        assert result["next_question_id"] == "middle"

    @pytest.mark.case("TC-J04", "TC-J05")
    def test_partial_missing_key_stops_but_explicit_optional_null_advances(self):
        questions, rules = check_definition([question("single", "first"), question("text", "optional", required=False),
                                             question("number", "last")], [])
        empty = evaluate_path(questions, rules, {}, partial=True)
        assert empty["path"] == ["first"] and empty["next_question_id"] == "first" and empty["complete"] is False
        first = evaluate_path(questions, rules, {"first": "a"}, partial=True)
        assert first["path"] == ["first", "optional"] and first["next_question_id"] == "optional"
        skipped = evaluate_path(questions, rules, {"first": "a", "optional": None}, partial=True)
        assert skipped["path"] == ["first", "optional", "last"] and skipped["next_question_id"] == "last"
        complete = evaluate_path(questions, rules, {"first": "a", "optional": None, "last": 1.0}, partial=True)
        assert complete["path"] == ["first", "optional", "last"] and complete["complete"] is True
        assert complete["next_question_id"] is None and complete["answers"]["last"] == 1
        assert type(complete["answers"]["last"]) is int
        omitted_optional = evaluate_path(questions, rules, {"first": "a", "last": 0}, partial=False)
        assert omitted_optional["complete"] is True and omitted_optional["path"] == ["first", "optional", "last"]
        assert omitted_optional["answers"].get("optional") is None
        invalid_call(evaluate_path, questions, rules, {"first": "a"}, partial=False, question_id="last")

    @pytest.mark.case("TC-J05")
    def test_skipped_required_question_and_changed_answer_recalculation(self):
        questions, rules = branch_definition()
        jumped = evaluate_path(questions, rules, {"start": "a"}, partial=False)
        assert jumped["complete"] is True and jumped["path"] == ["start", "end"]
        changed = evaluate_path(questions, rules, {"start": "b"}, partial=True)
        assert changed["next_question_id"] == "middle"
        invalid_call(evaluate_path, questions, rules, {"start": "b"}, partial=False, question_id="middle")
        answered = evaluate_path(questions, rules, {"start": "b", "middle": "new answer"}, partial=False)
        assert answered["complete"] is True and answered["path"] == ["start", "middle", "end"]
        invalid_call(evaluate_path, questions, rules, {"start": "a", "middle": "stale answer"}, partial=False)

    @pytest.mark.case("TC-J05")
    @pytest.mark.parametrize("answers", [None, [], "invalid", {"unknown": 1}, {"middle": "not yet reachable"}])
    def test_unknown_wrongly_typed_or_unreachable_payload_rejected(self, answers):
        questions, rules = branch_definition()
        invalid_call(evaluate_path, questions, rules, answers, partial=True)

    @pytest.mark.case("TC-J03", "TC-J05")
    def test_source_answer_is_validated_before_condition_evaluation(self):
        questions, rules = branch_definition("number", op="gt", value=10)
        invalid_call(evaluate_path, questions, rules, {"start": float("nan")}, partial=True, question_id="start")


@pytest.mark.integration
class TestNextAPI:
    @pytest.mark.case("TC-J01", "TC-J05", "TC-A02")
    def test_next_requires_auth_and_real_published_version_without_saving_draft_answers(self, client, client_factory, db):
        register_login(client)
        questions, rules = branch_definition()
        survey = publish_definition(client, questions, rules)
        stored = db.survey_versions.find_one({"survey_id": survey["id"], "version": 1})
        assert stored is not None
        assert [q["id"] for q in stored["questions"]] == ["start", "middle", "end"]
        path = f"/api/fill/{survey['share_code']}/next"
        payload = {"version": 1, "answers": {"start": "a"}}
        with client_factory() as unauthenticated:
            assert_api_error(unauthenticated.post(path, json=payload), 401)
        response = client.post(path, json=payload)
        assert response.status_code == 200
        assert response.json()["path"] == ["start", "end"] and response.json()["next_question_id"] == "end"
        assert response.json()["complete"] is False
        assert db.responses.count_documents({"survey_id": survey["id"]}) == 0
        assert_api_error(client.post(path, json={**payload, "version": 99}), 409)

    @pytest.mark.case("TC-J05")
    @pytest.mark.parametrize("payload", [
        {"version": 1, "answers": {"start": "a", "middle": "injected"}},
        {"version": 1, "answers": {"start": "a", "unknown": 1}},
        {"version": 1, "answers": {"start": "a"}, "path": ["start", "middle", "end"]},
        {"version": 1, "answers": {"start": "a"}, "owner_id": "injected"},
    ])
    def test_next_rejects_path_out_unknown_answers_and_client_control_fields(self, client, db, payload):
        register_login(client)
        questions, rules = branch_definition()
        survey = publish_definition(client, questions, rules)
        assert_api_error(client.post(f"/api/fill/{survey['share_code']}/next", json=payload), 422)
        assert db.responses.count_documents({"survey_id": survey["id"]}) == 0

    @pytest.mark.case("TC-J04", "TC-J05")
    def test_next_handles_explicit_null_then_recomputes_changed_branch(self, client):
        register_login(client)
        questions, rules = branch_definition()
        survey = publish_definition(client, questions, rules)
        path = f"/api/fill/{survey['share_code']}/next"
        first = client.post(path, json={"version": 1, "answers": {}})
        assert first.status_code == 200 and first.json()["path"] == ["start"]
        assert first.json()["next_question_id"] == "start"
        jumped = client.post(path, json={"version": 1, "answers": {"start": "a", "end": None}})
        assert jumped.status_code == 200 and jumped.json()["complete"] is True
        changed = client.post(path, json={"version": 1, "answers": {"start": "b"}})
        assert changed.status_code == 200 and changed.json()["path"] == ["start", "middle"]
        assert changed.json()["next_question_id"] == "middle" and changed.json()["complete"] is False
        assert_api_error(client.post(path, json={"version": 1, "answers": {"start": None}}), 422)

    @pytest.mark.case("TC-J04", "TC-Q03")
    def test_next_checks_draft_closed_expired_and_unknown_lifecycle(self, client):
        register_login(client)
        created = client.post("/api/surveys", json={"title": "Unpublished S4 fixture"})
        assert created.status_code == 201
        assert_api_error(client.post(f"/api/fill/{created.json()['share_code']}/next", json={"version": 1, "answers": {}}), 409)
        questions, rules = branch_definition()
        survey = publish_definition(client, questions, rules)
        path = f"/api/fill/{survey['share_code']}/next"
        assert client.post(path, json={"version": 1, "answers": {}}).status_code == 200
        past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        assert client.patch(f"/api/surveys/{survey['id']}/deadline", json={"closes_at": past}).status_code == 200
        assert_api_error(client.post(path, json={"version": 1, "answers": {}}), 410)
        assert client.patch(f"/api/surveys/{survey['id']}/deadline", json={"closes_at": None}).status_code == 200
        assert client.post(f"/api/surveys/{survey['id']}/close").status_code == 200
        assert_api_error(client.post(path, json={"version": 1, "answers": {}}), 410)
        assert_api_error(client.post("/api/fill/nonexistent-s4-share/next", json={"version": 1, "answers": {}}), 404)

    @pytest.mark.case("TC-V01", "TC-V02", "TC-V03", "TC-V04")
    @pytest.mark.parametrize("kind,value", [("single", ["a"]), ("multi", ["a", "a"]), ("text", 12), ("number", "10")])
    def test_next_uses_same_server_validator_for_all_question_types(self, client, kind, value):
        register_login(client)
        questions, rules = check_definition([question(kind, "only")], [])
        survey = publish_definition(client, questions, rules)
        assert_api_error(client.post(f"/api/fill/{survey['share_code']}/next", json={"version": 1, "answers": {"only": value}}), 422)
