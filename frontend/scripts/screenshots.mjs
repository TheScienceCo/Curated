/**
 * Regenerate the README screenshots.
 *
 * Playwright is not a project dependency (it would slow every CI install for
 * something only run when the UI changes), so install it on demand:
 *
 *   cd frontend && npm i --no-save playwright && npx playwright install chromium
 *
 * Then, with the demo data seeded and both servers running:
 *
 *   cd backend  && PYTHONPATH=. uvicorn app.main:app --port 8000
 *   cd frontend && npm run build && npm run start
 *   cd frontend && node scripts/screenshots.mjs
 *
 * Set CHROMIUM_PATH to use a browser Playwright did not install itself.
 */
import { chromium } from "playwright";

const OUT = process.env.SHOT_OUT ?? "../docs/screenshots";
const BASE = process.env.SHOT_BASE ?? "http://localhost:3000";
const API = process.env.SHOT_API ?? "http://localhost:8000";
const EXECUTABLE = process.env.CHROMIUM_PATH;

const browser = await chromium.launch(EXECUTABLE ? { executablePath: EXECUTABLE } : {});

/** A fresh page per capture: a full-page screenshot of a tall page leaves the
 *  shared page in a state where later navigations render blank. */
async function withPage(fn) {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 2,
    colorScheme: "light",
  });
  const page = await ctx.newPage();
  try {
    return await fn(page);
  } finally {
    await ctx.close();
  }
}

async function open(page, path) {
  await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("load");
  await page.waitForTimeout(800);
}

async function shot(path, file) {
  await withPage(async (page) => {
    await open(page, path);
    await page.screenshot({ path: `${OUT}/${file}`, fullPage: true });
  });
  console.log("captured", file);
}

/**
 * Click until the control has an effect.
 *
 * Server-rendered buttons exist in the DOM before React attaches handlers, so
 * a click landing mid-hydration is silently dropped.
 */
async function clickUntil(page, locator, condition, attempts = 12) {
  for (let i = 0; i < attempts; i += 1) {
    await locator.click();
    try {
      await condition();
      return;
    } catch {
      await page.waitForTimeout(500);
    }
  }
  throw new Error("control never took effect - hydration may have failed");
}

const { rows } = await (await fetch(`${API}/api/dashboard`)).json();
const top = [...rows].sort((a, b) => b.overall_score - a.overall_score)[0];
const gated = rows.find((r) => r.hard_gate_count > 0);

await shot("/", "dashboard.png");
await shot(`/opportunities/${top.opportunity_id}`, "opportunity-detail.png");
if (gated) await shot(`/opportunities/${gated.opportunity_id}`, "hard-gate.png");

// The examples gallery, with the first case actually run.
await withPage(async (page) => {
  await open(page, "/examples");
  await clickUntil(
    page,
    page.getByRole("button", { name: "Run this case" }).first(),
    () => page.waitForSelector("text=What it extracted", { timeout: 2500 }),
  );
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/examples.png`, fullPage: true });
});
console.log("captured examples.png");

// The analyze page with the documented example loaded and analysed (preview only).
await withPage(async (page) => {
  await open(page, "/analyze");
  await clickUntil(
    page,
    page.getByRole("button", { name: /Load the example/i }),
    () =>
      page.waitForFunction(() => document.querySelector("textarea")?.value.length > 100, null, {
        timeout: 800,
      }),
  );
  await page.getByLabel(/Save to the dashboard/i).uncheck();
  await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await page.waitForSelector("text=Prove-it analysis", { timeout: 20000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/analyze.png`, fullPage: true });
});
console.log("captured analyze.png");

await shot("/profile", "profile.png");
await shot("/resumes", "resumes.png");

await withPage(async (page) => {
  await open(page, "/equity");
  await clickUntil(
    page,
    page.getByRole("button", { name: /Calculate scenarios/i }),
    () => page.waitForSelector("text=Exit valuation", { timeout: 2000 }),
  );
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/equity.png`, fullPage: true });
});
console.log("captured equity.png");

await browser.close();
