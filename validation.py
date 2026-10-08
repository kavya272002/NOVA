"""Data validation (Apps Script: validateCampaign()).

Business purpose: stop incomplete or illogical requests at the door, so approvers never waste time
on a request that cannot be executed - and tell the requester EXACTLY which fields to fix.
"""
from datetime import date, datetime

from . import clock
from . import constants as C

REQUIRED = [
    ("Region", "Region"), ("Campaign_Name", "Campaign name"), ("Product", "Product"),
    ("Campaign_Type", "Campaign type"), ("Objective", "Marketing objective"),
    ("Target_Audience", "Target audience"), ("Marketing_Channel", "Marketing channel"),
    ("Start_Date", "Start date"), ("End_Date", "End date"), ("Proposed_Budget", "Proposed budget"),
    ("Expected_Leads", "Expected leads"), ("Expected_Conversions", "Expected conversions"),
    ("Expected_Revenue", "Expected revenue"), ("Campaign_Description", "Campaign description"),
]

MIN_BUDGET = 5_000
MAX_BUDGET = 5_000_000
MAX_DURATION_DAYS = 120


def _blank(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _to_date(v):
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def validate_campaign(data, check_start_in_past=True):
    """Return a list of {field, message}. Empty list = valid."""
    errors = []

    def err(field, msg):
        errors.append({"field": field, "message": msg})

    # 1. Required fields -------------------------------------------------------------
    missing = set()
    for key, label in REQUIRED:
        if _blank(data.get(key)):
            err(key, f"{label} is required")
            missing.add(key)

    # 2. Controlled vocabularies -----------------------------------------------------
    if "Region" not in missing and data.get("Region") not in C.REGIONS:
        err("Region", "Region must be one of: " + ", ".join(C.REGIONS))
    if "Campaign_Type" not in missing and data.get("Campaign_Type") not in C.CAMPAIGN_TYPES:
        err("Campaign_Type", "Campaign type is not in the approved list")
    if "Objective" not in missing and data.get("Objective") not in C.OBJECTIVES:
        err("Objective", "Marketing objective must be one of: " + ", ".join(C.OBJECTIVES))
    if "Marketing_Channel" not in missing:
        chans = [c.strip() for c in str(data["Marketing_Channel"]).split("+") if c.strip()]
        bad = [c for c in chans if c not in C.CHANNELS]
        if not chans or bad:
            err("Marketing_Channel", "Unknown channel: " + ", ".join(bad) if bad else "Select at least one channel")

    # 3. Target audience / description quality --------------------------------------
    if "Target_Audience" not in missing and len(str(data["Target_Audience"]).strip()) < 5:
        err("Target_Audience", "Describe the target audience (at least 5 characters)")
    if "Campaign_Description" not in missing and len(str(data["Campaign_Description"]).strip()) < 20:
        err("Campaign_Description", "Campaign description must be at least 20 characters")
    link = data.get("Creative_Link")
    if not _blank(link) and not str(link).strip().lower().startswith(("http://", "https://")):
        err("Creative_Link", "Creative link must start with http:// or https://")

    # 4. Budget ----------------------------------------------------------------------
    budget = None
    if "Proposed_Budget" not in missing:
        budget = _num(data["Proposed_Budget"])
        if budget is None:
            err("Proposed_Budget", "Budget must be a number")
        elif budget <= 0:
            err("Proposed_Budget", "Budget must be greater than zero")
        elif budget < MIN_BUDGET:
            err("Proposed_Budget", f"Budget is below the minimum of ₹{MIN_BUDGET:,}")
        elif budget > MAX_BUDGET:
            err("Proposed_Budget", f"Budget exceeds the ₹{MAX_BUDGET:,} single-request ceiling; split or escalate")

    # 5. Dates -----------------------------------------------------------------------
    sd = ed = None
    if "Start_Date" not in missing:
        sd = _to_date(data["Start_Date"])
        if sd is None:
            err("Start_Date", "Start date must be a valid date (YYYY-MM-DD)")
        elif check_start_in_past and sd < clock.today():
            err("Start_Date", "Start date cannot be in the past")
    if "End_Date" not in missing:
        ed = _to_date(data["End_Date"])
        if ed is None:
            err("End_Date", "End date must be a valid date (YYYY-MM-DD)")
    if sd and ed:
        if ed < sd:
            err("End_Date", "End date cannot be before the start date")
        elif (ed - sd).days > MAX_DURATION_DAYS:
            err("End_Date", f"Campaign duration cannot exceed {MAX_DURATION_DAYS} days")

    # 6. Expected leads / conversions / revenue --------------------------------------
    leads = conv = None
    if "Expected_Leads" not in missing:
        leads = _num(data["Expected_Leads"])
        if leads is None or leads != int(leads):
            err("Expected_Leads", "Expected leads must be a whole number")
            leads = None
        elif leads <= 0:
            err("Expected_Leads", "Expected leads must be greater than zero")
    if "Expected_Conversions" not in missing:
        conv = _num(data["Expected_Conversions"])
        if conv is None or conv != int(conv):
            err("Expected_Conversions", "Expected conversions must be a whole number")
            conv = None
        elif conv < 0:
            err("Expected_Conversions", "Expected conversions cannot be negative")
        elif leads is not None and conv > leads:
            err("Expected_Conversions", "Expected conversions cannot exceed expected leads")
    if "Expected_Revenue" not in missing:
        rev = _num(data["Expected_Revenue"])
        if rev is None:
            err("Expected_Revenue", "Expected revenue must be a number")
        elif rev <= 0:
            err("Expected_Revenue", "Expected revenue must be greater than zero")
    return errors


def normalize(data):
    """Trim strings and coerce numbers so that the database stores clean values."""
    out = {}
    for key, _ in REQUIRED:
        out[key] = data.get(key)
    out["Creative_Link"] = data.get("Creative_Link")
    for k, v in list(out.items()):
        if isinstance(v, str):
            out[k] = v.strip()
    for k in ("Proposed_Budget", "Expected_Revenue"):
        n = _num(out.get(k))
        out[k] = n if n is not None else out.get(k)
    for k in ("Expected_Leads", "Expected_Conversions"):
        n = _num(out.get(k))
        out[k] = int(n) if n is not None and n == int(n) else out.get(k)
    if isinstance(out.get("Marketing_Channel"), list):
        out["Marketing_Channel"] = " + ".join(out["Marketing_Channel"])
    elif isinstance(out.get("Marketing_Channel"), str):
        out["Marketing_Channel"] = " + ".join(c.strip() for c in out["Marketing_Channel"].split("+") if c.strip())
    return out
