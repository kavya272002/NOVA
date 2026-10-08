"""Analytics layer (Looker Studio in the Google build).

calculateKPIs() -> calculate_kpis()  | every dashboard card/chart is driven by the same filtered query,
exactly like a Looker Studio data source with filter controls.
"""
import json
from statistics import median

from . import auth, clock
from . import constants as C
from .db import get_setting
from .governance import check_governance, get_campaign

FILTER_KEYS = ["region", "campaign", "campaign_type", "channel", "status", "approval_status", "date_from", "date_to"]


# ------------------------------------------------------------------ filtered campaign set
def build_where(user, f):
    """WHERE clause (alias cr = campaign_requests, p = v_campaign_pipeline) = role scope + dashboard filters."""
    scope, params = auth.scope_clause(user, "cr")
    where = [scope]
    f = f or {}
    if f.get("region"):
        where.append("cr.Region = ?"); params.append(f["region"])
    if f.get("campaign"):
        where.append("cr.Campaign_ID = ?"); params.append(f["campaign"])
    if f.get("campaign_type"):
        where.append("cr.Campaign_Type = ?"); params.append(f["campaign_type"])
    if f.get("channel"):
        where.append("(' + ' || cr.Marketing_Channel || ' + ') LIKE ?"); params.append(f"% + {f['channel']} + %")
    if f.get("status"):
        where.append("p.Pipeline_Stage = ?"); params.append(f["status"])
    if f.get("approval_status"):
        where.append("cr.Approval_Status = ?"); params.append(f["approval_status"])
    if f.get("date_from"):
        where.append("cr.Start_Date >= ?"); params.append(f["date_from"])
    if f.get("date_to"):
        where.append("cr.Start_Date <= ?"); params.append(f["date_to"])
    return " AND ".join(where), params


FROM = " FROM campaign_requests cr JOIN v_campaign_pipeline p ON p.Campaign_ID = cr.Campaign_ID "


def _safe_div(a, b):
    return (a / b) if b else None


def calculate_kpis(conn, user, f=None):
    """Business purpose: one place that computes every headline number so cards, charts and exports agree."""
    where, params = build_where(user, f)
    cnt = conn.execute(
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN cr.Approval_Status='Pending Approval' THEN 1 ELSE 0 END) AS pending,"
        " SUM(CASE WHEN cr.Approval_Status='Fully Approved' THEN 1 ELSE 0 END) AS approved,"
        " SUM(CASE WHEN cr.Approval_Status='Rejected' THEN 1 ELSE 0 END) AS rejected,"
        " SUM(CASE WHEN cr.Approval_Status='Rework Required' THEN 1 ELSE 0 END) AS rework,"
        " SUM(CASE WHEN cr.Approval_Status='Fully Approved' THEN cr.Proposed_Budget ELSE 0 END) AS approved_budget"
        + FROM + "WHERE " + where, params).fetchone()
    perf = conn.execute(
        "SELECT COALESCE(SUM(pf.Actual_Spend),0) spend, COALESCE(SUM(pf.Impressions),0) impressions,"
        " COALESCE(SUM(pf.Clicks),0) clicks, COALESCE(SUM(pf.Leads),0) leads, COALESCE(SUM(pf.Qualified_Leads),0) qualified,"
        " COALESCE(SUM(pf.Conversions),0) conversions, COALESCE(SUM(pf.Revenue),0) revenue, COUNT(pf.Campaign_ID) tracked"
        + FROM + "JOIN campaign_performance pf ON pf.Campaign_ID = cr.Campaign_ID WHERE " + where, params).fetchone()
    k = {x: (cnt[x] or 0) for x in cnt.keys()}
    k.update({x: perf[x] for x in perf.keys()})
    k["conversion_rate"] = _safe_div(k["conversions"], k["leads"])            # Conversions / Leads
    k["cpl"] = _safe_div(k["spend"], k["leads"])                              # Actual Spend / Leads
    k["roas"] = _safe_div(k["revenue"], k["spend"])                           # Revenue / Spend
    k["roi"] = _safe_div(k["revenue"] - k["spend"], k["spend"])               # (Revenue - Spend) / Spend
    k["qualification_rate"] = _safe_div(k["qualified"], k["leads"])
    return k


