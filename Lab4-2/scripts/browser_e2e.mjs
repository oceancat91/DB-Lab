#!/usr/bin/env node
/**
 * Real-browser check of the whole question-library flow, driven through the Chrome DevTools Protocol.
 *
 * No npm dependencies: Node 24 ships fetch and WebSocket. Steps:
 *   1. launch headless Chrome with a throw-away profile
 *   2. register + log in from inside the page (cookies stay in the browser)
 *   3. create a question through the real form, open its detail, open the statistics panel
 *   4. prepare a second version, a bank item pinned to v1, a draft survey and a second user
 *   5. click the four actions that were previously only covered by HTTP tests:
 *      restore an old version, share the question, update the bank pin, add it to a draft survey
 *
 * Usage: node scripts/browser_e2e.mjs [--base http://127.0.0.1:8012] [--output results/stage2/browser]
 */
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const args = process.argv.slice(2);
const argValue = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const BASE = argValue("--base", "http://127.0.0.1:8012");
const OUTPUT = resolve(ROOT, argValue("--output", "results/stage2/browser"));
const CHROME = argValue("--chrome", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe");
const PORT = 9400 + Math.floor(Math.random() * 150);
const steps = [];

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

function record(name, ok, detail) {
  steps.push({ step: name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? " :: " + detail : ""}`);
}

async function waitForHttp(url, attempts = 60) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch { /* not up yet */ }
    await sleep(250);
  }
  throw new Error(`timed out waiting for ${url}`);
}

class Cdp {
  constructor(url) {
    this.url = url;
    this.nextId = 1;
    this.pending = new Map();
    this.loaded = null;
  }
  async open() {
    this.ws = new WebSocket(this.url);
    await new Promise((done, fail) => {
      this.ws.addEventListener("open", done, { once: true });
      this.ws.addEventListener("error", fail, { once: true });
    });
    this.ws.addEventListener("message", async (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve: done, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        message.error ? reject(new Error(JSON.stringify(message.error))) : done(message.result);
      } else if (message.method === "Page.javascriptDialogOpening") {
        // The page uses alert() on failures; accept it so the script can report the real state.
        await this.send("Page.handleJavaScriptDialog", { accept: true });
      } else if (message.method === "Page.loadEventFired" && this.loaded) {
        const done = this.loaded;
        this.loaded = null;
        done();
      }
    });
  }
  send(method, params = {}) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((done, fail) => this.pending.set(id, { resolve: done, reject: fail }));
  }
  waitForLoad(timeout = 15000) {
    return new Promise((done, fail) => {
      const timer = setTimeout(() => fail(new Error("page load timed out")), timeout);
      this.loaded = () => { clearTimeout(timer); done(); };
    });
  }
  async goto(url) {
    const loaded = this.waitForLoad();
    await this.send("Page.navigate", { url });
    await loaded;
  }
  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression, awaitPromise: true, returnByValue: true, userGesture: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description || "page script threw");
    }
    return result.result.value;
  }
  async waitFor(condition, timeout = 10000) {
    return this.evaluate(`new Promise((done) => {
      const started = Date.now();
      const timer = setInterval(() => {
        let value = null;
        try { value = (${condition})(); } catch (error) { value = null; }
        if (value) { clearInterval(timer); done(value); }
        else if (Date.now() - started > ${timeout}) { clearInterval(timer); done(null); }
      }, 100);
    })`);
  }
  async screenshot(path) {
    const shot = await this.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(path, Buffer.from(shot.data, "base64"));
  }
  close() { try { this.ws.close(); } catch { /* ignore */ } }
}

async function main() {
  if (!existsSync(CHROME)) throw new Error(`Chrome not found: ${CHROME}`);
  mkdirSync(OUTPUT, { recursive: true });
  const profile = mkdtempSync(join(tmpdir(), "lab4-cdp-"));
  const chrome = spawn(CHROME, [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--window-size=1280,900",
    "about:blank",
  ], { stdio: "ignore" });

  let cdp;
  try {
    await waitForHttp(`http://127.0.0.1:${PORT}/json/version`);
    const targets = await waitForHttp(`http://127.0.0.1:${PORT}/json/list`);
    const page = targets.find((target) => target.type === "page");
    if (!page) throw new Error("no page target");
    cdp = new Cdp(page.webSocketDebuggerUrl);
    await cdp.open();
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");

    const stamp = Date.now().toString(36);
    const owner = `ui_owner_${stamp}`;
    const mate = `ui_mate_${stamp}`;
    await cdp.goto(`${BASE}/`);
    const accounts = await cdp.evaluate(`(async () => {
      const call = (path, body) => fetch(path, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const owner = await call('/api/auth/register', { username: ${JSON.stringify(owner)}, password: 'Lab4pass123!' });
      const mate = await call('/api/auth/register', { username: ${JSON.stringify(mate)}, password: 'Lab4pass123!' });
      const login = await call('/api/auth/login', { username: ${JSON.stringify(owner)}, password: 'Lab4pass123!' });
      return { owner: owner.status, mate: mate.status, login: login.status };
    })()`);
    record("页面内注册两个账号并登录", accounts.owner === 201 && accounts.mate === 201 && accounts.login === 200,
           JSON.stringify(accounts));

    await cdp.goto(`${BASE}/library`);
    record("登录后进入题目库", (await cdp.waitFor(() => !document.getElementById("library-body").hidden)) === true);
    await cdp.screenshot(join(OUTPUT, "01-library.png"));

    const filled = await cdp.evaluate(`(() => {
      document.getElementById('question-title').value = '浏览器验证题';
      const rows = document.querySelectorAll('#option-list .option-row input');
      rows[0].value = '18-25'; rows[0].dispatchEvent(new Event('input', { bubbles: true }));
      rows[1].value = '26-35'; rows[1].dispatchEvent(new Event('input', { bubbles: true }));
      document.getElementById('question-submit').click();
      return rows.length;
    })()`);
    record("填写并提交新建题目表单", filled === 2, `option rows=${filled}`);
    const listed = await cdp.waitFor(() =>
      [...document.querySelectorAll(".question-card .title")].map((node) => node.textContent)
        .includes("浏览器验证题") && "浏览器验证题");
    record("新题目出现在列表中", listed === "浏览器验证题", String(listed));

    record("点击题目打开详情与版本历史", (await cdp.waitFor(() => {
      document.querySelector(".question-card").click();
      const detail = document.getElementById("detail");
      return !detail.hidden && detail.textContent.includes("版本历史");
    })) === true);
    await cdp.screenshot(join(OUTPUT, "02-detail.png"));

    record("跨问卷统计面板可打开", (await cdp.evaluate(`(async () => {
      const button = [...document.querySelectorAll('#detail button')]
        .find((node) => node.textContent.includes('跨问卷统计'));
      if (!button) return 'NO_BUTTON';
      button.click();
      const started = Date.now();
      while (Date.now() - started < 10000) {
        const panel = document.getElementById('stats-panel');
        if (!panel.hidden && panel.textContent.includes('跨问卷统计')) return 'OK';
        await new Promise((done) => setTimeout(done, 100));
      }
      return 'TIMEOUT';
    })()`)) === "OK");
    await cdp.screenshot(join(OUTPUT, "03-statistics.png"));

    /* --- prepare the state the four action buttons need ----------------------------- */
    const prepared = await cdp.evaluate(`(async () => {
      const get = async (path) => (await fetch(path)).json();
      const send = async (method, path, body) => (await fetch(path, { method,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })).json();
      const mine = await get('/api/questions');
      const question = mine.find((item) => item.title === '浏览器验证题');
      const version2 = await send('POST', '/api/questions/' + question.id + '/versions',
        { type: 'single', title: '浏览器验证题（v2）', required: true,
          options: [{ id: 'a', label: '18-25' }, { id: 'b', label: '26-35' }, { id: 'c', label: '36 以上' }],
          validation: {}, note: '浏览器验证：生成第二版' });
      const bank = await send('POST', '/api/banks', { name: '浏览器题库', description: '' });
      await send('POST', '/api/banks/' + bank.id + '/items', { question_id: question.id, version: 1 });
      const survey = await send('POST', '/api/surveys', { title: '浏览器草稿问卷', description: '',
        allow_anonymous: true, allow_repeat: true, closes_at: null });
      return { question: question.id, version2: version2.current_version, bank: bank.id, survey: survey.id };
    })()`);
    record("准备第二版、题库与草稿问卷", Boolean(prepared.question && prepared.bank && prepared.survey),
           JSON.stringify(prepared));

    await cdp.goto(`${BASE}/library`);
    await cdp.waitFor(() => !document.getElementById("library-body").hidden);
    await cdp.waitFor(() => {
      document.querySelector(".question-card").click();
      return !document.getElementById("detail").hidden;
    });

    record("点击“恢复此版本”", (await cdp.evaluate(`(async () => {
      const button = [...document.querySelectorAll('#detail button')]
        .find((node) => node.textContent === '恢复此版本');
      if (!button) return 'NO_BUTTON';
      button.click();
      const started = Date.now();
      while (Date.now() - started < 10000) {
        const text = document.getElementById('detail').textContent;
        if (text.includes('恢复自 v1')) return 'OK';
        await new Promise((done) => setTimeout(done, 100));
      }
      return 'TIMEOUT';
    })()`)) === "OK");
    await cdp.screenshot(join(OUTPUT, "04-restored.png"));

    record("提交共享表单", (await cdp.evaluate(`(async () => {
      const input = [...document.querySelectorAll('#detail input')]
        .find((node) => node.placeholder === '对方用户名');
      const button = [...document.querySelectorAll('#detail button')]
        .find((node) => node.textContent === '共享');
      if (!input || !button) return 'NO_CONTROLS';
      input.value = ${JSON.stringify(mate)};
      button.click();
      const started = Date.now();
      while (Date.now() - started < 10000) {
        if (document.getElementById('detail').textContent.includes(${JSON.stringify(mate)})) return 'OK';
        await new Promise((done) => setTimeout(done, 100));
      }
      return 'TIMEOUT';
    })()`)) === "OK");
    await cdp.screenshot(join(OUTPUT, "05-shared.png"));

    record("题库“更新版本”", (await cdp.evaluate(`(async () => {
      const button = [...document.querySelectorAll('#bank-list button')]
        .find((node) => node.textContent === '更新版本');
      if (!button) return 'NO_BUTTON';
      button.click();
      const started = Date.now();
      while (Date.now() - started < 10000) {
        const labels = [...document.querySelectorAll('#bank-list .badge')].map((node) => node.textContent);
        if (!labels.some((text) => text.includes('→'))) return 'OK';
        await new Promise((done) => setTimeout(done, 100));
      }
      return 'TIMEOUT';
    })()`)) === "OK");
    await cdp.screenshot(join(OUTPUT, "06-bank-updated.png"));

    record("从题库/题目加入草稿问卷", (await cdp.evaluate(`(async () => {
      const selects = [...document.querySelectorAll('#detail select')];
      const button = [...document.querySelectorAll('#detail button')]
        .find((node) => node.textContent === '加入问卷');
      if (selects.length < 2 || !button) return 'NO_CONTROLS';
      selects[0].selectedIndex = 0;
      selects[1].selectedIndex = 0;
      button.click();
      const started = Date.now();
      while (Date.now() - started < 10000) {
        const text = document.getElementById('detail').textContent;
        if (text.includes('草稿') && text.includes('加入我的草稿问卷')) return 'OK';
        await new Promise((done) => setTimeout(done, 100));
      }
      return 'TIMEOUT';
    })()`)) === "OK");
    await cdp.screenshot(join(OUTPUT, "07-added-to-survey.png"));

    record("页面脚本无未捕获异常", (await cdp.evaluate(`window.__lab4Errors || 0`)) === 0);
  } finally {
    cdp?.close();
    chrome.kill();
  }

  const failed = steps.filter((step) => !step.ok);
  const report = {
    generated_at: new Date().toISOString(),
    base: BASE,
    chrome: CHROME,
    screenshots: ["01-library.png", "02-detail.png", "03-statistics.png", "04-restored.png",
                  "05-shared.png", "06-bank-updated.png", "07-added-to-survey.png"],
    steps,
    passed: steps.length - failed.length,
    failed: failed.length,
    status: failed.length === 0 ? "PASS" : "FAIL",
  };
  writeFileSync(join(OUTPUT, "report.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
  console.log(JSON.stringify({ status: report.status, passed: report.passed, failed: report.failed }));
  process.exit(failed.length === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error(`browser check failed: ${error.message}`);
  process.exit(1);
});
