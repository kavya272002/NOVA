"""Central database (the 'Google Sheets' layer).

SQLite stands in for the Google Sheets workbook. Column names are kept identical to the
sheet headers in the project brief so the mapping is 1:1.

Governance is enforced *inside the database* with triggers, not only in the UI:
  * Execution_Status can never become 'Ready for Execution' / 'Executed' unless
    Approval_Status = 'Fully Approved'                      (Google Sheets: protected range + onEdit guard)
  * 'Fully Approved' is impossible unless every required approval level is logged for the
    current revision                                        (Google Sheets: onEdit validation)
  * Approval fields are frozen while a request is pending or approved
  * APPROVAL_LOG and AUDIT_TRAIL are append-only           (Google Sheets: protected sheets, no edit rights)
"""
import os
import sqlite3
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("NOVA_DB", os.path.join(BASE_DIR, "data", "nova_marketing.db"))

SCHEMA = """
CREATE TABLE users (
    User_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Name TEXT NOT NULL,
    Email TEXT NOT NULL UNIQUE,
    Role TEXT NOT NULL,
    Region TEXT NOT NULL,
    Password_Hash TEXT NOT NULL,
    Active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE settings (
    Key TEXT PRIMARY KEY,
    Value TEXT NOT NULL,
    Description TEXT
);

CREATE TABLE id_counters (
    Year INTEGER PRIMARY KEY,
    Last_Seq INTEGER NOT NULL
);

CREATE TABLE approval_rules (
    Rule_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Rule_Name TEXT NOT NULL,
    Min_Budget REAL NOT NULL,
    Min_Inclusive INTEGER NOT NULL DEFAULT 1,
    Max_Budget REAL,
    Max_Inclusive INTEGER NOT NULL DEFAULT 0,
    Approval_Chain TEXT NOT NULL,          -- ordered roles separated by '|'
    Active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE campaign_requests (
    Campaign_ID TEXT PRIMARY KEY,
    Submission_Date TEXT NOT NULL,
    Region TEXT,
    Requester_Name TEXT NOT NULL,
    Requester_Email TEXT NOT NULL,
    Campaign_Name TEXT,
    Product TEXT,
    Campaign_Type TEXT,
    Objective TEXT,
    Target_Audience TEXT,
    Marketing_Channel TEXT,
    Start_Date TEXT,
    End_Date TEXT,
    Proposed_Budget REAL,
    Expected_Leads INTEGER,
    Expected_Conversions INTEGER,
    Expected_Revenue REAL,
    Campaign_Description TEXT,
    Creative_Link TEXT,
    Approval_Level INTEGER,                -- number of approval levels required by the rule engine
    Current_Approver TEXT,
    Approval_Status TEXT NOT NULL DEFAULT 'Draft',
    Execution_Status TEXT NOT NULL DEFAULT 'Not Ready',
    Rejection_Reason TEXT,
    Created_Timestamp TEXT NOT NULL,
    Updated_Timestamp TEXT NOT NULL,
    -- system columns (hidden helper columns in the Google Sheet)
    Requester_ID INTEGER NOT NULL,
    Approval_Chain TEXT,
    Approval_Step INTEGER NOT NULL DEFAULT 0,
    Rule_ID INTEGER,
    Revision_No INTEGER NOT NULL DEFAULT 0,
    Validation_Errors TEXT,
    Submitted_Timestamp TEXT,
    Approved_Timestamp TEXT,
    Ready_Timestamp TEXT,
    Executed_Timestamp TEXT
);

CREATE TABLE approval_log (
    Approval_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Campaign_ID TEXT NOT NULL REFERENCES campaign_requests(Campaign_ID),
    Approver_Name TEXT NOT NULL,
    Approver_Role TEXT NOT NULL,
    Approval_Level INTEGER NOT NULL,
    Decision TEXT NOT NULL,                -- Approved | Rejected | Sent Back
    Decision_Date TEXT NOT NULL,
    Comments TEXT,
    Previous_Status TEXT,
    New_Status TEXT,
    Revision_No INTEGER NOT NULL,
    Approver_ID INTEGER NOT NULL
);

CREATE TABLE audit_trail (
    Audit_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Timestamp TEXT NOT NULL,
    User TEXT NOT NULL,
    User_Role TEXT,
    Action TEXT NOT NULL,
    Campaign_ID TEXT,
    Previous_Status TEXT,
    New_Status TEXT,
    Details TEXT
);

CREATE TABLE notifications (
    Notification_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Timestamp TEXT NOT NULL,
    Campaign_ID TEXT,
    Notification_Type TEXT NOT NULL,
    To_Name TEXT NOT NULL,
    To_Email TEXT NOT NULL,
    Subject TEXT NOT NULL,
    Body TEXT NOT NULL,
    Channel TEXT NOT NULL DEFAULT 'Gmail (simulated)',
    Status TEXT NOT NULL DEFAULT 'Sent'
);

CREATE TABLE chat_messages (
    Message_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Campaign_ID TEXT,
    Sender_ID INTEGER NOT NULL,
    Sender_Name TEXT NOT NULL,
    Sender_Role TEXT NOT NULL,
    Recipient_ID INTEGER,
    Recipient_Name TEXT,
    Content TEXT NOT NULL,
    Timestamp TEXT NOT NULL,
    Read_Status INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE lead_data (
    Lead_ID TEXT PRIMARY KEY,
    Campaign_ID TEXT NOT NULL REFERENCES campaign_requests(Campaign_ID),
    Region TEXT NOT NULL,
    Lead_Source TEXT NOT NULL,
    Lead_Date TEXT NOT NULL,
    Customer_Segment TEXT NOT NULL,
    Lead_Score INTEGER NOT NULL,
    Lead_Status TEXT NOT NULL,
    Sales_Assigned TEXT NOT NULL,
    Conversion_Status TEXT NOT NULL,
    Revenue REAL NOT NULL DEFAULT 0
);
CREATE INDEX idx_lead_campaign ON lead_data(Campaign_ID);

-- Input columns are entered/synced; the metric columns are GENERATED (= spreadsheet formulas).
CREATE TABLE campaign_performance (
    Campaign_ID TEXT PRIMARY KEY REFERENCES campaign_requests(Campaign_ID),
    Campaign_Name TEXT,
    Region TEXT,
    Budget REAL NOT NULL DEFAULT 0,
    Actual_Spend REAL NOT NULL DEFAULT 0,
    Impressions INTEGER NOT NULL DEFAULT 0,
    Clicks INTEGER NOT NULL DEFAULT 0,
    Leads INTEGER NOT NULL DEFAULT 0,
    Qualified_Leads INTEGER NOT NULL DEFAULT 0,
    Conversions INTEGER NOT NULL DEFAULT 0,
    Revenue REAL NOT NULL DEFAULT 0,
    Last_Updated TEXT,
    CPL REAL GENERATED ALWAYS AS (CASE WHEN Leads > 0 THEN Actual_Spend * 1.0 / Leads END) VIRTUAL,
    Conversion_Rate REAL GENERATED ALWAYS AS (CASE WHEN Leads > 0 THEN Conversions * 1.0 / Leads END) VIRTUAL,
    ROAS REAL GENERATED ALWAYS AS (CASE WHEN Actual_Spend > 0 THEN Revenue * 1.0 / Actual_Spend END) VIRTUAL,
    ROI REAL GENERATED ALWAYS AS (CASE WHEN Actual_Spend > 0 THEN (Revenue - Actual_Spend) * 1.0 / Actual_Spend END) VIRTUAL
);

CREATE VIEW v_campaign_pipeline AS
SELECT Campaign_ID,
  CASE
    WHEN Approval_Status IN ('Draft','Validation Failed') THEN 'Draft'
    WHEN Approval_Status = 'Pending Approval' THEN 'Pending Approval'
    WHEN Approval_Status = 'Rejected' THEN 'Rejected'
    WHEN Approval_Status = 'Rework Required' THEN 'Rework Required'
    WHEN Approval_Status = 'Fully Approved' AND Execution_Status = 'Executed' THEN 'Executed'
    WHEN Approval_Status = 'Fully Approved' AND Execution_Status = 'Ready for Execution' THEN 'Ready for Execution'
    WHEN Approval_Status = 'Fully Approved' THEN 'Approved'
    ELSE Approval_Status
  END AS Pipeline_Stage
FROM campaign_requests;

-- ===================== GOVERNANCE TRIGGERS =====================
CREATE TRIGGER trg_gov_exec_insert BEFORE INSERT ON campaign_requests
WHEN NEW.Execution_Status IN ('Ready for Execution','Executed') AND NEW.Approval_Status <> 'Fully Approved'
BEGIN
    SELECT RAISE(ABORT, 'GOVERNANCE VIOLATION: Execution_Status cannot be Ready for Execution/Executed unless Approval_Status is Fully Approved');
END;

CREATE TRIGGER trg_gov_exec_update BEFORE UPDATE OF Execution_Status, Approval_Status ON campaign_requests
WHEN NEW.Execution_Status IN ('Ready for Execution','Executed') AND NEW.Approval_Status <> 'Fully Approved'
BEGIN
    SELECT RAISE(ABORT, 'GOVERNANCE VIOLATION: Execution_Status cannot be Ready for Execution/Executed unless Approval_Status is Fully Approved');
END;

CREATE TRIGGER trg_gov_full_approval BEFORE UPDATE OF Approval_Status ON campaign_requests
WHEN NEW.Approval_Status = 'Fully Approved' AND OLD.Approval_Status <> 'Fully Approved'
 AND (SELECT COUNT(DISTINCT Approval_Level) FROM approval_log
       WHERE Campaign_ID = NEW.Campaign_ID AND Revision_No = NEW.Revision_No AND Decision = 'Approved')
     < COALESCE(NEW.Approval_Level, 999)
BEGIN
    SELECT RAISE(ABORT, 'GOVERNANCE VIOLATION: Fully Approved requires every required approval level to be logged for the current revision');
END;

CREATE TRIGGER trg_gov_freeze BEFORE UPDATE OF Region, Campaign_Name, Product, Campaign_Type, Objective,
    Target_Audience, Marketing_Channel, Start_Date, End_Date, Proposed_Budget, Expected_Leads,
    Expected_Conversions, Expected_Revenue ON campaign_requests
WHEN OLD.Approval_Status IN ('Pending Approval','Fully Approved')
BEGIN
    SELECT RAISE(ABORT, 'GOVERNANCE VIOLATION: campaign details are locked while pending approval or after approval');
END;

CREATE TRIGGER trg_approval_log_no_update BEFORE UPDATE ON approval_log
BEGIN SELECT RAISE(ABORT, 'AUDIT PROTECTION: APPROVAL_LOG is append-only'); END;
CREATE TRIGGER trg_approval_log_no_delete BEFORE DELETE ON approval_log
BEGIN SELECT RAISE(ABORT, 'AUDIT PROTECTION: APPROVAL_LOG is append-only'); END;
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE ON audit_trail
BEGIN SELECT RAISE(ABORT, 'AUDIT PROTECTION: AUDIT_TRAIL is append-only'); END;
CREATE TRIGGER trg_audit_no_delete BEFORE DELETE ON audit_trail
BEGIN SELECT RAISE(ABORT, 'AUDIT PROTECTION: AUDIT_TRAIL is append-only'); END;
"""


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)


@contextmanager
def transaction(conn):
    """One business operation = one atomic transaction.

    Exceptions flagged ``persist`` (denied/blocked attempts) still commit so that the
    attempt is recorded in the audit trail; everything else rolls back cleanly.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception as exc:  # noqa: BLE001
        if getattr(exc, "persist", False):
            conn.execute("COMMIT")
        else:
            conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


def get_setting(conn, key, default=None, cast=str):
    r = conn.execute("SELECT Value FROM settings WHERE Key=?", (key,)).fetchone()
    if r is None:
        return default
    try:
        return cast(r["Value"])
    except (TypeError, ValueError):
        return default
