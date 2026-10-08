"""Workflow automation (Apps Script: createApprovalRequest, sendApprovalNotification, processApproval,
processRejection, processRevision, dispatchCampaign + submission / modification / execution).

Every public function is ONE atomic business operation: the caller wraps it in db.transaction().
Every function checks the caller's role itself - the UI is never trusted.
"""
import json
import sqlite3

from . import audit, auth, clock
from . import constants as C
from . import rules as R
from .errors import (AccessDenied, DuplicateRequest, GovernanceViolation, InvalidState, LockedCampaign,
                     MissingData, NotFound, OutOfSequence)
from .governance import check_governance, get_campaign
from .notifications import inr, send_notification
from .validation import normalize, validate_campaign

EDITABLE_FIELDS = ["Region", "Campaign_Name", "Product", "Campaign_Type", "Objective", "Target_Audience",
                   "Marketing_Channel", "Start_Date", "End_Date", "Proposed_Budget", "Expected_Leads",
                   "Expected_Conversions", "Expected_Revenue", "Campaign_Description", "Creative_Link"]


# ----------------------------------------------------------------------------- helpers
def _must_get(conn, campaign_id):
    c = get_campaign(conn, campaign_id)
    if c is None:
        raise NotFound(f"Campaign {campaign_id} not found")
    return c


def _update(conn, campaign_id, **fields):
    fields["Updated_Timestamp"] = clock.ts()
    cols = ", ".join(f"{k}=?" for k in fields)
    try:
        conn.execute(f"UPDATE campaign_requests SET {cols} WHERE Campaign_ID=?", [*fields.values(), campaign_id])
    except sqlite3.IntegrityError as exc:  # database-level governance trigger fired
        msg = str(exc)
        e = GovernanceViolation(msg.replace("GOVERNANCE VIOLATION: ", ""))
        e.persist = False
        raise e from exc


def _deny(conn, user, c, exc_cls, message, action):
    """Record the blocked attempt in the audit trail, then raise (the transaction commits the audit row)."""
    audit.log_event(conn, user, action, c["Campaign_ID"] if c else None,
                    c["Approval_Status"] if c else None, c["Approval_Status"] if c else None, message)
    raise exc_cls(message)


def _approver_label(u):
    return f"{u['Name']} ({u['Role']})"


def _fmt_route(chain):
    return " → ".join(chain)


