/* Views C: Governance, Process metrics, Reports. */

function bandText(r) {
  const lo = F.inr(r.Min_Budget), hi = r.Max_Budget == null ? null : F.inr(r.Max_Budget);
  if (r.Min_Budget === 0 && hi) return `${r.Max_Inclusive ? "Up to" : "Below"} ${hi}`;
  if (!hi) return `${r.Min_Inclusive ? "" : "Above "}${lo}${r.Min_Inclusive ? " and above" : ""}`;
  return `${lo} – ${hi}${r.Max_Inclusive ? "" : " (excl.)"}`;
}
const STATE_LABEL = { compliant: "Fully compliant", pending: "Pending approval", blocked: "Blocked", violation: "Non-compliant" };

route("governance", async (page) => {
  const [g, rules] = await Promise.all([GET("/api/governance"), GET("/api/rules")]);
  const c = g.counts;
  const canEdit = NOVA.perms.edit_rules;
  page.innerHTML = setHead({ title: "Governance", sub: "No campaign can execute unless its approval status is <b>Fully Approved</b> and every control below passes. This is enforced in the application <i>and</i> in the database." }) + `
  <div class="kpi-band"><div class="kpi"><div class="k">Governance compliance</div><div class="v" style="color:var(--good)">${g.compliance_rate == null ? "—" : Math.round(g.compliance_rate * 100) + "%"}</div><div class="s">${g.execution_compliant} of ${g.execution_total} dispatched campaigns</div></div>
    <div class="kpi"><div class="k">Fully compliant</div><div class="v">${c.compliant}</div><div class="s">may execute</div></div><div class="kpi ${c.pending ? "attn" : ""}"><div class="k">Pending approval</div><div class="v">${c.pending}</div><div class="s">execution locked</div></div>
    <div class="kpi"><div class="k">Blocked</div><div class="v">${c.blocked}</div><div class="s">rejected, sent back, not submitted</div></div><div class="kpi ${c.violation ? "neg" : ""}"><div class="k">Non-compliant</div><div class="v">${c.violation}</div><div class="s">control failures</div></div></div>
  <div class="grid" style="gap:16px">
  <div class="panel"><div class="ph"><h3>Approval bottlenecks</h3><span class="note">pending requests by the role that holds them · SLA ${F.mins(g.sla_minutes)}</span></div><div class="pb flush table-wrap">${g.bottlenecks.length ? `<table class="table"><thead><tr><th>Waiting on</th><th class="right">Pending</th><th class="right">Average wait</th><th class="right">Oldest</th><th class="right">Over SLA</th></tr></thead><tbody>${g.bottlenecks.map((b) => `<tr><td class="name">${esc(b.role)}</td><td class="num right">${b.pending}</td><td class="num right">${F.mins(b.avg_wait_minutes)}</td><td class="num right"><a href="#/campaign/${esc(b.oldest_id)}">${esc(b.oldest_id)}</a> · ${F.mins(b.oldest_minutes)}</td><td class="num right">${b.overdue ? `<span class="neg-text">${b.overdue}</span>` : "0"}</td></tr>`).join("")}</tbody></table>` : emptyState("No pending approvals", "Nothing is waiting on any approver.")}</div></div>
  <div class="panel"><div class="ph"><h3>Approval rules</h3><span class="note">the route is read from this table - it is not hard-coded${canEdit ? "" : " · editable by the Business Head"}</span></div><div class="pb flush table-wrap"><table class="table"><thead><tr><th>Rule</th><th>Budget</th><th>Required approval chain</th><th></th></tr></thead><tbody>${rules.map((r) => `<tr><td class="name">${esc(r.Rule_Name)}</td><td>${esc(bandText(r))}</td><td>${r.Chain.map((x, i) => `${i ? " → " : ""}<b>${esc(x)}</b>`).join("")}</td><td class="right">${canEdit ? `<button class="btn small" data-edit="${r.Rule_ID}">Edit</button>` : ""}</td></tr>`).join("")}</tbody></table></div>
    <div class="pb" style="border-top:1px solid var(--line-soft)"><div class="field" style="max-width:300px;display:inline-flex"><label>Test a budget (₹)</label><input type="number" id="rt" placeholder="e.g. 150000"></div><div id="rt-out" style="margin-top:10px"></div><p class="small muted" style="margin-top:8px">Rule changes apply to new submissions only; requests already in approval keep the route they were given.</p></div></div>
  <div class="panel"><div class="ph"><h3>Governance status by campaign</h3><span class="note">click a row to see the full check</span></div><div class="pb" style="padding-bottom:6px"><div class="chips" id="gchips"><span class="chip on" data-s="">All</span>${Object.entries(STATE_LABEL).map(([k, v]) => `<span class="chip" data-s="${k}">${v}</span>`).join("")}</div></div><div class="pb flush table-wrap" id="glist"></div></div></div>`;
  const drawList = (s) => {
    const r = g.rows.filter((x) => !s || x.state === s);
    $("#glist").innerHTML = `<table class="table"><thead><tr><th>Campaign</th><th>Region</th><th class="right">Budget</th><th>Approval</th><th>Execution</th><th class="right">Controls</th><th>Governance status</th></tr></thead><tbody>${r.map((x) => `<tr class="click" data-id="${esc(x.Campaign_ID)}"><td class="name"><span class="cid">${esc(x.Campaign_ID)}</span><div class="small muted" style="font-weight:400">${esc(x.Campaign_Name || "")}</div></td><td>${esc(x.Region)}</td><td class="num right">${F.inr(x.Proposed_Budget)}</td><td>${pill(x.Approval_Status)}</td><td>${pill(x.Execution_Status)}</td><td class="num right">${x.controls_passed}/${x.controls_total}</td><td><span class="pill ${GOVKIND[x.state]}">${esc(x.label)}</span></td></tr>`).join("")}</tbody></table>`;
    $$("tr.click", $("#glist")).forEach((tr) => (tr.onclick = async () => { try { const gv = await GET(`/api/campaigns/${tr.dataset.id}/governance`); openModal({ title: `Governance check · ${tr.dataset.id}`, body: governanceCard(gv), footer: `<a class="btn" href="#/campaign/${esc(tr.dataset.id)}" data-close>Open campaign</a><button class="btn primary" data-close>Close</button>` }); } catch (e) { fail(e); } }));
  };
  drawList("");
  $$("#gchips .chip").forEach((ch) => (ch.onclick = () => { $$("#gchips .chip").forEach((x) => x.classList.toggle("on", x === ch)); drawList(ch.dataset.s); }));
  $("#rt").oninput = (e) => { $("#rt-out").innerHTML = previewRoute(e.target.value); };
  $$("[data-edit]", page).forEach((b) => (b.onclick = () => ruleModal(rules.find((r) => r.Rule_ID == b.dataset.edit))));
});

