/**
 * Browser acceptance test for the new UI.
 *
 * Drives the real app served by the backend at :8000 — creates a project through
 * the modal, starts a live run, watches the twelve stages advance, visits every
 * tab, then starts a second run and cancels it from the UI.
 *
 * Run with:  node /home/user/scripts/ui_acceptance.mjs
 * Screenshots land in /home/user/screenshots/ui-*.png
 */
import { chromium } from "playwright";
import fs from "node:fs";

const OUT = "/home/user/screenshots";
const BASE = "http://localhost:8000";
fs.mkdirSync(OUT, { recursive: true });

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? " — " + detail : ""}`);
}

const api = async (path, init) => {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  return res.json();
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1560, height: 1000 } });
const consoleErrors = [];
page.on("console", (m) => {
  if (m.type() === "error") consoleErrors.push(m.text());
});
page.on("pageerror", (e) => consoleErrors.push(String(e)));

await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
await page.waitForSelector("text=Research Assistant", { timeout: 30000 });
await page.waitForTimeout(2500);
await page.screenshot({ path: `${OUT}/ui-01-overview.png` });

/* ---------------------------------------------------------------- new project */
await page.getByRole("button", { name: "New project" }).first().click();
await page.waitForTimeout(400);
const stamp = Date.now().toString().slice(-6);
const projectName = `UI acceptance ${stamp}`;
await page.getByPlaceholder("Precision agriculture — yield prediction").fill(projectName);
await page
  .getByPlaceholder("AI-driven precision agriculture for crop yield prediction")
  .fill("Edge AI for real-time defect detection in industrial manufacturing");
await page.getByPlaceholder(/Focus on smallholder farms/).fill(
  "Focus on real-time vision systems deployed on constrained hardware. Prefer studies reporting latency and accuracy on named industrial datasets. Exclude purely theoretical papers.",
);
await page.getByPlaceholder(/Which sensors and models/).fill(
  "Which model architectures are used for real-time defect detection?",
);
await page.screenshot({ path: `${OUT}/ui-02-new-project.png` });
await page.getByRole("button", { name: "Create project" }).click();
await page.waitForTimeout(2000);

const projects = await api("/api/projects");
const created = projects.find((p) => p.name === projectName);
check("project created through the UI modal", !!created, created ? created.id.slice(0, 8) : "missing");
check(
  "domain auto-detected from the topic",
  created?.domain === "computer_science",
  created?.domain,
);
check("instructions stored separately from the topic", (created?.research_instructions || "").length > 50);
check("research question stored", (created?.research_questions || []).length === 1);
await page.screenshot({ path: `${OUT}/ui-03-new-project-overview.png` });

/* --------------------------------------------------------------- live run */
const before = Date.now();
await page.getByRole("button", { name: /^Run research$/ }).click();
await page.waitForTimeout(1200);
await page.screenshot({ path: `${OUT}/ui-04-run-started.png` });

// the live strip is rendered only while the backend reports an active run
const liveSeen = await page
  .locator("text=/stage \\d+ of 12/i")
  .first()
  .isVisible()
  .catch(() => false);
check("live stage strip appears while the run is active", liveSeen);

let status = "pending";
for (let i = 0; i < 120; i++) {
  const runs = await api(`/api/projects/${created.id}/runs`);
  status = runs[0]?.status ?? "pending";
  if (!["pending", "running", "cancelling"].includes(status)) break;
  if (i === 2) await page.screenshot({ path: `${OUT}/ui-05-run-running.png` });
  await page.waitForTimeout(1000);
}
await page.waitForTimeout(2500);
await page.screenshot({ path: `${OUT}/ui-06-run-finished.png` });
check("run reached a terminal state", !["pending", "running"].includes(status), status);

const run = (await api(`/api/projects/${created.id}/runs`))[0];
const detail = await api(`/api/runs/${run.id}`);
const completed = detail.stages.filter((s) => s.status === "completed").length;
check("all twelve stages completed in the UI run", completed === 12, `${completed}/12`);
check(
  "stage durations were measured by the backend",
  detail.stages.every((s) => s.status !== "completed" || typeof s.duration_ms === "number"),
);
check("stage tool-call counts recorded", detail.stages.some((s) => s.tool_calls > 0));

const renderedStages = await page.locator("li:has(button) >> text=/Understand Topic/").count();
check("stage timeline rendered in the browser", renderedStages > 0);

const papers = await api(`/api/projects/${created.id}/papers`);
check("papers retrieved and stored", papers.count > 0, `${papers.count} papers`);

/* ----------------------------------------------------------------- every tab */
const tabs = [
  ["Literature", "ui-07-literature.png"],
  ["Gaps & Ideas", "ui-08-gaps.png"],
  ["Draft", "ui-09-draft.png"],
  ["Citations", "ui-10-citations.png"],
  ["Venues & funding", "ui-11-radar.png"],
  ["Trace & audit", "ui-12-trace.png"],
  ["Exports", "ui-13-exports.png"],
  ["System", "ui-14-system.png"],
];
for (const [label, file] of tabs) {
  await page.getByRole("button", { name: label, exact: true }).click();
  await page.waitForTimeout(1400);
  await page.screenshot({ path: `${OUT}/${file}` });
  const bodyText = await page.locator("main").innerText();
  const empty = /No papers stored yet|No gaps recorded|No draft yet|No citation audit yet|No venue or funding scan yet/i.test(
    bodyText,
  );
  check(`tab renders real data: ${label}`, !empty, empty ? "empty state shown" : `${bodyText.length} chars`);
}
await page.getByRole("button", { name: "Overview", exact: true }).click();
await page.waitForTimeout(600);

/* -------------------------------------------------------------- cancel a run */
await page.getByRole("button", { name: /^Run research$/ }).click();
await page.waitForTimeout(2500);
const cancelVisible = await page
  .getByRole("button", { name: /Cancel run/ })
  .first()
  .isVisible()
  .catch(() => false);
check("cancel button is available while a run is live", cancelVisible);
await page.screenshot({ path: `${OUT}/ui-15-cancel-visible.png` });
await page.getByRole("button", { name: /Cancel run/ }).first().click();
await page.waitForTimeout(4000);
await page.screenshot({ path: `${OUT}/ui-16-cancelled.png` });

const runsAfter = await api(`/api/projects/${created.id}/runs`);
check("run cancelled from the UI is stored as cancelled", runsAfter[0]?.status === "cancelled", runsAfter[0]?.status);
check(
  "cancellation reason persisted",
  (runsAfter[0]?.stats || {}).cancel_reason === "Cancelled from the UI",
  JSON.stringify((runsAfter[0]?.stats || {}).cancel_reason),
);
const cancelledStages = runsAfter[0].stages.filter((s) => s.status === "cancelled");
check("exactly one stage is marked cancelled", cancelledStages.length === 1, JSON.stringify(cancelledStages.map((s) => s.key)));
check(
  "earlier artifacts survived the cancellation",
  (await api(`/api/projects/${created.id}/papers`)).count > 0,
);

/* ------------------------------------------------------------- new project form */
await page.getByRole("button", { name: "New project" }).first().click();
await page.waitForTimeout(300);
await page.getByPlaceholder("Precision agriculture — yield prediction").fill("Too long topic");
await page
  .getByPlaceholder("AI-driven precision agriculture for crop yield prediction")
  .fill("x".repeat(320));
await page.waitForTimeout(300);
const blocked = await page.getByRole("button", { name: "Create project" }).isDisabled();
check("over-long topic is blocked before it reaches the API", blocked);
await page.screenshot({ path: `${OUT}/ui-17-validation.png` });
await page.keyboard.press("Escape");

check("no uncaught browser errors", consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));

/* ---------------------------------------------------------------------- report */
const summary = {
  project: projectName,
  project_id: created.id,
  first_run: { id: run.id, status: status, stages_completed: completed, papers: papers.count },
  wall_clock_s: Math.round((Date.now() - before) / 1000),
  results,
  console_errors: consoleErrors,
};
fs.writeFileSync("/home/user/screenshots/ui-acceptance.json", JSON.stringify(summary, null, 2));
console.log("\n" + results.filter((r) => !r.ok).length + " failing check(s)");
await browser.close();
