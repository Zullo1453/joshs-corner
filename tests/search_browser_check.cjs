/* Fictional local browser fixture: run search_browser_server.py first.
   Requires Playwright available to Node; no user profile or live data is opened. */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const { expect } = require("playwright/test");
const path = require("node:path");

let runningBrowser;
(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  runningBrowser = browser;
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  const requests = [];
  page.on("request", request => { if (request.url().includes("/search")) requests.push({url:request.url(), method:request.method()}); });
  const base = "http://127.0.0.1:5011";
  const dialog = page.locator("[data-universal-search]");
  const input = dialog.locator("[data-search-input]");
  const status = page.locator("[data-search-status]");
  const open = async () => {
    await page.waitForLoadState("load");
    await page.locator("[data-nav-toggle]").focus();
    await page.keyboard.press("Control+k");
    await expect(dialog).toBeVisible();
    await expect(input).toBeFocused();
  };
  const query = async value => {
    await input.fill(value);
    await expect(status).not.toHaveText("Searching…");
  };
  for (const start of ["/", "/journal/", "/todos/", "/automations", "/gym"]) {
    await page.goto(base + start);
    const before = page.url();
    await open();
    await query("Public Economics");
    await expect(page.locator(".search-result")).toHaveCount(11);
    await page.locator(".search-result").filter({hasText:"Public Economics Notes"}).click();
    await expect(page).toHaveURL(base + "/notes/?note_id=1");
    await expect(page.locator('[name="title"]')).toHaveValue("Public Economics Notes");
    await page.goBack();
    await expect(page).toHaveURL(before);
  }

  // Editor shortcuts are preserved; global action still opens search.
  await page.goto(base + "/notes/?note_id=1");
  await page.locator('[contenteditable="true"]').first().click();
  await page.keyboard.press("Control+k");
  await expect(dialog).not.toBeVisible();
  await page.locator("[data-search-open]").click();
  await expect(input).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator("[data-search-open]")).toBeFocused();
  for (let i=0; i<3; i++) {
    await page.keyboard.press("Control+k");
    await expect(input).toBeFocused();
    await page.keyboard.press("Escape");
  }
  // Focus trapping and native keyboard link activation.
  await page.locator("[data-search-open]").click();
  await page.keyboard.press("Shift+Tab");
  assert(await page.evaluate(() => document.querySelector("[data-universal-search]").contains(document.activeElement)));
  await input.focus();
  await query("Public Economics Notes");
  await page.keyboard.press("ArrowDown");
  assert(await input.getAttribute("aria-activedescendant"));
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(base + "/notes/?note_id=1");

  await page.locator("[data-search-open]").click();
  await input.fill("Pu");
  await input.fill("Public");
  await input.fill("Public Economics");
  await expect(page.locator(".search-result")).toHaveCount(11);
  await input.fill("");
  await expect(page.locator(".search-result")).toHaveCount(0);
  await query("zz-no-match-zz");
  await expect(status).toHaveText('No results for "zz-no-match-zz"');
  await query("x".repeat(200));
  await expect(page.locator(".search-result")).toHaveCount(0);
  await query("Safety sample");
  await expect(page.locator(".search-result")).toHaveCount(1);
  await expect(page.locator(".search-result img")).toHaveCount(0);
  await query("Public Economics");
  await page.screenshot({path:path.join("instance","search-desktop.png")});

  // Expanded rail Search retains its action role and the same icon centre.
  await page.keyboard.press("Escape");
  await page.locator("[data-nav-toggle]").click();
  await page.locator("[data-search-open]").click();
  await page.keyboard.press("Escape");
  await expect(page.locator("[data-search-open]")).toBeFocused();
  assert(await page.locator("[data-application-nav]").evaluate(el => el.classList.contains("is-open")));
  await page.locator("[data-nav-dismiss]").click();

  // Existing partial navigation still replaces only the detail panel.
  await page.goto(base + "/notes/?note_id=1");
  const sidebarLink = page.locator(".note-card-link").filter({hasText:"Scrolling sample 0"}).first();
  await sidebarLink.click();
  await expect(page.locator('[name="title"]')).toHaveValue("Scrolling sample 0");
  assert(await page.locator("[data-universal-search]").count() === 1);
  await page.locator("[data-search-open]").click();
  await query("Public Economics");
  await expect(page.locator(".search-result")).toHaveCount(11);
  await page.keyboard.press("Escape");
  await page.goBack();
  await expect(page.locator('[name="title"]')).toHaveValue("Public Economics Notes");

  // Search navigation respects the editor's existing unsaved-change guard.
  await page.locator('[name="title"]').fill("Unsaved local draft");
  await page.locator("[data-search-open]").click();
  await query("Public Economics Exam");
  page.once("dialog", confirmation => confirmation.dismiss());
  await page.locator('.search-result[href="/deadlines/1"]').click();
  await expect(page).toHaveURL(base + "/notes/?note_id=1");
  await expect(page.locator('[name="title"]')).toHaveValue("Unsaved local draft");
  // Discard only this fictional draft when leaving the test page.
  page.once("dialog", confirmation => confirmation.accept());
  await page.goto(base + "/");
  await page.locator("[data-nav-toggle]").focus();
  await page.keyboard.press("Meta+k");
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");

  for (const width of [320,375,390,430]) {
    const mobile = await browser.newContext({viewport:{width,height:720}, isMobile:true, hasTouch:true});
    const tab = await mobile.newPage();
    tab.on("pageerror", error => errors.push(error.message));
    await tab.goto(base + "/");
    await tab.locator("[data-nav-toggle]").tap();
    await tab.locator("[data-search-open]").tap();
    const field = tab.locator("[data-universal-search] [data-search-input]");
    await expect(field).toBeFocused();
    await field.fill("Scrolling");
    await expect(tab.locator(".search-result")).toHaveCount(40);
    // Reduced viewport simulates space consumed by an on-screen keyboard.
    await tab.setViewportSize({width,height:390});
    assert(await tab.evaluate(() => {
      const d=document.querySelector("[data-universal-search]").getBoundingClientRect();
      const r=document.querySelector("[data-search-results]");
      return d.left>=0 && d.right<=innerWidth && d.bottom<=innerHeight &&
        document.documentElement.scrollWidth<=innerWidth &&
        r.scrollHeight>r.clientHeight && r.clientHeight>0;
    }));
    await tab.locator(".search-result").last().scrollIntoViewIfNeeded();
    await expect(tab.locator(".search-result").last()).toBeVisible();
    if (width===390) await tab.screenshot({path:path.join("instance","search-mobile.png")});
    await tab.locator("[data-search-close]").tap();
    await expect(tab.locator("[data-search-open]")).toBeFocused();
    await tab.locator("[data-search-open]").tap();
    await field.fill("Public Economics Notes");
    await expect(tab.locator(".search-result")).toHaveCount(1);
    await tab.locator(".search-result").tap();
    await expect(tab).toHaveURL(base + "/notes/?note_id=1");
    await mobile.close();
  }
  assert(requests.every(item=>item.method==="POST" && !item.url.includes("?")));
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(JSON.stringify({desktopStarts:5, mobileWidths:[320,375,390,430], reducedHeight:390,
    consoleErrors:errors.length, searchRequests:requests.length, passed:true}));
})().catch(async error => { console.error(error); await runningBrowser?.close(); process.exitCode=1; });
