"""Nova Consumer Brands - Marketing Operations Control Center (local prototype).

Layer mapping to the Google stack:
    static/ (this SPA)     -> AppSheet user interface + Google Form input
    SQLite (engine/db.py)  -> Google Sheets database
    engine/*.py            -> Google Apps Script automation engine (see /apps_script)
    notifications outbox   -> Gmail
    /api/dashboard         -> Looker Studio

Run:  python app.py      then open http://127.0.0.1:5000
"""
import csv
import io
import os
import sqlite3

from flask import Flask, Response, g, jsonify, request, send_from_directory, session

import seed
from engine import analytics, audit, auth, clock, db, demo, messaging, rules, tracking, workflow
from engine import constants as C
from engine.errors import AccessDenied, GovernanceError, MissingData, NotFound
from engine.governance import check_governance, get_campaign

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.environ.get("NOVA_SECRET", "nova-demo-secret-change-me")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
DEMO_MODE = os.environ.get("NOVA_DEMO", "1") == "1"

# Ensure database exists when running via WSGI (e.g. Gunicorn / Render / PythonAnywhere)
if not os.path.exists(db.DB_PATH):
    seed.run()



# ----------------------------------------------------------------------------- plumbing
def conn():
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


@app.teardown_appcontext
def _close(_exc):
    c = g.pop("conn", None)
    if c is not None:
        c.close()


def current_user():
    uid = session.get("uid")
    return auth.get_user(conn(), uid) if uid else None


def login_required(roles=None):
    def deco(fn):
        from functools import wraps

        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return jsonify({"error": "Please sign in", "code": "UNAUTHENTICATED"}), 401
            if roles and u["Role"] not in roles:
                return jsonify({"error": f"Access denied: the {u['Role']} role cannot use this function", "code": "ACCESS_DENIED"}), 403
            g.user = u
            return fn(*a, **kw)
        return wrapper
    return deco


@app.errorhandler(GovernanceError)
def _gov_error(e):
    return jsonify(e.to_dict()), e.status


@app.errorhandler(sqlite3.IntegrityError)
def _integrity(e):
    msg = str(e).replace("GOVERNANCE VIOLATION: ", "").replace("AUDIT PROTECTION: ", "")
    return jsonify({"error": msg, "code": "DATABASE_RULE"}), 409


def body():
    return request.get_json(silent=True) or {}


def filters():
    return {k: request.args.get(k) for k in analytics.FILTER_KEYS if request.args.get(k)}


def permissions(u):
    r = u["Role"]
    return {
        "create_campaign": r == C.ROLE_EXEC,
        "approve": r in C.APPROVER_ROLES,
        "dispatch": r in (C.ROLE_EXECUTION, C.ROLE_MH, C.ROLE_BH),
        "execute": r in (C.ROLE_EXECUTION, C.ROLE_MH),
        "load_results": r in (C.ROLE_EXECUTION, C.ROLE_MH),
        "add_leads": r in (C.ROLE_EXECUTION, C.ROLE_MM, C.ROLE_MH, C.ROLE_EXEC),
        "edit_rules": r == C.ROLE_BH,
        "reset_demo": r in C.MANAGEMENT_ROLES and DEMO_MODE,
        "view_all_audit": r in C.MANAGEMENT_ROLES,
        "run_scenario": DEMO_MODE and r in (C.ROLE_MH, C.ROLE_BH),
    }


# ----------------------------------------------------------------------------- static
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ----------------------------------------------------------------------------- auth
@app.post("/api/login")
def login():
    d = body()
    u = auth.authenticate(conn(), d.get("email"), d.get("password"))
    if not u:
        return jsonify({"error": "Email or password is incorrect", "code": "BAD_LOGIN"}), 401
    session.clear()
    session["uid"] = u["User_ID"]
    audit_login(u)
    return jsonify(me_payload(u))


def audit_login(u):
    pass  # logins are not business events; kept out of the audit trail on purpose


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.post("/api/demo/switch")
def demo_switch():
    """Demo convenience: jump between role logins without retyping credentials (disabled with NOVA_DEMO=0)."""
    if not DEMO_MODE:
        return jsonify({"error": "Demo switching is disabled", "code": "ACCESS_DENIED"}), 403
    u = auth.get_user_by_email(conn(), body().get("email", ""))
    if not u:
        return jsonify({"error": "Unknown demo user"}), 404
    session.clear()
    session["uid"] = u["User_ID"]
    return jsonify(me_payload(u))


