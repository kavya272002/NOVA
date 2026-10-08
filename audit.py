"""Audit trail (Google Sheets: AUDIT_TRAIL sheet, written only by Apps Script).

Business purpose: every material event is recorded with who / when / what / before / after,
so that any campaign can be reconstructed for an internal or statutory audit.
"""
from . import clock

EVENTS = [
    "Campaign Created", "Validation Completed", "Approval Requested", "Approval Granted",
    "Approval Rejected", "Sent Back for Revision", "Campaign Modified", "Governance Check",
    "Campaign Dispatched", "Campaign Executed", "Performance Updated", "Lead Captured",
]


def log_event(conn, user, action, campaign_id=None, prev_status=None, new_status=None, details=None):
    u = user or {}
    conn.execute(
        "INSERT INTO audit_trail(Timestamp, User, User_Role, Action, Campaign_ID, Previous_Status, New_Status, Details)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (clock.ts(), u.get("Name", "System"), u.get("Role", "System"), action, campaign_id,
         prev_status, new_status, details),
    )
