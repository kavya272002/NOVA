/* Views B: Create/Edit campaign, Pending approvals, Approval history, Lead management, Campaign performance. */

/* ================================================================ CREATE / EDIT */
function bandContains(r, b) {
  const lo = r.Min_Inclusive ? b >= r.Min_Budget : b > r.Min_Budget;
  if (r.Max_Budget == null) return lo;
  return lo && (r.Max_Inclusive ? b <= r.Max_Budget : b < r.Max_Budget);
}
function previewRoute(budget) {
  const b = Number(budget);
  if (!budget || isNaN(b) || b <= 0) return `<div class="muted small">Enter a proposed budget to see the approval route the rule engine will apply.</div>`;
  const r = NOVA.meta.rules.filter((x) => x.Active).find((x) => bandContains(x, b));
  if (!r) return `<div class="banner bad">No approval rule covers this budget.</div>`;
  return `<div class="small muted" style="margin-bottom:6px">${esc(r.Rule_Name)} · ${r.Chain.length} level${r.Chain.length > 1 ? "s" : ""}</div><div class="route-preview">${r.Chain.map((x, i) => `${i ? '<div class="arrow">↓</div>' : ""}<div class="row"><span class="step-no">${i + 1}</span><b>${esc(x)}</b></div>`).join("")}<div class="arrow">↓</div><div class="row"><span class="step-no" style="background:var(--good)">✓</span><b>Governance check → Ready for Execution</b></div></div>`;
}

