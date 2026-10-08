/**
 * Config.gs - constants shared by every script file.
 * Business purpose: one place that names the sheets, roles and statuses, so a rename in the
 * business (e.g. a new approval status) is a one-line change and not a hunt through the code.
 * These names are identical to the Flask/SQLite prototype so both builds behave the same.
 */
var SHEETS = {
  REQUESTS: 'CAMPAIGN_REQUESTS',
  RULES: 'APPROVAL_RULES',
  LOG: 'APPROVAL_LOG',
  LEADS: 'LEAD_DATA',
  PERF: 'CAMPAIGN_PERFORMANCE',
  USERS: 'USERS',
  SETTINGS: 'SETTINGS',
  AUDIT: 'AUDIT_TRAIL',
  NOTIFY: 'NOTIFICATIONS'
};

var ST = {
  DRAFT: 'Draft', VALFAIL: 'Validation Failed', PENDING: 'Pending Approval',
  APPROVED: 'Fully Approved', REJECTED: 'Rejected', REWORK: 'Rework Required'
};
var EX = { NOT_READY: 'Not Ready', READY: 'Ready for Execution', DONE: 'Executed' };
var ROLE = {
  EXEC: 'Regional Marketing Executive', RM: 'Regional Manager', MM: 'Marketing Manager',
  MH: 'Marketing Head', BH: 'Business Head', EXECUTION: 'Execution Team'
};
var APPROVER_ROLES = [ROLE.RM, ROLE.MM, ROLE.MH, ROLE.BH];
var CHAIN_SEP = '|';   // APPROVAL_RULES.Approval_Chain, e.g. "Regional Manager|Marketing Manager"

/** Header row -> {columnName: index}. Reading by header name means inserting a column never breaks the code. */
function headerMap_(sheet) {
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var map = {};
  headers.forEach(function (h, i) { map[h] = i; });
  return map;
}

/** All rows of a sheet as objects, each carrying its sheet row number in `_row`. */
function readTable_(sheetName) {
  var sh = SpreadsheetApp.getActive().getSheetByName(sheetName);
  if (!sh) throw new Error('Sheet missing: ' + sheetName + '. Run Setup > Initialise workbook.');
  var last = sh.getLastRow();
  if (last < 2) return [];
  var map = headerMap_(sh);
  var names = Object.keys(map);
  var values = sh.getRange(2, 1, last - 1, sh.getLastColumn()).getValues();
  return values.map(function (row, i) {
    var o = { _row: i + 2 };
    names.forEach(function (n) { o[n] = row[map[n]]; });
    return o;
  });
}

function findCampaign_(campaignId) {
  var rows = readTable_(SHEETS.REQUESTS);
  for (var i = 0; i < rows.length; i++) if (rows[i].Campaign_ID === campaignId) return rows[i];
  throw new Error('Campaign not found: ' + campaignId);
}

/** Write only the named fields of one row (never overwrites other columns). */
function updateRow_(sheetName, row, fields) {
  var sh = SpreadsheetApp.getActive().getSheetByName(sheetName);
  var map = headerMap_(sh);
  Object.keys(fields).forEach(function (k) {
    if (!(k in map)) throw new Error('Unknown column ' + k + ' in ' + sheetName);
    sh.getRange(row, map[k] + 1).setValue(fields[k]);
  });
}

function appendRow_(sheetName, obj) {
  var sh = SpreadsheetApp.getActive().getSheetByName(sheetName);
  var map = headerMap_(sh);
  var row = new Array(sh.getLastColumn()).fill('');
  Object.keys(obj).forEach(function (k) { if (k in map) row[map[k]] = obj[k]; });
  sh.appendRow(row);
}

function nowStamp_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');
}

function currentUser_() {
  var email = Session.getActiveUser().getEmail();
  var users = readTable_(SHEETS.USERS);
  for (var i = 0; i < users.length; i++) {
    if (String(users[i].Email).toLowerCase() === String(email).toLowerCase() && users[i].Active !== false) return users[i];
  }
  throw new Error('Access denied: ' + email + ' is not an active user in the USERS sheet.');
}
