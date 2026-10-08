# Simple Guide: Understanding Nova Marketing Governance System

> [!TIP]
> **Goal of this guide:** Explain the entire project in simple, plain English so you can explain it to anyone, answer interview questions easily, and feel 100% confident!

---

## 1. The Story: What is this project?

Imagine a big company (**Nova Consumer Brands**) that spends lakhs of rupees on advertising campaigns (like Diwali sales, shoes ads, snack ads).

### ❌ The Old Problem (Before our system):
1. **WhatsApp & E-mail Chaos**: Employees asked for campaign budgets on WhatsApp or email.
2. **Slow Approvals**: Requests sat in managers' inboxes for 2 to 3 days.
3. **No Safety Rules**: Sometimes team members started spending money **before** the final boss actually approved it!
4. **No Money Tracking**: Nobody tracked how much profit (Revenue & ROAS) the ads actually brought back.

### ✅ The Solution (Our Nova System):
We built an **automated digital system** that acts like a smart control room:
- It automatically checks who needs to approve the budget based on company rules.
- It **locks** execution until all approvals are completed.
- It calculates **ROAS (Return on Ad Spend)** to show if ads made money or lost money.
- It reduces approval time from **2 hours down to 21 minutes!**

---

## 2. Step-by-Step: How a Campaign Moves Through the System

```
[1. Create Request] ➔ [2. System Checks Budget Rule] ➔ [3. Approval Chain] ➔ [4. Governance Lock] ➔ [5. Record Results]
```

### Step 1: Submit Request
An executive (e.g., Aman Sharma) fills out a form: Campaign name, product, region, start date, and proposed budget (e.g., ₹1,80,000).

### Step 2: System Checks the Rule Table
The system checks the budget table automatically:
- **Small Budget ($\le$ ₹50,000)**: Requires **1 approval** (Regional Manager).
- **Medium Budget (₹50,000 – ₹2,00,000)**: Requires **2 approvals** (Regional Manager $\rightarrow$ Marketing Manager).
- **Large Budget ($>$ ₹2,00,000)**: Requires **4 approvals** (Regional Manager $\rightarrow$ Marketing Manager $\rightarrow$ Marketing Head $\rightarrow$ Business Head).

### Step 3: Approval Chain
The system emails and notifies the first approver. Once they approve, it moves to the next approver automatically.

### Step 4: The Governance Gate (The Lock)
This is the most important feature! The database **refuses** to let the campaign run unless:
1. Status is `Fully Approved`.
2. All required approvers signed off.
3. The requester did NOT approve their own request (Segregation of Duties).

### Step 5: Record Financial Results & ROAS
Once the campaign finishes, the team enters actual spend and revenue earned.
- **ROAS Formula**:
  $$\text{ROAS} = \frac{\text{Realized Revenue}}{\text{Actual Spend}}$$
- If ROAS $\ge 1.0$, it shows a green badge: `PROFITABLE / SUCCESS`.
- If ROAS $< 1.0$, it shows a red badge: `LOW RETURN / LOSS`.

---

## 3. How Was It Built? (The Tech Stack)

You don't need complicated buzzwords. Here is how to explain the tech stack simply:

| Part | Tech Used | What It Does (In Simple Words) |
| :--- | :--- | :--- |
| **Frontend** | HTML, CSS, Vanilla JavaScript, Chart.js | The visual screens in the browser (buttons, tables, status badges, and bar charts). |
| **Backend Engine** | Python Flask (`app.py`) | The brain server that processes requests, checks rules, and handles logins. |
| **Database** | SQLite (`nova_marketing.db`) | The digital notebook where all campaigns, approval logs, and audit trails are saved safely. |

---

## 4. How Does the Automated Test Runner Work? (`run_tests.py`)

You just looked at lines 560–598 in `tests/run_tests.py`. Here is what that code actually does:

1. **Creates 35 Test Scenarios**: Tests things like:
   - *"What if someone enters a negative budget?"* $\rightarrow$ Should fail validation.
   - *"What if a manager tries to approve a request in another region?"* $\rightarrow$ Should be blocked.
   - *"What if a user tries to approve their own request?"* $\rightarrow$ Should be blocked.
2. **Runs every scenario in a fresh temporary database**:
   - Loops through all 35 tests (`for c in CASES`).
   - If test passes, it prints `PASS`.
   - Saves a summary report in `docs/test_results.json`.
3. **Result**: All **35 out of 35 tests pass** in less than 1 second!

---

## 5. Easy Answers to Common Questions (Interview Cheat Sheet)

### Q1: "Can you explain your project in 2 sentences?"
> **Answer**: "I built an automated Marketing Governance System for a consumer brands company. It automatically validates campaign requests, routes approvals based on budget rules, locks execution until fully approved, and calculates ROAS upon campaign completion."

### Q2: "How are the approval rules set up?"
> **Answer**: "The rules are stored in a database table (`approval_rules`), not hardcoded in Python. For example, budgets under ₹50,000 require 1 approval, while budgets over ₹2,00,000 require 4 approvals up to the Business Head. If Finance changes budget limits in the table, the system updates immediately without needing code changes."

### Q3: "How do you make sure people don't cheat or bypass approvals?"
> **Answer**: "We have a **Governance Gate**. The database physically rejects any attempt to mark a campaign as ready for execution unless it has the status `Fully Approved` and all required approvers are logged in the audit log."

### Q4: "What happens if a campaign is rejected or sent back?"
> **Answer**: "If a reviewer rejects it, execution is blocked and the requester gets a notification. If sent back for revision, the requester can edit the details and resubmit, which restarts the approval chain from Level 1 with a new revision number."

### Q5: "How did you test the system?"
> **Answer**: "I wrote an automated test runner (`run_tests.py`) that tests 35 different real-world scenarios—such as invalid dates, self-approvals, regional boundary checks, and lead calculations. All 35 tests pass 100%."
