/**
 * Analytics.gs - lead tracking, performance updates and KPI calculation.
 */

/**
 * updatePerformance
 * Business purpose: roll lead data and delivery numbers (spend, impressions, clicks) into one performance row per
 * campaign, so the dashboard always reflects LEAD_DATA. Only executed campaigns can be tracked.
 */
function updatePerformance(campaignId, delivery) {
  var c = findCampaign_(campaignId);
  if (c.Execution_Status !== EX.DONE) throw new Error('Performance can only be tracked after the campaign is executed.');
  var leads = readTable_(SHEETS.LEADS).filter(function (l) { return l.Campaign_ID === campaignId; });
  var threshold = Number((readTable_(SHEETS.SETTINGS).filter(function (s) { return s.Key === 'qualified_score_threshold'; })[0] || { Value: 60 }).Value);
  var qualified = leads.filter(function (l) { return Number(l.Lead_Score) >= threshold || l.Lead_Status === 'Qualified' || l.Lead_Status === 'Converted'; }).length;
  var converted = leads.filter(function (l) { return l.Conversion_Status === 'Converted'; });
  var revenue = converted.reduce(function (s, l) { return s + Number(l.Revenue || 0); }, 0);
  var sh = SpreadsheetApp.getActive().getSheetByName(SHEETS.PERF), map = headerMap_(sh);
  var existing = readTable_(SHEETS.PERF).filter(function (p) { return p.Campaign_ID === campaignId; })[0];
  var fields = {
    Campaign_ID: campaignId, Campaign_Name: c.Campaign_Name, Region: c.Region, Budget: c.Proposed_Budget,
    Actual_Spend: delivery && delivery.actualSpend != null ? delivery.actualSpend : (existing ? existing.Actual_Spend : 0),
    Impressions: delivery && delivery.impressions != null ? delivery.impressions : (existing ? existing.Impressions : 0),
    Clicks: delivery && delivery.clicks != null ? delivery.clicks : (existing ? existing.Clicks : 0),
    Leads: leads.length, Qualified_Leads: qualified, Conversions: converted.length, Revenue: revenue
  };
  if (existing) updateRow_(SHEETS.PERF, existing._row, fields); else appendRow_(SHEETS.PERF, fields);
  // CPL, Conversion_Rate, ROAS and ROI are spreadsheet formulas in the sheet (see GOOGLE_DEPLOYMENT.md) and recalculate themselves.
  logEvent_(currentUser_(), 'Performance updated', campaignId, '', '', leads.length + ' leads, ' + converted.length + ' conversions');
}

/**
 * calculateKPIs
 * Business purpose: one definition of every headline number, used by the dashboard and the weekly report.
 * Optional filter: {region, campaignId}. Divisions are guarded so an empty filter returns 0, not an error.
 */
function calculateKPIs(filter) {
  filter = filter || {};
  var rows = readTable_(SHEETS.PERF).filter(function (p) {
    return (!filter.region || p.Region === filter.region) && (!filter.campaignId || p.Campaign_ID === filter.campaignId);
  });
  function sum(f) { return rows.reduce(function (s, r) { return s + Number(r[f] || 0); }, 0); }
  function div(a, b) { return b ? a / b : 0; }
  var spend = sum('Actual_Spend'), leads = sum('Leads'), conv = sum('Conversions'), rev = sum('Revenue');
  var reqs = readTable_(SHEETS.REQUESTS);
  return {
    totalCampaigns: reqs.length,
    activeCampaigns: reqs.filter(function (r) { return r.Execution_Status === EX.DONE; }).length,
    pendingApprovals: reqs.filter(function (r) { return r.Approval_Status === ST.PENDING; }).length,
    totalBudget: reqs.reduce(function (s, r) { return s + Number(r.Proposed_Budget || 0); }, 0),
    totalSpend: spend, totalLeads: leads, conversions: conv, revenue: rev,
    cpl: div(spend, leads), conversionRate: div(conv, leads), roas: div(rev, spend), roi: div(rev - spend, spend)
  };
}
