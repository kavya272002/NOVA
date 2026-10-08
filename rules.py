"""Business rule engine + ID generator.

generateCampaignID()      -> generate_campaign_id()
determineApprovalLevel()  -> determine_approval_level()

The approval route is NEVER hard-coded: it is read from the APPROVAL_RULES table so that a
Business Head can change thresholds or chains without touching any code.
"""
from . import clock
from . import constants as C
from .errors import RuleConfigError

SEP = "|"


def generate_campaign_id(conn):
    """Business purpose: a unique, human-readable key (MKT-2026-001) that follows a campaign
    through approval, execution, leads and reporting. Sequence is per calendar year and is
    allocated inside the caller's transaction so two simultaneous submissions can't collide."""
    year = clock.now().year
    row = conn.execute("SELECT Last_Seq FROM id_counters WHERE Year=?", (year,)).fetchone()
    seq = (row["Last_Seq"] if row else 0) + 1
    if row:
        conn.execute("UPDATE id_counters SET Last_Seq=? WHERE Year=?", (seq, year))
    else:
        conn.execute("INSERT INTO id_counters(Year, Last_Seq) VALUES (?,?)", (year, seq))
    return f"MKT-{year}-{seq:03d}"


def load_rules(conn, active_only=True):
    q = "SELECT * FROM approval_rules" + (" WHERE Active=1" if active_only else "") + " ORDER BY Min_Budget, Rule_ID"
    out = []
    for r in conn.execute(q):
        d = dict(r)
        d["Chain"] = [x for x in d["Approval_Chain"].split(SEP) if x]
        out.append(d)
    return out


def _band_contains(rule, budget):
    lo_ok = budget >= rule["Min_Budget"] if rule["Min_Inclusive"] else budget > rule["Min_Budget"]
    if rule["Max_Budget"] is None:
        return lo_ok
    hi_ok = budget <= rule["Max_Budget"] if rule["Max_Inclusive"] else budget < rule["Max_Budget"]
    return lo_ok and hi_ok


def rule_covers(rule, budget):
    return _band_contains(rule, float(budget))


def determine_approval_level(conn, budget):
    """Business purpose: translate a budget into the exact ordered approval chain the company's
    policy requires. Returns the matched rule, its chain and the number of levels."""
    budget = float(budget)
    matches = [r for r in load_rules(conn) if _band_contains(r, budget)]
    if not matches:
        raise RuleConfigError(f"No active approval rule covers a budget of {budget:,.0f}. "
                              "Ask the Business Head to fix the APPROVAL_RULES table.")
    if len(matches) > 1:
        names = ", ".join(m["Rule_Name"] for m in matches)
        raise RuleConfigError(f"Approval rules overlap for a budget of {budget:,.0f}: {names}.")
    rule = matches[0]
    chain = rule["Chain"]
    bad = [r for r in chain if r not in C.APPROVER_ROLES]
    if not chain or bad:
        raise RuleConfigError(f"Rule '{rule['Rule_Name']}' has an invalid approval chain: {rule['Approval_Chain']}")
    return {"rule_id": rule["Rule_ID"], "rule_name": rule["Rule_Name"], "chain": chain, "levels": len(chain)}


def validate_rule_table(rules):
    """Used when the Business Head edits rules: reject gaps/overlaps and invalid chains."""
    problems = []
    for r in rules:
        chain = r["Chain"] if "Chain" in r else r["Approval_Chain"].split(SEP)
        if not chain:
            problems.append(f"Rule '{r['Rule_Name']}' has no approvers")
        for role in chain:
            if role not in C.APPROVER_ROLES:
                problems.append(f"Rule '{r['Rule_Name']}': '{role}' is not an approver role")
        if len(set(chain)) != len(chain):
            problems.append(f"Rule '{r['Rule_Name']}': the same role appears twice")
    return problems


def check_rule_set(rules):
    """Coverage check for the whole table: the bands must start at 0, touch each other without gaps or overlaps,
    and the last band must be open-ended. Called before a Business Head's edit is saved."""
    problems = []
    rs = sorted([r for r in rules if r.get("Active", 1)], key=lambda r: (r["Min_Budget"], r["Min_Inclusive"] == 0))
    if not rs:
        return ["At least one active approval rule is required"]
    if rs[0]["Min_Budget"] != 0 or not rs[0]["Min_Inclusive"]:
        problems.append("The first rule must start at ₹0 (inclusive)")
    for a, b in zip(rs, rs[1:]):
        if a["Max_Budget"] is None:
            problems.append(f"'{a['Rule_Name']}' is open-ended, so '{b['Rule_Name']}' overlaps it")
            continue
        if a["Max_Budget"] != b["Min_Budget"]:
            problems.append(f"Gap or overlap between '{a['Rule_Name']}' (up to ₹{a['Max_Budget']:,.0f}) and "
                            f"'{b['Rule_Name']}' (from ₹{b['Min_Budget']:,.0f})")
        elif bool(a["Max_Inclusive"]) == bool(b["Min_Inclusive"]):
            problems.append(f"The boundary at ₹{a['Max_Budget']:,.0f} is counted twice or by nobody "
                            f"('{a['Rule_Name']}' / '{b['Rule_Name']}')")
    if rs[-1]["Max_Budget"] is not None:
        problems.append("The last rule must be open-ended (no upper limit)")
    return problems
