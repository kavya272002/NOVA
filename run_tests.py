"""Executable test suite + test report generator.

Run:  python tests/run_tests.py
Writes docs/TEST_REPORT.md and docs/test_results.json with the EXPECTED and ACTUAL result of every case.
Each test runs against a fresh copy of the seeded sample database.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import seed  # noqa: E402
from engine import analytics, auth, clock, db, demo, rules, tracking, workflow  # noqa: E402
from engine import constants as C  # noqa: E402
from engine.errors import (AccessDenied, DuplicateRequest, GovernanceViolation, InvalidState, LockedCampaign,  # noqa: E402
                           OutOfSequence, GovernanceError)
from engine.governance import check_governance, get_campaign  # noqa: E402

TMP = tempfile.mkdtemp(prefix="nova_tests_")
TEMPLATE = os.path.join(TMP, "template.db")
CASES = []


def case(tid, title, scenario, expected):
    def deco(fn):
        CASES.append({"id": tid, "title": title, "scenario": scenario, "expected": expected, "fn": fn})
        return fn
    return deco


class Env:
    """Fresh database + convenience helpers for one test."""
    _n = 0

    def __init__(self):
        Env._n += 1
        self.path = os.path.join(TMP, f"t{Env._n}.db")
        shutil.copy(TEMPLATE, self.path)
        db.DB_PATH = self.path
        self.conn = db.connect(self.path)
        self.seq = 0

    def u(self, name):
        return auth.get_user_by_email(self.conn, name.lower().replace(" ", ".") + "@novabrands.in")

    def payload(self, budget=150000, **over):
        self.seq += 1
        start = clock.today() + timedelta(days=5)
        d = {"Region": "Delhi NCR", "Campaign_Name": f"Test Campaign {Env._n}-{self.seq}", "Product": "NovaGlow Skincare",
             "Campaign_Type": "Lead Generation", "Objective": "Lead Generation",
             "Target_Audience": "Urban women 22-38 in Delhi NCR", "Marketing_Channel": "Instagram + Google Ads",
             "Start_Date": start.isoformat(), "End_Date": (start + timedelta(days=20)).isoformat(),
             "Proposed_Budget": budget, "Expected_Leads": 500, "Expected_Conversions": 50, "Expected_Revenue": 400000,
             "Campaign_Description": "A valid test campaign description that is long enough.", "Creative_Link": "https://example.com/c"}
        d.update(over)
        return d

    def create(self, budget=150000, who="Aman Sharma", submit=True, **over):
        with db.transaction(self.conn):
            return workflow.create_campaign(self.conn, self.u(who), self.payload(budget, **over), submit=submit)

    def approve(self, cid, who, comments=""):
        with db.transaction(self.conn):
            return workflow.process_approval(self.conn, self.u(who), cid, comments)

    def get(self, cid):
        return get_campaign(self.conn, cid)

    def audit_actions(self, cid):
        return [r["Action"] for r in self.conn.execute("SELECT Action FROM audit_trail WHERE Campaign_ID=? ORDER BY Audit_ID", (cid,))]


def raises(exc, fn):
    try:
        fn()
    except exc as e:  # noqa: PERF203
        return e
    raise AssertionError(f"Expected {exc.__name__} but the call succeeded")


# ================================================================== test cases
@case("T01", "Budget ₹30,000 routes to Regional Manager only", "Submit a valid ₹30,000 request",
      "Chain = Regional Manager (1 level)")
def t01(e):
    r = e.create(30000)
    assert r["route"]["chain"] == [C.ROLE_RM], r["route"]
    return f"Rule '{r['route']['rule_name']}' -> {' > '.join(r['route']['chain'])} ({r['route']['levels']} level)"


@case("T02", "Budget ₹1,50,000 routes to Regional Manager + Marketing Manager", "Submit a valid ₹1,50,000 request",
      "Chain = Regional Manager > Marketing Manager")
def t02(e):
    r = e.create(150000)
    assert r["route"]["chain"] == [C.ROLE_RM, C.ROLE_MM]
    return f"{r['route']['rule_name']} -> {' > '.join(r['route']['chain'])}"


@case("T03", "Budget ₹3,00,000 routes to all four approvers", "Submit a valid ₹3,00,000 request",
      "Chain = Regional Manager > Marketing Manager > Marketing Head > Business Head")
def t03(e):
    r = e.create(300000)
    assert r["route"]["chain"] == [C.ROLE_RM, C.ROLE_MM, C.ROLE_MH, C.ROLE_BH]
    return f"{r['route']['rule_name']} -> {' > '.join(r['route']['chain'])}"


@case("T04", "Rule boundaries are exact", "Classify ₹49,999 / ₹50,000 / ₹2,00,000 / ₹2,00,001",
      "1 / 2 / 2 / 4 approval levels")
def t04(e):
    got = [rules.determine_approval_level(e.conn, b)["levels"] for b in (49999, 50000, 200000, 200001)]
    assert got == [1, 2, 2, 4], got
    return "Levels: " + " / ".join(map(str, got))


@case("T05", "Missing campaign objective fails validation", "Submit a request with no Objective",
      "Status = Validation Failed; error names the Objective field; requester is notified; no approver is notified")
def t05(e):
    r = e.create(150000, Objective="")
    c = e.get(r["campaign_id"])
    assert c["Approval_Status"] == C.ST_VALFAIL and not r["ok"]
    assert any(x["field"] == "Objective" for x in r["errors"])
    n = e.conn.execute("SELECT Notification_Type FROM notifications WHERE Campaign_ID=?", (r["campaign_id"],)).fetchall()
    assert [x[0] for x in n] == ["Validation Failed"], [x[0] for x in n]
    return f"{c['Approval_Status']}; errors: " + "; ".join(x["message"] for x in r["errors"]) + "; notification: Validation Failed to requester"


@case("T06", "Invalid budget values are rejected", "Submit budgets of -5, 'abc', 0 and ₹60,00,000",
      "Each returns Validation Failed with a Proposed_Budget message")
def t06(e):
    msgs = []
    for b in (-5, "abc", 0, 6000000):
        r = e.create(b, Campaign_Name=f"Budget test {b}")
        err = [x["message"] for x in r["errors"] if x["field"] == "Proposed_Budget"]
        assert err, f"no budget error for {b}"
        msgs.append(f"{b!r}: {err[0]}")
    return " | ".join(msgs)


@case("T07", "Invalid dates are rejected", "Submit end-before-start, start in the past, and a 200-day campaign",
      "Date errors on Start_Date / End_Date for each")
def t07(e):
    today = clock.today()
    out = []
    for label, s, en in (("end<start", today + timedelta(days=10), today + timedelta(days=3)),
                         ("past start", today - timedelta(days=3), today + timedelta(days=10)),
                         ("200 days", today + timedelta(days=5), today + timedelta(days=205))):
        r = e.create(150000, Campaign_Name=f"Date test {label}", Start_Date=s.isoformat(), End_Date=en.isoformat())
        err = [x["message"] for x in r["errors"] if x["field"] in ("Start_Date", "End_Date")]
        assert err, label
        out.append(f"{label}: {err[0]}")
    return " | ".join(out)


@case("T08", "Expected conversions cannot exceed expected leads", "Submit 100 leads with 150 conversions",
      "Validation Failed on Expected_Conversions")
def t08(e):
    r = e.create(150000, Expected_Leads=100, Expected_Conversions=150)
    assert any(x["field"] == "Expected_Conversions" for x in r["errors"])
    return [x["message"] for x in r["errors"]][0]


@case("T09", "Duplicate request is blocked", "Submit the same name/region/start date twice",
      "Second submission raises DuplicateRequest, no new campaign is created, attempt is audited")
def t09(e):
    d = e.payload(150000)
    with db.transaction(e.conn):
        workflow.create_campaign(e.conn, e.u("Aman Sharma"), d)
    before = e.conn.execute("SELECT COUNT(*) FROM campaign_requests").fetchone()[0]
    def again():
        with db.transaction(e.conn):
            workflow.create_campaign(e.conn, e.u("Aman Sharma"), d)
    exc = raises(DuplicateRequest, again)
    after = e.conn.execute("SELECT COUNT(*) FROM campaign_requests").fetchone()[0]
    assert before == after
    logged = e.conn.execute("SELECT COUNT(*) FROM audit_trail WHERE Action='Duplicate Request Blocked'").fetchone()[0]
    assert logged == 1
    return f"Blocked: {exc.message[:90]}... (rows unchanged at {after}, audited)"


@case("T10", "Campaign IDs are unique and sequential", "Create three campaigns",
      "IDs follow MKT-<year>-NNN and increase by one")
def t10(e):
    ids = [e.create(40000)["campaign_id"] for _ in range(3)]
    nums = [int(i.split("-")[2]) for i in ids]
    assert nums == [nums[0], nums[0] + 1, nums[0] + 2] and all(i.startswith(f"MKT-{clock.now().year}-") for i in ids)
    return ", ".join(ids)


@case("T11", "Executive cannot approve their own campaign", "Aman Sharma (executive) tries to approve the campaign he raised",
      "AccessDenied; campaign remains Pending Approval; attempt is written to the audit trail")
def t11(e):
    cid = e.create(150000)["campaign_id"]
    exc = raises(AccessDenied, lambda: e.approve(cid, "Aman Sharma"))
    assert e.get(cid)["Approval_Status"] == C.ST_PENDING
    assert "Unauthorized Approval Attempt" in e.audit_actions(cid)
    return f"{exc.message} | status still {C.ST_PENDING} | audit: Unauthorized Approval Attempt"


@case("T12", "Segregation of duties: an approver cannot approve a request attributed to them",
      "Requester identity on a request is set to the Regional Manager (simulating a manager-raised request) and that manager tries to approve",
      "AccessDenied (segregation of duties)")
def t12(e):
    cid = e.create(30000)["campaign_id"]
    rm = e.u("Rahul Mehta")
    e.conn.execute("UPDATE campaign_requests SET Requester_ID=? WHERE Campaign_ID=?", (rm["User_ID"], cid))
    exc = raises(AccessDenied, lambda: e.approve(cid, "Rahul Mehta"))
    assert "segregation" in exc.message
    return exc.message


@case("T13", "Approval out of sequence is refused", "Marketing Manager tries to approve before the Regional Manager",
      "OutOfSequence; no approval recorded")
def t13(e):
    cid = e.create(150000)["campaign_id"]
    exc = raises(OutOfSequence, lambda: e.approve(cid, "Priya Kapoor"))
    n = e.conn.execute("SELECT COUNT(*) FROM approval_log WHERE Campaign_ID=?", (cid,)).fetchone()[0]
    assert n == 0
    return f"{exc.message} | approval_log rows: {n}"


@case("T14", "Regional Manager of another region is refused", "Mumbai's Vikram Desai tries to approve a Delhi NCR campaign",
      "AccessDenied (outside region)")
def t14(e):
    cid = e.create(30000)["campaign_id"]
    exc = raises(AccessDenied, lambda: e.approve(cid, "Vikram Desai"))
    return exc.message


@case("T15", "Dispatch before approval is blocked", "Execution Team tries to dispatch a Pending Approval campaign",
      "GovernanceViolation; Execution_Status stays 'Not Ready'; blocked attempt audited")
def t15(e):
    cid = e.create(150000)["campaign_id"]
    def go():
        with db.transaction(e.conn):
            workflow.dispatch_campaign(e.conn, e.u("Rohit Bansal"), cid)
    exc = raises(GovernanceViolation, go)
    assert e.get(cid)["Execution_Status"] == C.EX_NOT_READY
    assert "Dispatch Blocked" in e.audit_actions(cid)
    return f"{exc.message[:120]}... | Execution_Status = {e.get(cid)['Execution_Status']}"


@case("T16", "Database refuses 'Ready for Execution' without full approval", "Raw SQL: set Execution_Status='Ready for Execution' on a pending campaign",
      "SQLite trigger aborts the update (rule enforced below the application)")
def t16(e):
    cid = e.create(150000)["campaign_id"]
    try:
        e.conn.execute("UPDATE campaign_requests SET Execution_Status='Ready for Execution' WHERE Campaign_ID=?", (cid,))
    except sqlite3.IntegrityError as ex:
        return str(ex)
    raise AssertionError("trigger did not fire")


@case("T17", "Database refuses 'Fully Approved' without every required approval", "Raw SQL: set Approval_Status='Fully Approved' with 0 approvals logged",
      "SQLite trigger aborts the update")
def t17(e):
    cid = e.create(150000)["campaign_id"]
    try:
        e.conn.execute("UPDATE campaign_requests SET Approval_Status='Fully Approved' WHERE Campaign_ID=?", (cid,))
    except sqlite3.IntegrityError as ex:
        assert e.get(cid)["Approval_Status"] == C.ST_PENDING
        return str(ex)
    raise AssertionError("trigger did not fire")


@case("T18", "Rejected campaign cannot execute and requester is notified", "Regional Manager rejects (with and without a reason), then execution is attempted",
      "Reason is mandatory; status Rejected; dispatch blocked; requester receives a 'Rejected' e-mail")
def t18(e):
    cid = e.create(30000)["campaign_id"]
    rm = e.u("Rahul Mehta")
    def no_reason():
        with db.transaction(e.conn):
            workflow.process_rejection(e.conn, rm, cid, "  ")
    raises(Exception, no_reason)
    with db.transaction(e.conn):
        workflow.process_rejection(e.conn, rm, cid, "Budget duplicates the running Instagram campaign")
    c = e.get(cid)
    assert c["Approval_Status"] == C.ST_REJECTED and c["Execution_Status"] == C.EX_NOT_READY
    def disp():
        with db.transaction(e.conn):
            workflow.dispatch_campaign(e.conn, e.u("Rohit Bansal"), cid)
    raises(GovernanceViolation, disp)
    n = e.conn.execute("SELECT To_Name FROM notifications WHERE Campaign_ID=? AND Notification_Type='Rejected'", (cid,)).fetchone()
    assert n and n[0] == "Aman Sharma"
    return f"Status {c['Approval_Status']}, reason stored: '{c['Rejection_Reason']}', dispatch blocked, e-mail to {n[0]}"


@case("T19", "Send back for revision, edit, resubmit restarts the chain", "MM sends back at level 2; requester edits and resubmits",
      "Rework Required -> Pending Approval, Revision 2, approvals restart at Regional Manager; old approvals do not count")
def t19(e):
    cid = e.create(150000)["campaign_id"]
    e.approve(cid, "Rahul Mehta")
    with db.transaction(e.conn):
        workflow.process_revision(e.conn, e.u("Priya Kapoor"), cid, "Split the target audience by locality")
    assert e.get(cid)["Approval_Status"] == C.ST_REWORK
    with db.transaction(e.conn):
        workflow.modify_campaign(e.conn, e.u("Aman Sharma"), cid, {"Target_Audience": "Women 22-30 in South Delhi and Gurugram"})
        workflow.submit_campaign(e.conn, e.u("Aman Sharma"), cid)
    c = e.get(cid)
    assert c["Approval_Status"] == C.ST_PENDING and c["Revision_No"] == 2 and c["Approval_Step"] == 1
    gov = check_governance(e.conn, cid)
    assert gov["items"][0]["status"] == "pending"
    return f"Status {c['Approval_Status']}, revision {c['Revision_No']}, current approver {c['Current_Approver']}; level-1 control shows '{gov['items'][0]['status']}'"


@case("T20", "Campaign cannot be modified while pending or after approval", "Requester edits a pending campaign and an approved campaign; raw SQL edits budget of a pending campaign",
      "App refuses with 'locked'; DB trigger refuses the raw edit; edit attempts audited")
def t20(e):
    cid = e.create(30000)["campaign_id"]
    raises(LockedCampaign, lambda: _modify(e, cid, {"Proposed_Budget": 10000}))
    try:
        e.conn.execute("UPDATE campaign_requests SET Proposed_Budget=1 WHERE Campaign_ID=?", (cid,))
        raise AssertionError("freeze trigger did not fire")
    except sqlite3.IntegrityError as ex:
        trig = str(ex)
    e.approve(cid, "Rahul Mehta")
    assert e.get(cid)["Approval_Status"] == C.ST_APPROVED
    exc = raises(LockedCampaign, lambda: _modify(e, cid, {"Proposed_Budget": 9999999}))
    assert "Modification Blocked" in e.audit_actions(cid)
    return f"App: {exc.message[:80]}... | DB: {trig}"


def _modify(e, cid, data):
    with db.transaction(e.conn):
        workflow.modify_campaign(e.conn, e.u("Aman Sharma"), cid, data)


@case("T21", "Approval log and audit trail are append-only", "Raw SQL UPDATE and DELETE against APPROVAL_LOG and AUDIT_TRAIL",
      "All four statements are aborted by triggers")
def t21(e):
    cid = e.create(30000)["campaign_id"]
    e.approve(cid, "Rahul Mehta")
    out = []
    for sql in ("UPDATE approval_log SET Decision='Rejected'", "DELETE FROM approval_log",
                "UPDATE audit_trail SET User='X'", "DELETE FROM audit_trail"):
        try:
            e.conn.execute(sql)
            raise AssertionError("not blocked: " + sql)
        except sqlite3.IntegrityError as ex:
            out.append(str(ex).replace("AUDIT PROTECTION: ", ""))
    return f"{len(out)}/4 blocked ({out[0]})"


@case("T22", "Two-level happy path to Ready for Execution", "₹1,50,000: Rahul Mehta then Priya Kapoor approve",
      "Fully Approved, governance FULLY COMPLIANT, Ready for Execution, execution team e-mail contains all required fields")
def t22(e):
    cid = e.create(150000)["campaign_id"]
    r1 = e.approve(cid, "Rahul Mehta")
    assert not r1["final"] and e.get(cid)["Approval_Status"] == C.ST_PENDING
    r2 = e.approve(cid, "Priya Kapoor")
    c = e.get(cid)
    assert r2["final"] and c["Approval_Status"] == C.ST_APPROVED and c["Execution_Status"] == C.EX_READY
    g = check_governance(e.conn, cid)
    assert g["label"] == "FULLY COMPLIANT" and g["can_execute"]
    mail = e.conn.execute("SELECT Subject, Body FROM notifications WHERE Campaign_ID=? AND Notification_Type='Execution Dispatch'", (cid,)).fetchone()
    for needle in (cid, c["Campaign_Name"], c["Region"], "₹1,50,000", c["Start_Date"], c["Objective"], "Fully Approved", "Execution instructions"):
        assert needle in mail["Body"], needle
    return f"{c['Approval_Status']} / {c['Execution_Status']} / {g['label']}; dispatch e-mail has ID, name, region, budget, dates, objective, status, instructions"


@case("T23", "Four-level path needs all four approvals", "₹3,00,000: approve in order; check state after each level",
      "Pending after levels 1-3; Fully Approved only after Business Head; 4 approvals logged")
def t23(e):
    cid = e.create(300000)["campaign_id"]
    states = []
    for who in ("Rahul Mehta", "Priya Kapoor", "Arjun Malhotra", "Neha Verma"):
        e.approve(cid, who)
        states.append(e.get(cid)["Approval_Status"])
    assert states == [C.ST_PENDING] * 3 + [C.ST_APPROVED], states
    n = e.conn.execute("SELECT COUNT(*) FROM approval_log WHERE Campaign_ID=? AND Decision='Approved'", (cid,)).fetchone()[0]
    assert n == 4
    return " -> ".join(states) + f"; {n} approvals logged"


@case("T24", "Only executives of their own region can raise requests", "Regional Manager creates a request; Delhi executive creates a Mumbai request",
      "Both are AccessDenied")
def t24(e):
    exc1 = raises(AccessDenied, lambda: e.create(30000, who="Rahul Mehta"))
    exc2 = raises(AccessDenied, lambda: e.create(30000, Region="Mumbai"))
    return f"{exc1.message} | {exc2.message}"


@case("T25", "Execution requires dispatch; execution opens performance tracking", "Mark executed before and after dispatch",
      "Blocked before approval; allowed after; performance row created")
def t25(e):
    cid = e.create(30000)["campaign_id"]
    def ex():
        with db.transaction(e.conn):
            workflow.mark_executed(e.conn, e.u("Rohit Bansal"), cid)
    raises(GovernanceViolation, ex)
    e.approve(cid, "Rahul Mehta")
    ex()
    c = e.get(cid)
    p = e.conn.execute("SELECT * FROM campaign_performance WHERE Campaign_ID=?", (cid,)).fetchone()
    assert c["Execution_Status"] == C.EX_DONE and p is not None
    return f"Blocked while pending; after approval -> {c['Execution_Status']}; performance row created (Budget {p['Budget']:,.0f})"


@case("T26", "Missing lead data is handled", "Update performance with no leads; add a lead to a non-executed campaign",
      "Warning + blank CPL/ROAS (no crash); lead on non-executed campaign refused")
def t26(e):
    cid = e.create(30000)["campaign_id"]
    e.approve(cid, "Rahul Mehta")
    with db.transaction(e.conn):
        workflow.mark_executed(e.conn, e.u("Rohit Bansal"), cid)
    with db.transaction(e.conn):
        res = tracking.update_performance(e.conn, e.u("Rohit Bansal"), cid, impressions=1000, clicks=50, actual_spend=5000)
    assert res["warnings"] and res["performance"]["CPL"] is None and res["performance"]["Conversion_Rate"] is None
    cid2 = e.create(30000)["campaign_id"]
    def lead():
        with db.transaction(e.conn):
            tracking.add_lead(e.conn, e.u("Rohit Bansal"), cid2, {})
    raises(InvalidState, lead)
    return f"Warning: '{res['warnings'][0][:70]}...'; CPL = {res['performance']['CPL']}; lead on non-executed campaign refused"


@case("T27", "KPI formulas: CPL, conversion rate, ROAS, ROI", "Check MKT-2026-001 (spec example: 850 leads, 95 conversions, ₹7,20,000 revenue)",
      "CPL = spend/leads, Conv. rate = conversions/leads, ROAS = revenue/spend, ROI = (revenue-spend)/spend")
def t27(e):
    e.conn.execute(
        """INSERT INTO campaign_performance (Campaign_ID, Campaign_Name, Region, Budget, Actual_Spend, Impressions, Clicks, Leads, Qualified_Leads, Conversions, Revenue, Last_Updated)
           VALUES ('MKT-2026-001', 'Summer Glow', 'Delhi NCR', 120000, 108500, 250000, 12500, 850, 420, 95, 720000, datetime('now'))
           ON CONFLICT(Campaign_ID) DO UPDATE SET Actual_Spend=108500, Impressions=250000, Clicks=12500, Leads=850, Qualified_Leads=420, Conversions=95, Revenue=720000"""
    )
    p = dict(e.conn.execute("SELECT * FROM campaign_performance WHERE Campaign_ID='MKT-2026-001'").fetchone())
    assert (p["Impressions"], p["Clicks"], p["Leads"], p["Qualified_Leads"], p["Conversions"], p["Revenue"]) == (250000, 12500, 850, 420, 95, 720000)
    assert abs(p["CPL"] - p["Actual_Spend"] / 850) < 1e-9
    assert abs(p["Conversion_Rate"] - 95 / 850) < 1e-12
    assert abs(p["ROAS"] - 720000 / p["Actual_Spend"]) < 1e-12
    assert abs(p["ROI"] - (720000 - p["Actual_Spend"]) / p["Actual_Spend"]) < 1e-12
    return (f"Spend ₹{p['Actual_Spend']:,.0f}: CPL ₹{p['CPL']:.2f}, conversion {p['Conversion_Rate']*100:.2f}%, "
            f"ROAS {p['ROAS']:.2f}x, ROI {p['ROI']*100:.1f}%")


@case("T28", "Lead roll-up reconciles with LEAD_DATA", "Compare CAMPAIGN_PERFORMANCE totals with a recount of LEAD_DATA for every executed campaign",
      "Leads, qualified, conversions and revenue match exactly for all campaigns")
def t28(e):
    bad = 0
    rows = e.conn.execute("SELECT * FROM campaign_performance").fetchall()
    for p in rows:
        r = tracking.rollup_leads(e.conn, p["Campaign_ID"])
        if (r["leads"], r["qualified"], r["conversions"], r["revenue"]) != (p["Leads"], p["Qualified_Leads"], p["Conversions"], p["Revenue"]):
            bad += 1
    total = e.conn.execute("SELECT COUNT(*) FROM lead_data").fetchone()[0]
    assert bad == 0
    return f"{len(rows)} campaigns reconcile; {total:,} lead rows"


@case("T29", "Dashboard filters and role scoping", "Compare Delhi NCR filter to its raw count; executive sees only own campaigns; regional manager sees own region",
      "Counts equal; executive and RM scopes enforced")
def t29(e):
    mgmt, ex, rm = e.u("Neha Verma"), e.u("Aman Sharma"), e.u("Rahul Mehta")
    k = analytics.calculate_kpis(e.conn, mgmt, {"region": "Delhi NCR"})
    raw = e.conn.execute("SELECT COUNT(*) FROM campaign_requests WHERE Region='Delhi NCR'").fetchone()[0]
    assert k["total"] == raw
    own = e.conn.execute("SELECT COUNT(*) FROM campaign_requests WHERE Requester_ID=?", (ex["User_ID"],)).fetchone()[0]
    assert analytics.calculate_kpis(e.conn, ex)["total"] == own
    assert all(c["Region"] == "Delhi NCR" for c in analytics.list_campaigns(e.conn, rm))
    chan = analytics.calculate_kpis(e.conn, mgmt, {"channel": "Instagram"})["total"]
    return f"Delhi NCR filter = {k['total']} (raw {raw}); Aman sees {own}; RM scope = Delhi only; channel 'Instagram' matches {chan}"


@case("T30", "Approval rules are table-driven, not hard-coded", "Business Head changes Tier 1 to require RM + MM; a ₹30,000 request is submitted",
      "New request routes to RM > MM; an invalid rule set (gap) is rejected")
def t30(e):
    e.conn.execute("UPDATE approval_rules SET Approval_Chain=? WHERE Rule_ID=1", ("Regional Manager|Marketing Manager",))
    r = e.create(30000)
    assert r["route"]["chain"] == [C.ROLE_RM, C.ROLE_MM]
    rs = [dict(x) for x in e.conn.execute("SELECT * FROM approval_rules")]
    rs[0]["Max_Budget"] = 40000  # creates a gap 40,000-50,000
    problems = rules.check_rule_set(rs)
    assert problems
    return f"₹30,000 now routes {' > '.join(r['route']['chain'])}; invalid edit rejected: {problems[0]}"


@case("T31", "Process metrics: reduction formula", "Compute (Before - After) / Before x 100 from measured timestamps",
      "Matches manual calculation; measured average for standard requests < 25 min")
def t31(e):
    pm = analytics.process_metrics(e.conn)
    after, before = pm["after"]["avg_minutes_standard"], pm["before"]["avg_minutes"]
    manual = (before - after) / before * 100
    assert abs(manual - pm["reduction_measured_pct"]) < 1e-9 and after < 25
    return (f"Before {before:.0f} min -> after {after:.1f} min (n={pm['after']['standard_count']}) = {manual:.1f}% reduction; "
            f"at the 25-min ceiling = {pm['reduction_at_target_pct']:.1f}%")


@case("T32", "Audit trail covers the whole lifecycle", "Run a campaign from creation to performance; list audit events",
      "Created, Validation Completed, Approval Requested, Approval Granted, Campaign Dispatched, Campaign Executed, Performance Updated all present with user, timestamp and status transition")
def t32(e):
    cid = e.create(30000)["campaign_id"]
    e.approve(cid, "Rahul Mehta")
    with db.transaction(e.conn):
        workflow.mark_executed(e.conn, e.u("Rohit Bansal"), cid)
    with db.transaction(e.conn):
        tracking.simulate_results(e.conn, e.u("Rohit Bansal"), cid)
    acts = e.audit_actions(cid)
    need = ["Campaign Created", "Validation Completed", "Approval Requested", "Approval Granted", "Campaign Dispatched",
            "Campaign Executed", "Performance Updated"]
    assert all(a in acts for a in need), acts
    row = e.conn.execute("SELECT * FROM audit_trail WHERE Campaign_ID=? AND Action='Approval Granted'", (cid,)).fetchone()
    assert row["User"] == "Rahul Mehta" and row["Timestamp"] and row["Previous_Status"] and row["New_Status"]
    rj = e.create(30000)["campaign_id"]
    with db.transaction(e.conn):
        workflow.process_rejection(e.conn, e.u("Rahul Mehta"), rj, "Not aligned")
    assert "Approval Rejected" in e.audit_actions(rj)
    return f"{len(acts)} events: " + ", ".join(dict.fromkeys(acts))


@case("T33", "Scripted Diwali demo runs end to end", "Run the 15-step Diwali Smart Savings scenario (₹1,80,000, Delhi NCR)",
      "Campaign created, routed RM > MM, fully approved, Ready for Execution, executed with leads; dashboard KPIs increase")
def t33(e):
    mgmt = e.u("Neha Verma")
    k0 = analytics.calculate_kpis(e.conn, mgmt)
    res = demo.run_scenario(e.conn)
    cid = res["campaign_id"]
    c = e.get(cid)
    k1 = analytics.calculate_kpis(e.conn, mgmt)
    assert c["Proposed_Budget"] == 180000 and c["Approval_Level"] == 2 and c["Approval_Status"] == C.ST_APPROVED
    assert c["Execution_Status"] == C.EX_DONE
    assert k1["total"] == k0["total"] + 1 and k1["leads"] > k0["leads"]
    cycle = clock.minutes_between(c["Submitted_Timestamp"], c["Approved_Timestamp"])
    return (f"{cid}: {len(res['steps'])} steps in {res['total_seconds']}s; budget ₹{c['Proposed_Budget']:,.0f}, "
            f"route {c['Approval_Chain'].replace('|', ' > ')}; campaigns {k0['total']}->{k1['total']}, leads {k0['leads']:,}->{k1['leads']:,}")


@case("T34", "Every executed/dispatched campaign in the data set is governance-compliant", "Run check_governance on all Ready/Executed campaigns",
      "100% FULLY COMPLIANT")
def t34(e):
    ids = [r[0] for r in e.conn.execute("SELECT Campaign_ID FROM campaign_requests WHERE Execution_Status IN ('Ready for Execution','Executed')")]
    ok = [i for i in ids if check_governance(e.conn, i)["label"] == "FULLY COMPLIANT"]
    assert ids and len(ok) == len(ids)
    return f"{len(ok)}/{len(ids)} compliant (100%)"


@case("T35", "HTTP layer enforces roles", "Unauthenticated call; executive POSTs /approve; executive GETs the audit export; manager approves via API",
      "401, 403, 403, 200")
def t35(e):
    import app as A
    cl = A.app.test_client()
    r0 = cl.get("/api/campaigns")
    cl.post("/api/login", json={"email": "aman.sharma@novabrands.in", "password": "Demo@123"})
    cid = cl.post("/api/campaigns", json={"data": e.payload(30000), "submit": True}).json["campaign_id"]
    r1 = cl.post(f"/api/campaigns/{cid}/approve", json={})
    r2 = cl.get("/api/export/audit_trail.csv")
    cl.post("/api/login", json={"email": "rahul.mehta@novabrands.in", "password": "Demo@123"})
    r3 = cl.post(f"/api/campaigns/{cid}/approve", json={"comments": "ok"})
    assert (r0.status_code, r1.status_code, r2.status_code, r3.status_code) == (401, 403, 403, 200), (r0.status_code, r1.status_code, r2.status_code, r3.status_code)
    bad = cl.post("/api/login", json={"email": "rahul.mehta@novabrands.in", "password": "wrong"})
    assert bad.status_code == 401
    return f"{r0.status_code}, {r1.status_code} ({r1.json['error'][:50]}...), {r2.status_code}, {r3.status_code}; wrong password -> 401"


# ================================================================== runner
def main():
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    db.DB_PATH = TEMPLATE
    conn, _ = seed.run(TEMPLATE)
    conn.close()
    results, started = [], time.time()
    for c in CASES:
        t0 = time.time()
        env = Env()
        try:
            actual = c["fn"](env)
            status = "PASS"
        except Exception as ex:  # noqa: BLE001
            status = "FAIL"
            actual = f"{type(ex).__name__}: {ex}\n{traceback.format_exc(limit=3)}"
        finally:
            clock.clear()
            env.conn.close()
        results.append({**{k: c[k] for k in ("id", "title", "scenario", "expected")}, "actual": actual, "status": status,
                        "ms": round((time.time() - t0) * 1000)})
        title_safe = c['title'].replace('₹', 'Rs.')
        print(f"{status}  {c['id']}  {title_safe}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"\n{passed}/{len(results)} passed in {time.time() - started:.1f}s")
    with open(os.path.join(ROOT, "docs", "test_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    write_report(results, passed)
    shutil.rmtree(TMP, ignore_errors=True)
    return 0 if passed == len(results) else 1


def write_report(results, passed):
    L = ["# Test Report", "",
         f"**Result: {passed} of {len(results)} test cases passed.**  ",
         f"Generated by `python tests/run_tests.py` on {time.strftime('%Y-%m-%d %H:%M')} against a fresh copy of the seeded sample database for every test.", "",
         "> All data is simulated for an academic project. 'Actual' is the real output captured from the running system, not hand-written.", "",
         "| # | Test | Result |", "|---|------|--------|"]
    for r in results:
        L.append(f"| {r['id']} | {r['title']} | {'✅ PASS' if r['status'] == 'PASS' else '❌ FAIL'} |")
    L.append("")
    for r in results:
        L += [f"## {r['id']} - {r['title']}", f"- **Scenario:** {r['scenario']}", f"- **Expected:** {r['expected']}",
              f"- **Actual:** {r['actual']}", f"- **Result:** {'PASS' if r['status'] == 'PASS' else 'FAIL'}", ""]
    with open(os.path.join(ROOT, "docs", "TEST_REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
