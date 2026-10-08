"""Lead tracking & performance (Apps Script: updatePerformance()).

Business purpose: connect campaign execution to results. Leads are captured against a Campaign_ID, rolled
up into CAMPAIGN_PERFORMANCE, and the metrics (CPL, conversion rate, ROAS, ROI) are *formula columns* in
the database - never typed in by hand.
"""
import random
from datetime import date, datetime, timedelta

from . import audit, clock
from . import constants as C
from .errors import AccessDenied, InvalidState, MissingData, NotFound
from .governance import get_campaign

SALES_REPS = {
    "Delhi NCR": ["Manish Gupta", "Ritu Chawla", "Sahil Bhatia"],
    "Mumbai": ["Nikhil Joshi", "Farah Sheikh", "Omkar Patil"],
    "Bangalore": ["Deepa Hegde", "Naveen Kumar", "Shruti Gowda"],
    "Hyderabad": ["Venkat Rao", "Sana Fatima", "Harsha Vardhan"],
    "Chennai": ["Murali Krishnan", "Janani Selvam", "Arvind Raj"],
}
ORGANIC = "Organic / Referral"
TRACKING_ROLES = {C.ROLE_EXECUTION, C.ROLE_MM, C.ROLE_MH}


def _qualified_threshold(conn):
    from .db import get_setting
    return get_setting(conn, "qualified_score_threshold", 60, int)


def _authorize(user, c):
    if user["Role"] in TRACKING_ROLES:
        return
    if user["Role"] == C.ROLE_EXEC and c["Requester_ID"] == user["User_ID"]:
        return
    raise AccessDenied(f"Access denied: the {user['Role']} role cannot update lead or performance data for {c['Campaign_ID']}")


def _executed(c):
    if c["Execution_Status"] != C.EX_DONE:
        raise InvalidState(f"Lead and performance data can only be recorded for executed campaigns "
                           f"({c['Campaign_ID']} is '{c['Execution_Status']}')")


def rollup_leads(conn, campaign_id):
    th = _qualified_threshold(conn)
    r = conn.execute(
        "SELECT COUNT(*) AS leads, COALESCE(SUM(CASE WHEN Lead_Score >= ? THEN 1 ELSE 0 END),0) AS qualified,"
        " COALESCE(SUM(CASE WHEN Conversion_Status='Converted' THEN 1 ELSE 0 END),0) AS conversions,"
        " COALESCE(SUM(Revenue),0) AS revenue FROM lead_data WHERE Campaign_ID=?", (th, campaign_id)).fetchone()
    return dict(r)


def update_performance(conn, user, campaign_id, impressions=None, clicks=None, actual_spend=None,
                       write_audit=True, note=None):
    """Sync lead-derived numbers (Leads, Qualified, Conversions, Revenue) from LEAD_DATA and store the
    ad-platform numbers (spend, impressions, clicks). CPL / Conversion_Rate / ROAS / ROI are formulas."""
    c = get_campaign(conn, campaign_id)
    if not c:
        raise NotFound(f"Campaign {campaign_id} not found")
    _authorize(user, c)
    _executed(c)
    cur = conn.execute("SELECT * FROM campaign_performance WHERE Campaign_ID=?", (campaign_id,)).fetchone()
    cur = dict(cur) if cur else {"Impressions": 0, "Clicks": 0, "Actual_Spend": 0}
    imp = cur["Impressions"] if impressions is None else impressions
    clk = cur["Clicks"] if clicks is None else clicks
    spend = cur["Actual_Spend"] if actual_spend is None else actual_spend
    for name, v in (("Impressions", imp), ("Clicks", clk), ("Actual spend", spend)):
        try:
            if float(v) < 0:
                raise MissingData(f"{name} cannot be negative")
        except (TypeError, ValueError):
            raise MissingData(f"{name} must be a number") from None
    if float(clk) > float(imp) and float(imp) > 0:
        raise MissingData("Clicks cannot exceed impressions")
    roll = rollup_leads(conn, campaign_id)
    conn.execute(
        "INSERT INTO campaign_performance(Campaign_ID, Campaign_Name, Region, Budget, Actual_Spend, Impressions, Clicks,"
        " Leads, Qualified_Leads, Conversions, Revenue, Last_Updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(Campaign_ID) DO UPDATE SET Actual_Spend=excluded.Actual_Spend, Impressions=excluded.Impressions,"
        " Clicks=excluded.Clicks, Leads=excluded.Leads, Qualified_Leads=excluded.Qualified_Leads,"
        " Conversions=excluded.Conversions, Revenue=excluded.Revenue, Last_Updated=excluded.Last_Updated",
        (campaign_id, c["Campaign_Name"], c["Region"], c["Proposed_Budget"], float(spend), int(float(imp)), int(float(clk)),
         roll["leads"], roll["qualified"], roll["conversions"], roll["revenue"], clock.ts()))
    warnings = []
    if roll["leads"] == 0:
        warnings.append("No lead data captured yet for this campaign - CPL, conversion rate, ROAS and ROI will stay blank")
    if float(spend) > c["Proposed_Budget"]:
        warnings.append(f"Actual spend exceeds the approved budget of {c['Proposed_Budget']:,.0f}")
    if write_audit:
        audit.log_event(conn, user, "Performance Updated", campaign_id, c["Execution_Status"], c["Execution_Status"],
                        note or f"Spend {float(spend):,.0f}, impressions {int(float(imp)):,}, clicks {int(float(clk)):,}, "
                                f"leads {roll['leads']:,}, conversions {roll['conversions']:,}")
    perf = dict(conn.execute("SELECT * FROM campaign_performance WHERE Campaign_ID=?", (campaign_id,)).fetchone())
    return {"ok": True, "performance": perf, "warnings": warnings}