async function renderCampaignForm(page, editId) {
  const m = NOVA.meta, me = NOVA.me;
  let cur = null, currentId = editId || null;
  if (editId) { const d = await GET(`/api/campaigns/${encodeURIComponent(editId)}`); cur = d.campaign; if (cur.Requester_ID !== me.User_ID) { page.innerHTML = `<div class="banner bad">Only the requester can edit this campaign.</div>`; return; } if (!["Draft", "Validation Failed", "Rejected", "Rework Required"].includes(cur.Approval_Status)) { page.innerHTML = `<div class="banner warn"><div><b>This campaign is locked.</b> ${esc(cur.Approval_Status)} requests cannot be changed - approvals were given on these exact details. Raise a new request if something must change.</div></div><p style="margin-top:12px"><a class="btn" href="#/campaign/${esc(editId)}">Back to campaign</a></p>`; return; } }
  const v = (k, d = "") => esc(cur ? cur[k] ?? d : d);
  const chans = new Set((cur ? cur.Marketing_Channel || "" : "").split("+").map((x) => x.trim()).filter(Boolean));
  const opts = (arr, sel, ph) => `<option value="">${ph}</option>` + arr.map((x) => `<option ${sel === x ? "selected" : ""}>${esc(x)}</option>`).join("");
  page.innerHTML = setHead({ title: editId ? `Edit ${editId}` : "Create campaign", sub: editId ? "Fix the issues, then resubmit - the approval chain restarts from the first approver." : "Fill in the request. Validation, approval routing and notifications happen automatically on submit.", actions: !editId ? `<button class="btn" id="fill-demo">Fill Diwali demo data</button>` : "" }) +
    (cur && cur.Approval_Status === "Rejected" ? `<div class="banner bad" style="margin-bottom:14px"><div><b>Rejected.</b> ${esc(cur.Rejection_Reason)}</div></div>` : "") +
    (cur && cur.Approval_Status === "Rework Required" ? `<div class="banner warn" style="margin-bottom:14px"><div><b>Sent back for revision.</b> ${esc(cur.Rejection_Reason)}</div></div>` : "") +
    (cur && cur.Approval_Status === "Validation Failed" ? `<div class="banner bad" style="margin-bottom:14px"><div><b>Validation failed.</b> Fix the highlighted fields.</div></div>` : "") +
    `<div id="form-result"></div><div class="split"><div class="panel"><div class="pb">
    <div class="section-title">Campaign</div><div class="form-grid">
      <div class="field s4" data-field="Campaign_Name"><label>Campaign name</label><input type="text" data-k="Campaign_Name" value="${v("Campaign_Name")}" maxlength="120"><div class="err"></div></div>
      <div class="field s2" data-field="Region"><label>Region</label><select data-k="Region" disabled><option>${esc(me.Region)}</option></select><div class="hint">Locked to your region</div><div class="err"></div></div>
      <div class="field s2" data-field="Product"><label>Product</label><select data-k="Product">${opts(m.products, cur && cur.Product, "Select product")}</select><div class="err"></div></div>
      <div class="field s2" data-field="Campaign_Type"><label>Campaign type</label><select data-k="Campaign_Type">${opts(m.campaign_types, cur && cur.Campaign_Type, "Select type")}</select><div class="err"></div></div>
      <div class="field s2" data-field="Objective"><label>Marketing objective</label><select data-k="Objective">${opts(m.objectives, cur && cur.Objective, "Select objective")}</select><div class="err"></div></div>
      <div class="field s6" data-field="Marketing_Channel"><label>Marketing channels</label><div class="chips" id="chan-chips">${m.channels.map((c) => `<span class="chip ${chans.has(c) ? "on" : ""}" data-chan="${esc(c)}" role="checkbox" tabindex="0" aria-checked="${chans.has(c)}">${esc(c)}</span>`).join("")}</div><div class="err"></div></div>
    </div>
    <div class="section-title">Audience and schedule</div><div class="form-grid">
      <div class="field s6" data-field="Target_Audience"><label>Target audience</label><input type="text" data-k="Target_Audience" value="${v("Target_Audience")}" maxlength="200"><div class="err"></div></div>
      <div class="field s3" data-field="Start_Date"><label>Start date</label><input type="date" data-k="Start_Date" value="${v("Start_Date")}"><div class="err"></div></div>
      <div class="field s3" data-field="End_Date"><label>End date</label><input type="date" data-k="End_Date" value="${v("End_Date")}"><div class="err"></div></div>
    </div>
    <div class="section-title">Budget and forecast</div><div class="form-grid">
      <div class="field s2" data-field="Proposed_Budget"><label>Proposed budget (₹)</label><input type="number" data-k="Proposed_Budget" min="0" step="1000" value="${v("Proposed_Budget")}"><div class="err"></div></div>
      <div class="field s2" data-field="Expected_Leads"><label>Expected leads</label><input type="number" data-k="Expected_Leads" min="0" value="${v("Expected_Leads")}"><div class="err"></div></div>
      <div class="field s2" data-field="Expected_Conversions"><label>Expected conversions</label><input type="number" data-k="Expected_Conversions" min="0" value="${v("Expected_Conversions")}"><div class="err"></div></div>
      <div class="field s3" data-field="Expected_Revenue"><label>Expected revenue (₹)</label><input type="number" data-k="Expected_Revenue" min="0" step="1000" value="${v("Expected_Revenue")}"><div class="err"></div></div>
      <div class="field s3" data-field="Creative_Link"><label>Creative link (Drive) <span class="muted">optional</span></label><input type="text" data-k="Creative_Link" placeholder="https://drive…" value="${v("Creative_Link")}"><div class="err"></div></div>
      <div class="field s6" data-field="Campaign_Description"><label>Campaign description</label><textarea data-k="Campaign_Description" rows="3" maxlength="600">${v("Campaign_Description")}</textarea><div class="err"></div></div>
    </div>
    <div class="act-bar" style="margin-top:20px;justify-content:flex-end">${editId ? `<a class="btn" href="#/campaign/${esc(editId)}">Cancel</a><button class="btn" id="save-draft">Save changes</button><button class="btn primary" id="submit">Save and resubmit for approval</button>` : `<button class="btn" id="save-draft">Save as draft</button><button class="btn primary" id="submit">Submit for approval</button>`}</div>
    </div></div>
    <div class="grid" style="gap:16px;position:sticky;top:76px"><div class="panel"><div class="ph"><h3>Approval route preview</h3></div><div class="pb" id="route-prev"></div></div>
    <div class="panel"><div class="ph"><h3>On submit</h3></div><div class="pb small"><ol style="margin:0;padding-left:18px;line-height:1.7"><li>Campaign ID and timestamp are generated</li><li>Required fields, budget, dates and forecast are validated</li><li>The budget is classified from the approval rules table</li><li>The first approver is e-mailed automatically</li></ol></div></div></div></div>`;
  const val = (k) => { const el = $(`[data-k="${k}"]`, page); return el ? el.value : ""; };
  const collect = () => { const d = {}; $$("[data-k]", page).forEach((el) => (d[el.dataset.k] = el.value)); d.Region = me.Region; d.Marketing_Channel = $$(".chip.on", page).map((c) => c.dataset.chan).join(" + "); return d; };
  const refresh = () => {
    const rp = $("#route-prev");
    if (rp) rp.innerHTML = previewRoute(val("Proposed_Budget"));
  };
  $$("[data-k]", page).forEach((el) => el.addEventListener("input", refresh));
  $$(".chip", page).forEach((ch) => { const t = () => { ch.classList.toggle("on"); ch.setAttribute("aria-checked", ch.classList.contains("on")); }; ch.onclick = t; ch.onkeydown = (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); t(); } }; });
  refresh();
  const fd = $("#fill-demo");
  const fill = () => { const p = m.demo_prefill; $$("[data-k]", page).forEach((el) => { if (p[el.dataset.k] != null && el.dataset.k !== "Region") el.value = p[el.dataset.k]; }); $$(".chip", page).forEach((ch) => ch.classList.toggle("on", p.Marketing_Channel.split("+").map((x) => x.trim()).includes(ch.dataset.chan))); refresh(); toast("Demo data filled", "Diwali Smart Savings Campaign · ₹1,80,000", "good"); };
  if (fd) fd.onclick = fill;
  if (NOVA.prefill && !editId) { NOVA.prefill = false; fill(); }

  const showErrors = (errs) => {
    $$(".field.invalid", page).forEach((f) => f.classList.remove("invalid"));
    errs.forEach((e) => { const f = $(`[data-field="${e.field}"]`, page); if (f) { f.classList.add("invalid"); $(".err", f).textContent = e.message; } });
    const first = $(".field.invalid", page); if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const send = async (submit) => {
    const data = collect(), btns = $$("#save-draft, #submit", page); btns.forEach((b) => (b.disabled = true));
    $("#form-result").innerHTML = "";
    try {
      let res;
      if (currentId) res = await PUT(`/api/campaigns/${encodeURIComponent(currentId)}`, { data, resubmit: submit });
      else { res = await POST("/api/campaigns", { data, submit }); currentId = res.campaign_id; }
      if (!res.ok) {
        $("#form-result").innerHTML = `<div class="banner bad" style="margin-bottom:14px"><div><b>Validation failed - ${esc(currentId)} was returned to you.</b> ${res.errors.length} field${res.errors.length > 1 ? "s need" : " needs"} attention:<ul>${res.errors.map((e) => `<li>${esc(e.message)}</li>`).join("")}</ul></div></div>`;
        showErrors(res.errors);
      } else if (!submit) {
        $("#form-result").innerHTML = `<div class="banner info" style="margin-bottom:14px"><div><b>Draft saved as ${esc(currentId)}.</b> Submit it when you are ready.</div></div>`;
        toast("Draft saved", currentId, "good");
      } else {
        const r = res.route;
        page.innerHTML = `${setHead({ title: "Request submitted", sub: "Validation passed and the approval route was created automatically." })}
        <div class="panel" style="max-width:860px"><div class="pb"><div class="kv-strip" style="margin-bottom:16px"><div class="kv"><div class="l">Campaign ID</div><div class="v">${esc(res.campaign_id)}</div></div><div class="kv"><div class="l">Validation</div><div class="v" style="color:var(--good)">Passed</div></div><div class="kv"><div class="l">Budget</div><div class="v">${F.inr(res.campaign.Proposed_Budget)}</div></div><div class="kv"><div class="l">Approval levels</div><div class="v">${r.levels}</div></div></div>
        <div class="small muted" style="margin-bottom:4px">Rule applied: ${esc(r.rule_name)}</div>
        <div class="route"><div class="stop done"><div class="dot">✓</div><div class="role">Submitted</div><div class="who">${esc(me.Name)}</div></div>${r.chain.map((role, i) => `<div class="stop ${i === 0 ? "current" : ""}"><div class="dot">${i + 1}</div><div class="role">${esc(role)}</div><div class="who">${esc((r.approvers[i] || "").replace(/ \(.*/, ""))}</div></div>`).join("")}<div class="stop end terminus"><div class="dot">★</div><div class="role">Governance gate</div><div class="who">Execution locked</div></div></div>
        <div class="banner info" style="margin-top:16px"><div>${esc(r.approvers[0])} has been e-mailed. You will be notified at every step. Execution stays locked until all approvals are complete.</div></div>
        <div class="act-bar" style="margin-top:16px"><a class="btn primary" href="#/campaign/${esc(res.campaign_id)}">Track this request</a><a class="btn" href="#/create">Create another</a></div></div></div>`;
        refreshPending();
      }
    } catch (e) {
      if (e.code === "DUPLICATE_REQUEST") $("#form-result").innerHTML = `<div class="banner bad" style="margin-bottom:14px"><div><b>Duplicate blocked.</b> ${esc(e.error)} <a href="#/campaign/${esc(e.existing_id || "")}">Open ${esc(e.existing_id || "it")}</a></div></div>`;
      else { fail(e, "Could not save"); if (e.errors) showErrors(e.errors.map((x) => ({ field: "", message: x }))); }
    }
    btns.forEach((b) => (b.disabled = false));
  };
  $("#save-draft").onclick = () => send(false);
  $("#submit").onclick = () => send(true);
}
route("create", (page) => renderCampaignForm(page, null));
route("edit", (page, id) => renderCampaignForm(page, id));

/* ================================================================ PENDING APPROVALS */
route("approvals", async (page) => {
  const list = await GET("/api/approvals/pending");
  const sla = 240;
  page.innerHTML = setHead({ title: "Pending approvals", sub: `Campaigns waiting for your decision as <b>${esc(NOVA.me.Role)}</b>${NOVA.me.Role === "Regional Manager" ? ` for ${esc(NOVA.me.Region)}` : ""}. Oldest first.` }) +
    (list.length ? list.map((c) => {
      const mine = c.route.find((s) => s.state === "current");
      const overdue = (c.waiting_minutes || 0) > sla;
      return `<div class="approval-card" data-id="${esc(c.Campaign_ID)}"><div class="top"><h3>${esc(c.Campaign_Name)}</h3><span class="cid">${esc(c.Campaign_ID)}</span>${pill(`Level ${c.Approval_Step} of ${c.Approval_Level}`, "info")}${pill(`Waiting ${F.mins(c.waiting_minutes)}`, overdue ? "bad" : "warn")}${c.Revision_No > 1 ? pill(`Revision ${c.Revision_No}`, "neutral") : ""}<span class="grow" style="flex:1"></span><a href="#/campaign/${esc(c.Campaign_ID)}" class="small">Full record →</a></div>
      <div class="body"><div class="f"><label>Budget</label><div class="big">${F.inr(c.Proposed_Budget)}</div></div><div class="f"><label>Expected leads</label><div class="big">${F.num(c.Expected_Leads)}</div></div><div class="f"><label>Expected conversions</label><div class="big">${F.num(c.Expected_Conversions)}</div></div><div class="f"><label>Expected revenue</label><div class="big">${F.inr(c.Expected_Revenue, true)}</div></div>
      <div class="f"><label>Objective</label>${esc(c.Objective)}</div><div class="f"><label>Region · requester</label>${esc(c.Region)} · ${esc(c.Requester_Name)}</div><div class="f"><label>Channels</label>${esc(c.Marketing_Channel)}</div><div class="f"><label>Dates</label>${F.date(c.Start_Date)} → ${F.date(c.End_Date)}</div>
      <div class="f full"><label>Target audience</label>${esc(c.Target_Audience)}</div><div class="f full"><label>Description</label>${esc(c.Campaign_Description)}${c.Creative_Link ? ` · <a href="${esc(c.Creative_Link)}" target="_blank" rel="noopener noreferrer">creative</a>` : ""}</div>
      <div class="f full">${routeLine(c.route)}</div></div>
      <div class="foot"><div class="field"><label>Comments ${"<span class='muted'>(required to reject or send back)</span>"}</label><textarea rows="2" data-comment></textarea></div><div class="act-bar"><button class="btn good" data-d="approve">${c.Approval_Step === c.Approval_Level ? "Approve (final)" : "Approve"}</button><button class="btn warn" data-d="revise">Send back</button><button class="btn danger" data-d="reject">Reject</button></div></div></div>`;
    }).join("") : `<div class="panel"><div class="pb">${emptyState("Nothing is waiting for you", "New requests that reach your approval level appear here and you are e-mailed automatically.")}</div></div>`);
  $$(".approval-card", page).forEach((card) => {
    const cid = card.dataset.id;
    $$("[data-d]", card).forEach((b) => (b.onclick = async () => {
      const kind = b.dataset.d, comments = $("[data-comment]", card).value.trim();
      if (kind !== "approve" && !comments) { $("[data-comment]", card).focus(); return toast("Comment required", kind === "reject" ? "Enter the reason for rejection." : "Tell the requester what to change.", "warn"); }
      $$("[data-d]", card).forEach((x) => (x.disabled = true));
      try {
        const r = await POST(`/api/campaigns/${cid}/${kind}`, { comments });
        if (kind === "approve") toast(r.final ? "Fully approved" : "Approved", r.final ? `${cid} passed governance and is ${r.campaign.Execution_Status}. Execution team notified.` : `${cid} moved to ${r.next_approver}.`, "good");
        else toast(kind === "reject" ? "Campaign rejected" : "Sent back for revision", `${cid} - requester notified.`, "warn");
        renderRoute();
      } catch (e) { $$("[data-d]", card).forEach((x) => (x.disabled = false)); fail(e, "Decision not recorded"); }
    }));
  });
});

/* ================================================================ APPROVAL HISTORY */
route("history", async (page) => {
  const rows = await GET("/api/approvals/history");
  page.innerHTML = setHead({ title: "Approval history", sub: "Every approval, rejection and send-back. This log is append-only: entries cannot be edited or deleted." }) +
    `<div class="panel"><div class="pb" style="padding-bottom:8px;display:flex;gap:10px;flex-wrap:wrap"><input type="search" id="hq" placeholder="Search campaign, approver or comment" style="max-width:340px"><select id="hd" style="max-width:190px"><option value="">All decisions</option><option>Approved</option><option>Rejected</option><option>Sent Back</option></select></div><div class="pb flush table-wrap" id="hlist"></div></div>`;
  const draw = () => {
    const q = $("#hq").value.toLowerCase(), d = $("#hd").value;
    const r = rows.filter((x) => (!d || x.Decision === d) && (!q || [x.Campaign_ID, x.Campaign_Name, x.Approver_Name, x.Comments].join(" ").toLowerCase().includes(q)));
    $("#hlist").innerHTML = r.length ? `<table class="table"><thead><tr><th>Log #</th><th>When</th><th>Campaign</th><th>Level</th><th>Approver</th><th>Decision</th><th>Status change</th><th>Comments</th></tr></thead><tbody>${r.map((x) => `<tr><td class="num muted">${x.Approval_ID}</td><td class="num small">${F.dt(x.Decision_Date)}</td><td><a class="cid" href="#/campaign/${esc(x.Campaign_ID)}">${esc(x.Campaign_ID)}</a><div class="small muted">${esc(x.Campaign_Name)}</div></td><td>${x.Approval_Level}<span class="small muted"> · rev ${x.Revision_No}</span></td><td>${esc(x.Approver_Name)}<div class="small muted">${esc(x.Approver_Role)}</div></td><td>${pill(x.Decision, x.Decision === "Approved" ? "good" : x.Decision === "Rejected" ? "bad" : "warn")}</td><td class="small">${esc(x.Previous_Status)} → ${esc(x.New_Status)}</td><td class="small">${esc(x.Comments)}</td></tr>`).join("")}</tbody></table>` : emptyState("No approval decisions found");
  };
  $("#hq").oninput = draw; $("#hd").onchange = draw; draw();
});

/* ================================================================ LEAD MANAGEMENT */
route("leads", async (page) => {
  page.innerHTML = setHead({ title: "Lead management", sub: "Leads captured against executed campaigns. A lead scoring 60 or more counts as qualified.", actions: `${NOVA.perms.add_leads ? `<button class="btn" id="l-add">Add lead</button>` : ""}${NOVA.perms.load_results ? `<button class="btn" id="l-sim">Load simulated lead feed</button>` : ""}` }) + `<div id="fbar"></div><div id="lbody">${loading()}</div>`;
  const fb = filterBar("leads", ["region", "campaign", "campaign_type", "channel", "date_from", "date_to"], () => load(true));
  $("#fbar").innerHTML = fb.html; fb.bind($("#fbar"));
  let offset = 0, q = "", acc = [];
  async function load(reset) {
    if (reset) { offset = 0; acc = []; }
    const d = await GET("/api/leads", { ...NOVA.filters.leads, q, limit: 200, offset });
    acc = acc.concat(d.rows);
    const maxS = Math.max(1, ...d.by_source.map((s) => s.n));
    $("#lbody").innerHTML = `<div class="kpi-band" style="grid-template-columns:repeat(4,1fr)"><div class="kpi"><div class="k">Leads</div><div class="v">${F.num(d.total)}</div><div class="s">matching the filters</div></div><div class="kpi"><div class="k">Qualified (score ≥ ${d.threshold})</div><div class="v">${F.num(d.qualified)}</div><div class="s">${F.pct(d.total ? d.qualified / d.total : null)}</div></div><div class="kpi"><div class="k">Converted</div><div class="v">${F.num(d.converted)}</div><div class="s">${F.pct(d.total ? d.converted / d.total : null)} conversion</div></div><div class="kpi"><div class="k">Revenue</div><div class="v">${F.inr(d.revenue, true)}</div><div class="s">from converted leads</div></div></div>
    <div class="grid g2" style="margin-bottom:16px"><div class="panel"><div class="ph"><h3>By lead source</h3></div><div class="pb">${d.by_source.map((s) => `<div style="display:grid;grid-template-columns:150px 1fr 90px;gap:10px;align-items:center;margin:6px 0;font-size:13px"><span>${esc(s.s)}</span><span><span class="bar-inline" style="width:${Math.max(2, (s.n / maxS) * 100)}%"></span></span><span class="num right">${F.num(s.n)} · ${F.pct(s.n ? s.c / s.n : null, 0)} conv.</span></div>`).join("") || '<div class="muted">No data</div>'}</div></div>
    <div class="panel"><div class="ph"><h3>By lead status</h3></div><div class="pb">${d.by_status.map((s) => `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px dashed var(--line)"><span>${esc(s.s)}</span><b class="num">${F.num(s.n)}</b></div>`).join("") || '<div class="muted">No data</div>'}</div></div></div>
    <div class="panel"><div class="pb" style="padding-bottom:8px"><input type="search" id="lq" placeholder="Search lead ID, campaign, sales rep or segment" value="${esc(q)}" style="max-width:380px"></div><div class="pb flush table-wrap">${acc.length ? `<table class="table"><thead><tr><th>Lead ID</th><th>Campaign</th><th>Region</th><th>Source</th><th>Date</th><th>Segment</th><th class="right">Score</th><th>Status</th><th>Sales assigned</th><th>Conversion</th><th class="right">Revenue</th></tr></thead><tbody>${acc.map((l) => `<tr><td class="cid">${esc(l.Lead_ID)}</td><td><a href="#/campaign/${esc(l.Campaign_ID)}" class="cid">${esc(l.Campaign_ID)}</a></td><td>${esc(l.Region)}</td><td>${esc(l.Lead_Source)}</td><td class="num">${F.date(l.Lead_Date)}</td><td>${esc(l.Customer_Segment)}</td><td class="num right">${l.Lead_Score}</td><td>${pill(l.Lead_Status, { Converted: "good", Qualified: "info", Lost: "bad", New: "neutral", Contacted: "warn" }[l.Lead_Status])}</td><td>${esc(l.Sales_Assigned)}</td><td>${esc(l.Conversion_Status)}</td><td class="num right">${l.Revenue ? F.inr(l.Revenue) : "—"}</td></tr>`).join("")}</tbody></table>` : emptyState("No leads yet", "Leads appear after a campaign is executed. Use “Load simulated lead feed” to generate some.")}</div>
    <div class="pb" style="display:flex;justify-content:space-between;align-items:center"><span class="small muted">Showing ${F.num(acc.length)} of ${F.num(d.total)}</span>${acc.length < d.total ? `<button class="btn small" id="l-more">Load more</button>` : ""}</div></div>`;
    $("#lq").oninput = (() => { let t; return (e) => { clearTimeout(t); t = setTimeout(() => { q = e.target.value; load(true).then(() => { const i = $("#lq"); i.focus(); i.setSelectionRange(q.length, q.length); }); }, 300); }; })();
    const more = $("#l-more"); if (more) more.onclick = () => { offset += 200; load(false); };
  }
  async function pickCampaign(title, fn) {
    const ex = await GET("/api/campaigns", { status: "Executed" });
    if (!ex.length) return toast("No executed campaigns", "Dispatch and execute a campaign first.", "warn");
    openModal({ title, body: `<div class="field"><label>Executed campaign</label><select id="pc">${ex.map((c) => `<option value="${esc(c.Campaign_ID)}">${esc(c.Campaign_ID)} · ${esc(c.Campaign_Name)}</option>`).join("")}</select></div>`, footer: `<button class="btn" data-close>Cancel</button><button class="btn primary" id="pc-go">Continue</button>`, onMount: (m, close) => { $("#pc-go", m).onclick = () => { const c = ex.find((x) => x.Campaign_ID === $("#pc", m).value); close(); fn(c); }; } });
  }
  const add = $("#l-add"); if (add) add.onclick = () => pickCampaign("Add a lead", (c) => leadModal(c, () => load(true)));
  const sim = $("#l-sim"); if (sim) sim.onclick = () => pickCampaign("Load simulated lead feed", async (c) => { try { const r = await POST(`/api/campaigns/${c.Campaign_ID}/simulate-results`); toast("Lead feed loaded", `${r.added_leads} leads added to ${c.Campaign_ID}.`, "good"); load(true); } catch (e) { fail(e); } });
  await load(true);
});

/* ================================================================ CAMPAIGN PERFORMANCE */
route("performance", async (page) => {
  page.innerHTML = setHead({ title: "Campaign performance", sub: "Spend and results per executed campaign. CPL, conversion rate, ROAS and ROI are calculated by formula, never typed in." }) + `<div id="fbar"></div><div id="pbody">${loading()}</div>`;
  const fb = filterBar("performance", ["region", "campaign", "campaign_type", "channel", "date_from", "date_to"], () => load());
  $("#fbar").innerHTML = fb.html; fb.bind($("#fbar"));
  async function load() {
    const rows = await GET("/api/performance", NOVA.filters.performance);
    const T = rows.reduce((a, r) => { ["Budget", "Actual_Spend", "Impressions", "Clicks", "Leads", "Qualified_Leads", "Conversions", "Revenue"].forEach((k) => (a[k] = (a[k] || 0) + r[k])); return a; }, {});
    const roi = (r) => (r == null ? "—" : `<span class="${r < 0 ? "neg-text" : "pos-text"}">${F.pct(r)}</span>`);
    $("#pbody").innerHTML = rows.length ? `<div class="panel"><div class="pb flush table-wrap"><table class="table"><thead><tr><th>Campaign</th><th>Region</th><th class="right">Budget</th><th class="right">Actual spend</th><th class="right">Impressions</th><th class="right">Clicks</th><th class="right">Leads</th><th class="right">Qualified</th><th class="right">Conversions</th><th class="right">Revenue</th><th class="right">CPL</th><th class="right">Conv. rate</th><th class="right">ROAS</th><th class="right">ROI</th></tr></thead><tbody>
      ${rows.map((r) => `<tr class="click" data-id="${esc(r.Campaign_ID)}"><td class="name"><span class="cid">${esc(r.Campaign_ID)}</span><div class="small muted" style="font-weight:400">${esc(r.Campaign_Name)}</div></td><td>${esc(r.Region)}</td><td class="num right">${F.inr(r.Budget)}</td><td class="num right">${F.inr(r.Actual_Spend)}<div class="small ${r.Actual_Spend > r.Budget ? "neg-text" : "muted"}">${r.Budget ? Math.round((r.Actual_Spend / r.Budget) * 100) : 0}% of budget</div></td><td class="num right">${F.num(r.Impressions)}</td><td class="num right">${F.num(r.Clicks)}</td><td class="num right">${F.num(r.Leads)}</td><td class="num right">${F.num(r.Qualified_Leads)}</td><td class="num right">${F.num(r.Conversions)}</td><td class="num right">${F.inr(r.Revenue)}</td><td class="num right">${r.CPL == null ? "—" : F.inr2(r.CPL)}</td><td class="num right">${F.pct(r.Conversion_Rate)}</td><td class="num right">${F.x(r.ROAS)}</td><td class="num right">${roi(r.ROI)}</td></tr>`).join("")}
      <tr style="background:#f4f7f5;font-weight:700"><td>Total (${rows.length} campaigns)</td><td></td><td class="num right">${F.inr(T.Budget)}</td><td class="num right">${F.inr(T.Actual_Spend)}</td><td class="num right">${F.num(T.Impressions)}</td><td class="num right">${F.num(T.Clicks)}</td><td class="num right">${F.num(T.Leads)}</td><td class="num right">${F.num(T.Qualified_Leads)}</td><td class="num right">${F.num(T.Conversions)}</td><td class="num right">${F.inr(T.Revenue)}</td><td class="num right">${T.Leads ? F.inr2(T.Actual_Spend / T.Leads) : "—"}</td><td class="num right">${T.Leads ? F.pct(T.Conversions / T.Leads) : "—"}</td><td class="num right">${T.Actual_Spend ? F.x(T.Revenue / T.Actual_Spend) : "—"}</td><td class="num right">${T.Actual_Spend ? roi((T.Revenue - T.Actual_Spend) / T.Actual_Spend) : "—"}</td></tr></tbody></table></div></div>
      <div class="panel" style="margin-top:16px"><div class="ph"><h3>How the metrics are calculated</h3></div><div class="pb"><div class="grid g4 small"><div><b>CPL</b><br>Actual spend ÷ leads</div><div><b>Conversion rate</b><br>Conversions ÷ leads</div><div><b>ROAS</b><br>Revenue ÷ marketing spend</div><div><b>ROI</b><br>(Revenue − marketing spend) ÷ marketing spend</div></div><p class="small muted" style="margin-top:10px">Totals use summed numerators and denominators (a weighted figure), not an average of campaign percentages. Leads, qualified leads, conversions and revenue roll up from the lead records automatically.</p></div></div>` : `<div class="panel"><div class="pb">${emptyState("No performance data", "Performance is recorded for executed campaigns.")}</div></div>`;
    $$("tr.click", page).forEach((tr) => (tr.onclick = () => (location.hash = `#/campaign/${tr.dataset.id}`)));
  }
  await load();
});