def dashboard(conn, user, f=None):
    where, params = build_where(user, f)
    kpis = calculate_kpis(conn, user, f)

    # 1) campaigns by region + 2) spend by region
    reg = {r: {"region": r, "campaigns": 0, "spend": 0, "approved_budget": 0, "revenue": 0} for r in C.REGIONS}
    for r in conn.execute("SELECT cr.Region, COUNT(*) n, SUM(CASE WHEN cr.Approval_Status='Fully Approved' THEN cr.Proposed_Budget ELSE 0 END) b"
                          + FROM + "WHERE " + where + " GROUP BY cr.Region", params):
        if r["Region"] in reg:
            reg[r["Region"]]["campaigns"] = r["n"]; reg[r["Region"]]["approved_budget"] = r["b"] or 0
    for r in conn.execute("SELECT cr.Region, SUM(pf.Actual_Spend) s, SUM(pf.Revenue) rev" + FROM +
                          "JOIN campaign_performance pf ON pf.Campaign_ID=cr.Campaign_ID WHERE " + where + " GROUP BY cr.Region", params):
        if r["Region"] in reg:
            reg[r["Region"]]["spend"] = r["s"] or 0; reg[r["Region"]]["revenue"] = r["rev"] or 0

    perf_rows = [dict(r) for r in conn.execute(
        "SELECT pf.*, cr.Campaign_Type, cr.Marketing_Channel, cr.Start_Date" + FROM +
        "JOIN campaign_performance pf ON pf.Campaign_ID=cr.Campaign_ID WHERE " + where + " ORDER BY pf.Leads DESC", params)]
    leads_by_campaign = [{"id": r["Campaign_ID"], "name": r["Campaign_Name"], "leads": r["Leads"],
                          "qualified": r["Qualified_Leads"], "conversions": r["Conversions"]} for r in perf_rows[:12]]
    roi = sorted([{"id": r["Campaign_ID"], "name": r["Campaign_Name"], "roi": r["ROI"], "roas": r["ROAS"], "spend": r["Actual_Spend"], "revenue": r["Revenue"]}
                  for r in perf_rows if r["ROI"] is not None], key=lambda x: -x["roi"])

    # 6) approval pipeline
    stages = {s: 0 for s in C.PIPELINE + ["Rejected", "Rework Required"]}
    for r in conn.execute("SELECT p.Pipeline_Stage s, COUNT(*) n" + FROM + "WHERE " + where + " GROUP BY p.Pipeline_Stage", params):
        stages[r["s"]] = r["n"]

    # 7) monthly trend (lead month). Spend is attributed to months in proportion to each campaign's leads.
    month = {}
    for r in conn.execute(
            "SELECT substr(ld.Lead_Date,1,7) m, COUNT(*) leads,"
            " SUM(CASE WHEN ld.Lead_Score >= ? THEN 1 ELSE 0 END) qualified,"
            " SUM(CASE WHEN ld.Conversion_Status='Converted' THEN 1 ELSE 0 END) conversions, SUM(ld.Revenue) revenue"
            " FROM lead_data ld JOIN campaign_requests cr ON cr.Campaign_ID=ld.Campaign_ID JOIN v_campaign_pipeline p ON p.Campaign_ID=cr.Campaign_ID"
            " WHERE " + where + " GROUP BY m ORDER BY m", [get_setting(conn, "qualified_score_threshold", 60, int)] + params):
        month[r["m"]] = {"month": r["m"], "leads": r["leads"], "qualified": r["qualified"],
                         "conversions": r["conversions"], "revenue": r["revenue"] or 0, "spend": 0.0}
    for r in conn.execute(
            "SELECT ld.Campaign_ID cid, substr(ld.Lead_Date,1,7) m, COUNT(*) n, pf.Actual_Spend sp, pf.Leads tl"
            " FROM lead_data ld JOIN campaign_requests cr ON cr.Campaign_ID=ld.Campaign_ID JOIN v_campaign_pipeline p ON p.Campaign_ID=cr.Campaign_ID"
            " JOIN campaign_performance pf ON pf.Campaign_ID=ld.Campaign_ID WHERE " + where + " GROUP BY ld.Campaign_ID, m", params):
        if r["tl"] and r["m"] in month:
            month[r["m"]]["spend"] += r["sp"] * r["n"] / r["tl"]
    trend = [{**v, "spend": round(v["spend"])} for _, v in sorted(month.items())]

    return {
        "kpis": kpis,
        "charts": {
            "campaigns_by_region": [reg[r] for r in C.REGIONS],
            "spend_by_region": [reg[r] for r in C.REGIONS],
            "leads_by_campaign": leads_by_campaign,
            "funnel": [{"stage": "Impressions", "value": kpis["impressions"]}, {"stage": "Clicks", "value": kpis["clicks"]},
                       {"stage": "Leads", "value": kpis["leads"]}, {"stage": "Qualified leads", "value": kpis["qualified"]},
                       {"stage": "Conversions", "value": kpis["conversions"]}],
            "roi": roi,
            "pipeline": [{"stage": s, "count": stages[s]} for s in C.PIPELINE],
            "pipeline_other": {"Rejected": stages["Rejected"], "Rework Required": stages["Rework Required"]},
            "trend": trend,
        },
        "performance": perf_rows,
    }


