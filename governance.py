"""Governance control (Apps Script: checkGovernance()).

Business purpose: the single gate between 'a request' and 'money being spent'. A campaign may only
move to Ready for Execution if THIS function says it is fully compliant. The result is shown to
users as the visible Governance Check card.

State machine enforced:
    Pending Approval  -> cannot execute        Rejected -> cannot execute
    Rework Required   -> cannot execute        Fully Approved (all checks pass) -> can execute
"""
import json

from . import constants as C
from . import rules as R
from .validation import normalize, validate_campaign

PASS, PENDING, BLOCKED, FAIL = "pass", "pending", "blocked", "fail"


def get_campaign(conn, campaign_id):
    r = conn.execute("SELECT * FROM campaign_requests WHERE Campaign_ID=?", (campaign_id,)).fetchone()
    if not r:
        return None
    c = dict(r)
    c["Chain"] = [x for x in (c.get("Approval_Chain") or "").split(R.SEP) if x]
    try:
        c["Validation_Errors_List"] = json.loads(c["Validation_Errors"]) if c.get("Validation_Errors") else []
    except ValueError:
        c["Validation_Errors_List"] = []
    return c


def current_revision_log(conn, c):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM approval_log WHERE Campaign_ID=? AND Revision_No=? ORDER BY Approval_ID",
        (c["Campaign_ID"], c["Revision_No"]))]


def check_governance(conn, campaign_id):
    """Evaluate every control for one campaign and return a structured, displayable verdict."""
    c = get_campaign(conn, campaign_id)
    if c is None:
        return None
    log = current_revision_log(conn, c)
    items = []
    status = c["Approval_Status"]
    chain = c["Chain"]
    approved = {}
    for row in log:
        if row["Decision"] == "Approved":
            approved.setdefault(row["Approval_Level"], []).append(row)
    last_negative = next((row for row in reversed(log) if row["Decision"] in ("Rejected", "Sent Back")), None)

    # 1) one line per required approval level ----------------------------------------
    if not chain:
        items.append({"key": "route", "label": "Approval route determined", "status": PENDING,
                      "detail": "Request not yet routed (validate & submit first)"})
    for i, role in enumerate(chain, start=1):
        label = C.ROLE_APPROVAL_LABEL.get(role, role)
        rows = approved.get(i, [])
        if rows:
            row = rows[0]
            if row["Approver_Role"] != role:
                items.append({"key": f"level{i}", "label": label, "status": FAIL,
                              "detail": f"Level {i} was approved by {row['Approver_Name']} ({row['Approver_Role']}), not a {role}"})
            else:
                items.append({"key": f"level{i}", "label": label, "status": PASS,
                              "detail": f"Approved by {row['Approver_Name']} on {row['Decision_Date']}"})
        elif last_negative and last_negative["Approval_Level"] == i:
            verb = "Rejected" if last_negative["Decision"] == "Rejected" else "Sent back for revision"
            items.append({"key": f"level{i}", "label": label, "status": BLOCKED,
                          "detail": f"{verb} by {last_negative['Approver_Name']}"})
        elif status == C.ST_PENDING and i == c["Approval_Step"]:
            items.append({"key": f"level{i}", "label": label, "status": PENDING,
                          "detail": f"Awaiting decision from {c['Current_Approver']}"})
        else:
            items.append({"key": f"level{i}", "label": label, "status": PENDING, "detail": "Not yet reached"})

    # 2) approvals were given in the right order, once each -----------------------------
    seq = [row["Approval_Level"] for row in log if row["Decision"] == "Approved"]
    if seq == list(range(1, len(seq) + 1)):
        items.append({"key": "sequence", "label": "Approval sequence respected", "status": PASS,
                      "detail": "Levels approved strictly in order" if seq else "No approvals recorded yet"})
    else:
        items.append({"key": "sequence", "label": "Approval sequence respected", "status": FAIL,
                      "detail": f"Approval order was {seq}; expected 1..{len(seq)}"})

    # 3) segregation of duties --------------------------------------------------------------
    selfs = [row for row in log if row["Decision"] == "Approved" and row["Approver_ID"] == c["Requester_ID"]]
    items.append({"key": "sod", "label": "Segregation of duties (requester did not approve)",
                  "status": FAIL if selfs else PASS,
                  "detail": "Requester approved their own campaign" if selfs else "Requester and approvers are different people"})

    # 4) budget validation against the rule that routed it ------------------------------
    budget = c["Proposed_Budget"]
    if c["Rule_ID"] is None:
        items.append({"key": "budget", "label": "Budget validation", "status": PENDING,
                      "detail": "Budget not yet classified by the rule engine"})
    else:
        rule = conn.execute("SELECT * FROM approval_rules WHERE Rule_ID=?", (c["Rule_ID"],)).fetchone()
        ok = bool(rule) and budget is not None and budget > 0 and R.rule_covers(dict(rule), budget) \
            and len(chain) == c["Approval_Level"]
        items.append({"key": "budget", "label": "Budget validation", "status": PASS if ok else FAIL,
                      "detail": (f"₹{budget:,.0f} falls in '{rule['Rule_Name']}' ({c['Approval_Level']} level(s))"
                                 if ok else "Budget no longer matches the approval rule that routed this request")})

    # 5) mandatory fields -------------------------------------------------------------
    errs = validate_campaign(normalize(c), check_start_in_past=False)
    # incomplete fields on a not-yet-submitted request are expected (blocked); on a routed request they are a breach
    unsubmitted = status in (C.ST_DRAFT, C.ST_VALFAIL)
    items.append({"key": "fields", "label": "Mandatory fields",
                  "status": (BLOCKED if unsubmitted else FAIL) if errs else PASS,
                  "detail": ("Missing/invalid: " + ", ".join(e["field"] for e in errs)) if errs
                  else "All mandatory fields present and valid"})

    # 6) execution lock consistency ----------------------------------------------------
    inconsistent = c["Execution_Status"] in (C.EX_READY, C.EX_DONE) and status != C.ST_APPROVED
    items.append({"key": "lock", "label": "Execution lock consistent", "status": FAIL if inconsistent else PASS,
                  "detail": "Execution status is ahead of approval status" if inconsistent
                  else "Execution status consistent with approval status"})

    all_pass = all(i["status"] == PASS for i in items)
    any_fail = any(i["status"] == FAIL for i in items)

    if any_fail:
        state, label = "violation", "NON-COMPLIANT - EXECUTION BLOCKED"
    elif status == C.ST_APPROVED and all_pass:
        state, label = "compliant", "FULLY COMPLIANT"
    elif status == C.ST_PENDING:
        state, label = "pending", "PENDING APPROVAL - EXECUTION BLOCKED"
    elif status == C.ST_REJECTED:
        state, label = "blocked", "REJECTED - EXECUTION BLOCKED"
    elif status == C.ST_REWORK:
        state, label = "blocked", "REWORK REQUIRED - EXECUTION BLOCKED"
    elif status == C.ST_APPROVED:
        state, label = "violation", "NON-COMPLIANT - EXECUTION BLOCKED"
    else:
        state, label = "blocked", "NOT SUBMITTED - EXECUTION BLOCKED"

    return {
        "campaign_id": campaign_id,
        "campaign_name": c["Campaign_Name"],
        "approval_status": status,
        "execution_status": c["Execution_Status"],
        "items": items,
        "all_checks_pass": all_pass,
        "state": state,
        "label": label,
        "can_execute": state == "compliant",
        "revision_no": c["Revision_No"],
    }
