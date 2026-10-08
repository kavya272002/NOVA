"""Create and populate the sample database.

Every campaign below is pushed through the REAL workflow functions (create -> validate -> route -> approve ->
dispatch -> execute -> performance) with the clock moved back in time, so the sample data carries a genuine audit
trail, approval log and notifications - not hand-typed rows.   Run:  python seed.py
"""
import os
import random
import sys
from datetime import datetime, timedelta

from engine import auth, clock, db, tracking, workflow
from engine import constants as C
from engine.errors import GovernanceError

PASSWORD = "Demo@123"
DOMAIN = "novabrands.in"

USERS = [  # name, role, region
    ("Aman Sharma", C.ROLE_EXEC, "Delhi NCR"), ("Rahul Mehta", C.ROLE_RM, "Delhi NCR"),
    ("Kunal Saxena", C.ROLE_EXEC, "Delhi NCR"),
    ("Sneha Iyer", C.ROLE_EXEC, "Mumbai"), ("Vikram Desai", C.ROLE_RM, "Mumbai"),
    ("Karthik Rao", C.ROLE_EXEC, "Bangalore"), ("Anita Nair", C.ROLE_RM, "Bangalore"),
    ("Imran Qureshi", C.ROLE_EXEC, "Hyderabad"), ("Lakshmi Reddy", C.ROLE_RM, "Hyderabad"),
    ("Divya Krishnan", C.ROLE_EXEC, "Chennai"), ("Suresh Babu", C.ROLE_RM, "Chennai"),
    ("Priya Kapoor", C.ROLE_MM, "All"), ("Arjun Malhotra", C.ROLE_MH, "All"), ("Neha Verma", C.ROLE_BH, "All"),
    ("Rohit Bansal", C.ROLE_EXECUTION, "All"),
]

RULES = [  # name, min, min_incl, max, max_incl, chain
    ("Tier 1 - Below ₹50,000", 0, 1, 50000, 0, [C.ROLE_RM]),
    ("Tier 2 - ₹50,000 to ₹2,00,000", 50000, 1, 200000, 1, [C.ROLE_RM, C.ROLE_MM]),
    ("Tier 3 - Above ₹2,00,000", 200000, 0, None, 0, [C.ROLE_RM, C.ROLE_MM, C.ROLE_MH, C.ROLE_BH]),
]

SETTINGS = [
    ("qualified_score_threshold", "60", "Lead score at/above which a lead counts as a Qualified Lead"),
    ("before_minutes", "120", "SIMULATED: average manual approval/coordination time (minutes)"),
    ("target_minutes", "25", "Target ceiling for a standard automated request (minutes)"),
    ("before_touchpoints", "14", "SIMULATED: manual touchpoints per campaign (e-mails, WhatsApp pings, sheet edits)"),
    ("before_followups", "6", "SIMULATED: follow-up messages per campaign before automation"),
    ("before_undocumented_pct", "30", "SIMULATED: % of requests with incomplete approval records before automation"),
    ("approval_sla_minutes", "240", "A pending approval older than this is flagged overdue"),
]

