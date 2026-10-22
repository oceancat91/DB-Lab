"""Validate questionnaire configuration, answers and server-computed paths."""

from __future__ import annotations

import math
import re
from copy import deepcopy

from bson import BSON
from bson.errors import BSONError

from .errors import DomainError


_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_QUESTION_FIELDS = {"id", "type", "title", "required", "options", "validation"}
_OPTION_FIELDS = {"id", "label"}
_RULE_FIELDS = {"source", "op", "value", "target", "priority"}
_QUESTION_TYPES = {"single", "multi", "text", "number"}
_VALIDATION_FIELDS = {
    "single": set(),
    "multi": {"min_choices", "max_choices", "exact_choices"},
    "text": {"min_length", "max_length"},
    "number": {"min_value", "max_value", "integer_only"},
}


def _invalid(message: str, question_id: str | None = None) -> None:
    raise DomainError(422, "validation", message, question_id)


def _object(value: object, allowed: set[str], label: str,
            question_id: str | None = None) -> dict:
    if not isinstance(value, dict):
        _invalid(f"{label}必须为对象", question_id)
    if set(value) - allowed:
        _invalid(f"{label}包含不支持的字段", question_id)
    return value


def _identifier(value: object, label: str,
                question_id: str | None = None) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        _invalid(f"{label}须为 1–64 个英文字母、数字、下划线或连字符", question_id)
    return value


def _text(value: object, label: str, maximum: int,
          question_id: str | None = None) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        _invalid(f"{label}须为 1–{maximum} 个字符", question_id)
    if not value.strip():
        _invalid(f"{label}不能全部为空白", question_id)
    return value


