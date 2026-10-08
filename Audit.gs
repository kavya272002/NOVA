/**
 * Audit.gs - append-only audit trail and e-mail notifications.
 * Business purpose: every governance-relevant event (submit, approve, reject, dispatch, denied attempt)
 * leaves a timestamped record, so an auditor can reconstruct who did what and when.
 */
function logEvent_(user, action, campaignId, prevStatus, newStatus, details) {
  appendRow_(SHEETS.AUDIT, {
    Audit_ID: SpreadsheetApp.getActive().getSheetByName(SHEETS.AUDIT).getLastRow(),
    Timestamp: nowStamp_(),
    User: user ? user.Name : 'System',
    User_Role: user ? user.Role : 'System',
    Action: action, Campaign_ID: campaignId || '',
    Previous_Status: prevStatus || '', New_Status: newStatus || '', Details: details || ''
  });
}

/** Sends a real Gmail message through MailApp and records it in NOTIFICATIONS. */
function notify_(type, campaignId, toName, toEmail, subject, body) {
  var status = 'Sent';
  try { MailApp.sendEmail(toEmail, subject, body); } catch (e) { status = 'Failed: ' + e.message; }
  appendRow_(SHEETS.NOTIFY, {
    Notification_ID: SpreadsheetApp.getActive().getSheetByName(SHEETS.NOTIFY).getLastRow(),
    Timestamp: nowStamp_(), Campaign_ID: campaignId, Notification_Type: type,
    To_Name: toName, To_Email: toEmail, Subject: subject, Channel: 'Gmail', Status: status
  });
}

/** Indian digit grouping: 180000 -> "Rs 1,80,000". */
function inr_(n) {
  var s = String(Math.round(Number(n) || 0)), last3 = s.slice(-3), rest = s.slice(0, -3);
  if (rest) last3 = ',' + last3;
  return 'Rs ' + rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + last3;
}