# ------------------------------------------------------------------ campaign lists & detail
def list_campaigns(conn, user, f=None, limit=500):
    where, params = build_where(user, f)
    sql = ("SELECT cr.Campaign_ID, cr.Campaign_Name, cr.Region, cr.Requester_Name, cr.Product, cr.Campaign_Type, cr.Marketing_Channel,"
           " cr.Objective, cr.Start_Date, cr.End_Date, cr.Proposed_Budget, cr.Approval_Level, cr.Current_Approver, cr.Approval_Status,"
           " cr.Execution_Status, cr.Submission_Date, cr.Rejection_Reason, cr.Updated_Timestamp, cr.Approval_Step, cr.Approval_Chain,"
           " cr.Requester_ID, p.Pipeline_Stage, pf.Actual_Spend, pf.Revenue, pf.ROAS, pf.ROI"
           + FROM +
           " LEFT JOIN campaign_performance pf ON pf.Campaign_ID = cr.Campaign_ID "
           + "WHERE " + where + " ORDER BY cr.Campaign_ID DESC LIMIT ?")
    rows = [dict(r) for r in conn.execute(sql, params + [limit])]
    return rows


def route_progress(conn, c):
    """Chain of approvers with their decision state - drives the approval-tracker UI."""
    log = [dict(r) for r in conn.execute(
        "SELECT * FROM approval_log WHERE Campaign_ID=? AND Revision_No=? ORDER BY Approval_ID", (c["Campaign_ID"], c["Revision_No"]))]
    out = []
    for i, role in enumerate(c["Chain"], start=1):
        a = auth.find_approver(conn, role, c["Region"])
        dec = next((x for x in log if x["Approval_Level"] == i), None)
        if dec and dec["Decision"] == "Approved":
            state = "done"
        elif dec:
            state = "stopped"
        elif c["Approval_Status"] == C.ST_PENDING and i == c["Approval_Step"]:
            state = "current"
        else:
            state = "waiting"
        out.append({"level": i, "role": role, "assigned": a["Name"] if a else None, "state": state,
                    "decision": dec["Decision"] if dec else None, "decided_by": dec["Approver_Name"] if dec else None,
                    "decided_at": dec["Decision_Date"] if dec else None, "comments": dec["Comments"] if dec else None})
    return out


