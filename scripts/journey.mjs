#!/usr/bin/env node
// The first-session user journey, run in CI against the BUILT wheel.
//
// Six of the fifteen shipped defects lived on paths only a browser walks:
// first-run, tour, charts, export, drag-drop, agent view. Unit tests cannot
// see them; this script fails the release if any step breaks or if anything
// logs a console error.
//
//   node scripts/journey.mjs --port 8399
//
// Uses `playwright` with its bundled chromium (CI has no Google Chrome).
// The server must already be serving a FRESH `datacharter init` workspace
// (no --demo: the journey starts at the first-run screen and loads the demo
// the way a user does).
import { mkdirSync } from "node:fs";
import { join } from "node:path";

// CI uses `playwright` (bundled chromium); local dev can fall back to
// playwright-core + system Chrome via JOURNEY_CHANNEL=chrome.
let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  ({ chromium } = await import("playwright-core"));
}

const args = process.argv.slice(2);
const port = args.includes("--port") ? args[args.indexOf("--port") + 1] : "8399";
const base = `http://127.0.0.1:${port}`;
const shotsDir = process.env.JOURNEY_SHOTS ?? "journey-shots";
mkdirSync(shotsDir, { recursive: true });

const channel = process.env.JOURNEY_CHANNEL;
const browser = await chromium.launch({ headless: true, ...(channel ? { channel } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

const consoleErrors = [];
page.on("console", (m) => {
  if (m.type() === "error") consoleErrors.push(m.text());
});
page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));

let stepNo = 0;
async function step(name, fn) {
  stepNo += 1;
  const label = `${String(stepNo).padStart(2, "0")}-${name}`;
  try {
    await fn();
    await page.screenshot({ path: join(shotsDir, `${label}.png`) });
    console.log(`✓ ${label}`);
  } catch (err) {
    await page.screenshot({ path: join(shotsDir, `${label}-FAILED.png`) }).catch(() => {});
    console.error(`✗ ${label}: ${err.message}`);
    throw err;
  }
}

async function runSql(sql) {
  await page.locator(".monaco-editor").first().click();
  await page.keyboard.press("ControlOrMeta+a");
  // insertText, not keyboard.type: Monaco drops characters under type().
  await page.keyboard.insertText(sql);
  await page.getByRole("button", { name: "Run", exact: true }).click();
}

async function dismissTour() {
  const skip = page.getByText("Skip tour", { exact: true });
  if (await skip.isVisible().catch(() => false)) {
    await page.screenshot({ path: join(shotsDir, "tour-shown.png") });
    await skip.click();
    return true;
  }
  return false;
}

try {
  await step("first-run", async () => {
    await page.goto(base, { waitUntil: "networkidle" });
    await page.getByText("No data sources yet").waitFor({ timeout: 15000 });
  });

  await step("load-demo", async () => {
    await page.getByRole("button", { name: "Load the demo dataset" }).click();
    await page.getByText("store", { exact: true }).first().waitFor({ timeout: 30000 });
  });

  await step("tour", async () => {
    await dismissTour();
    // The demo must actually demonstrate: guides, evals, and a verifiable
    // audit chain — empty panels were one of the shipped defects.
    const audit = await page.evaluate(async () =>
      (await fetch("/api/audit/verify")).json()
    );
    if (!audit.ok || audit.entries < 1) {
      throw new Error(`demo seeded no audit chain: ${JSON.stringify(audit)}`);
    }
  });

  await step("query", async () => {
    await dismissTour();
    await runSql(
      "SELECT tier, count(*) AS n FROM store.customers GROUP BY 1 ORDER BY 2 DESC"
    );
    // exact: true — a bare getByText("pro") substring-matches the Profile tab.
    await page.getByText("pro", { exact: true }).first().waitFor({ timeout: 15000 });
  });

  await step("charts", async () => {
    await page.getByRole("button", { name: "Chart", exact: true }).click();
    const kindSelect = page.locator(".chart-controls select").first();
    await kindSelect.waitFor({ timeout: 15000 });
    // Every offered chart kind must actually render — only scatter worked once.
    const kinds = await kindSelect.locator("option").allTextContents();
    if (kinds.length < 2) throw new Error(`only ${kinds} chart kinds offered`);
    for (const kind of kinds) {
      await kindSelect.selectOption(kind);
      await page
        .locator(".chart-body canvas, .chart-body svg")
        .first()
        .waitFor({ timeout: 10000 });
    }
    await page.getByRole("button", { name: "Results", exact: true }).click();
  });

  await step("export", async () => {
    const download = page.waitForEvent("download", { timeout: 15000 });
    await page.getByRole("button", { name: /^Export/ }).click();
    const file = await download;
    if (!file.suggestedFilename().endsWith(".csv")) {
      throw new Error(`unexpected export filename: ${file.suggestedFilename()}`);
    }
    // Export must not take the app down with it (defect: app closed on export).
    await page.getByText("store", { exact: true }).first().waitFor({ timeout: 5000 });
  });

  await step("drag-drop-pii", async () => {
    await page.evaluate(async () => {
      const csv =
        "who,contact\nada,ada@example.com\ngrace,grace@example.com\nedsger,e@example.com\n";
      const dt = new DataTransfer();
      dt.items.add(new File([csv], "contacts.csv", { type: "text/csv" }));
      const target = document.querySelector(".app");
      target.dispatchEvent(new DragEvent("dragover", { bubbles: true, dataTransfer: dt }));
      target.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer: dt }));
    });
    await page.getByText("contacts", { exact: true }).first().waitFor({ timeout: 20000 });
  });

  await step("agent-view-masks-upload", async () => {
    await page.locator(".agent-view-toggle input").check();
    await runSql("SELECT who, contact FROM contacts ORDER BY who");
    await page.getByText("•••").first().waitFor({ timeout: 15000 });
    const gridText = await page.locator(".app").innerText();
    if (gridText.includes("ada@example.com")) {
      throw new Error("agent view leaked a raw value-detected email");
    }
  });

  await step("masking-toggle", async () => {
    // The table toggle is coarse: with mixed access (who=real, contact=masked)
    // the first click masks the whole table, the second allows the whole table.
    const toggle = page.getByLabel("Toggle agent access for table contacts").first();
    const contactMasked = async () => {
      const tables = await page.evaluate(async () =>
        (await (await fetch("/api/tables")).json()).tables
      );
      return tables.find((t) => t.table === "contacts")?.access?.contact?.masked;
    };
    const clickUntil = async (wantMasked) => {
      for (let i = 0; i < 3; i++) {
        if ((await contactMasked()) === wantMasked) return;
        await toggle.click();
        await page.waitForTimeout(600); // write + catalog refresh
      }
      throw new Error(`contact never reached masked=${wantMasked}`);
    };
    await clickUntil(false);
    await runSql("SELECT who, contact FROM contacts ORDER BY who");
    await page.getByText("ada@example.com").first().waitFor({ timeout: 15000 });
    await clickUntil(true);
    await runSql("SELECT who, contact FROM contacts ORDER BY who");
    await page.getByText("•••").first().waitFor({ timeout: 15000 });
  });

  await step("backend-switch-surface", async () => {
    // No real LLM in CI: assert the local-runtime discovery endpoint and the
    // agent-backend state machine both respond (the seam behind the switcher).
    const local = await page.evaluate(async () => (await fetch("/api/llm/local")).status);
    if (local !== 200) throw new Error(`/api/llm/local returned ${local}`);
    const status = await page.evaluate(async () =>
      (await fetch("/api/agent/available")).json()
    );
    if (typeof status.claude_code_available !== "boolean") {
      throw new Error(`agent status missing claude_code_available: ${JSON.stringify(status)}`);
    }
  });

  if (consoleErrors.length) {
    console.error(`CONSOLE ERRORS (${consoleErrors.length}):`);
    for (const e of consoleErrors) console.error(`  ${e}`);
    process.exitCode = 1;
  } else {
    console.log("journey complete: console clean");
  }
} catch (err) {
  console.error(`journey FAILED: ${err.message}`);
  if (consoleErrors.length) {
    console.error("console errors so far:");
    for (const e of consoleErrors) console.error(`  ${e}`);
  }
  process.exitCode = 1;
} finally {
  await browser.close();
}
