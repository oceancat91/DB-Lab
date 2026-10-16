#!/usr/bin/env python3
"""Build the stage-1 completion report PDF from docs/REPORT_STAGE1.md.

Pipeline: Markdown -> print-ready HTML (cover page + table of contents) -> PDF via headless
Chrome. Chrome is the only external prerequisite; when it is missing the script exits with
code 2 and prints why instead of producing an incomplete file.

    python scripts/build_report_pdf.py                      # -> dist/Lab4-stage1-report.pdf
    python scripts/build_report_pdf.py --output D:\\report.pdf

The PDF is a build artefact: it is not tracked in git, so regenerate it after editing the
report. The cover page leaves name and student-id blank for the author to fill in.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "REPORT_STAGE1.md"
WORKDIR = ROOT / ".runtime" / "report_pdf"
DEFAULT_OUTPUT = ROOT / "dist" / "Lab4-stage1-report.pdf"
CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]

STYLE = """
@page { size: A4; margin: 18mm 17mm 18mm 17mm; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Microsoft YaHei", "Microsoft YaHei UI", "PingFang SC", sans-serif;
       font-size: 10pt; line-height: 1.62; color: #1b2422; }
h1 { font-size: 19pt; line-height: 1.45; margin: 0 0 5mm; }
h2 { font-size: 13pt; margin: 6.5mm 0 2mm; padding-bottom: 1.2mm; border-bottom: 0.6pt solid #cfd6d0;
     break-after: avoid; }
h3 { font-size: 11pt; margin: 4mm 0 1.5mm; break-after: avoid; }
p { margin: 0 0 2mm; text-align: justify; }
ul, ol { margin: 0 0 2mm; padding-left: 6mm; }
li { margin-bottom: 0.8mm; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9pt;
       background: #f2f4f2; padding: 0.2mm 0.7mm; border-radius: 1mm; }
pre { background: #f6f8f6; border: 0.5pt solid #dde3de; border-radius: 1mm; padding: 2mm;
      font-size: 8.5pt; line-height: 1.45; white-space: pre-wrap; break-inside: avoid; }
table { width: 100%; border-collapse: collapse; margin: 1.5mm 0 3mm; font-size: 8.8pt; break-inside: avoid; }
th, td { border: 0.5pt solid #cfd6d0; padding: 1mm 1.6mm; vertical-align: top; text-align: left;
         line-height: 1.5; }
th { background: #eef2ef; font-weight: 600; }
blockquote { margin: 1.5mm 0; padding: 0.8mm 0 0.8mm 3mm; border-left: 1pt solid #b9cec8; color: #56615e; }
hr { border: 0; border-top: 0.5pt solid #cfd6d0; margin: 4mm 0; }
a { color: #14514a; text-decoration: none; }
a.ext::after { content: " (" attr(href) ")"; font-size: 8pt; color: #6b7671; }
.cover { height: 251mm; display: flex; flex-direction: column; justify-content: center; break-after: page; }
.cover .kicker { font-size: 11pt; color: #56615e; letter-spacing: 0.28em; margin-bottom: 6mm; }
.cover h1 { font-size: 25pt; }
.cover .rule { width: 34mm; height: 1.2mm; background: #1d6b5e; margin: 7mm 0 8mm; }
.cover .meta { font-size: 11pt; line-height: 2.1; }
.cover .meta b { display: inline-block; width: 22mm; font-weight: 600; color: #56615e; }
.cover .fill { display: inline-block; min-width: 46mm; border-bottom: 0.6pt solid #8f9a95; }
.cover .note { margin-top: 10mm; font-size: 9.5pt; color: #6b7671; max-width: 120mm; }
.toc { break-after: page; }
.toc h2 { border: 0; margin-top: 0; }
.toc ol { list-style: none; padding-left: 0; font-size: 10.5pt; }
.toc li { margin-bottom: 1.8mm; }
.toc .num { display: inline-block; width: 9mm; color: #56615e; }
"""


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", text)

    def link(match: re.Match) -> str:
        label, target = match.group(1), match.group(2)
        if re.match(r"^https?://", target):
            return f'<a class="ext" href="{html.escape(target, quote=True)}">{label}</a>'
        return label  # internal references print as their file name

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    return re.sub(r"\*\*([^*]+)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", text)


def convert(markdown: str, name: str = "", student_id: str = "") -> str:
    lines = markdown.splitlines()
    body: list[str] = []
    headings: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()

        if stripped.startswith("```"):
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            body.append("<pre>" + html.escape("\n".join(block)) + "</pre>")
            index += 1
            continue

        if re.match(r"^#{1,4} ", stripped):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped[level + 1:].strip()
            if level == 1:
                index += 1
                continue  # the title already appears on the cover page
            headings.append((level, text))
            body.append(f"<h{level}>{inline(text)}</h{level}>")
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[index + 1].strip()):
            header = [cell.strip() for cell in stripped.strip("|").split("|")]
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            table = ["<table><thead><tr>", "".join(f"<th>{inline(cell)}</th>" for cell in header),
                     "</tr></thead><tbody>"]
            for row in rows:
                table.append("<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>")
            table.append("</tbody></table>")
            body.append("".join(table))
            continue

        if re.match(r"^\s*[-*] ", lines[index]):
            items = []
            while index < len(lines) and re.match(r"^\s*[-*] ", lines[index]):
                items.append(re.sub(r"^\s*[-*] ", "", lines[index]).strip())
                index += 1
            body.append("<ul>" + "".join(f"<li>{inline(item)}</li>" for item in items) + "</ul>")
            continue

        if re.match(r"^\s*\d+\. ", lines[index]):
            items = []
            while index < len(lines) and re.match(r"^\s*\d+\. ", lines[index]):
                items.append(re.sub(r"^\s*\d+\. ", "", lines[index]).strip())
                index += 1
            body.append("<ol>" + "".join(f"<li>{inline(item)}</li>" for item in items) + "</ol>")
            continue

        if stripped.startswith("> "):
            body.append(f"<blockquote>{inline(stripped[2:].strip())}</blockquote>")
            index += 1
            continue

        if stripped in {"---", "***", "___"}:
            body.append("<hr>")
            index += 1
            continue

        if not stripped:
            index += 1
            continue

        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip() and not re.match(
                r"^(#{1,4} |\s*[-*] |\s*\d+\. |\||> |```|---$)", lines[index].strip()):
            paragraph.append(lines[index].strip())
            index += 1
        body.append("<p>" + inline(" ".join(paragraph)) + "</p>")

    toc_items = "".join(
        f'<li><span class="num">'
        f'{html.escape(text.split(".")[0]) if text[:1].isdigit() else ""}</span>'
        f'{inline(text.split(". ", 1)[-1])}</li>'
        for level, text in headings if level == 2 and text != "目录")
    blank = '<span class="fill"></span>'
    author_fields = "".join(
        f'<div><b>{label}</b>{html.escape(value) if value else blank}</div>'
        for label, value in (("姓名", name), ("学号", student_id)))
    cover = f"""
<section class="cover">
  <div class="kicker">数据库管理系统 · 大作业一</div>
  <h1>MongoDB 在线问卷系统<br>第一阶段项目完成报告</h1>
  <div class="rule"></div>
  <div class="meta">
    <div><b>课程</b>数据库管理系统</div>
    <div><b>项目</b>基于 MongoDB 的问卷系统开发（第一阶段）</div>
    {author_fields}
    <div><b>日期</b>2026 年 10 月 16 日</div>
  </div>
  <div class="note">本报告对应《大作业一第一阶段》“七、提交内容”第 4 项，覆盖项目目标、系统设计、MongoDB 设计、跳转设计、校验设计、AI 使用过程、测试结果、遇到的问题及解决办法。</div>
</section>
"""
    toc = f'<section class="toc"><h2>目录</h2><ol>{toc_items}</ol></section>'
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            f"<title>MongoDB 在线问卷系统第一阶段项目完成报告</title>"
            f"<style>{STYLE}</style></head><body>{cover}{toc}{''.join(body)}</body></html>")


def chrome() -> Path | None:
    for candidate in CHROME_CANDIDATES:
        if candidate.is_file():
            return candidate
    for name in ("chrome", "chrome.exe", "msedge"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(SOURCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--name", default="", help="封面姓名；留空则打印空白填写行（不写入仓库）")
    parser.add_argument("--student-id", default="", help="封面学号；留空则打印空白填写行（不写入仓库）")
    arguments = parser.parse_args()

    source, output = Path(arguments.source), Path(arguments.output)
    if not source.is_file():
        print(f"源报告不存在：{source}")
        return 1
    binary = chrome()
    if binary is None:
        print("SKIP：未找到 Chrome/Edge，无法打印 PDF；本脚本不生成替代文件")
        return 2

    WORKDIR.mkdir(parents=True, exist_ok=True)
    page = WORKDIR / "report.html"
    page.write_text(convert(source.read_text(encoding="utf-8"), arguments.name, arguments.student_id),
                    encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [str(binary), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
               "--virtual-time-budget=4000", "--run-all-compositor-stages-before-draw",
               f"--print-to-pdf={output}", page.resolve().as_uri()]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not output.is_file() or output.stat().st_size == 0:
        print("PDF 生成失败；Chrome 输出：")
        print((completed.stdout or "")[-800:])
        print((completed.stderr or "")[-800:])
        return 1
    print(f"源：{source}")
    print(f"HTML：{page}")
    print(f"PDF：{output}（{output.stat().st_size} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