def _nonnegative_integer(value: object, label: str,
                         question_id: str | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _invalid(f"{label}必须为非负整数", question_id)
    return value


def _number(value: object, label: str,
            question_id: str | None = None) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _invalid(f"{label}必须为有限数值", question_id)
    if isinstance(value, float) and not math.isfinite(value):
        _invalid(f"{label}必须为有限数值", question_id)
    return value


def _validation(value: object, question_type: str, option_count: int,
                question_id: str) -> dict:
    raw = _object(value, _VALIDATION_FIELDS[question_type], "校验配置", question_id)
    result = {}
    if question_type == "multi":
        for name in ("min_choices", "max_choices", "exact_choices"):
            if name in raw:
                count = _nonnegative_integer(raw[name], name, question_id)
                if count > option_count:
                    _invalid("多选数量限制不能超过选项数量", question_id)
                result[name] = count
        minimum = result.get("min_choices", 0)
        maximum = result.get("max_choices", option_count)
        if minimum > maximum:
            _invalid("最少选择数量不能大于最多选择数量", question_id)
        if "exact_choices" in result and not minimum <= result["exact_choices"] <= maximum:
            _invalid("精确选择数量与最少或最多选择数量冲突", question_id)
    elif question_type == "text":
        for name in ("min_length", "max_length"):
            if name in raw:
                length = _nonnegative_integer(raw[name], name, question_id)
                if length > 10000:
                    _invalid("文本长度限制不能超过 10000 个字符", question_id)
                result[name] = length
        if result.get("min_length", 0) > result.get("max_length", 10000):
            _invalid("最少文本长度不能大于最多文本长度", question_id)
    elif question_type == "number":
        for name in ("min_value", "max_value"):
            if name in raw:
                result[name] = _number(raw[name], name, question_id)
        if "integer_only" in raw:
            if not isinstance(raw["integer_only"], bool):
                _invalid("整数限制必须为布尔值", question_id)
            result["integer_only"] = raw["integer_only"]
        if ("min_value" in result and "max_value" in result
                and result["min_value"] > result["max_value"]):
            _invalid("数字最小值不能大于最大值", question_id)
    return result


def _required_answer_space(question: dict) -> None:
    """A required question must permit at least one nonempty answer."""
    if not question["required"]:
        return
    question_id = question["id"]
    validation = question["validation"]
    if question["type"] == "multi":
        minimum = max(1, validation.get("min_choices", 0))
        maximum = validation.get("max_choices", len(question["options"]))
        if "exact_choices" in validation:
            minimum = max(minimum, validation["exact_choices"])
            maximum = min(maximum, validation["exact_choices"])
        if minimum > maximum:
            _invalid("必答多选题必须允许至少选择一个选项", question_id)
    elif question["type"] == "text":
        if max(1, validation.get("min_length", 0)) > validation.get("max_length", 10000):
            _invalid("必答文本题必须允许输入非空白内容", question_id)
    elif (question["type"] == "number" and validation.get("integer_only", False)
          and "min_value" in validation and "max_value" in validation):
        if math.ceil(validation["min_value"]) > math.floor(validation["max_value"]):
            _invalid("必答整数题的范围内必须至少存在一个整数", question_id)


def check_definition(questions: list, rules: list,
                     for_publish: bool = False) -> tuple[list[dict], list[dict]]:
    """Return detached normalized definitions, rejecting malformed configuration."""
    if not isinstance(questions, list):
        _invalid("题目必须为列表")
    if not isinstance(rules, list):
        _invalid("跳转规则必须为列表")
    if not isinstance(for_publish, bool):
        _invalid("发布标记必须为布尔值")
    if len(questions) > 100:
        _invalid("每份问卷最多包含 100 道题目")
    if len(rules) > 500:
        _invalid("每份问卷最多包含 500 条跳转规则")
    if for_publish and not questions:
        _invalid("发布问卷时至少需要一道题目")

    normalized_questions = []
    questions_by_id = {}
    positions = {}
    for position, value in enumerate(questions):
        raw = _object(value, _QUESTION_FIELDS, "题目")
        question_id = _identifier(raw.get("id"), "题目 ID")
        if question_id in questions_by_id:
            _invalid("题目 ID 不能重复", question_id)
        question_type = raw.get("type")
        if not isinstance(question_type, str) or question_type not in _QUESTION_TYPES:
            _invalid("不支持的题目类型", question_id)
        title = _text(raw.get("title"), "题目标题", 500, question_id)
        required = raw.get("required", False)
        if not isinstance(required, bool):
            _invalid("是否必答必须为布尔值", question_id)

        options = []
        raw_options = raw.get("options", [])
        if not isinstance(raw_options, list):
            _invalid("题目选项必须为列表", question_id)
        if question_type in {"single", "multi"}:
            if not 2 <= len(raw_options) <= 50:
                _invalid("选择题必须设置 2–50 个选项", question_id)
            option_ids = set()
            for raw_option in raw_options:
                option = _object(raw_option, _OPTION_FIELDS, "选项", question_id)
                option_id = _identifier(option.get("id"), "选项 ID", question_id)
                if option_id in option_ids:
                    _invalid("同一题的选项 ID 不能重复", question_id)
                label = _text(option.get("label"), "选项文字", 200, question_id)
                options.append({"id": option_id, "label": label})
                option_ids.add(option_id)
        elif raw_options:
            _invalid("非选择题不能设置选项", question_id)

        question = {
            "id": question_id,
            "type": question_type,
            "title": title,
            "required": required,
            "options": options,
            "validation": _validation(raw.get("validation", {}), question_type,
                                      len(options), question_id),
        }
        _required_answer_space(question)
        normalized_questions.append(question)
        questions_by_id[question_id] = question
        positions[question_id] = position

    normalized_rules = []
    priorities = {}
    for value in rules:
        raw = _object(value, _RULE_FIELDS, "跳转规则")
        if set(raw) != _RULE_FIELDS:
            _invalid("跳转规则必须包含来源、算子、条件值、目标及优先级")
        source = _identifier(raw["source"], "规则来源题 ID")
        target = _identifier(raw["target"], "规则目标题 ID", source)
        if source not in questions_by_id:
            _invalid("跳转规则来源题不存在", source)
        if target not in questions_by_id:
            _invalid("跳转规则目标题不存在", source)
        if positions[target] <= positions[source]:
            _invalid("跳转目标必须严格位于来源题之后", source)

        source_question = questions_by_id[source]
        question_type = source_question["type"]
        if question_type not in {"single", "multi", "number"}:
            _invalid("仅单选、多选和数字题可以配置跳转", source)
        priority = _nonnegative_integer(raw["priority"], "跳转优先级", source)
        source_priorities = priorities.setdefault(source, set())
        if priority in source_priorities:
            _invalid("同一来源题的跳转优先级不能重复", source)
        source_priorities.add(priority)

        operation = raw["op"]
        allowed_operations = {
            "single": {"eq"},
            "multi": {"any", "all"},
            "number": {"eq", "lt", "lte", "gt", "gte"},
        }[question_type]
        if not isinstance(operation, str) or operation not in allowed_operations:
            _invalid("题型不支持该跳转条件算子", source)

        condition = raw["value"]
        option_ids = {option["id"] for option in source_question["options"]}
        if question_type == "single":
            condition = _identifier(condition, "跳转条件选项 ID", source)
            if condition not in option_ids:
                _invalid("跳转条件引用了不存在的选项", source)
        elif question_type == "multi":
            if not isinstance(condition, list) or not condition:
                _invalid("多选跳转条件必须为非空选项列表", source)
            seen = set()
            normalized_condition = []
            for option_value in condition:
                option_id = _identifier(option_value, "跳转条件选项 ID", source)
                if option_id not in option_ids:
                    _invalid("跳转条件引用了不存在的选项", source)
                if option_id in seen:
                    _invalid("多选跳转条件不能重复包含同一选项", source)
                seen.add(option_id)
                normalized_condition.append(option_id)
            condition = normalized_condition
        else:
            condition = _number(condition, "数字跳转条件值", source)

        normalized_rules.append({
            "source": source,
            "op": operation,
            "value": condition,
            "target": target,
            "priority": priority,
        })

    return deepcopy(normalized_questions), deepcopy(normalized_rules)


def _answer(question: dict, value: object) -> str | list[str] | int | float | None:
    """Normalize one answer against an already checked question definition."""
    question_id = question["id"]
    question_type = question["type"]
    validation = question["validation"]
    empty = value is None
    if question_type == "single" and isinstance(value, str) and value == "":
        empty = True
    elif question_type == "multi" and isinstance(value, list) and not value:
        empty = True
    elif question_type == "text" and isinstance(value, str) and not value.strip():
        empty = True
    if empty:
        if question["required"]:
            _invalid("此题为必答题，请填写后继续", question_id)
        return None

    if question_type == "single":
        if not isinstance(value, str):
            _invalid("单选题必须提供一个选项 ID", question_id)
        if value not in {option["id"] for option in question["options"]}:
            _invalid("单选答案引用了不存在的选项", question_id)
        return value

    if question_type == "multi":
        if not isinstance(value, list):
            _invalid("多选题答案必须为选项 ID 列表", question_id)
        option_ids = [option["id"] for option in question["options"]]
        selected = set()
        for option_id in value:
            if not isinstance(option_id, str) or option_id not in option_ids:
                _invalid("多选答案引用了不存在的选项", question_id)
            if option_id in selected:
                _invalid("多选答案不能重复选择同一选项", question_id)
            selected.add(option_id)
        count = len(value)
        if count < validation.get("min_choices", 0):
            _invalid("多选答案未达到最少选择数量", question_id)
        if count > validation.get("max_choices", len(option_ids)):
            _invalid("多选答案超过最多选择数量", question_id)
        if "exact_choices" in validation and count != validation["exact_choices"]:
            _invalid("多选答案不符合精确选择数量", question_id)
        return [option_id for option_id in option_ids if option_id in selected]

    if question_type == "text":
        if not isinstance(value, str):
            _invalid("文本题答案必须为文字", question_id)
        length = len(value)
        if length < validation.get("min_length", 0):
            _invalid("文本答案未达到最少长度", question_id)
        if length > validation.get("max_length", 10000):
            _invalid("文本答案超过最多长度", question_id)
        return value

    numeric = _number(value, "数字题答案", question_id)
    if (validation.get("integer_only", False) and isinstance(numeric, float)
            and not numeric.is_integer()):
        _invalid("此数字题必须填写整数", question_id)
    if "min_value" in validation and numeric < validation["min_value"]:
        _invalid("数字答案小于允许的最小值", question_id)
    if "max_value" in validation and numeric > validation["max_value"]:
        _invalid("数字答案大于允许的最大值", question_id)
    # Keep large finite BSON doubles representable while canonicalizing 1.0 to 1.
    if (isinstance(numeric, float) and numeric.is_integer()
            and -(1 << 63) <= numeric < (1 << 63)):
        return int(numeric)
    return numeric


def validate_answer(question: dict, value: object) -> str | list[str] | int | float | None:
    """Validate one question and return a detached, canonical answer or None."""
    checked_questions, _ = check_definition([question], [])
    return _answer(checked_questions[0], value)


def _matches(rule: dict, answer: str | list[str] | int | float | None) -> bool:
    if answer is None:
        return False
    operation, condition = rule["op"], rule["value"]
    if operation == "eq":
        return answer == condition
    if operation == "any":
        return any(option_id in answer for option_id in condition)
    if operation == "all":
        return all(option_id in answer for option_id in condition)
    if operation == "lt":
        return answer < condition
    if operation == "lte":
        return answer <= condition
    if operation == "gt":
        return answer > condition
    if operation == "gte":
        return answer >= condition
    _invalid("不支持的跳转条件算子", rule["source"])


def evaluate_path(questions: list, rules: list, answers: dict,
                  partial: bool = False) -> dict:
    """Recompute the reachable path, preserving explicit optional skips as null."""
    checked_questions, checked_rules = check_definition(questions, rules)
    if not isinstance(answers, dict):
        _invalid("答案必须为题目 ID 到填写值的对象")
    if not isinstance(partial, bool):
        _invalid("部分校验标记必须为布尔值")
    positions = {question["id"]: index for index, question in enumerate(checked_questions)}
    for question_id in answers:
        _identifier(question_id, "答案题目 ID")
        if question_id not in positions:
            _invalid("答案引用了未知题目", question_id)

    by_source = {}
    for rule in checked_rules:
        by_source.setdefault(rule["source"], []).append(rule)
    for source_rules in by_source.values():
        source_rules.sort(key=lambda rule: rule["priority"])

    path = []
    normalized_answers = {}
    next_question_id = None
    index = 0
    while index < len(checked_questions):
        question = checked_questions[index]
        question_id = question["id"]
        path.append(question_id)
        if partial and question_id not in answers:
            next_question_id = question_id
            break
        normalized = _answer(question, answers.get(question_id))
        normalized_answers[question_id] = normalized
        next_index = index + 1
        for rule in by_source.get(question_id, []):
            if _matches(rule, normalized):
                next_index = positions[rule["target"]]
                break
        index = next_index

    visited = set(path)
    for question_id in answers:
        if question_id not in visited:
            _invalid("答案包含当前路径之外或尚未访问的题目", question_id)
    return {
        "path": path,
        "next_question_id": next_question_id,
        "complete": next_question_id is None,
        "answers": deepcopy(normalized_answers),
    }


def ensure_document_size(document: dict, limit: int = 1048576) -> None:
    """Reject invalid BSON documents or encoded documents exceeding the limit."""
    if not isinstance(document, dict):
        _invalid("待保存文档必须为对象")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        _invalid("文档大小上限必须为正整数")
    try:
        encoded = BSON.encode(document)
    except (BSONError, OverflowError, TypeError, ValueError, RecursionError) as exc:
        raise DomainError(422, "validation", "文档包含无法存储的 BSON 字段或数值") from exc
    if len(encoded) > limit:
        raise DomainError(422, "too_large", "文档编码后超过允许的大小上限")
