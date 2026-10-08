/**
 * Workflow.gs - submission, approval, rejection, revision and dispatch.
 * Every public function checks the caller's role first (RBAC), writes the audit trail, and notifies.
 */

function findApprover_(role, region) {
  var users = readTable_(SHEETS.USERS);
  var national = (role === ROLE.MM || role === ROLE.MH || role === ROLE.BH);
  for (var i = 0; i < users.length; i++) {
    var u = users[i];
    if (u.Role === role && u.Active !== false && (national || u.Region === region)) return u;
  }
  throw new Error('No active ' + role + (national ? '' : ' for ' + region) + ' in USERS.');
}

/** Entry point from the Google Form / AppSheet: validates, assigns an ID, routes and notifies. */
function submitCampaign(data) {
  var user = currentUser_();
  if (user.Role !== ROLE.EXEC) throw new Error('Access denied: only Regional Marketing Executives raise requests.');
  if (user.Region !== data.Region) throw new Error('Access denied: you can only raise requests for ' + user.Region + '.');
  var check = validateCampaign(data);
  var id = generateCampaignID();
  var base = {
    Campaign_ID: id, Submission_Date: nowStamp_(), Requester_Name: user.Name, Requester_Email: user.Email,
    Created_Timestamp: nowStamp_(), Updated_Timestamp: nowStamp_(), Revision_No: 0, Approval_Step: 0,
    Execution_Status: EX.NOT_READY
  };
  Object.keys(data).forEach(function (k) { base[k] = data[k]; });
  if (!check.valid) {
    base.Approval_Status = ST.VALFAIL; base.Rejection_Reason = check.errors.join('; ');
    appendRow_(SHEETS.REQUESTS, base);
    logEvent_(user, 'Validation failed', id, '', ST.VALFAIL, base.Rejection_Reason);
    return { campaignId: id, status: ST.VALFAIL, errors: check.errors };
  }
  appendRow_(SHEETS.REQUESTS, base);
  logEvent_(user, 'Campaign created', id, '', ST.DRAFT, inr_(data.Proposed_Budget));
  createApprovalRequest(id, user);
  return { campaignId: id, status: ST.PENDING };
}

/**
 * createApprovalRequest
 * Business purpose: start the approval chain the rules require and hand the request to the first approver.
 */
function createApprovalRequest(campaignId, user) {
  var c = findCampaign_(campaignId);
  var route = determineApprovalLevel(c.Proposed_Budget);
  var first = findApprover_(route.chain[0], c.Region);
  updateRow_(SHEETS.REQUESTS, c._row, {
    Approval_Level: route.levels, Approval_Chain: route.chain.join(CHAIN_SEP), Rule_ID: route.ruleId,
    Approval_Step: 1, Current_Approver: first.Name, Approval_Status: ST.PENDING,
    Submitted_Timestamp: nowStamp_(), Updated_Timestamp: nowStamp_(), Execution_Status: EX.NOT_READY
  });
  logEvent_(user, 'Submitted for approval', campaignId, ST.DRAFT, ST.PENDING, route.ruleName + ' -> ' + route.chain.join(' > '));
  sendApprovalNotification(c, first, 1, route.levels);
}

/** sendApprovalNotification - tells the approver exactly what is waiting and what it will cost. */
function sendApprovalNotification(c, approver, step, total) {
  notify_('Approval request', c.Campaign_ID, approver.Name, approver.Email,
    '[Approval needed] ' + c.Campaign_ID + ' - ' + c.Campaign_Name + ' (' + inr_(c.Proposed_Budget) + ')',
    'Hello ' + approver.Name + ',\n\nCampaign ' + c.Campaign_Name + ' (' + c.Region + ') needs your approval as ' +
    approver.Role + ' (step ' + step + ' of ' + total + ').\nBudget: ' + inr_(c.Proposed_Budget) +
    '\nObjective: ' + c.Objective + '\nChannels: ' + c.Marketing_Channel + '\n\nOpen the Pending Approvals view to decide.');
}

/** Shared RBAC: the caller must be the active approver for the current step, for the right region, and not the requester. */
function authorizeDecision_(user, c) {
  if (c.Approval_Status !== ST.PENDING) throw new Error('This campaign is not awaiting approval (status: ' + c.Approval_Status + ').');
  var chain = String(c.Approval_Chain).split(CHAIN_SEP);
  var expected = chain[Number(c.Approval_Step) - 1];
  if (user.Role !== expected) {
    logEvent_(user, 'DENIED: out of sequence / wrong role', c.Campaign_ID, c.Approval_Status, c.Approval_Status, 'expected ' + expected);
    throw new Error('Out of sequence: this step needs the ' + expected + '.');
  }
  if (user.Role === ROLE.RM && user.Region !== c.Region) throw new Error('Access denied: you manage ' + user.Region + ', not ' + c.Region + '.');
  if (String(user.Email).toLowerCase() === String(c.Requester_Email).toLowerCase())
    throw new Error('Segregation of duties: you cannot approve your own request.');
  return chain;
}

/**
 * processApproval
 * Business purpose: record one approval, then either pass the request to the next approver or, after the
 * last required approval, mark it Fully Approved and run the governance check + dispatch automatically.
 */