def me_payload(u):
    return {"user": u, "experience": auth.experience(u["Role"]), "permissions": permissions(u), "demo_mode": DEMO_MODE}


@app.get("/api/me")
def me():
    u = current_user()
    if not u:
        return jsonify({"user": None, "demo_mode": DEMO_MODE})
    return jsonify(me_payload(u))


@app.get("/api/demo/users")
def demo_users():
    if not DEMO_MODE:
        return jsonify([])
    rows = conn().execute("SELECT User_ID, Name, Email, Role, Region FROM users WHERE Active=1 ORDER BY User_ID").fetchall()
    return jsonify([dict(r) for r in rows])


# ----------------------------------------------------------------------------- metadata
@app.get("/api/meta")
@login_required()
def meta():
    c = conn()
    return jsonify({
        "regions": C.REGIONS, "campaign_types": C.CAMPAIGN_TYPES, "objectives": C.OBJECTIVES, "channels": C.CHANNELS,
        "products": C.PRODUCTS, "segments": C.SEGMENTS, "lead_statuses": C.LEAD_STATUSES,
        "conversion_statuses": C.CONVERSION_STATUSES, "approval_statuses": C.APPROVAL_STATUSES,
        "pipeline_stages": C.PIPELINE + ["Rejected", "Rework Required"], "roles": C.ALL_ROLES,
        "approver_roles": C.APPROVER_ROLES,
        "campaigns": [{"Campaign_ID": x["Campaign_ID"], "Campaign_Name": x["Campaign_Name"], "Region": x["Region"],
                       "Campaign_Type": x["Campaign_Type"], "Marketing_Channel": x["Marketing_Channel"],
                       "Approval_Status": x["Approval_Status"], "Pipeline_Stage": x["Pipeline_Stage"],
                       "Start_Date": x["Start_Date"]}
                      for x in analytics.list_campaigns(c, g.user)],
        "rules": rules.load_rules(c, active_only=False),
        "rules_preview_budgets": [30000, 150000, 300000],
        "demo_prefill": demo.diwali_payload(),
        "min_budget": 5000,
    })


# ----------------------------------------------------------------------------- campaigns
@app.get("/api/campaigns")
@login_required()
def campaigns():
    return jsonify(analytics.list_campaigns(conn(), g.user, filters()))


@app.post("/api/campaigns")
@login_required()
def create_campaign():
    d = body()
    with db.transaction(conn()):
        res = workflow.create_campaign(conn(), g.user, d.get("data", d), submit=bool(d.get("submit", True)))
    return jsonify(_slim(res)), 201


def _slim(res):
    out = {k: v for k, v in res.items() if k != "campaign"}
    c = res.get("campaign")
    if c:
        out["campaign"] = {k: v for k, v in c.items() if k not in ("Chain", "Validation_Errors_List")}
    return out


@app.get("/api/campaigns/<cid>")
@login_required()
def campaign_get(cid):
    d = analytics.campaign_detail(conn(), g.user, cid)
    if not d:
        raise NotFound(f"Campaign {cid} not found or not visible to you")
    return jsonify(d)


@app.put("/api/campaigns/<cid>")
@login_required()
def campaign_modify(cid):
    d = body()
    with db.transaction(conn()):
        workflow.modify_campaign(conn(), g.user, cid, d.get("data", d))
        res = workflow.submit_campaign(conn(), g.user, cid) if d.get("resubmit") else {"ok": True, "campaign": get_campaign(conn(), cid)}
    return jsonify(_slim(res))


@app.post("/api/campaigns/<cid>/submit")
@login_required()
def campaign_submit(cid):
    with db.transaction(conn()):
        res = workflow.submit_campaign(conn(), g.user, cid)
    return jsonify(_slim(res))


def _must_see(cid):
    c = get_campaign(conn(), cid)
    if not c or not auth.can_view(g.user, c):
        raise NotFound(f"Campaign {cid} not found or not visible to you")
    return c


@app.post("/api/campaigns/<cid>/approve")
@login_required()
def approve(cid):
    with db.transaction(conn()):
        res = workflow.process_approval(conn(), g.user, cid, body().get("comments", ""))
    return jsonify(_slim(res))


@app.post("/api/campaigns/<cid>/reject")
@login_required()
def reject(cid):
    with db.transaction(conn()):
        res = workflow.process_rejection(conn(), g.user, cid, body().get("comments", ""))
    return jsonify(_slim(res))