# (region, exec, name, product, type, objective, channels, audience, budget, exp_leads, exp_conv, exp_rev, description,
#  outcome, params)
CAMPAIGNS = [
    ("Delhi NCR", "Aman Sharma", "Summer Glow Skincare Sprint", "NovaGlow Skincare", "Lead Generation", "Lead Generation",
     "Instagram + Google Ads", "Women 22-38 in Delhi NCR interested in skincare", 120000, 800, 80, 650000,
     "Four-week lead generation sprint for the new SPF range using Instagram reels and branded search.",
     "executed", dict(ago=196, steps=[10, 13], lead_days=9, dur=28,
                      perf=dict(impr=250000, clicks=12500, leads=850, qual=420, conv=95, rev=720000, spend=108500))),
    ("Mumbai", "Sneha Iyer", "Monsoon Home Care Bundle Offer", "FreshNest Home Care", "Seasonal Sale", "Sales Conversion",
     "Facebook + Instagram + WhatsApp Business", "Urban families in Mumbai suburbs", 350000, 650, 80, 640000,
     "Monsoon bundle of floor cleaner, fabric care and dish wash with a limited-period combo price.",
     "executed", dict(ago=170, steps=[12, 14, 15, 11], lead_days=10, dur=35,
                      perf=dict(impr=420000, clicks=21000, leads=612, qual=301, conv=74, rev=610000, spend=318000))),
    ("Bangalore", "Karthik Rao", "Tech Park Snack Break Sampling", "CrunchBay Snacks", "Retail Activation", "Brand Awareness",
     "Retail In-store + Instagram", "IT professionals in Bangalore tech parks", 40000, 150, 12, 70000,
     "On-site sampling counters in five tech parks to build awareness of the new peri-peri range.",
     "executed", dict(ago=152, steps=[12], lead_days=8, dur=21,
                      perf=dict(impr=60000, clicks=2400, leads=140, qual=52, conv=11, rev=62000, spend=36500))),
    ("Hyderabad", "Imran Qureshi", "AquaPure Family Safe Water Drive", "AquaPure Water Purifiers", "Lead Generation", "Lead Generation",
     "Google Ads + Facebook", "Households in Hyderabad with hard-water complaints", 160000, 550, 55, 450000,
     "Lead generation for home demos of the RO+UV purifier targeted at hard-water localities.",
     "executed", dict(ago=133, steps=[11, 12], lead_days=8, dur=30,
                      perf=dict(impr=310000, clicks=11800, leads=520, qual=268, conv=49, rev=410000, spend=148000))),
    ("Chennai", "Divya Krishnan", "Summer Cooler Chai Chill", "Brewlane Tea & Coffee", "Seasonal Sale", "Sales Conversion",
     "YouTube + Instagram", "Tea drinkers in Chennai aged 20-40", 85000, 300, 36, 230000,
     "Iced-tea range push over summer with short video ads and creator collaborations.",
     "executed", dict(ago=118, steps=[14, 12], lead_days=7, dur=28,
                      perf=dict(impr=240000, clicks=9100, leads=310, qual=140, conv=38, rev=245000, spend=79000))),
    ("Delhi NCR", "Kunal Saxena", "Voltix Smart Home Expo Leads", "Voltix Smart Appliances", "Product Launch", "Lead Generation",
     "Google Ads + YouTube + Email", "Home owners in Delhi NCR planning appliance upgrades", 220000, 420, 36, 600000,
     "Product launch campaign around the smart-appliance expo with gated demo bookings.",
     "executed", dict(ago=101, steps=[10, 14, 13, 16], lead_days=9, dur=35,
                      perf=dict(impr=380000, clicks=14200, leads=405, qual=188, conv=31, rev=530000, spend=205000))),
    ("Mumbai", "Sneha Iyer", "KidoJoy New Parents Webinar Series", "KidoJoy Baby Care", "Lead Generation", "Lead Generation",
     "Instagram + Email", "New and expecting parents in Mumbai", 45000, 200, 20, 120000,
     "Fortnightly webinars with pediatricians and sampling offer for sign-ups.",
     "executed", dict(ago=84, steps=[11], lead_days=7, dur=21,
                      perf=dict(impr=92000, clicks=3900, leads=190, qual=98, conv=22, rev=118000, spend=41000))),
    ("Bangalore", "Karthik Rao", "StrideX Run Club Launch", "StrideX Footwear", "Product Launch", "Market Expansion",
     "Influencer + Instagram", "Amateur runners in Bangalore", 190000, 500, 55, 360000,
     "Run-club partnership and influencer challenge to launch the new trail running shoe.",
     "executed", dict(ago=67, steps=[12, 15], lead_days=9, dur=35,
                      perf=dict(impr=520000, clicks=17300, leads=470, qual=214, conv=57, rev=340000, spend=184000))),
    ("Hyderabad", "Imran Qureshi", "Biryani Season Snack Pairing", "CrunchBay Snacks", "Seasonal Sale", "Sales Conversion",
     "Instagram + Facebook + Retail In-store", "Families in Hyderabad shopping at modern trade stores", 70000, 260, 26, 90000,
     "In-store pairing promotion with a free mini pack for every festive-meal basket.",
     "executed", dict(ago=52, steps=[12, 12], lead_days=8, dur=24,
                      perf=dict(impr=150000, clicks=5200, leads=180, qual=70, conv=12, rev=48000, spend=66000))),
    ("Chennai", "Divya Krishnan", "AquaPure Monsoon Service Camp", "AquaPure Water Purifiers", "Retail Activation", "Lead Generation",
     "Retail In-store + WhatsApp Business", "Existing AquaPure owners and neighbours in Chennai", 55000, 220, 22, 150000,
     "Free filter-health check camps in residential societies to generate service and upgrade leads.",
     "ready", dict(ago_days=4, steps=[13, 10], lead_days=7, dur=21)),
    ("Delhi NCR", "Aman Sharma", "Navratri Skincare Gift Sets", "NovaGlow Skincare", "Festive Promotion", "Sales Conversion",
     "Instagram + Influencer + WhatsApp Business", "Gifting shoppers in Delhi NCR, women 25-45", 260000, 700, 90, 800000,
     "Festive gift-set campaign with creator unboxings and WhatsApp catalogue orders.",
     "ready", dict(ago_days=6, steps=[13, 15, 14, 17], lead_days=6, dur=21)),
    ("Mumbai", "Sneha Iyer", "FreshNest Fabric Care Refresh", "FreshNest Home Care", "Seasonal Sale", "Sales Conversion",
     "Facebook + WhatsApp Business", "Households in Mumbai with washing machines", 30000, 120, 14, 60000,
     "Short promotional burst for the new liquid detergent pack with a coupon.",
     "pending", dict(steps=[], waiting=1500, lead_days=8, dur=14)),
    ("Bangalore", "Karthik Rao", "StrideX Office Comfort Range", "StrideX Footwear", "Product Launch", "Lead Generation",
     "Google Ads + Instagram", "Office-going professionals in Bangalore", 145000, 380, 38, 330000,
     "Launch of the lightweight office-comfort shoe line targeted at hybrid workers.",
     "pending", dict(steps=[12], waiting=380, lead_days=9, dur=28)),
    ("Hyderabad", "Imran Qureshi", "Brewlane Cold Brew Trial Drive", "Brewlane Tea & Coffee", "Product Launch", "Lead Generation",
     "Instagram + YouTube", "Coffee drinkers in Hyderabad aged 22-35", 110000, 360, 40, 280000,
     "Cold-brew trial pack campaign driving sample requests through short video ads.",
     "pending", dict(steps=[13], waiting=4300, lead_days=10, dur=28)),
    ("Chennai", "Divya Krishnan", "Voltix Smart Appliances Exchange Mela", "Voltix Smart Appliances", "Festive Promotion", "Sales Conversion",
     "Google Ads + Facebook + Email", "Home owners in Chennai with appliances older than 8 years", 420000, 900, 100, 1500000,
     "Exchange festival offering instant trade-in value on old appliances with bank partner offers.",
     "pending", dict(steps=[11, 14], waiting=1560, lead_days=10, dur=30)),
    ("Delhi NCR", "Kunal Saxena", "KidoJoy Festive Gifting Drive", "KidoJoy Baby Care", "Festive Promotion", "Sales Conversion",
     "Instagram + Google Ads + Influencer + Email", "Parents of children under 5 in Delhi NCR", 650000, 1500, 150, 2000000,
     "Large festive gifting programme with influencer parents and curated gift hampers.",
     "pending", dict(steps=[12, 15, 14], waiting=310, lead_days=12, dur=40)),
    ("Bangalore", "Karthik Rao", "Whitefield Billboard Blitz", "Voltix Smart Appliances", "Brand Awareness", "Brand Awareness",
     "Outdoor / OOH", "Commuters on Outer Ring Road, Bangalore", 240000, 300, 20, 400000,
     "High-visibility billboard takeover across the Whitefield and ORR corridor for two weeks.",
     "rejected", dict(ago_days=24, steps=[14], reject_level=2, lead_days=14, dur=14,
                      reason="Expected leads are too low for a ₹2.4L OOH spend (₹800 per lead). ROI not justified; use digital with trackable response.")),
    ("Mumbai", "Sneha Iyer", "Instagram Always-On Skincare Push", "NovaGlow Skincare", "Brand Awareness", "Brand Awareness",
     "Instagram", "Women 20-35 in Mumbai", 90000, 250, 25, 140000,
     "Always-on Instagram awareness push for the skincare range.",
     "rejected", dict(ago_days=14, steps=[], reject_level=1, lead_days=10, dur=28,
                      reason="Overlaps with the running Instagram campaign for the same audience; budget duplication.")),
    ("Hyderabad", "Imran Qureshi", "Hyderabad Household Savings Fair", "FreshNest Home Care", "Lead Generation", "Lead Generation",
     "Facebook + Google Ads", "Households in Hyderabad", 175000, 450, 45, 300000,
     "Savings fair to generate leads for monthly subscription refills of home-care products.",
     "rework", dict(ago_days=11, steps=[13], rework_level=2, lead_days=12, dur=21,
                    reason="Target audience is too broad. Split by locality and segment, and add the creative link before resubmitting.")),
    ("Chennai", "Divya Krishnan", "Brewlane Filter Coffee Bundles", "Brewlane Tea & Coffee", "Seasonal Sale", "Sales Conversion",
     "WhatsApp Business + Email", "Existing Brewlane customers in Chennai", 35000, 100, 30, 90000,
     "WhatsApp and email push for filter-coffee bundles to existing customers.",
     "rework", dict(ago_days=7, steps=[], rework_level=1, lead_days=9, dur=14,
                    reason="30% conversion expectation is unrealistic compared with the last two campaigns (about 8-10%). Please revise.")),
    ("Delhi NCR", "Kunal Saxena", "Winter Wellness Snack Box", "CrunchBay Snacks", "Seasonal Sale", "Sales Conversion",
     "Instagram", "Health-conscious professionals in Delhi NCR", 60000, None, None, None, None,
     "draft", dict(ago_days=2, lead_days=15, dur=21)),
    ("Mumbai", "Sneha Iyer", "Local Train Commuter Offer", "StrideX Footwear", "Lead Generation", None,
     "Facebook", "Daily commuters", 80000, 100, 150, 200000,
     "Commuter offer for comfortable walking shoes through targeted Facebook ads.",
     "valfail", dict(ago_days=1, lead_days=10, dur=14, creative="www.example.com/creative")),
]


