# 5-Minute Recruiter Demo

**Before you start:** `python seed.py && python app.py`, open http://127.0.0.1:5000, log in as `aman.sharma@novabrands.in` / `Demo@123`. (Password for all users: `Demo@123`.)

| Time | Say | Do |
|---|---|---|
| 0:00 | "Nova's regional teams got campaign approvals by e-mail and WhatsApp: slow, untracked, and sometimes unapproved. I built the system that fixes that." | Show **Executive Demo** page: before/after and the flow. |
| 0:40 | "A regional executive raises a request." | **Create Campaign** > *Fill Diwali demo data* (₹1,80,000, Delhi NCR, Instagram + Google Ads). Point at the **route preview**: Regional Manager → Marketing Manager. Click **Submit for approval**. |
| 1:30 | "The system validated it, generated an ID, picked the chain from the rules table, and e-mailed the first approver." | Show ID `MKT-2026-0xx` and the Pending status. |
| 2:00 | "Watch the governance gate." | Switch user (top bar) to **Rahul Mehta (Regional Manager)** > Pending Approvals > Approve. Then **Priya Kapoor (Marketing Manager)** > Approve. |
| 3:00 | "Only now does the Governance Check pass." | Open the campaign: stamp **FULLY COMPLIANT**, all PASS, status Ready for Execution. Mention that before the last approval the stamp read BLOCKED. |
| 3:30 | "And it can't be bypassed." | Governance page: show blocked attempts in the audit log, or run the *Dispatch before approval* test (T15/T16). |
| 4:00 | "Execution tracks leads and results." | Switch to **Rohit Bansal (Execution Team)** > Open the campaign > *Mark as executed* > *Load simulated lead feed*. |
| 4:30 | "Management sees it live." | Switch to **Neha Verma (Business Head)** > Dashboard: KPIs, charts, filters. Process Metrics: 120 → 21.4 min, **82%** reduction (before = assumed, after = measured). |

**If something goes wrong:** Business Head > Executive Demo > *Reset sample data*, or rerun `python seed.py`.
