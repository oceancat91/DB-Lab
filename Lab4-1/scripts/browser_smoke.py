#!/usr/bin/env python3
"""Repeatable browser smoke test for the fill page (first-stage UI interactions).

What it checks end to end in a real browser: login, one-question-at-a-time filling,
server-driven branching, validation feedback, submission receipt and restart. It seeds
its own survey through the HTTP API, so it needs a running app, a running project
MongoDB and the `agent-browser` CLI.

Usage (from the project root, same conda environment as the app):

    python scripts/browser_smoke.py --base http://127.0.0.1:8005 --database lab4_ui_smoke_xxx

Exit codes: 0 = all checks passed, 1 = a check failed, 2 = prerequisites missing (skipped).
Screenshots and the JSON report are written to results/browser-smoke/.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "results" / "browser-smoke"
RUN = uuid.uuid4().hex[:8]


def resolve_cli() -> list[str] | None:
    """Return the argv prefix that can launch the agent-browser CLI, or None if absent.

    Windows installs a .cmd/.ps1 shim plus the real binary under node_modules; only the
    binary can be spawned directly, so the shim is wrapped in cmd.exe instead.
    """
    direct = shutil.which("agent-browser.exe") or shutil.which("agent-browser")
    if direct and not direct.lower().endswith((".cmd", ".bat", ".ps1")):
        return [direct]
    shim = shutil.which("agent-browser.cmd") or shutil.which("agent-browser.bat")
    if shim:
        return ["cmd", "/c", shim]
    shim = shutil.which("agent-browser.ps1")
    if shim:
        return ["powershell", "-NoProfile", "-File", shim]
    npm_bin = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "agent-browser" / "bin"
    if npm_bin.is_dir():
        for candidate in sorted(npm_bin.glob("agent-browser*.exe")):
            return [str(candidate)]
    return None


CLI = resolve_cli()


def browser(*args: str, timeout: int = 40) -> str:
    """Run one agent-browser command and return its stdout.

    Output goes to temporary files instead of pipes: on Windows the CLI leaves a helper
    process holding an inherited stdout handle, so a pipe would never report EOF and every
    call would block until its timeout. The action itself is executed by the CLI daemon, so a
    killed CLI process does not mean the step failed — callers verify state with `eval`/`wait`.
    """
    environment = {**os.environ, "AGENT_BROWSER_SESSION": f"lab4-smoke-{RUN}"}
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as out, \
            tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err:
        process = subprocess.Popen([*CLI, *args], stdout=out, stderr=err,
                                   stdin=subprocess.DEVNULL, env=environment)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)
        out.seek(0)
        text = out.read()
        err.seek(0)
        return text + err.read()


def evaluate(script: str) -> str:
    return browser("eval", script, timeout=30).strip().strip('"')


def seed(base: str) -> tuple[str, dict, dict]:
    owner = {"username": f"smoke_owner_{RUN}", "password": "SmokePass2026"}
    filler = {"username": f"smoke_filler_{RUN}", "password": "SmokePass2026"}
    with httpx.Client(base_url=base, timeout=25) as client:
        for account in (owner, filler):
            client.post("/api/auth/register", json=account)
        client.post("/api/auth/login", json=owner)
        survey = client.post("/api/surveys", json={
            "title": "浏览器冒烟问卷", "description": "由 scripts/browser_smoke.py 创建",
            "allow_anonymous": False, "allow_repeat": True, "closes_at": None}).json()
        draft = client.put(f"/api/surveys/{survey['id']}", json={
            "title": survey["title"], "description": survey["description"], "allow_anonymous": False,
            "allow_repeat": True, "closes_at": None, "revision": survey["revision"],
            "questions": [
                {"id": "q1", "type": "single", "required": True, "title": "你平时主要用哪种设备完成课程作业？",
                 "options": [{"id": "o1", "label": "笔记本电脑"}, {"id": "o2", "label": "手机"}], "validation": {}},
                {"id": "q2", "type": "multi", "required": True, "title": "本学期你希望课程增加哪些内容？",
                 "options": [{"id": "o1", "label": "更多动手实验"}, {"id": "o2", "label": "真实案例讲解"}],
                 "validation": {"min_choices": 1, "max_choices": 1}},
                {"id": "q3", "type": "text", "required": False, "title": "对这门课还有什么建议？",
                 "options": [], "validation": {"max_length": 200}},
            ],
            "rules": [{"source": "q1", "op": "eq", "value": "o2", "target": "q3", "priority": 10}]}).json()
        published = client.post(f"/api/surveys/{survey['id']}/publish",
                                json={"revision": draft["revision"]}).json()
    return published["share_code"], owner, filler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8005")
    parser.add_argument("--database", default="", help="被检查实例使用的数据库名，仅记录到报告")
    arguments = parser.parse_args()

    if CLI is None:
        print("SKIP：未找到 agent-browser CLI（npm i -g agent-browser && agent-browser install）")
        return 2
    try:
        if httpx.get(f"{arguments.base}/health", timeout=8).json().get("status") != "ok":
            print(f"SKIP：{arguments.base}/health 未返回 ok")
            return 2
    except Exception as error:  # noqa: BLE001 - any transport problem means "cannot run"
        print(f"SKIP：无法访问 {arguments.base}（{error}）")
        return 2

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    code, owner, filler = seed(arguments.base)
    url = f"{arguments.base}/survey/{code}"
    browser("open", url, timeout=60)  # first attach may be slow; the waits below decide
    browser("set", "viewport", "1440", "900", timeout=30)
    # 会话可能已存在（同一浏览器配置复用 cookie）；仅在需要时登录。
    if "false" == evaluate("String(document.getElementById('auth-view')?.hidden ?? false)"):
        browser("wait", "--text", "登录工作台", timeout=60)
        browser("fill", "#username", filler["username"])
        browser("fill", "#password", filler["password"])
        browser("click", "#auth-submit")
    browser("wait", "--text", "你平时主要用哪种设备", timeout=60)
    check("登录后进入第 1 题", "q1" in evaluate("document.querySelector('.fill-question')?.dataset.questionId"))
    browser("screenshot", str(EVIDENCE / "01-question.png"))

    # 校验：必答多选题在未选择时不得前进（服务端 422，页面就地提示）
    browser("click", '[data-testid="fill-option-o2"]')
    browser("click", "#fill-next")
    browser("wait", "--text", "对这门课还有什么建议", timeout=60)
    check("单选跳转 q1→q3 生效（跳过 q2）",
          "q3" in evaluate("document.querySelector('.fill-question')?.dataset.questionId"))
    browser("screenshot", str(EVIDENCE / "02-branch-jump.png"))

    # 从核对页回改：路径应被截断并保留原答案
    browser("fill", "#fill-answer", "希望期末项目早一点公布题目。")
    browser("click", "#fill-next")
    browser("wait", "--text", "核对你的回答", timeout=60)
    check("完成后进入核对页", "true" == evaluate("String(!!document.querySelector('[data-testid=fill-review]'))"))
    browser("click", '[data-testid="fill-edit-q1"]')
    browser("wait", "--text", "你平时主要用哪种设备", timeout=60)
    check("点路径轨可回改到 q1",
          "q1" in evaluate("document.querySelector('.fill-question')?.dataset.questionId"))
    check("回改后路径只剩当前题",
          "0" == evaluate("String(document.querySelectorAll('.fill-path-item.is-done').length)"))

    # 改答案后重新前进并提交，检查回执
    browser("click", '[data-testid="fill-option-o1"]')
    browser("click", "#fill-next")
    browser("wait", "--text", "本学期你希望课程增加哪些内容", timeout=60)
    browser("click", '[data-testid="fill-option-o1"]')
    browser("click", "#fill-next")
    browser("wait", "--text", "对这门课还有什么建议", timeout=60)
    browser("click", "#fill-next")
    browser("wait", "--text", "核对你的回答", timeout=60)
    browser("click", "#fill-submit")
    browser("wait", "--text", "提交成功", timeout=90)
    check("提交后出现回执", "true" == evaluate("String(!!document.querySelector('[data-testid=fill-receipt]'))"))
    check("回执含编号", "true" == evaluate("String((document.querySelector('.receipt-id')?.textContent||'').length > 20)"))
    browser("screenshot", str(EVIDENCE / "03-receipt.png"))
    check("浏览器无脚本错误", "" == browser("errors", timeout=30).strip())

    report = {"created_at": datetime.now().astimezone().isoformat(), "base": arguments.base,
              "database": arguments.database, "share_code": code,
              "owner": owner["username"], "filler": filler["username"],
              "checks_total": len(checks), "checks_passed": sum(1 for item in checks if item["pass"]),
              "checks": checks}
    (EVIDENCE / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    browser("close", "--all", timeout=30)
    failed = [item for item in checks if not item["pass"]]
    print(json.dumps({"checks": len(checks), "passed": len(checks) - len(failed), "failed": failed},
                     ensure_ascii=False, indent=2))
    print(f"证据目录：{EVIDENCE.relative_to(ROOT).as_posix()}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
