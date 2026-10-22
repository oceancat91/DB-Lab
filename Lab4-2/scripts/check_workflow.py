#!/usr/bin/env python3
"""Read-only structural checks for the second-stage records; never validates behaviour."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SHARED_ROOT = ROOT.parent
SHARED = ("AGENTS.md", "WORKFLOW.md", "README.md")
SOURCE_FILE = "大作业一：需求变更.docx"
SOURCE_SHA256 = "D9E5BDD8594810923570495CB22B0D8A992889FFF9B140E1607C700CB008DF1D"
REQUIRED = (
    "progress.json", "docs/REQUIREMENTS.md", "docs/DECISIONS.md", "docs/TEST_PLAN.md",
    "docs/TEST_REPORT.md", "docs/EXPERIMENT_LOG.md", "docs/AI_USAGE.md", "docs/DATABASE.md",
    "docs/API.md", "docs/LOGIC.md", "docs/SYSTEM.md", "docs/REPORT_STAGE2.md",
)
STAGE_IDS = [f"T{index}" for index in range(8)]
GATES_PER_STAGE = 2
EVIDENCE_KINDS = (
    ({"planning_review"}, {"decision_review"}),
    ({"design_review"}, {"real_mongodb"}),
    ({"automated_test"}, {"documentation"}),
    ({"manual_test", "http_check"},),
    ({"automated_test"}, {"real_mongodb"}),
    ({"migration_check"}, {"automated_test"}),
    ({"acceptance_test"},),
    ({"submission_review"}, {"baseline_snapshot"}),
)
STATES = {"pending", "active", "passed", "blocked"}
TEST_ID = re.compile(r"(?<![A-Za-z0-9_])TC-L\d{2}(?![A-Za-z0-9_])")
ERRORS: list[str] = []
WARNINGS: list[str] = []


def error(message: str) -> None:
    ERRORS.append(message)


def warn(message: str) -> None:
    WARNINGS.append(message)


def safe_path(value: object, context: str, base: Path = ROOT) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        error(f"{context}：需要非空相对路径")
        return None
    value = unquote(value.strip())
    normalized = value.replace("\\", "/")
    if ("\x00" in normalized or normalized.startswith(("/", "~"))
            or re.match(r"^[A-Za-z]:", normalized)
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", normalized)):
        error(f"{context}：禁止绝对路径、盘符路径或 URI：{value}")
        return None
    if any(re.fullmatch(r"lab\d+", part, re.IGNORECASE) for part in normalized.split("/")):
        error(f"{context}：不得引用独立 Lab 目录：{value}")
        return None
    try:
        path = (base / normalized).resolve()
        if path.parent == SHARED_ROOT.resolve() and path.name in SHARED:
            return path
        path.relative_to(ROOT)
    except (OSError, ValueError, RuntimeError):
        error(f"{context}：路径无效或越出阶段目录：{value}")
        return None
    return path


def nonempty_file(value: object, context: str) -> Path | None:
    path = safe_path(value, context)
    if path is None:
        return None
    try:
        if not path.is_file() or path.stat().st_size == 0:
            error(f"{context}：文件缺失、非普通文件或为空：{value}")
            return None
    except OSError as exc:
        error(f"{context}：文件无法检查：{exc}")
        return None
    return path


def read_text(path: Path, context: str) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        error(f"{context}：不能读取 UTF-8 文本：{exc}")
        return None


def without_fences(text: str) -> str:
    lines: list[str] = []
    fence: str | None = None
    width = 0
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence, width = marker[0], len(marker)
                continue
            if marker[0] == fence and len(marker) >= width:
                fence = None
                continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines)


def link_targets(text: str) -> list[str]:
    text = without_fences(text)
    text = re.sub(r"(`+).*?\1", "", text)
    targets: list[str] = []
    for match in re.finditer(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+[^\n]*?)?\s*\)", text):
        targets.append(match.group(1).strip("<>"))
    return targets


def check_links(path: Path, text: str) -> None:
    label = path.relative_to(SHARED_ROOT).as_posix()
    for target in link_targets(text):
        if target.startswith("#"):
            continue
        decoded = unquote(target)
        if re.match(r"^[A-Za-z]:", decoded):
            error(f"{label}：本地链接禁止硬编码盘符路径：{target}")
            continue
        try:
            parts = urlsplit(target)
        except ValueError:
            error(f"{label}：无效链接：{target}")
            continue
        if parts.scheme.lower() in {"http", "https", "mailto"}:
            continue
        if parts.scheme or parts.netloc:
            error(f"{label}：不支持的本地链接协议：{target}")
            continue
        if not parts.path:
            continue
        destination = safe_path(parts.path, f"{label} 链接", path.parent)
        if destination is not None and not destination.exists():
            error(f"{label}：本地链接目标不存在：{target}")


def check_source(progress: dict) -> None:
    source = progress.get("source")
    if not isinstance(source, dict):
        error("progress.json：source 必须是对象")
        return
    if source.get("file") != SOURCE_FILE:
        error(f"progress.json：source.file 必须为 {SOURCE_FILE}")
    digest = source.get("sha256")
    if not isinstance(digest, str) or digest.upper() != SOURCE_SHA256:
        error("progress.json：source.sha256 与已核验的需求变更 Word 摘要不符")
    path = nonempty_file(SOURCE_FILE, "需求变更 Word")
    if path is not None:
        try:
            hasher = hashlib.sha256()
            with path.open("rb") as source_file:
                for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                    hasher.update(chunk)
            if hasher.hexdigest().upper() != SOURCE_SHA256:
                error("需求变更 Word SHA-256 已变化；先核验来源并记录需求差异")
        except OSError as exc:
            error(f"需求变更 Word：不能计算摘要：{exc}")


def check_stages(progress: dict) -> None:
    stages = progress.get("stages")
    if not isinstance(stages, list) or len(stages) != len(STAGE_IDS):
        error("progress.json：stages 必须按顺序完整包含 T0–T7，共 8 项")
        return
    if [stage.get("id") if isinstance(stage, dict) else None for stage in stages] != STAGE_IDS:
        error("progress.json：阶段 ID 必须恰为按顺序排列的 T0–T7")
        return
    first_unpassed: str | None = None
    in_progress = 0
    for index, stage in enumerate(stages):
        stage_id = stage["id"]
        status = stage.get("status")
        if status not in STATES:
            error(f"{stage_id}：status 必须是 pending/active/passed/blocked")
        if not isinstance(stage.get("title"), str) or not stage["title"].strip():
            error(f"{stage_id}：缺少非空 title")
        if status != "passed" and first_unpassed is None:
            first_unpassed = stage_id
        elif status == "passed" and first_unpassed is not None:
            error(f"{stage_id}：不能跳过尚未通过的 {first_unpassed}")
        if status in {"active", "blocked"}:
            in_progress += 1
            if stage_id != first_unpassed:
                error(f"{stage_id}：只能在第一个未通过阶段 active/blocked")
        evidence = stage.get("evidence")
        if not isinstance(evidence, list):
            error(f"{stage_id}：evidence 必须是数组")
            evidence = []
        kinds: set[str] = set()
        for position, item in enumerate(evidence, start=1):
            context = f"{stage_id} evidence[{position}]"
            if not isinstance(item, dict):
                error(f"{context}：证据必须是对象")
                continue
            kind = item.get("kind")
            if not isinstance(kind, str) or not kind.strip():
                error(f"{context}：缺少非空 kind")
            else:
                kinds.add(kind)
            nonempty_file(item.get("path"), context)
        review_value = stage.get("gate_review")
        if status == "passed":
            review_path = nonempty_file(review_value, f"{stage_id} gate_review")
            if review_path is not None:
                review = read_text(review_path, f"{stage_id} gate_review")
                if review is not None:
                    for gate in range(1, GATES_PER_STAGE + 1):
                        gate_id = f"G{index}.{gate}"
                        if not re.search(rf"(?<![A-Za-z0-9]){re.escape(gate_id)}(?![A-Za-z0-9])", review):
                            error(f"{stage_id}：gate_review 缺少门禁 {gate_id}")
            for alternatives in EVIDENCE_KINDS[index]:
                if not kinds.intersection(alternatives):
                    error(f"{stage_id}：passed 缺少证据类别 {' 或 '.join(sorted(alternatives))}")
    if in_progress > 1:
        error("progress.json：最多允许一个 active 或 blocked 阶段")
    expected_current = first_unpassed or "complete"
    if progress.get("current_stage") != expected_current:
        error(f"progress.json：current_stage 应为 {expected_current}")


def check_traceability(documents: dict[str, str]) -> None:
    requirements = documents.get("docs/REQUIREMENTS.md")
    test_plan = documents.get("docs/TEST_PLAN.md")
    if requirements is None or test_plan is None:
        return
    requirements = without_fences(requirements)
    test_plan = without_fences(test_plan)
    expected = {f"R{number}" for number in range(15, 23)}
    headings = re.findall(r"^###\s+(R\d{2})\b[^\n]*", requirements, re.MULTILINE)
    seen: dict[str, int] = {}
    for identifier in headings:
        seen[identifier] = seen.get(identifier, 0) + 1
    for requirement_id in sorted(expected):
        if seen.get(requirement_id) != 1:
            error(f"REQUIREMENTS.md：标题 ### {requirement_id} 必须恰好出现一次")
    for identifier in sorted(set(seen) - expected):
        error(f"REQUIREMENTS.md：存在未知需求标题 {identifier}")
    test_headings = re.findall(r"^###\s+(TC-L\d{2})\b[^\n]*", test_plan, re.MULTILINE)
    if not test_headings:
        error("TEST_PLAN.md：未找到 ### TC-L01 形式的测试用例标题")
    duplicates = {item for item in test_headings if test_headings.count(item) > 1}
    if duplicates:
        error(f"TEST_PLAN.md：用例标题重复 {', '.join(sorted(duplicates))}")
    for requirement_match in re.finditer(r"^###\s+(R\d{2})\b[^\n]*", requirements, re.MULTILINE):
        following = requirements[requirement_match.end():]
        next_heading = re.search(r"^#{1,3}\s+", following, re.MULTILINE)
        section = following[:next_heading.start()] if next_heading else following
        if not TEST_ID.search(section):
            error(f"REQUIREMENTS.md：{requirement_match.group(1)} 缺少 TC 验收引用")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    print("二阶段流程结构检查（只读）：不运行应用、不连接数据库，不证明功能或测试真实性。")
    print(f"阶段目录：{ROOT.name}；公共文件目录：{SHARED_ROOT.name}")
    for name in SHARED:
        path = SHARED_ROOT / name
        if not path.is_file() or path.stat().st_size == 0:
            error(f"公共文件缺失或为空：{SHARED_ROOT.name}/{name}")
    documents: dict[str, str] = {}
    for name in REQUIRED:
        path = nonempty_file(name, "必需文件")
        if path is not None and path.suffix.lower() == ".md":
            value = read_text(path, name)
            if value is not None:
                documents[name] = value
    for name, value in documents.items():
        check_links(ROOT / name, value)
    check_traceability(documents)
    progress_path = safe_path("progress.json", "阶段状态")
    if progress_path is not None and progress_path.is_file():
        value = read_text(progress_path, "progress.json")
        if value is not None:
            try:
                progress = json.loads(value)
            except json.JSONDecodeError as exc:
                error(f"progress.json：JSON 格式错误：{exc}")
            else:
                if not isinstance(progress, dict):
                    error("progress.json：根节点必须是对象")
                else:
                    if type(progress.get("schema_version")) is not int or progress["schema_version"] != 1:
                        error("progress.json：schema_version 必须为整数 1")
                    check_source(progress)
                    check_stages(progress)
    for message in ERRORS:
        print(f"ERROR: {message}")
    for message in WARNINGS:
        print(f"WARN: {message}")
    print(f"结构检查结束：ERROR={len(ERRORS)}，WARN={len(WARNINGS)}。WARN 须在实验日志逐条解释。")
    if not ERRORS:
        print("结构检查通过；业务测试与逐条门禁仍需真实证据和人工审阅。")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    raise SystemExit(main())
