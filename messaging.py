"""In-app communication & chatbot messaging engine.

Enables instant communication between regional executives (e.g. Hyderabad, Delhi)
and approvers (Regional Manager, Marketing Manager) directly inside the app,
replacing untracked WhatsApp and email threads.
"""
from datetime import datetime
from engine import db


def send_message(conn, sender_user, content, campaign_id=None, recipient_id=None, recipient_name=None):
    """Send a chat message from sender_user."""
    if not content or not content.strip():
        return None

    if recipient_name and not recipient_id:
        r_user = conn.execute("SELECT User_ID FROM users WHERE Name=?", (recipient_name,)).fetchone()
        if r_user:
            recipient_id = r_user["User_ID"]

    now = datetime.now().isoformat()
    cur = conn.execute(
        """INSERT INTO chat_messages
           (Campaign_ID, Sender_ID, Sender_Name, Sender_Role, Recipient_ID, Recipient_Name, Content, Timestamp, Read_Status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (campaign_id, sender_user["User_ID"], sender_user["Name"], sender_user["Role"], recipient_id, recipient_name, content.strip(), now)
    )
    msg_id = cur.lastrowid

    # Auto-responder assistant logic if messaging the Governance Assistant
    if recipient_name and ("Assistant" in recipient_name or "Bot" in recipient_name or "assistant" in content.lower()):
        reply_content = generate_bot_reply(content, campaign_id, sender_user)
        conn.execute(
            """INSERT INTO chat_messages
               (Campaign_ID, Sender_ID, Sender_Name, Sender_Role, Recipient_ID, Recipient_Name, Content, Timestamp, Read_Status)
               VALUES (?, 0, 'Governance Assistant', 'AI Assistant', ?, ?, ?, ?, 1)""",
            (campaign_id, sender_user["User_ID"], sender_user["Name"], reply_content, datetime.now().isoformat())
        )

    return get_message(conn, msg_id)


def get_message(conn, msg_id):
    row = conn.execute("SELECT * FROM chat_messages WHERE Message_ID=?", (msg_id,)).fetchone()
    return db.row_to_dict(row)


def get_messages(conn, campaign_id=None, user_id=None, contact=None, limit=100):
    """Fetch messages between user_id and contact (or campaign_id)."""
    where_parts = []
    params = []

    if campaign_id:
        where_parts.append("Campaign_ID = ?")
        params.append(campaign_id)

    if contact:
        if "Assistant" in str(contact) or "Bot" in str(contact):
            where_parts.append("((Sender_ID = ? AND (Recipient_Name LIKE '%Assistant%' OR Recipient_ID = 0)) OR ((Sender_Name LIKE '%Assistant%' OR Sender_ID = 0) AND (Recipient_ID = ? OR Recipient_ID IS NULL)))")
            params.extend([user_id, user_id])
        else:
            contact_user = None
            try:
                contact_id = int(contact)
                contact_user = conn.execute("SELECT User_ID, Name FROM users WHERE User_ID=?", (contact_id,)).fetchone()
            except (ValueError, TypeError):
                contact_user = conn.execute("SELECT User_ID, Name FROM users WHERE Name=?", (str(contact),)).fetchone()

            if contact_user:
                c_id = contact_user["User_ID"]
                c_name = contact_user["Name"]
                where_parts.append("((Sender_ID = ? AND (Recipient_ID = ? OR Recipient_Name = ?)) OR (Sender_ID = ? AND (Recipient_ID = ? OR Recipient_Name = ?)) OR (Sender_Name = ? AND Recipient_ID = ?))")
                params.extend([user_id, c_id, c_name, c_id, user_id, user_id, c_name, user_id])
            else:
                c_name = str(contact)
                where_parts.append("((Sender_ID = ? AND Recipient_Name = ?) OR (Sender_Name = ? AND (Recipient_ID = ? OR Recipient_ID IS NULL)))")
                params.extend([user_id, c_name, c_name, user_id])
    elif user_id:
        where_parts.append("(Sender_ID = ? OR Recipient_ID = ? OR Recipient_ID IS NULL)")
        params.extend([user_id, user_id])

    sql = "SELECT * FROM chat_messages"
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    sql += " ORDER BY Message_ID ASC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return db.rows_to_list(rows)


def generate_bot_reply(prompt, campaign_id, user):
    """Simple intelligent helper for quick campaign approval status & rule guidance."""
    p = prompt.lower()
    if "rule" in p or "tier" in p or "budget" in p:
        return "Governance Rules: Campaigns < ₹50k require Regional Manager approval. ₹50k-₹2L require RM + Marketing Manager. Above ₹2L require 4 levels (RM, MM, MH, BH)."
    elif "status" in p or "approval" in p:
        if campaign_id:
            return f"Checking campaign {campaign_id}: All approvals are logged in SQLite triggers. Execution is locked until status reaches 'Fully Approved'."
        return "You can view all your campaign approval statuses on the Pending Approvals tab."
    else:
        return f"Hello {user['Name']}! I am your Governance Assistant. You can chat directly with your Regional Manager or track approval workflow requirements here."


def get_unread(conn, user_id):
    """Return unread message count and latest unread message for user_id."""
    cur_u = conn.execute("SELECT Name FROM users WHERE User_ID=?", (user_id,)).fetchone()
    u_name = cur_u["Name"] if cur_u else ""

    rows = conn.execute(
        """SELECT * FROM chat_messages
           WHERE (Recipient_ID = ? OR Recipient_Name = ?) AND Read_Status = 0 AND Sender_ID != ?
           ORDER BY Message_ID DESC""",
        (user_id, u_name, user_id)
    ).fetchall()
    msgs = db.rows_to_list(rows)
    return {"count": len(msgs), "latest": msgs[0] if msgs else None}


def mark_read(conn, user_id, contact=None):
    """Mark incoming messages as read for user_id."""
    cur_u = conn.execute("SELECT Name FROM users WHERE User_ID=?", (user_id,)).fetchone()
    u_name = cur_u["Name"] if cur_u else ""
    if contact:
        conn.execute(
            """UPDATE chat_messages SET Read_Status = 1
               WHERE (Recipient_ID = ? OR Recipient_Name = ?) AND (Sender_Name = ? OR Sender_ID = ?)""",
            (user_id, u_name, str(contact), str(contact))
        )
    else:
        conn.execute(
            """UPDATE chat_messages SET Read_Status = 1
               WHERE (Recipient_ID = ? OR Recipient_Name = ?)""",
            (user_id, u_name)
        )
    return True


def get_conversations(conn, user_id):
    """Summarize conversations per contact for user_id (for WhatsApp-style list sorting)."""
    cur_u = conn.execute("SELECT Name FROM users WHERE User_ID=?", (user_id,)).fetchone()
    u_name = cur_u["Name"] if cur_u else ""

    rows = conn.execute(
        """SELECT * FROM chat_messages
           WHERE Sender_ID = ? OR Recipient_ID = ? OR Recipient_Name = ?
           ORDER BY Message_ID DESC""",
        (user_id, user_id, u_name)
    ).fetchall()
    msgs = db.rows_to_list(rows)

    convs = {}
    for m in msgs:
        if m["Sender_ID"] == user_id:
            contact = m["Recipient_Name"] or "Governance Assistant"
        else:
            contact = m["Sender_Name"] or "Governance Assistant"

        if contact not in convs:
            convs[contact] = {
                "contact_name": contact,
                "unread_count": 0,
                "last_message": m["Content"],
                "last_timestamp": m["Timestamp"],
                "last_sender": m["Sender_Name"]
            }

        is_unread = (m["Recipient_ID"] == user_id or m["Recipient_Name"] == u_name) and m["Read_Status"] == 0 and m["Sender_ID"] != user_id
        if is_unread:
            convs[contact]["unread_count"] += 1

    return list(convs.values())