def campaign_detail(conn, user, campaign_id):
    c = get_campaign(conn, campaign_id)
    if not c or not auth.can_view(user, c):
        return None
    pipe = conn.execute("SELECT Pipeline_Stage FROM v_campaign_pipeline WHERE Campaign_ID=?", (campaign_id,)).fetchone()
    perf = conn.execute("SELECT * FROM campaign_performance WHERE Campaign_ID=?", (campaign_id,)).fetchone()
    cyc = None
    if c["Submitted_Timestamp"] and c["Approved_Timestamp"]:
        cyc = round(clock.minutes_between(c["Submitted_Timestamp"], c["Approved_Timestamp"]), 1)
    return {
        "campaign": {k: v for k, v in c.items() if k not in ("Chain", "Validation_Errors_List")},
        "pipeline_stage": pipe["Pipeline_Stage"],
        "validation_errors": c["Validation_Errors_List"],
        "route": route_progress(conn, c),
        "approval_log": [dict(r) for r in conn.execute("SELECT * FROM approval_log WHERE Campaign_ID=? ORDER BY Approval_ID", (campaign_id,))],
        "audit": [dict(r) for r in conn.execute("SELECT * FROM audit_trail WHERE Campaign_ID=? ORDER BY Audit_ID", (campaign_id,))],
        "governance": check_governance(conn, campaign_id),
        "performance": dict(perf) if perf else None,
        "lead_count": conn.execute("SELECT COUNT(*) FROM lead_data WHERE Campaign_ID=?", (campaign_id,)).fetchone()[0],
        "approval_cycle_minutes": cyc,
        "notifications": [dict(r) for r in conn.execute(
            "SELECT Notification_ID, Timestamp, Notification_Type, To_Name, Subject FROM notifications WHERE Campaign_ID=? ORDER BY Notification_ID", (campaign_id,))],
    }


def pending_for_user(conn, user):
    """Approval inbox: only campaigns whose CURRENT level matches the user's role (and region for RMs)."""
    out = []
    if user["Role"] not in C.APPROVER_ROLES:
        return out
    for c in list_campaigns(conn, user, {"approval_status": C.ST_PENDING}):
        chain = [x for x in (c["Approval_Chain"] or "").split("|") if x]
        if not chain or c["Approval_Step"] < 1:
            continue
        if chain[c["Approval_Step"] - 1] != user["Role"]:
            continue
        if user["Role"] == C.ROLE_RM and c["Region"] != user["Region"]:
            continue
        if c["Requester_ID"] == user["User_ID"]:
            continue
        full = get_campaign(conn, c["Campaign_ID"])
        last = conn.execute("SELECT MAX(Decision_Date) d FROM approval_log WHERE Campaign_ID=? AND Revision_No=?",
                            (c["Campaign_ID"], full["Revision_No"])).fetchone()["d"]
        waiting_since = last or full["Submitted_Timestamp"]
        out.append({**{k: full[k] for k in ("Campaign_ID", "Campaign_Name", "Region", "Requester_Name", "Product", "Campaign_Type",
                                           "Objective", "Target_Audience", "Marketing_Channel", "Start_Date", "End_Date",
                                           "Proposed_Budget", "Expected_Leads", "Expected_Conversions", "Expected_Revenue",
                                           "Campaign_Description", "Creative_Link", "Approval_Level", "Approval_Step", "Revision_No")},
                    "waiting_since": waiting_since,
                    "waiting_minutes": round(clock.minutes_between(waiting_since, clock.ts())) if waiting_since else None,
                    "route": route_progress(conn, full)})
    out.sort(key=lambda x: -(x["waiting_minutes"] or 0))
    return out


def approval_history(conn, user, campaign_id=None, limit=500):
    scope, params = auth.scope_clause(user, "cr")
    q = ("SELECT al.*, cr.Campaign_Name, cr.Region FROM approval_log al JOIN campaign_requests cr ON cr.Campaign_ID=al.Campaign_ID"
         " WHERE " + scope)
    if campaign_id:
        q += " AND al.Campaign_ID = ?"; params.append(campaign_id)
    q += " ORDER BY al.Approval_ID DESC LIMIT ?"
    return [dict(r) for r in conn.execute(q, params + [limit])]


