// Real end-to-end Builder test.
// 1. Sign in with hellojarvisai1@gmail.com
// 2. Navigate to /builder/probe (isolates WebContainer boot)
// 3. If probe passes, create a real project and watch the preview boot
// 4. Capture console + CSP + network failures along the way

import { chromium } from "playwright";

const EMAIL = "hellojarvisai1@gmail.com";
const PASSWORD = process.env.HELM_TEST_PASSWORD;
if (!PASSWORD) {
  console.error("set HELM_TEST_PASSWORD");
  process.exit(1);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1400, height: 900 },
  });
  const page = await ctx.newPage();

  const logs = [];
  const push = (line) => {
    logs.push(line);
    console.log("LOG", line);
  };
  page.on("console", (m) => push(`[${m.type()}] ${m.text()}`));
  page.on("pageerror", (e) => push(`[pageerror] ${e.message}`));
  page.on("requestfailed", (r) =>
    push(`[netfail] ${r.method()} ${r.url()} — ${r.failure()?.errorText ?? "?"}`),
  );

  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      // eslint-disable-next-line no-console
      console.warn(`[CSP] ${e.violatedDirective} blocked ${e.blockedURI}`);
    });
  });

  console.log("→ acquiring Supabase session via REST");
  // Hit Supabase auth directly to get tokens without the React form.
  const fs = await import("node:fs");
  const path = await import("node:path");
  const url = await import("node:url");
  // Resolve .env.local relative to this script (apps/web/scripts/) so the
  // test isn't tied to whatever absolute path the author had on their box.
  const here = path.dirname(url.fileURLToPath(import.meta.url));
  const envPath = process.env.HELM_ENV_FILE
    ? path.resolve(process.env.HELM_ENV_FILE)
    : path.resolve(here, "..", "..", "..", ".env.local");
  const envText = fs.readFileSync(envPath, "utf8");
  const envMap = Object.fromEntries(
    envText
      .split("\n")
      .filter((l) => l && !l.startsWith("#") && l.includes("="))
      .map((l) => {
        const idx = l.indexOf("=");
        return [l.slice(0, idx), l.slice(idx + 1)];
      }),
  );
  const supaUrl = (envMap.SUPABASE_URL || "").replace(/\/$/, "");
  const supaAnon = envMap.SUPABASE_ANON_KEY || "";
  const supaResp = await fetch(`${supaUrl}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: {
      apikey: supaAnon,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  const supaBody = await supaResp.json();
  if (!supaResp.ok || !supaBody.access_token) {
    console.log("supabase auth failed:", supaBody);
    throw new Error("supabase auth failed");
  }
  console.log("→ got access token");

  // Supabase-SSR uses cookies. Compute the chunked cookie format and set
  // them so both server-side and client-side reads of auth state work.
  const projectRef = supaUrl.replace(/^https?:\/\//, "").split(".")[0];
  const sessionObj = {
    access_token: supaBody.access_token,
    refresh_token: supaBody.refresh_token,
    expires_at: Math.floor(Date.now() / 1000) + supaBody.expires_in,
    expires_in: supaBody.expires_in,
    token_type: "bearer",
    user: supaBody.user,
  };
  const base64Url = (s) =>
    "base64-" + Buffer.from(s, "utf8").toString("base64");
  const payload = base64Url(JSON.stringify(sessionObj));
  // Chunk into pieces of ~3200 chars to match supabase-ssr's chunking.
  const chunks = [];
  for (let i = 0; i < payload.length; i += 3200) {
    chunks.push(payload.slice(i, i + 3200));
  }
  const cookies = chunks.map((val, i) => ({
    name: `sb-${projectRef}-auth-token.${i}`,
    value: val,
    domain: "localhost",
    path: "/",
    expires: Math.floor(Date.now() / 1000) + 3600,
    httpOnly: false,
    secure: false,
    sameSite: "Lax",
  }));
  await ctx.addCookies(cookies);
  console.log(`→ set ${cookies.length} auth cookie chunk(s)`);

  // Also set localStorage copy so client-only paths have it too.
  await page.goto("http://localhost:3000/", { waitUntil: "domcontentloaded" });
  await page.evaluate(
    ([key, obj]) => {
      localStorage.setItem(key, JSON.stringify(obj));
    },
    [`sb-${projectRef}-auth-token`, sessionObj],
  );
  console.log("→ session injected");

  console.log("\n=== 1. PROBE (/builder/probe) ===");
  await page.goto("http://localhost:3000/builder/probe", {
    waitUntil: "domcontentloaded",
  });
  const deadline = Date.now() + 45000;
  let probeReport = null;
  while (Date.now() < deadline) {
    probeReport = await page.evaluate(() => {
      const el = document.querySelector("#probe-report");
      if (!el?.textContent) return null;
      try {
        return JSON.parse(el.textContent);
      } catch {
        return null;
      }
    });
    if (
      probeReport &&
      (probeReport.stage === "spawn_done" || probeReport.stage === "error")
    )
      break;
    await page.waitForTimeout(1000);
  }
  console.log("probe report:", JSON.stringify(probeReport, null, 2));
  if (!probeReport || probeReport.stage !== "spawn_done") {
    console.log("\n=== STOP: probe failed ===");
    console.log("Recent logs:");
    for (const line of logs.slice(-40)) console.log(line);
    await browser.close();
    process.exit(2);
  }

  console.log("\n=== 2. LIST/CREATE PROJECT ===");
  await page.goto("http://localhost:3000/builder", {
    waitUntil: "domcontentloaded",
  });
  // Find existing project or create one.
  const existingHref = await page
    .locator('a[href^="/builder/"]')
    .first()
    .getAttribute("href")
    .catch(() => null);
  let projectUrl = null;
  if (existingHref && !existingHref.startsWith("/builder/new") && !existingHref.startsWith("/builder/probe")) {
    projectUrl = `http://localhost:3000${existingHref}`;
    console.log("→ resuming existing project:", projectUrl);
  } else {
    console.log("→ creating new project via API (faster, no flaky form)");
    const token = supaBody.access_token;
    const createResp = await fetch("http://localhost:8000/builder/projects", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: `E2E Test ${Date.now().toString(36)}`,
        source_type: "blank",
        template: "vite_react",
      }),
    });
    if (!createResp.ok) {
      console.log("create failed", createResp.status, await createResp.text());
      throw new Error("create failed");
    }
    const created = await createResp.json();
    projectUrl = `http://localhost:3000/builder/${created.id}`;
    console.log("→ created:", projectUrl);
  }

  console.log("\n=== 3. WORKSPACE → PREVIEW BOOT ===");
  await page.goto(projectUrl, { waitUntil: "domcontentloaded" });
  // Quick sanity check: what's actually on the page?
  await page.waitForTimeout(3000);
  const pageDump = await page.evaluate(() => ({
    url: location.href,
    title: document.title,
    body: document.body.innerText.slice(0, 1500),
    iframeCount: document.querySelectorAll("iframe").length,
    h2s: [...document.querySelectorAll("h2")].map((e) => e.textContent?.trim()),
  }));
  console.log("page dump after 3s:", JSON.stringify(pageDump, null, 2));
  const workspaceDeadline = Date.now() + 180_000;
  let lastFingerprint = "";
  let succeeded = false;
  let failureDetail = null;
  while (Date.now() < workspaceDeadline) {
    // Read our PreviewFrame's user-visible stage heading (NOT just any
    // iframe — WebContainer adds its own internal runtime iframe which
    // would false-positive).
    const state = await page.evaluate(() => {
      // PreviewFrame's stage heading is inside the center <main>.
      const mainEl = document.querySelector("main");
      const headings = mainEl
        ? [...mainEl.querySelectorAll("h2")].map((e) => e.textContent?.trim())
        : [];
      // The ready iframe is <iframe title="Project preview">.
      const previewIframe = mainEl?.querySelector(
        'iframe[title="Project preview"]',
      );
      const errorPre = mainEl?.querySelector("pre")?.textContent?.slice(0, 600);
      return {
        heading: headings[0] ?? null,
        previewIframeSrc: previewIframe?.getAttribute("src") ?? null,
        errorPre,
        isolated: window.crossOriginIsolated,
      };
    });
    const fp = JSON.stringify(state);
    if (fp !== lastFingerprint) {
      console.log(
        `t+${Math.round((Date.now() - (workspaceDeadline - 180000)) / 1000)}s`,
        state,
      );
      lastFingerprint = fp;
    }
    if (state.previewIframeSrc) {
      console.log("→ preview iframe loaded:", state.previewIframeSrc);
      succeeded = true;
      break;
    }
    if (
      state.heading === "Preview hit a snag" ||
      state.heading === "Preview unavailable"
    ) {
      failureDetail = state.errorPre;
      console.log("→ preview errored:", failureDetail);
      break;
    }
    await page.waitForTimeout(2000);
  }
  if (!succeeded && failureDetail) {
    console.log("\nFAILURE DETAIL:\n" + failureDetail);
  }

  console.log("\n=== RESULT:", succeeded ? "PASS" : "FAIL", "===");
  console.log("\nRecent logs (last 60):");
  for (const line of logs.slice(-60)) console.log(line);

  await browser.close();
  process.exit(succeeded ? 0 : 3);
}

main().catch((e) => {
  console.error("crash:", e);
  process.exit(1);
});
