"""Role-based access control helpers (Google Sheets/AppSheet: user-role table + security filters)."""
from werkzeug.security import check_password_hash, generate_password_hash

from . import constants as C

SYSTEM_USER = {"User_ID": 0, "Name": "System (Automation Engine)", "Email": "automation@novabrands.in",
               "Role": C.ROLE_SYSTEM, "Region": "All"}


def hash_password(pw):
    return generate_password_hash(pw)


def authenticate(conn, email, password):
    r = conn.execute("SELECT * FROM users WHERE lower(Email)=lower(?) AND Active=1", (email or "",)).fetchone()
    if r and check_password_hash(r["Password_Hash"], password or ""):
        return public_user(dict(r))
    return None


def get_user(conn, user_id):
    r = conn.execute("SELECT * FROM users WHERE User_ID=? AND Active=1", (user_id,)).fetchone()
    return public_user(dict(r)) if r else None


def get_user_by_email(conn, email):
    r = conn.execute("SELECT * FROM users WHERE lower(Email)=lower(?) AND Active=1", (email,)).fetchone()
    return public_user(dict(r)) if r else None


def public_user(u):
    u = dict(u)
    u.pop("Password_Hash", None)
    return u


def find_approver(conn, role, region):
    """Return the user who holds `role` for `region` (Regional Managers are region-specific)."""
    if role == C.ROLE_RM:
        r = conn.execute("SELECT * FROM users WHERE Role=? AND Region=? AND Active=1 ORDER BY User_ID LIMIT 1",
                         (role, region)).fetchone()
    else:
        r = conn.execute("SELECT * FROM users WHERE Role=? AND Active=1 ORDER BY User_ID LIMIT 1", (role,)).fetchone()
    return public_user(dict(r)) if r else None


def users_with_role(conn, role):
    return [public_user(dict(r)) for r in
            conn.execute("SELECT * FROM users WHERE Role=? AND Active=1 ORDER BY User_ID", (role,))]


def scope_clause(user, alias=""):
    """SQL filter limiting which campaigns a user may see.

    Executive -> own requests | Regional Manager -> own region | everyone else -> all.
    """
    a = alias + "." if alias else ""
    role = user["Role"]
    if role == C.ROLE_EXEC:
        return f"{a}Requester_ID = ?", [user["User_ID"]]
    if role == C.ROLE_RM:
        return f"{a}Region = ?", [user["Region"]]
    return "1=1", []


def can_view(user, campaign):
    role = user["Role"]
    if role == C.ROLE_EXEC:
        return campaign["Requester_ID"] == user["User_ID"]
    if role == C.ROLE_RM:
        return campaign["Region"] == user["Region"]
    return True


def experience(role):
    """Which of the three user experiences a role belongs to."""
    if role == C.ROLE_EXEC:
        return "EXECUTIVE"
    if role in (C.ROLE_RM, C.ROLE_MM):
        return "MANAGER"
    if role in (C.ROLE_MH, C.ROLE_BH):
        return "MANAGEMENT"
    if role == C.ROLE_EXECUTION:
        return "EXECUTION"
    return "OTHER"