@app.post("/api/campaigns/<cid>/revise")
@login_required()
def revise(cid):
    with db.transaction(conn()):
        res = workflow.process_revision(conn(), g.user, cid, body().get("comments", ""))
    return jsonify(_slim(res))


@app.get("/api/campaigns/<cid>/governance")
@login_required()
def governance_one(cid):
    _must_see(cid)
    return jsonify(check_governance(conn(), cid))


@app.post("/api/campaigns/<cid>/dispatch")
@login_required()
def dispatch(cid):
    _must_see(cid)
    with db.transaction(conn()):
        res = workflow.dispatch_campaign(conn(), g.user, cid)
    return jsonify(_slim(res))


@app.post("/api/campaigns/<cid>/execute")
@login_required()
def execute(cid):
    _must_see(cid)
    with db.transaction(conn()):
        res = workflow.mark_executed(conn(), g.user, cid)
    return jsonify(_slim(res))


# ----------------------------------------------------------------------------- approvals
@app.get("/api/approvals/pending")
@login_required()
def approvals_pending():
    return jsonify(analytics.pending_for_user(conn(), g.user))


@app.get("/api/approvals/history")
@login_required()
def approvals_history():
    return jsonify(analytics.approval_history(conn(), g.user, request.args.get("campaign_id")))


# ----------------------------------------------------------------------------- in-app messaging & chat
@app.get("/api/messages")
@login_required()
def get_messages():
    cid = request.args.get("campaign_id")
    contact = request.args.get("contact")
    return jsonify(messaging.get_messages(conn(), campaign_id=cid, user_id=g.user["User_ID"], contact=contact))


@app.post("/api/messages")
@login_required()
def send_message():
    d = body()
    content = d.get("content", "")
    cid = d.get("campaign_id")
    r_id = d.get("recipient_id")
    r_name = d.get("recipient_name")
    msg = messaging.send_message(conn(), g.user, content, campaign_id=cid, recipient_id=r_id, recipient_name=r_name)
    return jsonify({"ok": True, "message": msg}), 201


@app.get("/api/messages/unread")
@login_required()
def get_unread_messages():
    return jsonify(messaging.get_unread(conn(), g.user["User_ID"]))


@app.post("/api/messages/read")
@login_required()
def mark_messages_read():
    d = body()
    contact = d.get("contact")
    messaging.mark_read(conn(), g.user["User_ID"], contact=contact)
    return jsonify({"ok": True})


@app.get("/api/messages/conversations")
@login_required()
def get_conversations():
    return jsonify(messaging.get_conversations(conn(), g.user["User_ID"]))


@app.post("/api/campaigns/<cid>/actuals")
@login_required()
def update_actuals(cid):
    _must_see(cid)
    d = body()
    spend = float(d.get("actual_spend", 0))
    revenue = float(d.get("actual_revenue", 0))
    leads = int(d.get("leads", 0))
    conversions = int(d.get("conversions", 0))
    c = conn()
    with db.transaction(c):
        c.execute(
            """INSERT INTO campaign_performance (Campaign_ID, Actual_Spend, Revenue, Leads, Conversions, Last_Updated)
               VALUES (?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(Campaign_ID) DO UPDATE SET
                 Actual_Spend=excluded.Actual_Spend,
                 Revenue=excluded.Revenue,
                 Leads=excluded.Leads,
                 Conversions=excluded.Conversions,
                 Last_Updated=datetime('now')""",
            (cid, spend, revenue, leads, conversions)
        )
    return jsonify({"ok": True, "actual_spend": spend, "actual_revenue": revenue, "leads": leads, "conversions": conversions})


# ----------------------------------------------------------------------------- leads & performance
@app.get("/api/leads")
@login_required()
def leads():
    return jsonify(analytics.list_leads(conn(), g.user, filters(), request.args.get("q"),
                                        min(int(request.args.get("limit", 200)), 1000), int(request.args.get("offset", 0))))


@app.post("/api/campaigns/<cid>/leads")
@login_required()
def lead_add(cid):
    _must_see(cid)
    with db.transaction(conn()):
        res = tracking.add_lead(conn(), g.user, cid, body())
    return jsonify(res), 201


@app.post("/api/campaigns/<cid>/simulate-results")
@login_required()
def simulate(cid):
    _must_see(cid)
    with db.transaction(conn()):
        res = tracking.simulate_results(conn(), g.user, cid)
    return jsonify(res)