def list_leads(conn, user, f=None, search=None, limit=300, offset=0):
    where, params = build_where(user, f)
    q = (" FROM lead_data ld JOIN campaign_requests cr ON cr.Campaign_ID=ld.Campaign_ID JOIN v_campaign_pipeline p ON p.Campaign_ID=cr.Campaign_ID WHERE " + where)
    if search:
        q += " AND (ld.Lead_ID LIKE ? OR ld.Campaign_ID LIKE ? OR ld.Sales_Assigned LIKE ? OR ld.Customer_Segment LIKE ?)"
        params += [f"%{search}%"] * 4
    th = get_setting(conn, "qualified_score_threshold", 60, int)
    summ = conn.execute("SELECT COUNT(*) n, SUM(CASE WHEN ld.Lead_Score>=? THEN 1 ELSE 0 END) q,"
                        " SUM(CASE WHEN ld.Conversion_Status='Converted' THEN 1 ELSE 0 END) c, COALESCE(SUM(ld.Revenue),0) r" + q,
                        [th] + params).fetchone()
    rows = [dict(r) for r in conn.execute("SELECT ld.*, cr.Campaign_Name" + q + " ORDER BY ld.Lead_Date DESC, ld.Lead_ID DESC LIMIT ? OFFSET ?",
                                          params + [limit, offset])]
    by_source = [dict(r) for r in conn.execute("SELECT ld.Lead_Source s, COUNT(*) n, SUM(CASE WHEN ld.Conversion_Status='Converted' THEN 1 ELSE 0 END) c" + q +
                                               " GROUP BY ld.Lead_Source ORDER BY n DESC", params)]
    by_status = [dict(r) for r in conn.execute("SELECT ld.Lead_Status s, COUNT(*) n" + q + " GROUP BY ld.Lead_Status ORDER BY n DESC", params)]
    return {"rows": rows, "total": summ["n"], "qualified": summ["q"] or 0, "converted": summ["c"] or 0, "revenue": summ["r"],
            "by_source": by_source, "by_status": by_status, "threshold": th}


# ------------------------------------------------------------------ governance overview + bottlenecks
def governance_overview(conn, user, f=None):
    camps = list_campaigns(conn, user, f)
    rows, counts = [], {"compliant": 0, "pending": 0, "blocked": 0, "violation": 0}
    exec_total = exec_ok = 0
    for c in camps:
        g = check_governance(conn, c["Campaign_ID"])
        counts[g["state"]] += 1
        if c["Execution_Status"] in (C.EX_READY, C.EX_DONE):
            exec_total += 1
            exec_ok += 1 if g["can_execute"] else 0
        rows.append({"Campaign_ID": c["Campaign_ID"], "Campaign_Name": c["Campaign_Name"], "Region": c["Region"],
                     "Proposed_Budget": c["Proposed_Budget"], "Approval_Status": c["Approval_Status"],
                     "Execution_Status": c["Execution_Status"], "Approval_Level": c["Approval_Level"],
                     "state": g["state"], "label": g["label"], "controls_passed": sum(1 for i in g["items"] if i["status"] == "pass"),
                     "controls_total": len(g["items"])})
    bott = {}
    for c in camps:
        if c["Approval_Status"] != C.ST_PENDING:
            continue
        full = get_campaign(conn, c["Campaign_ID"])
        chain = full["Chain"]
        role = chain[full["Approval_Step"] - 1]
        last = conn.execute("SELECT MAX(Decision_Date) d FROM approval_log WHERE Campaign_ID=? AND Revision_No=?",
                            (c["Campaign_ID"], full["Revision_No"])).fetchone()["d"]
        waiting = clock.minutes_between(last or full["Submitted_Timestamp"], clock.ts())
        b = bott.setdefault(role, {"role": role, "pending": 0, "total_wait": 0.0, "oldest_minutes": 0, "oldest_id": None, "overdue": 0})
        b["pending"] += 1; b["total_wait"] += waiting
        if waiting > b["oldest_minutes"]:
            b["oldest_minutes"], b["oldest_id"] = round(waiting), c["Campaign_ID"]
        if waiting > get_setting(conn, "approval_sla_minutes", 240, int):
            b["overdue"] += 1
    bottlenecks = [{"role": b["role"], "pending": b["pending"], "avg_wait_minutes": round(b["total_wait"] / b["pending"]),
                    "oldest_minutes": b["oldest_minutes"], "oldest_id": b["oldest_id"], "overdue": b["overdue"]}
                   for b in sorted(bott.values(), key=lambda x: -x["total_wait"])]
    return {"rows": rows, "counts": counts, "execution_total": exec_total, "execution_compliant": exec_ok,
            "compliance_rate": (exec_ok / exec_total) if exec_total else None, "bottlenecks": bottlenecks,
            "sla_minutes": get_setting(conn, "approval_sla_minutes", 240, int)}


