#!/usr/bin/env node
/**
 * Real-browser check of the question-library page, driven through the Chrome DevTools Protocol.
 *
 * No npm dependencies: Node 24 ships fetch and WebSocket. Steps:
 *   1. launch headless Chrome with a throw-away profile
 *   2. register + log in from inside the page (cookies stay in the browser)
 *   3. open /library, fill the real form and click its submit button (library.js handles it)
 *   4. assert the new question shows up, open its detail panel, capture screenshots
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
const PORT = 9333 + Math.floor(Math.random() * 200);
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
    this.ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve: done, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        message.error ? reject(new Error(JSON.stringify(message.error))) : done(message.result);
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

    const username = `ui_${Date.now().toString(36)}`;
    await cdp.goto(`${BASE}/`);
    const registered = await cdp.evaluate(`(async () => {
      const call = (path, body) => fetch(path, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const created = await call('/api/auth/register', { username: ${JSON.stringify(username)}, password: 'Lab4pass123!' });
      const logged = await call('/api/auth/login', { username: ${JSON.stringify(username)}, password: 'Lab4pass123!' });
      return { created: created.status, logged: logged.status };
    })()`);
    record("页面内注册与登录", registered.created === 201 && registered.logged === 200, JSON.stringify(registered));

    await cdp.goto(`${BASE}/library`);
    const ready = await cdp.evaluate(`new Promise((done) => {
      const started = Date.now();
      const timer = setInterval(() => {
        if (!document.getElementById('library-body').hidden) { clearInterval(timer); done(true); }
        else if (Date.now() - started > 10000) { clearInterval(timer); done(false); }
      }, 100);
    })`);
    record("登录后进入题目库", ready === true);
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

    const listed = await cdp.evaluate(`new Promise((done) => {
      const started = Date.now();
      const timer = setInterval(() => {
        const cards = [...document.querySelectorAll('.question-card .title')].map((node) => node.textContent);
        if (cards.includes('浏览器验证题')) { clearInterval(timer); done(cards.join('|')); }
        else if (Date.now() - started > 10000) { clearInterval(timer); done('TIMEOUT:' + cards.join('|')); }
      }, 100);
    })`);
    record("新题目出现在列表中", listed.includes("浏览器验证题"), listed);

    const opened = await cdp.evaluate(`new Promise((done) => {
      document.querySelector('.question-card').click();
      const started = Date.now();
      const timer = setInterval(() => {
        const detail = document.getElementById('detail');
        if (!detail.hidden && detail.textContent.includes('版本历史')) { clearInterval(timer); done(true); }
        else if (Date.now() - started > 10000) { clearInterval(timer); done(false); }
      }, 100);
    })`);
    record("点击题目打开详情与版本历史", opened === true);
    await cdp.screenshot(join(OUTPUT, "02-detail.png"));

    const stats = await cdp.evaluate(`(async () => {
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
    })()`);
    record("跨问卷统计面板可打开", stats === "OK", stats);
    await cdp.screenshot(join(OUTPUT, "03-statistics.png"));

    const errors = await cdp.evaluate(`window.__lab4Errors || 0`);
    record("页面脚本无未捕获异常", !errors, String(errors));
  } finally {
    cdp?.close();
    chrome.kill();
  }

  const failed = steps.filter((step) => !step.ok);
  const report = {
    generated_at: new Date().toISOString(),
    base: BASE,
    chrome: CHROME,
    screenshots: ["01-library.png", "02-detail.png", "03-statistics.png"],
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