def _next_lead_no(conn):
    r = conn.execute("SELECT COALESCE(MAX(CAST(SUBSTR(Lead_ID, 4) AS INTEGER)), 0) AS n FROM lead_data").fetchone()
    return r["n"] + 1


def add_lead(conn, user, campaign_id, data):
    """Capture one lead (Google Form / CRM webhook in production)."""
    c = get_campaign(conn, campaign_id)
    if not c:
        raise NotFound(f"Campaign {campaign_id} not found")
    _authorize(user, c)
    _executed(c)
    errors = []
    sources = [x.strip() for x in c["Marketing_Channel"].split("+")] + [ORGANIC]
    src = data.get("Lead_Source")
    if src not in sources:
        errors.append("Lead_Source must be one of the campaign's channels or '" + ORGANIC + "'")
    try:
        ld = datetime.strptime(str(data.get("Lead_Date") or clock.today().isoformat()), "%Y-%m-%d").date()
        if ld < date.fromisoformat(c["Start_Date"]):
            errors.append("Lead_Date cannot be before the campaign start date")
        if ld > clock.today():
            errors.append("Lead_Date cannot be in the future")
    except ValueError:
        errors.append("Lead_Date must be YYYY-MM-DD")
        ld = None
    if data.get("Customer_Segment") not in C.SEGMENTS:
        errors.append("Customer_Segment is not in the approved list")
    try:
        score = int(data.get("Lead_Score"))
        if not 0 <= score <= 100:
            errors.append("Lead_Score must be between 0 and 100")
    except (TypeError, ValueError):
        errors.append("Lead_Score must be a whole number 0-100")
        score = 0
    if data.get("Lead_Status") not in C.LEAD_STATUSES:
        errors.append("Lead_Status is not valid")
    if data.get("Conversion_Status") not in C.CONVERSION_STATUSES:
        errors.append("Conversion_Status is not valid")
    if not (data.get("Sales_Assigned") or "").strip():
        errors.append("Sales_Assigned is required")
    try:
        revenue = float(data.get("Revenue") or 0)
        if revenue < 0:
            errors.append("Revenue cannot be negative")
        if revenue > 0 and data.get("Conversion_Status") != "Converted":
            errors.append("Revenue can only be recorded for converted leads")
    except ValueError:
        errors.append("Revenue must be a number")
        revenue = 0
    if errors:
        raise MissingData("; ".join(errors), errors=errors)
    lead_id = f"LD-{_next_lead_no(conn):06d}"
    conn.execute(
        "INSERT INTO lead_data(Lead_ID, Campaign_ID, Region, Lead_Source, Lead_Date, Customer_Segment, Lead_Score, Lead_Status,"
        " Sales_Assigned, Conversion_Status, Revenue) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (lead_id, campaign_id, c["Region"], src, ld.isoformat(), data["Customer_Segment"], score, data["Lead_Status"],
         data["Sales_Assigned"].strip(), data["Conversion_Status"], revenue))
    audit.log_event(conn, user, "Lead Captured", campaign_id, None, None, f"{lead_id} ({src}, score {score})")
    update_performance(conn, user, campaign_id, write_audit=False)
    return {"ok": True, "lead_id": lead_id}