@app.post("/api/campaigns/<cid>/performance")
@login_required()
def perf_update(cid):
    _must_see(cid)
    d = body()
    with db.transaction(conn()):
        res = tracking.update_performance(conn(), g.user, cid, d.get("impressions"), d.get("clicks"), d.get("actual_spend"))
    return jsonify(res)


@app.get("/api/performance")
@login_required()
def performance():
    return jsonify(analytics.dashboard(conn(), g.user, filters())["performance"])


@app.get("/api/dashboard")
@login_required()
def dashboard():
    return jsonify(analytics.dashboard(conn(), g.user, filters()))


# ----------------------------------------------------------------------------- governance / metrics / rules
@app.get("/api/summary")
@login_required()
def org_summary():
    """Company-wide headline numbers for the Executive Demo page (aggregates only, no campaign details)."""
    c = conn()
    k = analytics.calculate_kpis(c, auth.SYSTEM_USER)
    gv = analytics.governance_overview(c, auth.SYSTEM_USER)
    return jsonify({"kpis": k, "compliance_rate": gv["compliance_rate"], "execution_total": gv["execution_total"],
                    "execution_compliant": gv["execution_compliant"]})


@app.get("/api/governance")
@login_required()
def governance():
    return jsonify(analytics.governance_overview(conn(), g.user, filters()))


@app.get("/api/process-metrics")
@login_required()
def process_metrics():
    return jsonify(analytics.process_metrics(conn()))


@app.get("/api/rules")
@login_required()
def rules_get():
    return jsonify(rules.load_rules(conn(), active_only=False))


@app.put("/api/rules/<int:rule_id>")
@login_required([C.ROLE_BH])
def rules_put(rule_id):
    d = body()
    c = conn()
    cur = c.execute("SELECT * FROM approval_rules WHERE Rule_ID=?", (rule_id,)).fetchone()
    if not cur:
        raise NotFound("Rule not found")
    new = dict(cur)
    for k in ("Rule_Name", "Min_Budget", "Min_Inclusive", "Max_Budget", "Max_Inclusive", "Active"):
        if k in d:
            new[k] = d[k]
    if "Approval_Chain" in d:
        chain = d["Approval_Chain"]
        new["Approval_Chain"] = "|".join(chain) if isinstance(chain, list) else chain
    try:
        new["Min_Budget"] = float(new["Min_Budget"])
        new["Max_Budget"] = None if new["Max_Budget"] in (None, "") else float(new["Max_Budget"])
    except (TypeError, ValueError):
        raise MissingData("Budget limits must be numbers") from None
    allr = [dict(r) for r in c.execute("SELECT * FROM approval_rules")]
    for r in allr:
        if r["Rule_ID"] == rule_id:
            r.update(new)
        r["Chain"] = [x for x in r["Approval_Chain"].split("|") if x]
    problems = rules.validate_rule_table(allr) + rules.check_rule_set(allr)
    if problems:
        raise MissingData("Rule change rejected: " + "; ".join(problems), problems=problems)
    with db.transaction(c):
        c.execute("UPDATE approval_rules SET Rule_Name=?, Min_Budget=?, Min_Inclusive=?, Max_Budget=?, Max_Inclusive=?, "
                  "Approval_Chain=?, Active=? WHERE Rule_ID=?",
                  (new["Rule_Name"], new["Min_Budget"], int(new["Min_Inclusive"]), new["Max_Budget"], int(new["Max_Inclusive"]),
                   new["Approval_Chain"], int(new["Active"]), rule_id))
        audit.log_event(c, g.user, "Approval Rule Modified", None, None, None,
                        f"Rule {rule_id} '{new['Rule_Name']}' now: {new['Approval_Chain'].replace('|', ' > ')}")
    return jsonify(rules.load_rules(c, active_only=False))


