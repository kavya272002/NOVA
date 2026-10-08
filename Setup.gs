/**
 * Setup.gs - menu, workbook initialisation, triggers and the demo web-app endpoint.
 */
function onOpen() {
  SpreadsheetApp.getUi().createMenu('Nova Governance')
    .addItem('Initialise workbook (sheets, rules, dropdowns)', 'initialiseWorkbook')
    .addItem('Run governance check on selected row', 'menuGovernanceCheck')
    .addItem('Refresh KPIs', 'menuRefreshKpis')
    .addToUi();
}

/** Creates any missing sheet with its headers and seeds the three approval rules. Safe to run twice. */
function initialiseWorkbook() {
  var ss = SpreadsheetApp.getActive();
  var layout = {
    CAMPAIGN_REQUESTS: ['Campaign_ID','Submission_Date','Region','Requester_Name','Requester_Email','Campaign_Name','Product','Campaign_Type','Objective','Target_Audience','Marketing_Channel','Start_Date','End_Date','Proposed_Budget','Expected_Leads','Expected_Conversions','Expected_Revenue','Campaign_Description','Creative_Link','Approval_Level','Current_Approver','Approval_Status','Execution_Status','Rejection_Reason','Created_Timestamp','Updated_Timestamp','Approval_Chain','Approval_Step','Rule_ID','Revision_No','Submitted_Timestamp','Approved_Timestamp','Ready_Timestamp','Executed_Timestamp'],
    APPROVAL_RULES: ['Rule_ID','Rule_Name','Min_Budget','Min_Inclusive','Max_Budget','Max_Inclusive','Approval_Chain','Active'],
    APPROVAL_LOG: ['Approval_ID','Campaign_ID','Approver_Name','Approver_Role','Approval_Level','Decision','Decision_Date','Comments','Previous_Status','New_Status','Revision_No'],
    LEAD_DATA: ['Lead_ID','Campaign_ID','Region','Lead_Source','Lead_Date','Customer_Segment','Lead_Score','Lead_Status','Sales_Assigned','Conversion_Status','Revenue'],
    CAMPAIGN_PERFORMANCE: ['Campaign_ID','Campaign_Name','Region','Budget','Actual_Spend','Impressions','Clicks','Leads','Qualified_Leads','Conversions','Revenue','CPL','Conversion_Rate','ROAS','ROI'],
    USERS: ['User_ID','Name','Email','Role','Region','Active'],
    SETTINGS: ['Key','Value','Description'],
    AUDIT_TRAIL: ['Audit_ID','Timestamp','User','User_Role','Action','Campaign_ID','Previous_Status','New_Status','Details'],
    NOTIFICATIONS: ['Notification_ID','Timestamp','Campaign_ID','Notification_Type','To_Name','To_Email','Subject','Channel','Status']
  };
  Object.keys(layout).forEach(function (name) {
    var sh = ss.getSheetByName(name) || ss.insertSheet(name);
    if (sh.getLastRow() === 0) {
      sh.getRange(1, 1, 1, layout[name].length).setValues([layout[name]]).setFontWeight('bold').setBackground('#0f3d3e').setFontColor('#ffffff');
      sh.setFrozenRows(1);
    }
  });
  var rules = ss.getSheetByName('APPROVAL_RULES');
  if (rules.getLastRow() < 2) {
    rules.getRange(2, 1, 3, 8).setValues([
      [1, 'Tier 1 - Below Rs 50,000', 0, true, 50000, false, 'Regional Manager', true],
      [2, 'Tier 2 - Rs 50,000 to Rs 2,00,000', 50000, true, 200000, true, 'Regional Manager|Marketing Manager', true],
      [3, 'Tier 3 - Above Rs 2,00,000', 200000, false, '', false, 'Regional Manager|Marketing Manager|Marketing Head|Business Head', true]
    ]);
  }
  var cp = ss.getSheetByName('CAMPAIGN_PERFORMANCE');
  cp.getRange('L2:L500').setFormula('=IF(H2>0,E2/H2,0)');          // CPL
  cp.getRange('M2:M500').setFormula('=IF(H2>0,J2/H2,0)');          // Conversion rate
  cp.getRange('N2:N500').setFormula('=IF(E2>0,K2/E2,0)');          // ROAS
  cp.getRange('O2:O500').setFormula('=IF(E2>0,(K2-E2)/E2,0)');     // ROI
  var req = ss.getSheetByName('CAMPAIGN_REQUESTS');
  req.getRange('V2:V500').setDataValidation(SpreadsheetApp.newDataValidation()
    .requireValueInList(Object.keys(ST).map(function (k) { return ST[k]; }), true).build());
  req.getRange('W2:W500').setDataValidation(SpreadsheetApp.newDataValidation()
    .requireValueInList(Object.keys(EX).map(function (k) { return EX[k]; }), true).build());
  SpreadsheetApp.getUi().alert('Workbook initialised. Add your users to the USERS sheet, then protect the status columns (see GOOGLE_DEPLOYMENT.md).');
}

function menuGovernanceCheck() {
  var sh = SpreadsheetApp.getActiveSheet();
  if (sh.getName() !== SHEETS.REQUESTS) { SpreadsheetApp.getUi().alert('Select a row on CAMPAIGN_REQUESTS.'); return; }
  var id = sh.getRange(sh.getActiveRange().getRow(), 1).getValue();
  var g = checkGovernance(id);
  SpreadsheetApp.getUi().alert(g.label + '\n\n' + g.items.map(function (i) { return i.result + '  ' + i.control + ' - ' + i.detail; }).join('\n'));
}

function menuRefreshKpis() {
  SpreadsheetApp.getUi().alert(JSON.stringify(calculateKPIs(), null, 2));
}

/** Google Form trigger: install with Triggers > Add trigger > onFormSubmit > From form. */
function onFormSubmit(e) {
  var r = e.namedValues, pick = function (k) { return (r[k] || [''])[0]; };
  submitCampaign({
    Campaign_Name: pick('Campaign Name'), Region: pick('Region'), Product: pick('Product'), Campaign_Type: pick('Campaign Type'),
    Objective: pick('Objective'), Target_Audience: pick('Target Audience'), Marketing_Channel: pick('Marketing Channels'),
    Start_Date: pick('Start Date'), End_Date: pick('End Date'), Proposed_Budget: pick('Proposed Budget'),
    Expected_Leads: pick('Expected Leads'), Expected_Conversions: pick('Expected Conversions'),
    Expected_Revenue: pick('Expected Revenue'), Campaign_Description: pick('Description'), Creative_Link: pick('Creative Link')
  });
}

/** Daily trigger: nudges approvers whose request has waited more than 24 hours. */
function sendPendingReminders() {
  var cutoff = Date.now() - 24 * 3600 * 1000;
  readTable_(SHEETS.REQUESTS).filter(function (c) { return c.Approval_Status === ST.PENDING && new Date(c.Updated_Timestamp).getTime() < cutoff; })
    .forEach(function (c) {
      var chain = String(c.Approval_Chain).split(CHAIN_SEP), a = findApprover_(chain[Number(c.Approval_Step) - 1], c.Region);
      notify_('Reminder', c.Campaign_ID, a.Name, a.Email, '[Reminder] ' + c.Campaign_ID + ' is waiting for you', 'Pending for more than 24 hours.');
    });
}
