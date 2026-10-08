/**
 * RuleEngine.gs - campaign IDs, validation and config-driven approval routing.
 */

/**
 * generateCampaignID
 * Business purpose: every campaign gets a unique, human-readable reference (MKT-2026-001) that follows it
 * through approvals, leads and reports. LockService stops two simultaneous submissions getting the same ID.
 */
function generateCampaignID() {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var year = new Date().getFullYear();
    var max = 0;
    readTable_(SHEETS.REQUESTS).forEach(function (r) {
      var m = /^MKT-(\d{4})-(\d+)$/.exec(String(r.Campaign_ID));
      if (m && Number(m[1]) === year) max = Math.max(max, Number(m[2]));
    });
    return 'MKT-' + year + '-' + ('00' + (max + 1)).slice(-3);
  } finally { lock.releaseLock(); }
}

/**
 * validateCampaign
 * Business purpose: catch incomplete or illogical requests at the door, so approvers never waste time on
 * a request that cannot be executed. Returns {valid, errors[]}.
 */
function validateCampaign(d, checkPast) {
  if (checkPast === undefined) checkPast = true;
  var errors = [];
  ['Campaign_Name', 'Region', 'Product', 'Campaign_Type', 'Objective', 'Target_Audience',
   'Marketing_Channel', 'Start_Date', 'End_Date'].forEach(function (f) {
    if (d[f] === undefined || d[f] === null || String(d[f]).trim() === '') errors.push(f.replace(/_/g, ' ') + ' is required');
  });
  var budget = Number(d.Proposed_Budget);
  if (!(budget > 0)) errors.push('Proposed budget must be a number greater than 0');
  var leads = Number(d.Expected_Leads), conv = Number(d.Expected_Conversions);
  if (!(leads > 0)) errors.push('Expected leads must be greater than 0');
  if (isNaN(conv) || conv < 0) errors.push('Expected conversions must be 0 or more');
  else if (conv > leads) errors.push('Expected conversions cannot exceed expected leads');
  var s = new Date(d.Start_Date), e = new Date(d.End_Date);
  if (isNaN(s) || isNaN(e)) errors.push('Start and end dates must be valid dates');
  else {
    var today = new Date(); today.setHours(0, 0, 0, 0);
    if (e < s) errors.push('End date cannot be before start date');
    if (checkPast && s < today) errors.push('Start date cannot be in the past');
  }
  if (d.Region && ['Delhi NCR', 'Mumbai', 'Bangalore', 'Hyderabad', 'Chennai'].indexOf(d.Region) < 0)
    errors.push('Region must be one of the five Nova regions');
  return { valid: errors.length === 0, errors: errors };
}

/**
 * determineApprovalLevel
 * Business purpose: translate a budget into the exact approval chain company policy requires. Rules live in
 * the APPROVAL_RULES sheet, so Finance can change a threshold without touching code.
 * Returns {ruleId, ruleName, chain[], levels}. Refuses to guess if rules overlap or leave a gap.
 */
function determineApprovalLevel(budget) {
  budget = Number(budget);
  var rules = readTable_(SHEETS.RULES).filter(function (r) { return r.Active === true || r.Active === 1 || r.Active === 'TRUE'; });
  var hits = rules.filter(function (r) {
    var lo = r.Min_Inclusive ? budget >= r.Min_Budget : budget > r.Min_Budget;
    var noMax = r.Max_Budget === '' || r.Max_Budget === null;
    var hi = noMax ? true : (r.Max_Inclusive ? budget <= r.Max_Budget : budget < r.Max_Budget);
    return lo && hi;
  });
  if (hits.length === 0) throw new Error('No active approval rule covers a budget of ' + inr_(budget) + '. Fix APPROVAL_RULES.');
  if (hits.length > 1) throw new Error('Approval rules overlap for ' + inr_(budget) + ': ' + hits.map(function (h) { return h.Rule_Name; }).join(', '));
  var chain = String(hits[0].Approval_Chain).split(CHAIN_SEP).filter(String);
  chain.forEach(function (role) { if (APPROVER_ROLES.indexOf(role) < 0) throw new Error('Invalid role in rule: ' + role); });
  return { ruleId: hits[0].Rule_ID, ruleName: hits[0].Rule_Name, chain: chain, levels: chain.length };
}
