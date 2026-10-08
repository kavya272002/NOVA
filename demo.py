"""Executive-demo helpers: the Diwali Smart Savings scenario (pre-fill + one-click end-to-end run)."""
import time
from datetime import timedelta

from . import analytics, auth, clock, db, tracking, workflow
from . import constants as C
from .errors import GovernanceError
from .governance import check_governance
from .notifications import inr


def diwali_payload():
    start = clock.today() + timedelta(days=7)
    return {
        "Region": "Delhi NCR", "Campaign_Name": "Diwali Smart Savings Campaign", "Product": "Voltix Smart Appliances",
        "Campaign_Type": "Festive Promotion", "Objective": "Lead Generation",
        "Target_Audience": "Urban families in Delhi NCR (25-45 yrs) planning festive appliance upgrades",
        "Marketing_Channel": "Instagram + Google Ads", "Start_Date": start.isoformat(),
        "End_Date": (start + timedelta(days=27)).isoformat(), "Proposed_Budget": 180000, "Expected_Leads": 800,
        "Expected_Conversions": 80, "Expected_Revenue": 640000,
        "Campaign_Description": "Festive savings campaign promoting energy-efficient smart appliances with Diwali bundle offers, "
                                "driven by Instagram reels and Google search and shopping ads.",
        "Creative_Link": "https://drive.novabrands.in/creatives/diwali-smart-savings",
    }


def run_scenario(conn):
    """Run the full 15-step demo flow through the real engine, step by step, and return a readable log."""
    steps = []
    t0 = time.time()

    def add(actor, action, result, ok=True):
        steps.append({"n": len(steps) + 1, "actor": actor, "action": action, "result": result, "ok": ok,
                      "t": round(time.time() - t0, 2)})

    exec_u = auth.get_user_by_email(conn, "aman.sharma@novabrands.in")
    data = diwali_payload()
    dup = conn.execute("SELECT COUNT(*) FROM campaign_requests WHERE Campaign_Name LIKE ?", ("Diwali Smart Savings Campaign%",)).fetchone()[0]
    if dup:
        data["Campaign_Name"] += f" - Demo Run {dup + 1}"
    k0 = analytics.calculate_kpis(conn, auth.get_user_by_email(conn, "neha.verma@novabrands.in"))
    add(exec_u["Name"], "Logged in as Regional Marketing Executive (Delhi NCR)", "Session started")
    with db.transaction(conn):
        res = workflow.create_campaign(conn, exec_u, data, submit=True)
    cid = res["campaign_id"]
    add(exec_u["Name"], "Created and submitted the campaign", f"Campaign ID generated: {cid}")
    add("Automation engine", "Validated required fields, budget, dates, leads, conversions, objective, audience",
        "PASSED - no issues" if res["ok"] else "FAILED")
    route = res["route"]
    add("Rule engine", f"Classified budget {inr(data['Proposed_Budget'])} using APPROVAL_RULES",
        f"{route['rule_name']} -> " + " -> ".join(route["chain"]))
    chain = route["chain"]
    for i, role in enumerate(chain):
        approver = auth.find_approver(conn, role, data["Region"])
        with db.transaction(conn):
            r = workflow.process_approval(conn, approver, cid, "Approved via demo walkthrough")
        add(approver["Name"], f"Logged in as {role} and approved (level {i + 1}/{len(chain)})",
            "Fully approved" if r["final"] else f"Passed to {r['next_approver']}")
    gov = check_governance(conn, cid)
    add("Governance engine", f"Ran {len(gov['items'])} governance controls", gov["label"])
    c = workflow.get_campaign(conn, cid)
    add("Automation engine", "Set approval status", c["Approval_Status"])
    add("Automation engine", "Dispatched to execution team (e-mail sent)", c["Execution_Status"])
    executor = auth.get_user_by_email(conn, "rohit.bansal@novabrands.in")
    with db.transaction(conn):
        workflow.mark_executed(conn, executor, cid)
    add(executor["Name"], "Marked the campaign as executed (live)", "Lead tracking opened")
    with db.transaction(conn):
        sim = tracking.simulate_results(conn, executor, cid)
    p = sim["performance"]
    add("CRM / ad platforms (simulated feed)", "Loaded leads and performance",
        f"{p['Leads']} leads, {p['Conversions']} conversions, CPL {inr(p['CPL'])}, ROAS {p['ROAS']:.2f}x")
    k1 = analytics.calculate_kpis(conn, auth.get_user_by_email(conn, "neha.verma@novabrands.in"))
    add("Dashboard", "KPIs refreshed",
        f"Campaigns {k0['total']} -> {k1['total']}; leads {k0['leads']:,} -> {k1['leads']:,}; approved {k0['approved']} -> {k1['approved']}")
    return {"campaign_id": cid, "steps": steps, "total_seconds": round(time.time() - t0, 2)}
