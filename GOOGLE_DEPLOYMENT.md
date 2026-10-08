# Deploying the Google Workspace build

1. Create a Google Sheet. Import `google_sheets/Nova_Marketing_Governance_DB.xlsx` (File > Import) for the full sample data, **or** start empty and run the menu item in step 4.
2. Extensions > Apps Script. Create one script file per `.gs` file in `apps_script/` (Config, Audit, RuleEngine, Workflow, Governance, Analytics, Setup) and paste the contents.
3. Save, reload the sheet. A **Nova Governance** menu appears.
4. Menu > *Initialise workbook* creates any missing sheet, the three approval rules, the CPL / conversion / ROAS / ROI formulas and the status dropdowns.
5. Fill the **USERS** sheet with real Google account e-mails and roles (names must match `Role` values in `Config.gs`).
6. Create a Google Form with fields: Campaign Name, Region, Product, Campaign Type, Objective, Target Audience, Marketing Channels, Start Date, End Date, Proposed Budget, Expected Leads, Expected Conversions, Expected Revenue, Description, Creative Link. Link it to the sheet, then add a trigger: `onFormSubmit` > From form > On form submit. (Collect e-mail addresses so the requester can be identified.)
7. Triggers: add `sendPendingReminders` as a daily time-driven trigger.
8. Protect the sheet ranges for `Approval_Status`, `Execution_Status`, `Approval_Chain`, `Approval_Step` and the whole of APPROVAL_LOG and AUDIT_TRAIL (Data > Protect sheets and ranges) so only the script owner can edit them. The `onEdit` guard in `Governance.gs` reverts and logs any manual attempt to set Ready/Executed without full approval.
9. AppSheet: connect the spreadsheet as a data source for the approval inbox; Looker Studio: connect to `CAMPAIGN_PERFORMANCE` and `DASHBOARD_DATA` for the Control Center.

Call `processApproval(campaignId, comment)` from an AppSheet action or a web-app button; it reads the signed-in Google user, checks role, region, sequence and segregation of duties, and then continues or dispatches.

**Differences from the prototype:** Sheets has no database triggers, so the guarantee is `onEdit` plus protected ranges rather than a hard constraint; Apps Script quotas apply to Gmail (about 100 recipients/day on free accounts).