# ------------------------------------------------------------------ process metrics (before vs after)
def process_metrics(conn):
    """Business purpose: quantify the business-process improvement. 'Before' values are SIMULATED assumptions for the
    academic case (configurable in SETTINGS); 'After' values are MEASURED from this system's own timestamps."""
    s = lambda k, d, cast=float: get_setting(conn, k, d, cast)  # noqa: E731
    before_min, target = s("before_minutes", 120), s("target_minutes", 25)
    rows = conn.execute("SELECT Campaign_ID, Approval_Level, Submitted_Timestamp, Approved_Timestamp FROM campaign_requests "
                        "WHERE Approved_Timestamp IS NOT NULL AND Submitted_Timestamp IS NOT NULL").fetchall()
    std, lead = [], []
    for r in rows:
        m = clock.minutes_between(r["Submitted_Timestamp"], r["Approved_Timestamp"])
        (std if r["Approval_Level"] <= 2 else lead).append(m)
    avg_std = sum(std) / len(std) if std else None
    reduction_measured = ((before_min - avg_std) / before_min * 100) if avg_std is not None else None
    reduction_target = (before_min - target) / before_min * 100
    within = (sum(1 for m in std if m <= target) / len(std) * 100) if std else None
    notif = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    camps_notified = conn.execute("SELECT COUNT(DISTINCT Campaign_ID) FROM notifications").fetchone()[0] or 1
    levels = conn.execute("SELECT AVG(Approval_Level) FROM campaign_requests WHERE Approval_Level IS NOT NULL").fetchone()[0] or 2
    ap = conn.execute("SELECT SUM(CASE WHEN Approval_Status='Fully Approved' THEN 1 ELSE 0 END) a, "
                      "SUM(CASE WHEN Approval_Status='Rejected' THEN 1 ELSE 0 END) r FROM campaign_requests").fetchone()
    decided = (ap["a"] or 0) + (ap["r"] or 0)
    ids = [r[0] for r in conn.execute("SELECT Campaign_ID FROM campaign_requests WHERE Execution_Status IN ('Ready for Execution','Executed')")]
    ok = sum(1 for i in ids if check_governance(conn, i)["can_execute"])
    total_camps = conn.execute("SELECT COUNT(*) FROM campaign_requests").fetchone()[0]
    return {
        "disclaimer": "Academic simulation: 'Before' figures are assumptions for a hypothetical company; 'After' figures are measured from timestamps in this prototype's simulated data.",
        "before": {
            "avg_minutes": before_min, "touchpoints": s("before_touchpoints", 14), "followups": s("before_followups", 6),
            "visibility": "Low - status known only by asking via e-mail / WhatsApp",
            "governance_risk": f"High - about {s('before_undocumented_pct', 30, float):.0f}% of requests assumed to lack complete approval records",
        },
        "after": {
            "avg_minutes_standard": avg_std, "avg_minutes_leadership": (sum(lead) / len(lead) if lead else None),
            "standard_count": len(std), "leadership_count": len(lead), "within_target_pct": within,
            "manual_touchpoints": round(1 + levels, 1), "followups": 0,
            "automated_notifications": notif, "notifications_per_campaign": round(notif / camps_notified, 1),
            "approval_completion_pct": (ap["a"] / decided * 100) if decided else None,
            "governance_compliance_pct": (ok / len(ids) * 100) if ids else None, "governed_campaigns": len(ids),
            "visibility": f"100% - all {total_camps} requests tracked live in one database",
        },
        "target_minutes": target,
        "reduction_measured_pct": reduction_measured,
        "reduction_at_target_pct": reduction_target,
        "formula": "(Time Before - Time After) / Time Before x 100",
        "distribution": sorted(round(m, 1) for m in std),
    }
