#!/usr/bin/env node
/**
 * Print an HTML file to PDF through the DevTools protocol with an explicit scale of 1.
 *
 * The Chrome CLI silently shrinks content when it decides the page does not fit, which made the
 * stage-2 report render at two thirds of the intended size. Printing through Page.printToPDF with
 * preferCSSPageSize keeps the CSS millimetres exact.
 *
 * Usage: node scripts/print_pdf.mjs --html report.html --output report.pdf [--chrome <path>]
 */
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const args = process.argv.slice(2);
const argValue = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const HTML = resolve(argValue("--html", ""));
const OUTPUT = resolve(argValue("--output", ""));
const CHROME = argValue("--chrome", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe");
const PORT = 9600 + Math.floor(Math.random() * 200);
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

if (!HTML || !OUTPUT) {
  console.error("用法：node scripts/print_pdf.mjs --html report.html --output report.pdf");
  process.exit(2);
}
if (!existsSync(HTML)) {
  console.error(`HTML 不存在：${HTML}`);
  process.exit(2);
}
if (!existsSync(CHROME)) {
  console.error(`找不到 Chrome：${CHROME}`);
  process.exit(2);
}

async function waitForJson(url, attempts = 80) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch { /* not ready */ }
    await sleep(250);
  }
  throw new Error(`等待 ${url} 超时`);
}

class Cdp {
  constructor(url) { this.url = url; this.nextId = 1; this.pending = new Map(); }
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
      }
    });
  }
  send(method, params = {}) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((done, fail) => this.pending.set(id, { resolve: done, reject: fail }));
  }
  close() { try { this.ws.close(); } catch { /* ignore */ } }
}

const profile = mkdtempSync(join(tmpdir(), "lab4-print-"));
const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "about:blank",
], { stdio: "ignore" });

try {
  await waitForJson(`http://127.0.0.1:${PORT}/json/version`);
  const targets = await waitForJson(`http://127.0.0.1:${PORT}/json/list`);
  const page = targets.find((target) => target.type === "page");
  if (!page) throw new Error("没有可用的页面目标");
  const cdp = new Cdp(page.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send("Page.enable");
  const loaded = new Promise((done) => setTimeout(done, 1500));
  await cdp.send("Page.navigate", { url: pathToFileURL(HTML).href });
  await loaded;
  const printed = await cdp.send("Page.printToPDF", {
    printBackground: true,
    preferCSSPageSize: true,
    scale: 1,
    marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0,
  });
  writeFileSync(OUTPUT, Buffer.from(printed.data, "base64"));
  cdp.close();
  const bytes = readFileSync(OUTPUT).length;
  console.log(`PDF：${OUTPUT}（${bytes} 字节，scale=1）`);
} finally {
  chrome.kill();
}
