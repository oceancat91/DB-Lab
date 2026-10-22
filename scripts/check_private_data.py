#!/usr/bin/env python3
"""Scan tracked files for personal data and secret-like patterns.

History is intentionally not rewritten (see Lab4-2/docs/DECISIONS.md D21); this guard keeps the
current tree clean instead. Add names to scan for in an untracked `Lab4/.private-names` file
(one per line) so the names themselves never enter the repository.

    python scripts/check_private_data.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # Lab4/
NAMES_FILE = ROOT / ".private-names"
SKIP_PARTS = {".git", ".runtime", "dist", "__pycache__", ".pytest_cache"}
PATTERNS = {
    # Hex strings (uuid4().hex, digests) must not look like an 11-digit id.
    "学生证号样式（11 位、以 1 开头）": re.compile(r"(?<![0-9a-fA-F])1\d{10}(?![0-9a-fA-F])"),
    "私钥": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "OpenAI 风格密钥": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "会话密钥赋值": re.compile(r"SESSION_SECRET\s*=\s*(?!replace-with)[A-Za-z0-9/+_-]{16,}"),
    "导出文件名前缀": re.compile(r"2026_ECNU_"),
    "Office 锁文件": re.compile(r"~\$[^/\\\s]+"),
}
# Ignore rules quote these patterns on purpose; they are not evidence of a leak.
SKIP_NAMES = {".gitignore", ".gitattributes", ".private-names"}


def tracked_files() -> list[Path]:
    try:
        output = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True,
                                check=True).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.CalledProcessError):
        # Fall back to a bounded tree walk when git is unavailable.
        return [path for path in ROOT.rglob("*")
                if path.is_file() and not any(part in SKIP_PARTS for part in path.parts)]
    return [ROOT / name for name in output.split("\0") if name]


def names() -> list[str]:
    if not NAMES_FILE.is_file():
        return []
    return [line.strip() for line in NAMES_FILE.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.startswith("#")]


def main() -> int:
    files = tracked_files()
    hits: list[str] = []
    needles = names()
    for path in files:
        if any(part in SKIP_PARTS for part in path.parts) or not path.is_file():
            continue
        if path.name in SKIP_NAMES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = path.relative_to(ROOT).as_posix()
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                hits.append(f"{relative}: {label}: {match.group(0)[:40]}")
        for needle in needles:
            if needle in text:
                hits.append(f"{relative}: 出现 .private-names 中登记的词")
    print(f"扫描受控文件 {len(files)} 个；登记姓名 {len(needles)} 个；命中 {len(hits)} 处")
    for hit in hits[:20]:
        print("  !", hit)
    if hits:
        print("请先清理这些命中再提交；本脚本只读，不会修改文件。")
        return 1
    print("未发现个人资料或凭据样式字符串。历史不在此检查范围内（见 DECISIONS D21）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