# ----------------------------------------------------------------------------- step 1: create
def create_campaign(conn, user, data, submit=True):
    """Business purpose: capture a campaign request from a Regional Marketing Executive (Google Form
    -> row in CAMPAIGN_REQUESTS), stamp it with a unique ID, requester and timestamps, and (optionally)
    push it straight into validation and approval routing."""
    if user["Role"] != C.ROLE_EXEC:
        raise AccessDenied("Only Regional Marketing Executives can raise campaign requests")
    data = dict(data or {})
    if not data.get("Region"):
        data["Region"] = user["Region"]
    if data["Region"] != user["Region"]:
        raise AccessDenied(f"You can only raise requests for your own region ({user['Region']})")
    d = normalize(data)

    if d.get("Campaign_Name") and d.get("Start_Date"):
        dup = conn.execute(
            "SELECT Campaign_ID FROM campaign_requests WHERE Requester_ID=? AND lower(trim(Campaign_Name))=lower(?)"
            " AND Start_Date=? AND Region=?",
            (user["User_ID"], d["Campaign_Name"], d["Start_Date"], d["Region"])).fetchone()
        if dup:
            audit.log_event(conn, user, "Duplicate Request Blocked", dup["Campaign_ID"], None, None,
                            f"Duplicate of {dup['Campaign_ID']}: '{d['Campaign_Name']}' starting {d['Start_Date']}")
            raise DuplicateRequest(
                f"Duplicate request: you already raised '{d['Campaign_Name']}' starting {d['Start_Date']} "
                f"as {dup['Campaign_ID']}. Open that request instead.", existing_id=dup["Campaign_ID"])

    cid = R.generate_campaign_id(conn)
    now = clock.ts()
    conn.execute(
        """INSERT INTO campaign_requests(Campaign_ID, Submission_Date, Region, Requester_Name, Requester_Email,
            Campaign_Name, Product, Campaign_Type, Objective, Target_Audience, Marketing_Channel, Start_Date, End_Date,
            Proposed_Budget, Expected_Leads, Expected_Conversions, Expected_Revenue, Campaign_Description, Creative_Link,
            Approval_Status, Execution_Status, Created_Timestamp, Updated_Timestamp, Requester_ID)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cid, clock.today().isoformat(), d["Region"], user["Name"], user["Email"], d.get("Campaign_Name"),
         d.get("Product"), d.get("Campaign_Type"), d.get("Objective"), d.get("Target_Audience"),
         d.get("Marketing_Channel"), d.get("Start_Date"), d.get("End_Date"), d.get("Proposed_Budget"),
         d.get("Expected_Leads"), d.get("Expected_Conversions"), d.get("Expected_Revenue"),
         d.get("Campaign_Description"), d.get("Creative_Link"), C.ST_DRAFT, C.EX_NOT_READY, now, now, user["User_ID"]))
    audit.log_event(conn, user, "Campaign Created", cid, None, C.ST_DRAFT,
                    f"'{d.get('Campaign_Name') or '(untitled)'}' created by {user['Name']} ({d['Region']})")
    if submit:
        result = submit_campaign(conn, user, cid)
    else:
        result = {"ok": True, "submitted": False, "campaign": get_campaign(conn, cid), "errors": []}
    result["campaign_id"] = cid
    return result


# ----------------------------------------------------------------------------- step 2/3: validate + route
def submit_campaign(conn, user, campaign_id):
    """Business purpose: run automated validation, then (if clean) the business rule engine and approval
    routing. Invalid requests are returned to the requester with the exact fields to fix."""
    c = _must_get(conn, campaign_id)
    if c["Requester_ID"] != user["User_ID"]:
        _deny(conn, user, c, AccessDenied, "Only the requester can submit this campaign", "Unauthorized Submit Attempt")
    if c["Approval_Status"] not in C.EDITABLE_STATUSES:
        raise InvalidState(f"Campaign is '{c['Approval_Status']}' and cannot be submitted again")

    prev = c["Approval_Status"]
    errors = validate_campaign(normalize(c))
    if errors:
        _update(conn, campaign_id, Approval_Status=C.ST_VALFAIL, Validation_Errors=json.dumps(errors),
                Current_Approver=None, Approval_Step=0, Execution_Status=C.EX_NOT_READY)
        audit.log_event(conn, user, "Validation Completed", campaign_id, prev, C.ST_VALFAIL,
                        f"FAILED - {len(errors)} issue(s): " + "; ".join(e["field"] for e in errors))
        requester = auth.get_user(conn, c["Requester_ID"])
        send_notification(conn, campaign_id, "Validation Failed", requester,
                          f"[{campaign_id}] Action needed: request returned - {len(errors)} field(s) to fix",
                          f"Hi {requester['Name']},\n\nYour request '{c['Campaign_Name'] or campaign_id}' could not be routed "
                          "for approval because of the following issues:\n\n" +
                          "\n".join(f"  - {e['message']}" for e in errors) +
                          "\n\nOpen the request, correct these fields and submit again.\n\n- Marketing Operations Automation")
        return {"ok": False, "submitted": True, "errors": errors, "campaign": get_campaign(conn, campaign_id)}

    audit.log_event(conn, user, "Validation Completed", campaign_id, prev, prev, "PASSED - all mandatory checks satisfied")
    return create_approval_request(conn, user, campaign_id, prev)


def create_approval_request(conn, user, campaign_id, prev_status=None):
    """Business purpose: use the rule engine to build the approval route from APPROVAL_RULES, open the
    request with the first approver and notify them - replacing the e-mail/WhatsApp chase."""
    c = _must_get(conn, campaign_id)
    prev_status = prev_status or c["Approval_Status"]
    route = R.determine_approval_level(conn, c["Proposed_Budget"])
    approvers = []
    for role in route["chain"]:
        a = auth.find_approver(conn, role, c["Region"])
        if not a:
            raise InvalidState(f"No active {role} is configured for {c['Region']}; cannot route the request")
        approvers.append(a)
    first = approvers[0]
    _update(conn, campaign_id, Approval_Status=C.ST_PENDING, Execution_Status=C.EX_NOT_READY,
            Approval_Chain=R.SEP.join(route["chain"]), Approval_Level=route["levels"], Rule_ID=route["rule_id"],
            Approval_Step=1, Current_Approver=_approver_label(first), Rejection_Reason=None, Validation_Errors=None,
            Revision_No=c["Revision_No"] + 1, Submitted_Timestamp=clock.ts(), Submission_Date=clock.today().isoformat(),
            Approved_Timestamp=None, Ready_Timestamp=None)
    audit.log_event(conn, user, "Approval Requested", campaign_id, prev_status, C.ST_PENDING,
                    f"{route['rule_name']}: {_fmt_route(route['chain'])} (revision {c['Revision_No'] + 1})")
    c = _must_get(conn, campaign_id)
    send_approval_notification(conn, c, first, 1, route["levels"])
    requester = auth.get_user(conn, c["Requester_ID"])
    send_notification(conn, campaign_id, "Submission Confirmed", requester,
                      f"[{campaign_id}] Request received and routed for approval",
                      f"Hi {requester['Name']},\n\nCampaign '{c['Campaign_Name']}' ({campaign_id}) passed validation.\n"
                      f"Budget: {inr(c['Proposed_Budget'])}  ->  {route['rule_name']}\n"
                      f"Approval route: {_fmt_route(route['chain'])}\nFirst approver: {first['Name']}\n\n"
                      "You will be notified automatically at each step.\n\n- Marketing Operations Automation")
    return {"ok": True, "submitted": True, "errors": [],
            "route": {**route, "approvers": [_approver_label(a) for a in approvers]},
            "campaign": c}


def send_approval_notification(conn, c, approver, step, total):
    """Business purpose: tell the next approver, with every decision-relevant fact in the message."""
    send_notification(
        conn, c["Campaign_ID"], "Approval Request", approver,
        f"[{c['Campaign_ID']}] Approval needed ({step}/{total}): {c['Campaign_Name']} - {inr(c['Proposed_Budget'])}",
        f"Hi {approver['Name']},\n\nA campaign is waiting for your approval (level {step} of {total}).\n\n"
        f"Campaign:   {c['Campaign_Name']} ({c['Campaign_ID']})\nRegion:     {c['Region']}\n"
        f"Requester:  {c['Requester_Name']}\nBudget:     {inr(c['Proposed_Budget'])}\nObjective:  {c['Objective']}\n"
        f"Audience:   {c['Target_Audience']}\nChannels:   {c['Marketing_Channel']}\n"
        f"Dates:      {c['Start_Date']} to {c['End_Date']}\n"
        f"Expected:   {c['Expected_Leads']:,} leads, {c['Expected_Conversions']:,} conversions, "
        f"{inr(c['Expected_Revenue'])} revenue\n\nOpen 'Pending Approvals' to approve, reject or send back.\n\n"
        "- Marketing Operations Automation")


# ----------------------------------------------------------------------------- modification
def modify_campaign(conn, user, campaign_id, data):
    """Business purpose: let the requester fix a draft / failed / rejected / sent-back request, while
    making it impossible to change a request once it is in approval or approved (that would let
    someone change the budget AFTER leadership signed off)."""
    c = _must_get(conn, campaign_id)
    if c["Requester_ID"] != user["User_ID"]:
        _deny(conn, user, c, AccessDenied, "Only the requester can modify this campaign", "Unauthorized Modification Attempt")
    if c["Approval_Status"] not in C.EDITABLE_STATUSES:
        _deny(conn, user, c, LockedCampaign,
              f"Campaign is '{c['Approval_Status']}' and locked for editing. Approved or in-approval requests cannot be "
              "changed - raise a new request instead.", "Modification Blocked")
    d = normalize({**c, **{k: v for k, v in (data or {}).items() if k in EDITABLE_FIELDS}})
    if d.get("Region") != user["Region"]:
        raise AccessDenied(f"You can only raise requests for your own region ({user['Region']})")
    changed = [k for k in EDITABLE_FIELDS if str(d.get(k) if d.get(k) is not None else "") != str(c.get(k) if c.get(k) is not None else "")]
    if changed:
        _update(conn, campaign_id, **{k: d.get(k) for k in changed})
        audit.log_event(conn, user, "Campaign Modified", campaign_id, c["Approval_Status"], c["Approval_Status"],
                        "Changed: " + ", ".join(changed))
    return get_campaign(conn, campaign_id)


# ----------------------------------------------------------------------------- step 4: approvals
def _authorize_decision(conn, user, c):
    """Role-based control: only the approver whose turn it is may decide."""
    if c["Approval_Status"] != C.ST_PENDING:
        raise InvalidState(f"Campaign {c['Campaign_ID']} is '{c['Approval_Status']}', not pending approval. "
                           "Execution is blocked until it is fully approved.")
    if user["User_ID"] == c["Requester_ID"]:
        _deny(conn, user, c, AccessDenied,
              "Access denied: you cannot approve a campaign you requested (segregation of duties)", "Unauthorized Approval Attempt")
    chain, step = c["Chain"], c["Approval_Step"]
    required = chain[step - 1]
    role = user["Role"]
    if role == required:
        if role == C.ROLE_RM and user["Region"] != c["Region"]:
            _deny(conn, user, c, AccessDenied,
                  f"Access denied: you are the Regional Manager for {user['Region']}, this campaign belongs to {c['Region']}",
                  "Unauthorized Approval Attempt")
        return step
    if role in chain:
        idx = chain.index(role) + 1
        if idx > step:
            _deny(conn, user, c, OutOfSequence,
                  f"Out of sequence: this campaign is still waiting for the {required} (level {step}) before your "
                  f"{role} approval (level {idx}) can be given", "Out-of-sequence Approval Attempt")
        raise InvalidState(f"Your level ({role}) has already been completed for this campaign")
    _deny(conn, user, c, AccessDenied,
          f"Access denied: the {role} role is not part of this campaign's approval route ({_fmt_route(chain)})",
          "Unauthorized Approval Attempt")


def _log_decision(conn, user, c, level, decision, comments, new_status):
    conn.execute(
        "INSERT INTO approval_log(Campaign_ID, Approver_Name, Approver_Role, Approval_Level, Decision, Decision_Date,"
        " Comments, Previous_Status, New_Status, Revision_No, Approver_ID) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (c["Campaign_ID"], user["Name"], user["Role"], level, decision, clock.ts(), comments or "",
         c["Approval_Status"], new_status, c["Revision_No"], user["User_ID"]))


def process_approval(conn, user, campaign_id, comments=""):
    """Business purpose: record an approval, advance the request to the next level, and - after the final
    level - run the governance gate and release the campaign for execution."""
    c = _must_get(conn, campaign_id)
    step = _authorize_decision(conn, user, c)
    total = len(c["Chain"])
    final = step == total
    _log_decision(conn, user, c, step, "Approved", comments, C.ST_APPROVED if final else C.ST_PENDING)
    audit.log_event(conn, user, "Approval Granted", campaign_id, C.ST_PENDING, C.ST_APPROVED if final else C.ST_PENDING,
                    f"Level {step}/{total} approved by {user['Name']} ({user['Role']})" + (f" - '{comments}'" if comments else ""))
    requester = auth.get_user(conn, c["Requester_ID"])

    if not final:
        nxt = auth.find_approver(conn, c["Chain"][step], c["Region"])
        _update(conn, campaign_id, Approval_Step=step + 1, Current_Approver=_approver_label(nxt))
        c2 = _must_get(conn, campaign_id)
        send_approval_notification(conn, c2, nxt, step + 1, total)
        send_notification(conn, campaign_id, "Approval Progress", requester,
                          f"[{campaign_id}] Level {step}/{total} approved - now with {nxt['Name']}",
                          f"Hi {requester['Name']},\n\n{user['Name']} ({user['Role']}) approved '{c['Campaign_Name']}'."
                          + (f"\nComment: {comments}" if comments else "") +
                          f"\nIt is now with {nxt['Name']} ({nxt['Role']}).\n\n- Marketing Operations Automation")
        return {"ok": True, "final": False, "campaign": c2, "next_approver": _approver_label(nxt)}

    # final level -> governance gate
    gov = check_governance(conn, campaign_id)
    if not gov["all_checks_pass"]:
        failed = [i["label"] + ": " + i["detail"] for i in gov["items"] if i["status"] != "pass"]
        e = GovernanceViolation("Final governance check failed - approval not completed. " + "; ".join(failed),
                                governance=gov)
        e.persist = False
        raise e
    _update(conn, campaign_id, Approval_Status=C.ST_APPROVED, Current_Approver=None, Approved_Timestamp=clock.ts())
    audit.log_event(conn, user, "Governance Check", campaign_id, C.ST_PENDING, C.ST_APPROVED,
                    f"FULLY COMPLIANT ({len(gov['items'])} controls passed)")
    audit.log_event(conn, user, "Campaign Fully Approved", campaign_id, C.ST_PENDING, C.ST_APPROVED,
                    f"All {total} required approval(s) complete")
    send_notification(conn, campaign_id, "Fully Approved", requester,
                      f"[{campaign_id}] Fully approved - '{c['Campaign_Name']}'",
                      f"Hi {requester['Name']},\n\nGreat news: '{c['Campaign_Name']}' has all {total} required approval(s) and "
                      f"passed the governance check. Budget approved: {inr(c['Proposed_Budget'])}.\n"
                      "It has been released to the execution team.\n\n- Marketing Operations Automation")
    disp = dispatch_campaign(conn, auth.SYSTEM_USER, campaign_id, auto=True)
    return {"ok": True, "final": True, "campaign": disp["campaign"], "governance": check_governance(conn, campaign_id)}


def process_rejection(conn, user, campaign_id, reason):
    """Business purpose: stop a campaign cleanly, with a mandatory reason, an audit record, and an
    automatic notice to the requester. A rejected campaign can never execute."""
    c = _must_get(conn, campaign_id)
    step = _authorize_decision(conn, user, c)
    if not (reason or "").strip():
        raise MissingData("A rejection reason is required")
    _log_decision(conn, user, c, step, "Rejected", reason, C.ST_REJECTED)
    _update(conn, campaign_id, Approval_Status=C.ST_REJECTED, Execution_Status=C.EX_NOT_READY,
            Current_Approver=None, Rejection_Reason=reason.strip())
    audit.log_event(conn, user, "Approval Rejected", campaign_id, C.ST_PENDING, C.ST_REJECTED,
                    f"Level {step} rejected by {user['Name']}: {reason.strip()}")
    requester = auth.get_user(conn, c["Requester_ID"])
    send_notification(conn, campaign_id, "Rejected", requester,
                      f"[{campaign_id}] Rejected by {user['Name']} - execution blocked",
                      f"Hi {requester['Name']},\n\n'{c['Campaign_Name']}' was rejected by {user['Name']} ({user['Role']}).\n"
                      f"Reason: {reason.strip()}\n\nThe campaign cannot be executed. You may revise the request and resubmit it.\n\n"
                      "- Marketing Operations Automation")
    return {"ok": True, "campaign": _must_get(conn, campaign_id)}


def process_revision(conn, user, campaign_id, comments):
    """Business purpose: 'send back for revision' - keeps the request alive but locks execution until the
    requester fixes the issue and the full approval chain is run again."""
    c = _must_get(conn, campaign_id)
    step = _authorize_decision(conn, user, c)
    if not (comments or "").strip():
        raise MissingData("Comments are required when sending a campaign back for revision")
    _log_decision(conn, user, c, step, "Sent Back", comments, C.ST_REWORK)
    _update(conn, campaign_id, Approval_Status=C.ST_REWORK, Execution_Status=C.EX_NOT_READY,
            Current_Approver=None, Rejection_Reason=comments.strip())
    audit.log_event(conn, user, "Sent Back for Revision", campaign_id, C.ST_PENDING, C.ST_REWORK,
                    f"Level {step}: {user['Name']} asked for changes - {comments.strip()}")
    requester = auth.get_user(conn, c["Requester_ID"])
    send_notification(conn, campaign_id, "Revision Requested", requester,
                      f"[{campaign_id}] Changes requested by {user['Name']}",
                      f"Hi {requester['Name']},\n\n{user['Name']} ({user['Role']}) sent '{c['Campaign_Name']}' back for revision.\n"
                      f"Comments: {comments.strip()}\n\nUpdate the request and resubmit; it will restart the approval chain.\n\n"
                      "- Marketing Operations Automation")
    return {"ok": True, "campaign": _must_get(conn, campaign_id)}


# ----------------------------------------------------------------------------- step 6: dispatch
def _execution_instructions(c):
    chans = c["Marketing_Channel"]
    return (f"  1. Build and publish assets on: {chans}.\n"
            f"  2. Creative brief / assets: {c['Creative_Link'] or 'see campaign description'}.\n"
            f"  3. Spend must stay within the approved budget of {inr(c['Proposed_Budget'])} - no overspend without re-approval.\n"
            f"  4. Run the campaign between {c['Start_Date']} and {c['End_Date']}; target audience: {c['Target_Audience']}.\n"
            f"  5. Capture every lead against {c['Campaign_ID']}; report spend, impressions and clicks weekly.\n"
            "  6. Mark the campaign 'Executed' in the system when it goes live.")


def dispatch_campaign(conn, user, campaign_id, auto=False):
    """Business purpose: the only door to Execution_Status = 'Ready for Execution'. It re-runs the governance
    check and refuses to release anything that is not fully approved and fully compliant, then notifies the
    execution team with everything they need."""
    allowed = {C.ROLE_SYSTEM, C.ROLE_EXECUTION, C.ROLE_MH, C.ROLE_BH}
    c = _must_get(conn, campaign_id)
    if user["Role"] not in allowed:
        _deny(conn, user, c, AccessDenied, f"Access denied: the {user['Role']} role cannot dispatch campaigns",
              "Unauthorized Dispatch Attempt")
    if c["Execution_Status"] in (C.EX_READY, C.EX_DONE):
        return {"ok": True, "already_dispatched": True, "campaign": c}
    gov = check_governance(conn, campaign_id)
    if not gov["can_execute"]:
        reasons = [f"{i['label']} - {i['detail']}" for i in gov["items"] if i["status"] != "pass"]
        _deny(conn, user, c, GovernanceViolation,
              f"Dispatch blocked: campaign is '{c['Approval_Status']}' ({gov['label']}). "
              + ("Open items: " + "; ".join(reasons) if reasons else ""), "Dispatch Blocked")
    prev_ex = c["Execution_Status"]
    try:
        _update(conn, campaign_id, Execution_Status=C.EX_READY, Ready_Timestamp=clock.ts())
    except GovernanceViolation as e:
        e.persist = True
        raise
    audit.log_event(conn, user, "Campaign Dispatched", campaign_id, prev_ex, C.EX_READY,
                    "Released to execution team" + (" automatically after final approval" if auto else ""))
    c = _must_get(conn, campaign_id)
    team = auth.users_with_role(conn, C.ROLE_EXECUTION)
    for member in team:
        send_notification(
            conn, campaign_id, "Execution Dispatch", member,
            f"[{campaign_id}] READY FOR EXECUTION - {c['Campaign_Name']} ({c['Region']})",
            f"Hi {member['Name']},\n\nThe following campaign is fully approved and ready to go live.\n\n"
            f"Campaign ID:     {c['Campaign_ID']}\nCampaign name:   {c['Campaign_Name']}\nRegion:          {c['Region']}\n"
            f"Approved budget: {inr(c['Proposed_Budget'])}\nCampaign dates:  {c['Start_Date']} to {c['End_Date']}\n"
            f"Objective:       {c['Objective']}\nApproval status: {c['Approval_Status']} ({c['Approval_Level']} level(s) complete, governance compliant)\n\n"
            f"Execution instructions:\n{_execution_instructions(c)}\n\n- Marketing Operations Automation")
    return {"ok": True, "already_dispatched": False, "campaign": c}


def mark_executed(conn, user, campaign_id):
    """Business purpose: the execution team confirms the campaign is live. Only a campaign that was
    dispatched (and therefore fully approved) can be executed; this also opens performance tracking."""
    c = _must_get(conn, campaign_id)
    if user["Role"] not in (C.ROLE_EXECUTION, C.ROLE_MH):
        _deny(conn, user, c, AccessDenied, f"Access denied: the {user['Role']} role cannot mark campaigns as executed",
              "Unauthorized Execution Attempt")
    if c["Execution_Status"] == C.EX_DONE:
        return {"ok": True, "campaign": c, "already_executed": True}
    if c["Execution_Status"] != C.EX_READY or c["Approval_Status"] != C.ST_APPROVED:
        _deny(conn, user, c, GovernanceViolation,
              f"Execution blocked: campaign is '{c['Approval_Status']}' / '{c['Execution_Status']}'. Only fully approved campaigns "
              "that were dispatched can be executed.", "Execution Blocked")
    _update(conn, campaign_id, Execution_Status=C.EX_DONE, Executed_Timestamp=clock.ts())
    conn.execute(
        "INSERT OR IGNORE INTO campaign_performance(Campaign_ID, Campaign_Name, Region, Budget, Last_Updated)"
        " VALUES (?,?,?,?,?)", (campaign_id, c["Campaign_Name"], c["Region"], c["Proposed_Budget"], clock.ts()))
    audit.log_event(conn, user, "Campaign Executed", campaign_id, C.EX_READY, C.EX_DONE,
                    f"Campaign live - marked executed by {user['Name']}")
    requester = auth.get_user(conn, c["Requester_ID"])
    send_notification(conn, campaign_id, "Campaign Live", requester,
                      f"[{campaign_id}] Campaign is live - lead tracking open",
                      f"Hi {requester['Name']},\n\n'{c['Campaign_Name']}' has been executed. Leads and performance now flow into the "
                      "dashboard automatically.\n\n- Marketing Operations Automation")
    return {"ok": True, "campaign": _must_get(conn, campaign_id), "already_executed": False}
