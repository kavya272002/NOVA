/**
 * checkGovernance
 * Business purpose: a visible, repeatable pre-flight check. Returns each control as PASS/FAIL so the
 * Governance Check card (or an auditor) can see exactly why a campaign may or may not be executed.
 * Rule: Execution may start only if Approval_Status = "Fully Approved" AND every required level
 * is recorded in APPROVAL_LOG for the current revision.
 */
function checkGovernance(campaignId) {
  var c = findCampaign_(campaignId);
  var items = [], failed = [];
  function add(name, ok, detail) { items.push({ control: name, result: ok ? 'PASS' : 'FAIL', detail: detail }); if (!ok) failed.push(name + ' - ' + detail); }

  var required = String(c.Approval_Chain || '').split(CHAIN_SEP).filter(String);
  var logged = readTable_(SHEETS.LOG).filter(function (l) {
    return l.Campaign_ID === campaignId && l.Decision === 'Approved' && Number(l.Revision_No) === Number(c.Revision_No);
  });
  var loggedRoles = logged.map(function (l) { return l.Approver_Role; });

  add('Required fields complete', validateCampaign(c, false).valid, 'Campaign request validated');
  add('Approval level identified', required.length > 0, required.length + ' level(s) from rule ' + c.Rule_ID);
  required.forEach(function (role, i) {
    add(role + ' approval', loggedRoles.indexOf(role) >= 0, loggedRoles.indexOf(role) >= 0 ? 'Approved' : 'Not yet approved');
  });
  add('Approval status is Fully Approved', c.Approval_Status === ST.APPROVED, 'Status: ' + c.Approval_Status);
  var dup = readTable_(SHEETS.REQUESTS).filter(function (r) {
    return r.Campaign_ID !== campaignId && r.Campaign_Name === c.Campaign_Name && r.Region === c.Region &&
      String(r.Start_Date) === String(c.Start_Date) && [ST.PENDING, ST.APPROVED].indexOf(r.Approval_Status) >= 0;
  });
  add('No duplicate active request', dup.length === 0, dup.length ? 'Duplicate of ' + dup[0].Campaign_ID : 'Unique');

  return { campaignId: campaignId, items: items, failed: failed, canExecute: failed.length === 0,
           label: failed.length === 0 ? 'FULLY COMPLIANT' : 'BLOCKED' };
}

/**
 * onEdit guard - the Google Sheets equivalent of the database trigger in the prototype.
 * If anyone types "Ready for Execution" into CAMPAIGN_REQUESTS without full approval, the edit is reverted
 * and the attempt is logged. (Combine with Protected Ranges so only the script account can edit status columns.)
 */
function onEdit(e) {
  try {
    var sh = e.range.getSheet();
    if (sh.getName() !== SHEETS.REQUESTS) return;
    var map = headerMap_(sh);
    if (e.range.getColumn() - 1 !== map.Execution_Status) return;
    var v = String(e.value || '');
    if (v !== EX.READY && v !== EX.DONE) return;
    var status = sh.getRange(e.range.getRow(), map.Approval_Status + 1).getValue();
    if (status !== ST.APPROVED) {
      e.range.setValue(e.oldValue || EX.NOT_READY);
      logEvent_(null, 'DENIED: manual edit reverted', sh.getRange(e.range.getRow(), map.Campaign_ID + 1).getValue(), status, status, 'Tried to set ' + v);
      SpreadsheetApp.getActive().toast('Blocked: Execution Status cannot be changed unless the campaign is Fully Approved.', 'Governance', 8);
    }
  } catch (err) { /* never break normal editing */ }
}