function processApproval(campaignId, comments) {
  var lock = LockService.getScriptLock(); lock.waitLock(20000);
  try {
    var user = currentUser_(), c = findCampaign_(campaignId), chain = authorizeDecision_(user, c);
    var step = Number(c.Approval_Step), last = step === chain.length;
    appendRow_(SHEETS.LOG, {
      Approval_ID: SpreadsheetApp.getActive().getSheetByName(SHEETS.LOG).getLastRow(), Campaign_ID: campaignId,
      Approver_Name: user.Name, Approver_Role: user.Role, Approval_Level: step, Decision: 'Approved',
      Decision_Date: nowStamp_(), Comments: comments || '', Previous_Status: c.Approval_Status,
      New_Status: last ? ST.APPROVED : ST.PENDING, Revision_No: c.Revision_No
    });
    if (!last) {
      var next = findApprover_(chain[step], c.Region);
      updateRow_(SHEETS.REQUESTS, c._row, { Approval_Step: step + 1, Current_Approver: next.Name, Updated_Timestamp: nowStamp_() });
      logEvent_(user, 'Approved (level ' + step + ')', campaignId, ST.PENDING, ST.PENDING, comments);
      sendApprovalNotification(c, next, step + 1, chain.length);
      return { status: ST.PENDING, nextApprover: next.Name };
    }
    updateRow_(SHEETS.REQUESTS, c._row, {
      Approval_Status: ST.APPROVED, Current_Approver: '', Approved_Timestamp: nowStamp_(), Updated_Timestamp: nowStamp_()
    });
    logEvent_(user, 'Fully approved', campaignId, ST.PENDING, ST.APPROVED, comments);
    return dispatchCampaign(campaignId, true);
  } finally { lock.releaseLock(); }
}

/** processRejection - a rejection needs a reason; it stops the chain and tells the requester why. */
function processRejection(campaignId, reason) {
  if (!reason || !String(reason).trim()) throw new Error('A rejection reason is required.');
  var user = currentUser_(), c = findCampaign_(campaignId); authorizeDecision_(user, c);
  appendRow_(SHEETS.LOG, {
    Approval_ID: SpreadsheetApp.getActive().getSheetByName(SHEETS.LOG).getLastRow(), Campaign_ID: campaignId,
    Approver_Name: user.Name, Approver_Role: user.Role, Approval_Level: c.Approval_Step, Decision: 'Rejected',
    Decision_Date: nowStamp_(), Comments: reason, Previous_Status: c.Approval_Status, New_Status: ST.REJECTED, Revision_No: c.Revision_No
  });
  updateRow_(SHEETS.REQUESTS, c._row, {
    Approval_Status: ST.REJECTED, Execution_Status: EX.NOT_READY, Rejection_Reason: reason, Current_Approver: '', Updated_Timestamp: nowStamp_()
  });
  logEvent_(user, 'Rejected', campaignId, ST.PENDING, ST.REJECTED, reason);
  notify_('Rejected', campaignId, c.Requester_Name, c.Requester_Email, '[Rejected] ' + campaignId + ' - ' + c.Campaign_Name,
    'Your campaign was rejected by ' + user.Name + ' (' + user.Role + ').\nReason: ' + reason);
}

/** processRevision - send back for changes; resubmitting restarts the whole chain (Revision_No + 1). */
function processRevision(campaignId, comments) {
  if (!comments || !String(comments).trim()) throw new Error('Tell the requester what to change.');
  var user = currentUser_(), c = findCampaign_(campaignId); authorizeDecision_(user, c);
  appendRow_(SHEETS.LOG, {
    Approval_ID: SpreadsheetApp.getActive().getSheetByName(SHEETS.LOG).getLastRow(), Campaign_ID: campaignId,
    Approver_Name: user.Name, Approver_Role: user.Role, Approval_Level: c.Approval_Step, Decision: 'Sent Back',
    Decision_Date: nowStamp_(), Comments: comments, Previous_Status: c.Approval_Status, New_Status: ST.REWORK, Revision_No: c.Revision_No
  });
  updateRow_(SHEETS.REQUESTS, c._row, {
    Approval_Status: ST.REWORK, Execution_Status: EX.NOT_READY, Rejection_Reason: comments, Current_Approver: '',
    Revision_No: Number(c.Revision_No) + 1, Approval_Step: 0, Updated_Timestamp: nowStamp_()
  });
  logEvent_(user, 'Sent back for revision', campaignId, ST.PENDING, ST.REWORK, comments);
  notify_('Revision requested', campaignId, c.Requester_Name, c.Requester_Email, '[Changes requested] ' + campaignId, comments);
}

/**
 * dispatchCampaign
 * Business purpose: the final gate. Runs the governance check and ONLY THEN releases the campaign to the
 * Execution Team. A request that is not Fully Approved can never become Ready for Execution.
 */
function dispatchCampaign(campaignId, auto) {
  var user = auto ? null : currentUser_();
  var gov = checkGovernance(campaignId);
  var c = findCampaign_(campaignId);
  if (!gov.canExecute) {
    logEvent_(user, 'DENIED: dispatch blocked by governance', campaignId, c.Execution_Status, c.Execution_Status, gov.failed.join('; '));
    throw new Error('Governance check failed: ' + gov.failed.join('; '));
  }
  updateRow_(SHEETS.REQUESTS, c._row, { Execution_Status: EX.READY, Ready_Timestamp: nowStamp_(), Updated_Timestamp: nowStamp_() });
  logEvent_(user, 'Dispatched: Ready for Execution', campaignId, EX.NOT_READY, EX.READY, 'Governance check passed');
  var team = readTable_(SHEETS.USERS).filter(function (u) { return u.Role === ROLE.EXECUTION && u.Active !== false; });
  team.forEach(function (t) {
    notify_('Dispatch', campaignId, t.Name, t.Email, '[Ready for Execution] ' + campaignId + ' - ' + c.Campaign_Name,
      'Approved and cleared governance. Budget ' + inr_(c.Proposed_Budget) + ', channels: ' + c.Marketing_Channel + ', ' + c.Start_Date + ' to ' + c.End_Date + '.');
  });
  return { status: ST.APPROVED, execution: EX.READY };
}
