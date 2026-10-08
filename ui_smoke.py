"""Browser-level end-to-end check of the Diwali demo flow (needs the server running on :5000 with a freshly seeded DB).

Run:  python tests/ui_smoke.py [screenshot_dir]
Drives the real UI as five different users, asserts what each screen shows, and fails on any JavaScript error.
"""
import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("NOVA_URL", "http://127.0.0.1:5000")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else None
errors, checks = [], []


def check(name, cond, detail=""):
    checks.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def shot(page, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=True)


def switch(page, email):
    page.select_option("#switch-user", value=email)
    page.wait_for_timeout(500)


def goto(page, route):
    page.evaluate(f"location.hash = '#/{route}'")
    page.wait_for_timeout(700)


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" and "401" not in m.text and "409" not in m.text and "403" not in m.text else None)
    page.goto(BASE)
    page.wait_for_selector(".login")
    shot(page, "01_login")
    check("login page shows quick demo users", page.locator(".demo-users button").count() >= 5)
    # bad password
    page.fill("#em", "aman.sharma@novabrands.in"); page.fill("#pw", "wrong"); page.click("#login-form button[type=submit]")
    page.wait_for_selector("#login-err:not(.hidden)")
    check("wrong password is rejected", "incorrect" in page.inner_text("#login-err"))
    page.fill("#pw", "Demo@123"); page.click("#login-form button[type=submit]")
    page.wait_for_selector(".hero")
    check("executive lands on Executive Demo", "Aman Sharma" in page.inner_text(".userchip"))
    shot(page, "02_executive_demo")
    check("story shows live impact figure", re.search(r"~\d+% faster", page.inner_text(".story")) is not None, page.inner_text(".story .st:nth-child(4) .big"))
    nav = page.inner_text(".nav")
    check("executive nav has Create Campaign, no Pending Approvals", "Create Campaign" in nav and "Pending Approvals" not in nav)

    # ---- create the Diwali campaign
    page.click('a[data-nav="create"]'); page.wait_for_selector("#fill-demo")
    page.click("#fill-demo"); page.wait_for_timeout(300)
    check("route preview shows 2 levels for Rs 1,80,000", "Regional Manager" in page.inner_text("#route-prev") and "Marketing Manager" in page.inner_text("#route-prev") and "Marketing Head" not in page.inner_text("#route-prev"))
    shot(page, "03_create_form")
    page.click("#submit"); page.wait_for_selector("text=Request submitted")
    cid = page.locator(".kv .v").first.inner_text()
    check("campaign ID generated", re.fullmatch(r"MKT-\d{4}-\d{3}", cid) is not None, cid)
    check("validation passed + route created", "Passed" in page.inner_text(".panel") and "Marketing Manager" in page.inner_text(".panel"))
    shot(page, "04_submitted")

    # ---- negative: validation failure UI (new form, missing objective + bad budget)
    page.click('a[data-nav="create"]'); page.wait_for_selector("#fill-demo"); page.click("#fill-demo")
    page.fill('[data-k="Campaign_Name"]', "Validation demo"); page.select_option('[data-k="Objective"]', ""); page.fill('[data-k="Proposed_Budget"]', "-100")
    page.click("#submit"); page.wait_for_selector("#form-result .banner.bad")
    check("validation failure lists specific fields", "Marketing objective is required" in page.inner_text("#form-result") and "Budget must be greater than zero" in page.inner_text("#form-result"))
    check("invalid fields are highlighted", page.locator(".field.invalid").count() >= 2)
    shot(page, "05_validation_failed")

    # ---- executive must not be able to approve
    page.evaluate(f"location.hash = '#/campaign/{cid}'"); page.wait_for_selector(".route")
    check("executive sees no approve buttons", page.locator('[data-act="approve"]').count() == 0)
    check("pending campaign governance reads PENDING APPROVAL", "PENDING APPROVAL" in page.inner_text(".stamp"))

    # ---- Regional Manager approves
    switch(page, "rahul.mehta@novabrands.in"); goto(page, "approvals")
    page.wait_for_selector(f'.approval-card[data-id="{cid}"]')
    shot(page, "06_pending_approvals_rm")
    page.click(f'.approval-card[data-id="{cid}"] [data-d="approve"]'); page.wait_for_selector(".toast")
    check("RM approval moves to Marketing Manager", "Priya Kapoor" in page.locator(".toast.good").last.inner_text(), page.locator(".toast.good").last.inner_text()[:90])
    page.wait_for_timeout(600)

    # ---- Marketing Manager final approval
    switch(page, "priya.kapoor@novabrands.in"); goto(page, "approvals")
    page.wait_for_selector(f'.approval-card[data-id="{cid}"]')
    page.click(f'.approval-card[data-id="{cid}"] [data-d="approve"]')
    page.wait_for_selector(".toast.good"); page.wait_for_timeout(300)
    check("final approval toast says fully approved + Ready for Execution", "Fully approved" in page.inner_text("#toasts") and "Ready for Execution" in page.inner_text("#toasts"))

    # ---- governance check on the campaign
    goto(page, f"campaign/{cid}"); page.wait_for_selector(".stamp")
    check("governance stamp = FULLY COMPLIANT", "FULLY COMPLIANT" in page.inner_text(".stamp"))
    body = page.inner_text("#page")
    check("campaign shows Fully Approved and Ready for Execution", "Fully Approved" in body and "Ready for Execution" in body)
    check("audit trail contains dispatch event", "Campaign Dispatched" in body and "Approval Granted" in body)
    shot(page, "07_campaign_detail_compliant")

    # ---- Execution team: execute + load leads
    switch(page, "rohit.bansal@novabrands.in"); goto(page, f"campaign/{cid}"); page.wait_for_selector("#a-exec")
    page.click("#a-exec"); page.wait_for_selector("#a-sim"); page.wait_for_timeout(400)
    page.click("#a-sim"); page.wait_for_timeout(1200)
    body = page.inner_text("#page")
    check("lead data and KPIs appear after executing", "Cost per lead" in body and re.search(r"ROAS", body) is not None)
    shot(page, "08_campaign_performance")
    # dispatch-before-approval is blocked in the UI
    goto(page, "campaigns"); page.wait_for_selector("table")
    page.locator("tr.click", has_text="Whitefield Billboard").click(); page.wait_for_selector("#a-dispatch")
    page.click("#a-dispatch"); page.wait_for_selector(".toast.bad")
    check("dispatch of a rejected campaign is blocked with a reason", "blocked" in page.locator(".toast.bad").last.inner_text().lower(), page.locator(".toast.bad").last.inner_text()[:100])

    # ---- Management: dashboard reflects it
    switch(page, "neha.verma@novabrands.in"); goto(page, "dashboard"); page.wait_for_selector("#c1")
    page.wait_for_timeout(900)
    kpi = page.inner_text(".kpi-band")
    check("dashboard shows 24 campaigns (23 + the validation-failed record)", re.search(r"Total campaigns\s*24", kpi) is not None, kpi.split("\n")[0:3].__str__())
    shot(page, "09_dashboard")
    page.select_option('[data-f="region"]', "Mumbai"); page.wait_for_timeout(900)
    check("region filter updates KPIs", re.search(r"Total campaigns\s*(\d+)", page.inner_text(".kpi-band")).group(1) != "24")
    shot(page, "10_dashboard_filtered")

    # ---- remaining pages render without errors for management
    for r in ("campaigns", "history", "leads", "performance", "governance", "metrics", "reports", "demo"):
        goto(page, r); page.wait_for_timeout(900)
        txt = page.inner_text("#page")
        check(f"page '{r}' renders", len(txt) > 200 and "Could not load" not in txt)
        shot(page, "page_" + r)
    # process metrics numbers
    goto(page, "metrics"); page.wait_for_timeout(800)
    check("process metrics shows reduction %", re.search(r"\d+\.\d%", page.inner_text(".bigpct")) is not None, page.inner_text(".bigpct"))
    # rule edit as Business Head
    goto(page, "governance"); page.wait_for_selector("[data-edit]")
    page.click('[data-edit="1"]'); page.wait_for_selector(".modal")
    page.select_option('[data-slot="1"]', "Marketing Manager"); page.click("#r-go"); page.wait_for_timeout(700)
    check("business head can change a rule (table-driven)", "Marketing Manager" in page.inner_text("#page").split("Approval rules")[1][:400])
    # mobile viewport
    page.set_viewport_size({"width": 390, "height": 844}); goto(page, "dashboard"); page.wait_for_timeout(900); shot(page, "11_mobile_dashboard")
    b.close()

js_errors = [e for e in errors]
check("no JavaScript errors in the console", not js_errors, "; ".join(js_errors[:3]))
failed = [c for c in checks if not c[1]]
print(f"\n{len(checks) - len(failed)}/{len(checks)} UI checks passed")
sys.exit(1 if failed else 0)
