#!/usr/bin/env python3
"""Build the report PDF from the generated DOCX, so both stages share one deterministic layout.

Chrome's print pipeline scaled one report to two thirds and paginated differently per content;
LibreOffice renders the DOCX we control (A4, fixed margins, point sizes) and keeps the two stages
byte-comparably consistent. Node + the bundled LibreOffice Kit must be available.

    python scripts/build_report_pdf_from_docx.py --node <node.exe> --name 姓名 --student-id 学号
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="")
    parser.add_argument("--student-id", default="")
    parser.add_argument("--node", default="", help="Node 可执行文件")
    parser.add_argument("--cli", default="", help="libreoffice-kit 的 cli.js 路径")
    parser.add_argument("--output", default=str(ROOT / "dist" / "report.pdf"))
    arguments = parser.parse_args()

    node = arguments.node or shutil.which("node") or ""
    cli = arguments.cli
    if not cli:
        print("缺少 --cli（libreoffice-kit 的 cli.js）", file=sys.stderr)
        return 2
    if not node:
        print("缺少 --node（Node 可执行文件）", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="lab4-docx-") as workspace:
        docx = Path(workspace) / "report.docx"
        built = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_report_docx.py"),
             "--name", arguments.name, "--student-id", arguments.student_id,
             "--output", str(docx)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not docx.is_file():
            print("DOCX 生成失败：\n" + (built.stdout or "")[-500:] + (built.stderr or "")[-500:],
                  file=sys.stderr)
            return 1
        output = Path(arguments.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        converted = subprocess.run(
            [node, cli, "convert", "--input", str(docx), "--output", str(output)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not output.is_file() or output.stat().st_size == 0:
            print("PDF 转换失败：\n" + (converted.stdout or "")[-500:] + (converted.stderr or "")[-500:],
                  file=sys.stderr)
            return 1
    print(f"PDF：{output}（{output.stat().st_size} 字节，由 DOCX 转换）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