function ruleModal(r) {
  const roles = NOVA.meta.approver_roles;
  const slot = (i) => `<div class="field s3"><label>Level ${i + 1}</label><select data-slot="${i}"><option value="">- none -</option>${roles.map((x) => `<option ${r.Chain[i] === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div>`;
  openModal({
    title: `Edit rule · ${r.Rule_Name}`, wide: true,
    body: `<div class="form-grid"><div class="field s6"><label>Rule name</label><input type="text" id="r-name" value="${esc(r.Rule_Name)}"></div>
      <div class="field s2"><label>From budget (₹)</label><input type="number" id="r-min" value="${r.Min_Budget}"></div><div class="field s1" style="grid-column:span 1"><label>Incl.</label><input type="checkbox" id="r-mini" ${r.Min_Inclusive ? "checked" : ""}></div>
      <div class="field s2"><label>To budget (₹) - blank = no limit</label><input type="number" id="r-max" value="${r.Max_Budget ?? ""}"></div><div class="field s1" style="grid-column:span 1"><label>Incl.</label><input type="checkbox" id="r-maxi" ${r.Max_Inclusive ? "checked" : ""}></div>
      ${[0, 1, 2, 3].map(slot).join("")}</div><div id="r-err" class="banner bad hidden" style="margin-top:12px"></div><p class="small muted" style="margin-top:12px">Approvals run in level order. The whole rule table is checked for gaps and overlaps before saving, and the change is written to the audit trail.</p>`,
    footer: `<button class="btn" data-close>Cancel</button><button class="btn primary" id="r-go">Save rule</button>`,
    onMount: (m, close) => { $("#r-go", m).onclick = async () => {
      const chain = $$("[data-slot]", m).map((s) => s.value).filter(Boolean);
      try { await PUT(`/api/rules/${r.Rule_ID}`, { Rule_Name: $("#r-name", m).value, Min_Budget: $("#r-min", m).value, Min_Inclusive: $("#r-mini", m).checked ? 1 : 0, Max_Budget: $("#r-max", m).value, Max_Inclusive: $("#r-maxi", m).checked ? 1 : 0, Approval_Chain: chain }); close(); await loadMeta(); toast("Rule saved", "New submissions will use it.", "good"); renderRoute(); }
      catch (e) { const b = $("#r-err", m); b.textContent = e.error; b.classList.remove("hidden"); } }; },
  });
}

/* ================================================================ PROCESS METRICS */
route("metrics", async (page) => {
  const pm = await GET("/api/process-metrics");
  const b = pm.before, a = pm.after, red = pm.reduction_measured_pct, avg = a.avg_minutes_standard;
  const tp = (b.touchpoints - a.manual_touchpoints) / b.touchpoints;
  page.innerHTML = setHead({ title: "Process metrics", sub: "Operational dashboard: administrative cycle time before and after automation." }) + `
  <div class="banner warn" style="margin-bottom:16px"><div><b>Academic simulation.</b> ${esc(pm.disclaimer)}</div></div>
  <div class="grid g2" style="margin-bottom:16px;align-items:stretch">
    <div class="panel"><div class="pb"><div class="small muted" style="font-weight:600">Reduction in administrative cycle time (standard requests)</div><div class="bigpct" style="margin:8px 0">${red == null ? "—" : red.toFixed(1) + "%"}</div>
      <div class="small"><code>${esc(pm.formula)}</code><br>= (${b.avg_minutes} − ${avg == null ? "—" : avg.toFixed(1)}) ÷ ${b.avg_minutes} × 100</div>
      <div class="timebars" style="margin-top:16px"><div class="b"><span>Before</span><span><div class="t" style="width:100%;background:#c9d3cf"></div></span><b class="num right">${b.avg_minutes} min</b></div><div class="b"><span>After</span><span><div class="t" style="width:${avg == null ? 0 : (avg / b.avg_minutes) * 100}%;background:var(--good)"></div></span><b class="num right">${avg == null ? "—" : avg.toFixed(1)} min</b></div></div>
      <p class="small muted" style="margin-top:10px">Target: under ${pm.target_minutes} minutes. Note that exactly ${pm.target_minutes} minutes would be a ${pm.reduction_at_target_pct.toFixed(1)}% reduction, so the ~80% claim needs an average of 24 minutes or less - the measured average is ${avg == null ? "—" : avg.toFixed(1)}.</p></div></div>
    <div class="panel"><div class="ph"><h3>Measured cycle time per standard request</h3><span class="note">submission → fully approved, minutes</span></div><div class="pb"><div class="chart-box"><canvas id="cyc" role="img" aria-label="Cycle time per standard request"></canvas></div></div></div>
  </div>
  <div class="compare">
    <div class="col"><h3>Before automation <span class="badge-sim">SIMULATED</span></h3>
      <div class="m"><div class="l">Average approval coordination time</div><div class="v big">${b.avg_minutes} minutes</div></div>
      <div class="m"><div class="l">Manual touchpoints per campaign</div><div class="v">${b.touchpoints} (e-mails, WhatsApp pings, sheet edits)</div></div>
      <div class="m"><div class="l">Follow-ups per campaign</div><div class="v">${b.followups}</div></div>
      <div class="m"><div class="l">Approval visibility</div><div class="v">${esc(b.visibility)}</div></div>
      <div class="m"><div class="l">Governance risk</div><div class="v">${esc(b.governance_risk)}</div></div></div>
    <div class="col"><h3>After automation <span class="badge-meas">MEASURED IN PROTOTYPE</span></h3>
      <div class="m"><div class="l">Average processing time, standard requests (≤ ₹2,00,000; n = ${a.standard_count})</div><div class="v big">${avg == null ? "—" : avg.toFixed(1)} minutes</div><div class="small muted">${a.within_target_pct == null ? "" : Math.round(a.within_target_pct) + "% within the " + pm.target_minutes + "-minute target"}${a.avg_minutes_leadership != null ? ` · leadership-level requests (n = ${a.leadership_count}) average ${F.mins(a.avg_minutes_leadership)}` : ""}</div></div>
      <div class="m"><div class="l">Manual touchpoints per campaign · follow-ups</div><div class="v">${a.manual_touchpoints} (submit + one click per approver) · ${a.followups}</div><div class="small muted">${Math.round(tp * 100)}% fewer touchpoints · ${F.num(a.automated_notifications)} automated notifications sent (${a.notifications_per_campaign} per campaign)</div></div>
      <div class="m"><div class="l">Approval completion</div><div class="v">${a.approval_completion_pct == null ? "—" : a.approval_completion_pct.toFixed(0) + "%"} of decided requests fully approved</div></div>
      <div class="m"><div class="l">Governance compliance</div><div class="v" style="color:var(--good)">${a.governance_compliance_pct == null ? "—" : a.governance_compliance_pct.toFixed(0) + "%"} of ${a.governed_campaigns} dispatched campaigns passed every control</div></div>
      <div class="m"><div class="l">Campaign visibility</div><div class="v">${esc(a.visibility)}</div></div></div>
  </div>`;
  const d = pm.distribution;
  makeChart($("#cyc"), { type: "bar", data: { labels: d.map((_, i) => `#${i + 1}`), datasets: [{ type: "bar", label: "Minutes to full approval", data: d, backgroundColor: d.map((x) => (x <= pm.target_minutes ? SERIES[0] : SERIES[1])), borderRadius: { topLeft: 4, topRight: 4 }, maxBarThickness: 36, order: 2 }, { type: "line", label: `Target (${pm.target_minutes} min)`, data: d.map(() => pm.target_minutes), borderColor: "#17201f", borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, order: 1 }, { type: "line", label: `Manual baseline (${b.avg_minutes} min)`, data: [], borderColor: "#999" }] }, options: { responsive: true, layout: { padding: { top: 18 } }, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, suggestedMax: 30, grid: { color: "#e7ecea" }, title: { display: true, text: "minutes" } } }, plugins: { legend: { display: true, position: "bottom", labels: { filter: (i) => i.text.startsWith("Target") || i.text.startsWith("Minutes"), boxWidth: 12 } }, tooltip: { callbacks: { label: (c) => ` ${c.raw} min` } } } }, plugins: [barValuePlugin((v) => v)] });
});

