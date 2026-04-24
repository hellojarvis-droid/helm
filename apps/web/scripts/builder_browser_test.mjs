// Navigate to the /builder/__probe page, wait for its in-page
// WebContainer.boot() test to terminate, and dump the report + all
// console logs + any CSP violations.

import { chromium } from "playwright";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();

  const logs = [];
  page.on("console", (msg) => logs.push(`[${msg.type()}] ${msg.text()}`));
  page.on("pageerror", (err) => logs.push(`[pageerror] ${err.message}`));
  page.on("requestfailed", (req) =>
    logs.push(
      `[netfail] ${req.method()} ${req.url()} — ${req.failure()?.errorText ?? "?"}`,
    ),
  );

  console.log("→ opening /builder/probe");
  await page.goto("http://localhost:3000/builder/probe", {
    waitUntil: "domcontentloaded",
    timeout: 45000,
  });
  console.log("→ landed on:", page.url());
  console.log("→ title:", await page.title());
  console.log("→ body preview:", (await page.content()).slice(0, 400));

  const deadline = Date.now() + 60_000;
  let report = null;
  while (Date.now() < deadline) {
    report = await page.evaluate(() => {
      const el = document.querySelector("#probe-report");
      if (!el || !el.textContent) return null;
      try {
        return JSON.parse(el.textContent);
      } catch {
        return null;
      }
    });
    if (report && (report.stage === "spawn_done" || report.stage === "error")) break;
    await page.waitForTimeout(1000);
  }

  console.log("→ final probe report:");
  console.log(JSON.stringify(report, null, 2));
  console.log("\n=== browser logs ===");
  for (const line of logs.slice(-100)) console.log(line);

  await browser.close();
}

main().catch((e) => {
  console.error("test crashed:", e);
  process.exit(1);
});