def generate_leads(rng, c, n, q, conv, revenue, start_no, last_day=None):
    """Create realistic lead rows that EXACTLY add up to n leads / q qualified / conv conversions / revenue.

    Used by the seed script and by the 'simulate results' button (stands in for real lead capture)."""
    th = 60
    n, q, conv = int(n), min(int(q), int(n)), min(int(conv), int(q))
    start = date.fromisoformat(c["Start_Date"])
    end = min(date.fromisoformat(c["End_Date"]), last_day or clock.today())
    span = max((end - start).days, 0)
    sources = [x.strip() for x in c["Marketing_Channel"].split("+")]
    weights = [3] * len(sources) + [1]
    sources = sources + [ORGANIC]
    reps = SALES_REPS[c["Region"]]
    # revenue split across converted leads, rounded to ₹10 so the totals match exactly
    ws = [rng.uniform(0.6, 1.5) for _ in range(conv)]
    tot = sum(ws) or 1
    revs = [round(revenue * w / tot / 10) * 10 for w in ws]
    if revs:
        revs[-1] += round(revenue) - sum(revs)
    idx = list(range(n))
    rng.shuffle(idx)
    conv_set, qual_set = set(idx[:conv]), set(idx[:q])
    rows, ri = [], 0
    for i in range(n):
        if i in conv_set:
            score, status, cstat, rev = rng.randint(72, 98), "Converted", "Converted", revs[ri]
            ri += 1
        elif i in qual_set:
            lost = rng.random() < 0.2
            score = rng.randint(th, 89)
            status, cstat, rev = ("Lost", "Not Converted", 0) if lost else ("Qualified", "In Progress", 0)
        else:
            score = rng.randint(15, th - 1)
            status = rng.choice(["New", "Contacted", "Contacted", "Lost"])
            cstat, rev = ("Not Converted" if status == "Lost" else "In Progress"), 0
        day = int(span * (rng.betavariate(1.3, 2.2))) if span else 0
        rows.append((f"LD-{start_no + i:06d}", c["Campaign_ID"], c["Region"], rng.choices(sources, weights)[0],
                     (start + timedelta(days=day)).isoformat(), rng.choice(C.SEGMENTS), score, status,
                     rng.choice(reps), cstat, float(rev)))
    return rows


def simulate_results(conn, user, campaign_id):
    """DEMO helper: stand-in for a CRM/ad-platform feed. Generates a realistic batch of leads for an executed campaign
    (around the requester's forecast) and syncs the performance sheet."""
    c = get_campaign(conn, campaign_id)
    if not c:
        raise NotFound(f"Campaign {campaign_id} not found")
    if user["Role"] not in (C.ROLE_EXECUTION, C.ROLE_MH):
        raise AccessDenied("Access denied: only the Execution Team or Marketing Head can load campaign results")
    _executed(c)
    rng = random.Random(f"{campaign_id}-{conn.execute('SELECT COUNT(*) FROM lead_data WHERE Campaign_ID=?', (campaign_id,)).fetchone()[0]}")
    n = max(20, round(c["Expected_Leads"] * rng.uniform(0.28, 0.4)))     # first-weeks batch
    q = round(n * rng.uniform(0.42, 0.55))
    conv_target = c["Expected_Conversions"] / max(c["Expected_Leads"], 1)
    conv = min(q, max(1, round(n * conv_target * rng.uniform(0.8, 1.2))))
    ticket = c["Expected_Revenue"] / max(c["Expected_Conversions"], 1)
    revenue = round(conv * ticket * rng.uniform(0.85, 1.1) / 10) * 10
    rows = generate_leads(rng, c, n, q, conv, revenue, _next_lead_no(conn), last_day=clock.today())
    conn.executemany("INSERT INTO lead_data VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    perf = conn.execute("SELECT * FROM campaign_performance WHERE Campaign_ID=?", (campaign_id,)).fetchone()
    spend0 = perf["Actual_Spend"] if perf else 0
    spend = spend0 + round(c["Proposed_Budget"] * rng.uniform(0.22, 0.32) / 100) * 100
    clicks = round(n / rng.uniform(0.045, 0.085))
    impressions = round(clicks / rng.uniform(0.028, 0.05))
    res = update_performance(conn, user, campaign_id,
                             impressions=(perf["Impressions"] if perf else 0) + impressions,
                             clicks=(perf["Clicks"] if perf else 0) + clicks, actual_spend=spend,
                             note=f"Simulated lead feed: +{n} leads, +{conv} conversions")
    res["added_leads"] = n
    return res