/* ================================================================ REPORTS */
route("reports", async (page) => {
  page.innerHTML = setHead({ title: "Reports", sub: "Audit trail, notification outbox, regional summary and data exports." }) + `<div class="tabs" id="rtabs"><button data-t="audit" class="on">Audit trail</button><button data-t="mail">Notifications (Gmail)</button><button data-t="region">Regional summary</button><button data-t="export">Exports</button></div><div id="rbody"></div>`;
  const tabs = {
    async audit() {
      const el = $("#rbody"); el.innerHTML = loading();
      const state = { campaign_id: "", action: "" };
      const draw = async () => {
        const d = await GET("/api/audit", { ...state, limit: 400 });
        el.innerHTML = `<div class="filters"><div class="field wide"><label>Campaign</label><select id="au-c"><option value="">All campaigns</option>${NOVA.meta.campaigns.map((c) => `<option value="${esc(c.Campaign_ID)}" ${state.campaign_id === c.Campaign_ID ? "selected" : ""}>${esc(c.Campaign_ID)} · ${esc(c.Campaign_Name)}</option>`).join("")}</select></div><div class="field wide"><label>Event</label><select id="au-a"><option value="">All events</option>${d.actions.map((a) => `<option ${state.action === a ? "selected" : ""}>${esc(a)}</option>`).join("")}</select></div></div><div class="panel"><div class="pb flush table-wrap">${d.rows.length ? `<table class="table"><thead><tr><th>Timestamp</th><th>User</th><th>Event</th><th>Campaign</th><th>Previous</th><th>New</th><th>Details</th></tr></thead><tbody>${d.rows.map((r) => `<tr><td class="num small">${F.dt(r.Timestamp)}</td><td>${esc(r.User)}<div class="small muted">${esc(r.User_Role)}</div></td><td>${pill(r.Action, /Rejected|Blocked|Unauthorized|Out-of-sequence|Duplicate/.test(r.Action) ? "bad" : /Granted|Fully|Dispatched|Executed|Governance/.test(r.Action) ? "good" : "neutral")}</td><td>${r.Campaign_ID ? `<a class="cid" href="#/campaign/${esc(r.Campaign_ID)}">${esc(r.Campaign_ID)}</a>` : "—"}</td><td class="small">${esc(r.Previous_Status || "—")}</td><td class="small">${esc(r.New_Status || "—")}</td><td class="small">${esc(r.Details)}</td></tr>`).join("")}</tbody></table>` : emptyState("No audit events")}</div></div><p class="small muted" style="margin-top:8px">Showing the latest ${d.rows.length} events. The audit trail is append-only; blocked and unauthorized attempts are recorded too.</p>`;
        $("#au-c").onchange = (e) => { state.campaign_id = e.target.value; draw(); }; $("#au-a").onchange = (e) => { state.action = e.target.value; draw(); };
      };
      await draw();
    },
    async mail() {
      const el = $("#rbody"); el.innerHTML = loading();
      let all = false;
      const draw = async () => {
        const rows = await GET("/api/notifications", all ? { scope: "all" } : {});
        el.innerHTML = `<div class="banner info" style="margin-bottom:14px"><div>This is the notification layer (Gmail in the Google build). ${all ? "Showing every e-mail the system has sent." : "Showing e-mails addressed to you."} Click a message to read it.${NOVA.perms.view_all_audit ? ` <a href="#" id="mail-toggle">${all ? "Show only mine" : "Show all users"}</a>` : ""}</div></div><div class="panel"><div class="pb flush table-wrap">${rows.length ? `<table class="table"><thead><tr><th>Sent</th><th>To</th><th>Type</th><th>Subject</th><th>Status</th></tr></thead><tbody>${rows.map((r, i) => `<tr class="click" data-i="${i}"><td class="num small">${F.dt(r.Timestamp)}</td><td>${esc(r.To_Name)}</td><td>${pill(r.Notification_Type, { "Approval Request": "warn", "Execution Dispatch": "info", "Fully Approved": "good", Rejected: "bad", "Validation Failed": "bad", "Revision Requested": "warn" }[r.Notification_Type] || "neutral")}</td><td>${esc(r.Subject)}</td><td class="small muted">${esc(r.Status)}</td></tr>`).join("")}</tbody></table>` : emptyState("No e-mails", "Notifications appear as soon as requests are submitted and approved.")}</div></div>`;
        $$("tr.click", el).forEach((tr) => (tr.onclick = () => { const r = rows[+tr.dataset.i]; openModal({ title: r.Subject, wide: true, body: `<div class="small muted" style="margin-bottom:10px">To: ${esc(r.To_Name)} &lt;${esc(r.To_Email)}&gt; · ${F.dt(r.Timestamp)} · ${esc(r.Channel)}</div><div class="mail">${esc(r.Body)}</div>` }); }));
        const t = $("#mail-toggle"); if (t) t.onclick = (e) => { e.preventDefault(); all = !all; draw(); };
      };
      await draw();
    },
    async region() {
      const el = $("#rbody"); el.innerHTML = loading();
      const d = await GET("/api/dashboard"), R = d.charts.spend_by_region;
      const tot = R.reduce((a, r) => ({ c: a.c + r.campaigns, s: a.s + r.spend, b: a.b + r.approved_budget, r: a.r + r.revenue }), { c: 0, s: 0, b: 0, r: 0 });
      el.innerHTML = `<div class="panel"><div class="pb flush table-wrap"><table class="table"><thead><tr><th>Region</th><th class="right">Campaigns</th><th class="right">Approved budget</th><th class="right">Actual spend</th><th class="right">Revenue</th><th class="right">ROAS</th><th class="right">ROI</th></tr></thead><tbody>${R.map((r) => `<tr><td class="name"><a class="cid" href="#/dashboard" data-reg="${esc(r.region)}">${esc(r.region)}</a></td><td class="num right">${r.campaigns}</td><td class="num right">${F.inr(r.approved_budget)}</td><td class="num right">${F.inr(r.spend)}</td><td class="num right">${F.inr(r.revenue)}</td><td class="num right">${r.spend ? F.x(r.revenue / r.spend) : "—"}</td><td class="num right">${r.spend ? F.pct((r.revenue - r.spend) / r.spend) : "—"}</td></tr>`).join("")}<tr style="background:#f4f7f5;font-weight:700"><td>All regions</td><td class="num right">${tot.c}</td><td class="num right">${F.inr(tot.b)}</td><td class="num right">${F.inr(tot.s)}</td><td class="num right">${F.inr(tot.r)}</td><td class="num right">${tot.s ? F.x(tot.r / tot.s) : "—"}</td><td class="num right">${tot.s ? F.pct((tot.r - tot.s) / tot.s) : "—"}</td></tr></tbody></table></div></div>`;
      $$("[data-reg]", el).forEach((a) => {
        a.onclick = () => { NOVA.filters.dashboard = NOVA.filters.dashboard || {}; NOVA.filters.dashboard.region = a.dataset.reg; };
      });
    },
    async export() {
      const mg = NOVA.perms.view_all_audit || NOVA.me.Role === "Marketing Manager";
      $("#rbody").innerHTML = `<div class="panel"><div class="pb"><p class="muted" style="margin-bottom:12px">CSV exports respect your access: you only receive the campaigns you are allowed to see.</p><div class="act-bar"><a class="btn" href="/api/export/campaigns.csv">Campaigns (CSV)</a><a class="btn" href="/api/export/leads.csv">Leads (CSV)</a><a class="btn" href="/api/export/performance.csv">Performance (CSV)</a><a class="btn" href="/api/export/approval_log.csv">Approval log (CSV)</a>${NOVA.perms.view_all_audit ? `<a class="btn" href="/api/export/audit_trail.csv">Audit trail (CSV)</a>` : ""}</div>
        ${mg ? `<hr style="border:0;border-top:1px solid var(--line);margin:18px 0"><p style="margin-bottom:10px"><b>Google Sheets workbook</b><br><span class="muted">All tables in one .xlsx - with live formulas for CPL, conversion rate, ROAS, ROI and the KPI sheet. Import it into Google Sheets to get the same database the Apps Script code expects.</span></p><a class="btn primary" href="/api/export/workbook.xlsx">Download Google Sheets workbook (.xlsx)</a>` : ""}</div></div>`;
    },
  };
  const show = (t) => { $$("#rtabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === t)); return tabs[t](); };
  $$("#rtabs button").forEach((b) => (b.onclick = () => show(b.dataset.t)));
  await show("audit");
});