def _user(conn, name):
    return auth.get_user_by_email(conn, name.lower().replace(" ", ".") + "@" + DOMAIN)


def _approver(conn, role, region):
    return auth.find_approver(conn, role, region)


def reset_database(path=None):
    path = path or db.DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(path + ext):
            os.remove(path + ext)
    conn = db.connect(path)
    db.init_schema(conn)
    return conn


def populate(conn):
    rng = random.Random(2026)
    now = datetime.now().replace(second=0, microsecond=0)
    pw = auth.hash_password(PASSWORD)
    for name, role, region in USERS:
        conn.execute("INSERT INTO users(Name, Email, Role, Region, Password_Hash) VALUES (?,?,?,?,?)",
                     (name, name.lower().replace(" ", ".") + "@" + DOMAIN, role, region, pw))
    for k, v, d in SETTINGS:
        conn.execute("INSERT INTO settings(Key, Value, Description) VALUES (?,?,?)", (k, v, d))
    for name, lo, lo_i, hi, hi_i, chain in RULES:
        conn.execute("INSERT INTO approval_rules(Rule_Name, Min_Budget, Min_Inclusive, Max_Budget, Max_Inclusive, Approval_Chain)"
                     " VALUES (?,?,?,?,?,?)", (name, lo, lo_i, hi, hi_i, "|".join(chain)))

    # ---- work out each campaign's submission time, then create them in chronological order
    plan = []
    for spec in CAMPAIGNS:
        p = spec[-1]
        outcome = spec[-2]
        if outcome == "executed":
            sub = now - timedelta(days=p["ago"], hours=rng.randint(0, 3), minutes=rng.randint(0, 50))
        elif outcome == "pending":
            sub = now - timedelta(minutes=p["waiting"] + sum(p["steps"]))
        else:
            sub = now - timedelta(days=p["ago_days"], hours=rng.randint(0, 5), minutes=rng.randint(0, 50))
        plan.append((sub, spec))
    plan.sort(key=lambda x: x[0])

    stats = {}
    for sub, spec in plan:
        (region, exec_name, name, product, ctype, objective, channels, audience, budget, leads, conv, rev, desc,
         outcome, p) = spec
        user = _user(conn, exec_name)
        start = (sub + timedelta(days=p["lead_days"])).date()
        end = start + timedelta(days=p["dur"])
        data = {"Region": region, "Campaign_Name": name, "Product": product, "Campaign_Type": ctype, "Objective": objective,
                "Target_Audience": audience, "Marketing_Channel": channels, "Start_Date": start.isoformat(),
                "End_Date": end.isoformat(), "Proposed_Budget": budget, "Expected_Leads": leads, "Expected_Conversions": conv,
                "Expected_Revenue": rev, "Campaign_Description": desc,
                "Creative_Link": p.get("creative") or f"https://drive.novabrands.in/creatives/{name.lower().replace(' ', '-')[:40]}"}
        clock.set_time(sub)
        if outcome == "draft":
            data["Campaign_Description"] = None
            with db.transaction(conn):
                res = workflow.create_campaign(conn, user, data, submit=False)
            continue
        with db.transaction(conn):
            res = workflow.create_campaign(conn, user, data, submit=True)
        cid = res["campaign_id"]
        if outcome == "valfail":
            continue
        chain = res["route"]["chain"]
        t = sub
        # approvals
        if outcome in ("executed", "ready"):
            todo = list(range(len(chain)))
        else:
            todo = list(range(len(p["steps"])))
        for i in todo:
            t = t + timedelta(minutes=p["steps"][i], seconds=rng.randint(0, 20))
            clock.set_time(t)
            with db.transaction(conn):
                workflow.process_approval(conn, _approver(conn, chain[i], region), cid,
                                          rng.choice(["Looks good.", "Approved - aligned with regional plan.", "Budget and audience are reasonable.", ""]))
        if outcome in ("rejected", "rework"):
            lvl = p["reject_level"] if outcome == "rejected" else p["rework_level"]
            t = t + timedelta(minutes=rng.randint(15, 50))
            clock.set_time(t)
            approver = _approver(conn, chain[lvl - 1], region)
            with db.transaction(conn):
                (workflow.process_rejection if outcome == "rejected" else workflow.process_revision)(conn, approver, cid, p["reason"])
        if outcome == "executed":
            executor = _user(conn, "Rohit Bansal")
            clock.set_time(datetime.combine(start, datetime.min.time()) + timedelta(hours=9, minutes=rng.randint(0, 40)))
            with db.transaction(conn):
                workflow.mark_executed(conn, executor, cid)
            # Performance starts clean - entered manually by user after execution
    # Seed sample chat messages between regional teams and approvers for all contacts
    seed_chats = [
        ("MKT-2026-023", "Aman Sharma", "Executive", "Rahul Mehta", "Regional Manager", "Hi Rahul, submitted the Diwali campaign proposal for Delhi NCR. Proposed budget is ₹1,80,000."),
        ("MKT-2026-023", "Rahul Mehta", "Regional Manager", "Aman Sharma", "Executive", "Thanks Aman. I reviewed the channel split. Please adjust the budget allocations slightly."),
        ("MKT-2026-006", "Kunal Saxena", "Executive", "Rahul Mehta", "Regional Manager", "Hi Rahul, Voltix Smart Home Expo proposal is submitted for Tier 3 review."),
        ("MKT-2026-006", "Kunal Saxena", "Executive", "Priya Kapoor", "Marketing Manager", "Hi Priya, requesting your secondary review for Voltix Expo campaign."),
        ("MKT-2026-002", "Sneha Iyer", "Executive", "Vikram Desai", "Regional Manager", "Hello Vikram, Monsoon Home Care bundle offer campaign submitted for Mumbai region."),
        ("MKT-2026-002", "Vikram Desai", "Regional Manager", "Sneha Iyer", "Executive", "Approved from Regional level, Sneha. Moving to Marketing Manager queue."),
        ("MKT-2026-003", "Karthik Rao", "Executive", "Anita Nair", "Regional Manager", "Hi Anita, Tech Park Sampling activation is ready for Bangalore."),
        ("MKT-2026-003", "Anita Nair", "Regional Manager", "Karthik Rao", "Executive", "Tier 1 budget under ₹50,000 approved immediately!"),
        ("MKT-2026-004", "Imran Qureshi", "Executive", "Lakshmi Reddy", "Regional Manager", "Hi Lakshmi, AquaPure Safe Water Drive request for Hyderabad region is submitted."),
        ("MKT-2026-004", "Lakshmi Reddy", "Regional Manager", "Imran Qureshi", "Executive", "Looks great Imran. Approved from Hyderabad regional desk."),
        ("MKT-2026-005", "Divya Krishnan", "Executive", "Suresh Babu", "Regional Manager", "Hi Suresh, Summer Cooler Chai Chill campaign submitted for Chennai."),
        ("MKT-2026-001", "Aman Sharma", "Executive", "Priya Kapoor", "Marketing Manager", "Priya, Summer Glow Skincare lead campaign execution results are recorded."),
        ("MKT-2026-001", "Priya Kapoor", "Marketing Manager", "Aman Sharma", "Executive", "Excellent ROAS realized on skincare sprint Aman!"),
    ]
    for cid, sname, srole, rname, rrole, txt in seed_chats:
        s_usr = _user(conn, sname)
        r_usr = _user(conn, rname)
        conn.execute(
            """INSERT INTO chat_messages (Campaign_ID, Sender_ID, Sender_Name, Sender_Role, Recipient_ID, Recipient_Name, Content, Timestamp, Read_Status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (cid, s_usr["User_ID"], sname, srole, r_usr["User_ID"], rname, txt, datetime.now().isoformat())
        )
    clock.clear()
    return stats


def run(path=None):
    conn = reset_database(path)
    stats = populate(conn)
    return conn, stats


if __name__ == "__main__":
    conn, stats = run()
    n = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
    print(f"Database ready: {db.DB_PATH}")
    print(f"  users={n('users')} campaigns={n('campaign_requests')} leads={n('lead_data')} approvals={n('approval_log')} "
          f"audit_events={n('audit_trail')} notifications={n('notifications')}")
    print(f"  Demo login password for every user: {PASSWORD}")