# ----------------------------------------------------------------------------- audit / notifications
@app.get("/api/audit")
@login_required()
def audit_get():
    scope, params = auth.scope_clause(g.user, "cr")
    mgmt = g.user["Role"] in C.MANAGEMENT_ROLES or g.user["Role"] in (C.ROLE_MM, C.ROLE_EXECUTION)
    q = ("SELECT a.* FROM audit_trail a LEFT JOIN campaign_requests cr ON cr.Campaign_ID=a.Campaign_ID WHERE "
         "((cr.Campaign_ID IS NOT NULL AND " + scope + ") OR (cr.Campaign_ID IS NULL AND ?))")
    params = params + [1 if g.user["Role"] in C.MANAGEMENT_ROLES else 0]
    if request.args.get("campaign_id"):
        q += " AND a.Campaign_ID = ?"; params.append(request.args["campaign_id"])
    if request.args.get("action"):
        q += " AND a.Action = ?"; params.append(request.args["action"])
    q += " ORDER BY a.Timestamp DESC, a.Audit_ID DESC LIMIT ?"
    params.append(min(int(request.args.get("limit", 300)), 2000))
    rows = [dict(r) for r in conn().execute(q, params)]
    actions = [r[0] for r in conn().execute("SELECT DISTINCT Action FROM audit_trail ORDER BY Action")]
    return jsonify({"rows": rows, "actions": actions})


@app.get("/api/notifications")
@login_required()
def notifications():
    q, params = "SELECT * FROM notifications", []
    if request.args.get("scope") == "all" and g.user["Role"] in C.MANAGEMENT_ROLES:
        pass
    else:
        q += " WHERE To_Email = ?"; params.append(g.user["Email"])
    if request.args.get("campaign_id"):
        q += (" AND" if "WHERE" in q else " WHERE") + " Campaign_ID = ?"; params.append(request.args["campaign_id"])
    q += " ORDER BY Timestamp DESC, Notification_ID DESC LIMIT 200"
    return jsonify([dict(r) for r in conn().execute(q, params)])


# ----------------------------------------------------------------------------- exports
EXPORTS = {
    "campaigns": ("campaign_requests", True), "leads": ("lead_data", True), "performance": ("campaign_performance", True),
    "approval_log": ("approval_log", True), "audit_trail": ("audit_trail", False),
}


@app.get("/api/export/<name>.csv")
@login_required()
def export_csv(name):
    if name not in EXPORTS:
        raise NotFound("Unknown export")
    table, scoped = EXPORTS[name]
    u, c = g.user, conn()
    if name == "audit_trail" and u["Role"] not in C.MANAGEMENT_ROLES:
        raise AccessDenied("Access denied: only management can export the full audit trail")
    if scoped:
        scope, params = auth.scope_clause(u, "cr")
        key = "cr.Campaign_ID" if name == "campaigns" else f"t.Campaign_ID"
        if name == "campaigns":
            rows = c.execute("SELECT cr.* FROM campaign_requests cr WHERE " + scope, params).fetchall()
        else:
            rows = c.execute(f"SELECT t.* FROM {table} t JOIN campaign_requests cr ON cr.Campaign_ID=t.Campaign_ID WHERE " + scope, params).fetchall()
    else:
        rows = c.execute(f"SELECT * FROM {table}").fetchall()
    out = io.StringIO()
    if rows:
        w = csv.writer(out)
        w.writerow(rows[0].keys())
        for r in rows:
            w.writerow([r[k] for k in r.keys()])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}.csv"})


@app.get("/api/export/workbook.xlsx")
@login_required(C.MANAGEMENT_ROLES + [C.ROLE_MM])
def export_workbook():
    from google_sheets.build_workbook import build
    data = build(conn())
    return Response(data, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=Nova_Marketing_Governance_DB.xlsx"})


# ----------------------------------------------------------------------------- demo controls
@app.post("/api/admin/reset")
@login_required(C.MANAGEMENT_ROLES)
def reset_demo():
    if not DEMO_MODE:
        raise AccessDenied("Reset is disabled outside demo mode")
    email = g.user["Email"]
    c = g.pop("conn", None)
    if c is not None:
        c.close()
    seed.run()
    clock.clear()
    u = auth.get_user_by_email(conn(), email)
    session["uid"] = u["User_ID"]
    return jsonify({"ok": True})


@app.post("/api/demo/run-scenario")
@login_required()
def run_scenario():
    if not DEMO_MODE:
        raise AccessDenied("The scripted scenario is only available in demo mode")
    return jsonify(demo.run_scenario(conn()))


if __name__ == "__main__":
    if not os.path.exists(db.DB_PATH):
        print("No database found - creating the sample database...")
        seed.run()
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"\n  Marketing Operations Control Center -> http://{host}:{port}\n  Demo password for all users: {seed.PASSWORD}\n")
    app.run(host=host, port=port, debug=False, threaded=True)
