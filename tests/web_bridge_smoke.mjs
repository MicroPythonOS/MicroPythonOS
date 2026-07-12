// Headless smoke test for the web build's _webterm stdio bridge.
//
// Serves the built web/ export, loads shell.html in headless Chromium,
// installs Module.__webterm.onOutput, sends the raw-REPL handshake
// (\r + Ctrl-A) and asserts that:
//   1. output bytes arrive at onOutput at all (mirror alive), and
//   2. the standard banner "raw REPL; CTRL-B to exit\r\n" appears with CRLF
//      line endings, so stock raw-REPL clients (mpremote, ViperIDE) match it.
//
// Usage: node tests/web_bridge_smoke.mjs [web-dir]   (default: ./web)
// Requires: npm install puppeteer

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer";

const webDir = path.resolve(process.argv[2] || "web");
const TIMEOUT_MS = 120000; // wasm boot in CI can be slow

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".wasm": "application/wasm",
  ".data": "application/octet-stream",
  ".map": "application/json",
};

const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, "http://x").pathname);
  let file = path.join(webDir, rel === "/" ? "index.html" : rel);
  if (!file.startsWith(webDir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404).end("not found");
    return;
  }
  res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});

function fail(msg) {
  console.error("FAIL: " + msg);
  process.exit(1);
}

server.listen(0, "127.0.0.1", async () => {
  const url = `http://127.0.0.1:${server.address().port}/index.html`;
  console.log("Serving " + webDir + " at " + url);

  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const timer = setTimeout(() => fail(`timed out after ${TIMEOUT_MS}ms`), TIMEOUT_MS);

  try {
    const page = await browser.newPage();
    page.on("console", (m) => console.log("[page] " + m.text()));
    await page.goto(url, { waitUntil: "domcontentloaded" });

    // Wait for the runtime to be up and the Python-side bridge initialized.
    await page.waitForFunction(
      () => window.Module && Module.calledRun && Module.__webterm && Module.__webterm.ready === true,
      { timeout: TIMEOUT_MS },
    );
    console.log("Runtime up, __webterm.ready = true");

    // Install onOutput and send the raw-REPL handshake, then wait for banner.
    const result = await page.evaluate(
      () =>
        new Promise((resolve) => {
          let text = "";
          let bytes = 0;
          Module.__webterm.onOutput = (buf) => {
            bytes += buf.length;
            for (const b of buf) text += String.fromCharCode(b);
            if (text.includes("raw REPL; CTRL-B to exit\r\n")) {
              resolve({ ok: true, bytes });
            }
          };
          Module.__webterm.push([0x0d, 0x01]); // CR then Ctrl-A
          setTimeout(() => resolve({ ok: false, bytes, tail: text.slice(-200) }), 30000);
        }),
    );

    if (result.bytes === 0) fail("onOutput never fired: stdout mirror is dead");
    if (!result.ok) fail("raw REPL banner (CRLF) not seen; got tail: " + JSON.stringify(result.tail));

    console.log(`PASS: bridge alive, ${result.bytes} bytes mirrored, CRLF banner matched`);
    clearTimeout(timer);
    await browser.close();
    server.close();
    process.exit(0);
  } catch (e) {
    fail(e.stack || String(e));
  }
});
