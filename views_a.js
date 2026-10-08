/* Views A: Executive Demo, Dashboard, Campaigns, Campaign detail. */

const REG_TOTALS = (rows, k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
function tableDetails(title, headers, rows) {
  return `<details style="margin-top:8px"><summary class="small muted" style="cursor:pointer">${esc(title)}</summary><div class="table-wrap"><table class="table" style="margin-top:6px"><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td class="${i ? "num right" : ""}">${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
}
const barValuePlugin = (fmt, horizontal = false) => ({
  id: "barValues",
  afterDatasetsDraw(chart) {
    const { ctx } = chart; ctx.save();
    ctx.font = "600 11px Inter, sans-serif";
    ctx.fillStyle = "#334155";
    chart.data.datasets.forEach((ds, di) => {
      const meta = chart.getDatasetMeta(di);
      if (!meta || !meta.data) return;
      meta.data.forEach((bar, i) => {
        const v = ds.data[i]; if (v == null || isNaN(v)) return;
        const t = fmt(v);
        if (horizontal) { ctx.textAlign = v < 0 ? "right" : "left"; ctx.textBaseline = "middle"; ctx.fillText(t, bar.x + (v < 0 ? -6 : 6), bar.y); }
        else { ctx.textAlign = "center"; ctx.textBaseline = "bottom"; ctx.fillText(t, bar.x, bar.y - 4); }
      });
    });
    ctx.restore();
  },
});
const axisInr = (v) => F.inr(v, true);

/* ================================================================ EXECUTIVE DEMO */
route("demo", async (page) => {
  const canRun = NOVA.perms.run_scenario;
  page.innerHTML = `
  <div class="panel" style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:32px 36px; margin-bottom:24px; box-shadow:0 1px 3px rgba(15,23,42,0.05);">
    <div style="font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:#2563eb; margin-bottom:8px;">Enterprise Operations</div>
    <h1 style="font-size:24px; font-weight:700; margin-bottom:10px; color:#0f172a; letter-spacing:-0.02em;">Automated Campaign Governance Platform</h1>
    <p style="color:#64748b; font-size:14px; max-width:72ch; margin-bottom:20px; line-height:1.5;">Simulate request validation, dynamic budget-based approval routing, governance compliance checks, and real-time ROI tracking.</p>
    <div style="display:flex; gap:12px; flex-wrap:wrap; align-items:center;">
      <button class="btn primary" id="start-demo" style="padding:9px 18px; font-size:13.5px;">Start Guided Demo (Aman Sharma)</button>
      <button class="btn outline" id="auto-run" style="padding:9px 16px; font-size:13.5px;">Run Automated Scenario</button>
      <a href="#/dashboard" class="btn outline" style="padding:9px 16px; font-size:13.5px;">View Dashboard</a>
      <a href="#/approvals" class="btn outline" style="padding:9px 16px; font-size:13.5px;">Pending Approvals</a>
      ${NOVA.perms.reset_demo ? `<button class="btn danger" id="reset-demo" style="padding:9px 16px; font-size:13.5px;">Reset Sample Data</button>` : ""}
    </div>
    <div id="auto-result" style="margin-top:16px"></div>
  </div>`;

  const startBtn = $("#start-demo");
  if (startBtn) {
    startBtn.onclick = async () => {
      try {
        const r = await POST("/api/demo/switch", { email: "aman.sharma@novabrands.in" });
        applyMe(r);
        renderShell();
        NOVA.prefill = true;
        location.hash = "#/create";
        toast("Signed in as Aman Sharma", "Click “Fill Diwali demo data”, then submit.", "good");
      } catch (e) {
        fail(e);
      }
    };
  }

  const autoBtn = $("#auto-run");
  if (autoBtn) {
    autoBtn.onclick = async (ev) => {
      const btn = ev.currentTarget;
      btn.disabled = true;
      btn.innerHTML = `<span class="spin"></span> Running automated scenario…`;
      try {
        const res = await POST("/api/demo/run-scenario");
        $("#auto-result").innerHTML = `
          <div class="banner good" style="margin-top:16px;">
            <div>
              <b>Automated Scenario Completed in ${res.total_seconds}s!</b><br>
              Campaign <a href="#/campaign/${esc(res.campaign_id)}"><b>${esc(res.campaign_id)}</b></a> was automatically raised, routed through approvals, verified by governance rules, and executed.<br>
              <a href="#/campaign/${esc(res.campaign_id)}" class="btn small primary" style="margin-top:8px; display:inline-block;">View Created Campaign & Audit Trail</a>
            </div>
          </div>`;
        refreshPending();
      } catch (e) {
        fail(e, "Scenario failed");
      } finally {
        btn.disabled = false;
        btn.innerHTML = `Run Automated Scenario`;
      }
    };
  }

  const rs = $("#reset-demo");
  if (rs) rs.onclick = async () => {
    if (!confirm("Reset the demo database to initial sample data?")) return;
    try { await POST("/api/admin/reset"); toast("Database reset", "Sample data restored.", "good"); location.reload(); } catch (e) { fail(e); }
  };
});

/* ================================================================ DASHBOARD */
route("dashboard", async (page) => {
  const scopeNote = NOVA.me.Role === "Regional Marketing Executive" ? "Showing your own campaigns." : NOVA.me.Role === "Regional Manager" ? `Showing campaigns in ${NOVA.me.Region}.` : "Showing all regions.";
  page.innerHTML = setHead({ title: "Marketing Operations Control Center", cls: "control-title", sub: `Live view of campaign approval pipeline, budgets and realized revenues. ${esc(scopeNote)}` }) + `<div id="fbar"></div><div id="dash-body">${loading()}</div>`;
  const fb = filterBar("dashboard", ["region", "campaign", "campaign_type", "channel", "status", "approval_status", "date_from", "date_to"], () => load());
  $("#fbar").innerHTML = fb.html; fb.bind($("#fbar"));
  async function load() {
    destroyCharts();
    const d = await GET("/api/dashboard", NOVA.filters.dashboard);
    const k = d.kpis, ch = d.charts;
    const kp = (cls, label, val, sub) => `<div class="kpi ${cls}"><div class="k">${label}</div><div class="v" title="${esc(val)}">${val}</div><div class="s">${sub || ""}</div></div>`;
    $("#dash-body").innerHTML = `
    <div class="kpi-band">
      ${kp("", "Total Campaigns", F.num(k.total), `${k.rejected} rejected · ${k.rework} sent back`)}
      ${kp(k.pending ? "attn" : "", "Pending Approvals", F.num(k.pending), "awaiting manager review")}
      ${kp("", "Approved Budget", F.inr(k.approved_budget, true), `${k.approved} campaigns approved`)}
      ${kp("", "Actual Spend", F.inr(k.spend, true), `${k.tracked} tracked campaigns`)}
      ${kp("", "Realized Revenue", F.inr(k.revenue, true), "from completed campaigns")}
      ${kp("", "Return on Ad Spend (ROAS)", F.x(k.roas), "revenue ÷ spend")}
    </div>
    <div class="charts">
      <div class="panel c6"><div class="ph"><h3>Campaigns & Budget by Region</h3></div><div class="pb"><div class="legend"><span><i style="background:${SERIES[0]}"></i>Approved Budget</span><span><i style="background:${SERIES[1]}"></i>Actual Spend</span></div><div class="chart-box" style="height:260px"><canvas id="c2" role="img" aria-label="Spend by region"></canvas></div></div></div>
      <div class="panel c6"><div class="ph"><h3>Regional Campaign Count</h3></div><div class="pb"><div class="chart-box" style="height:260px"><canvas id="c1" role="img" aria-label="Campaigns by region"></canvas></div></div></div>
      <div class="panel c12"><div class="ph"><h3>Approval Pipeline Status</h3><span class="note">Rejected: ${ch.pipeline_other.Rejected} · Rework Required: ${ch.pipeline_other["Rework Required"]} · Click any step to filter</span></div><div class="pb"><div class="pipeline">${ch.pipeline.map((s) => `<div class="st ${s.stage === NOVA.filters.dashboard?.status ? "active" : ""} ${s.stage === "Pending Approval" && s.count ? "hot" : ""}" data-stage="${esc(s.stage)}" style="cursor:pointer" title="Click to filter by ${esc(s.stage)}"><div class="n">${s.count}</div><div class="l">${esc(s.stage)}</div></div>`).join("")}</div></div></div>
      <div class="panel c12"><div class="ph"><h3>Completed Campaign Financial Performance</h3><span class="note">Enter actual spend & revenue upon campaign completion to track returns</span></div><div class="pb">${tableDetails("Completed Campaigns Financial Table", ["Campaign", "Actual Spend", "Realized Revenue", "ROAS", "ROI"], ch.roi.map((r) => [`<a class="cid" href="#/campaign/${esc(r.id)}"><b>${esc(r.id)}</b> ${esc(r.name)}</a>`, F.inr(r.spend || 0), F.inr(r.revenue || 0), F.x(r.roas), F.pct(r.roi)]))}</div></div>
    </div>`;
    $$(".pipeline .st", page).forEach((st) => {
      st.onclick = () => {
        const stage = st.dataset.stage;
        if (!stage) return;
        const cur = NOVA.filters.dashboard.status;
        NOVA.filters.dashboard.status = (cur === stage) ? "" : stage;
        load();
      };
    });
    drawDash(d);
  }
  function drawDash(d) {
    try {
      const ch = d.charts;
      const makeBarOpts = (fmtTick, listKey) => ({
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 22, bottom: 4, left: 4, right: 4 } },
        onHover: (event, chartElement) => {
          if (event.native && event.native.target) {
            event.native.target.style.cursor = chartElement[0] ? "pointer" : "default";
          }
        },
        onClick: (evt, activeElements) => {
          if (activeElements.length > 0) {
            const idx = activeElements[0].index;
            const targetRegion = ch[listKey][idx]?.region;
            if (targetRegion) {
              const cur = NOVA.filters.dashboard.region;
              NOVA.filters.dashboard.region = (cur === targetRegion) ? "" : targetRegion;
              load();
            }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { family: "Inter, sans-serif", size: 12 }, color: "#64748b" } },
          y: { beginAtZero: true, ticks: { callback: fmtTick, maxTicksLimit: 5, font: { family: "Inter, sans-serif", size: 12 }, color: "#64748b" }, grid: { color: "#f1f5f9" } }
        }
      });
      const bar = (data, color) => ({ data, backgroundColor: color, borderRadius: { topLeft: 4, topRight: 4 }, maxBarThickness: 36, borderSkipped: false });
      const c1El = $("#c1");
      if (c1El) {
        makeChart(c1El, {
          type: "bar",
          data: { labels: ch.campaigns_by_region.map((r) => r.region), datasets: [{ label: "Campaigns", ...bar(ch.campaigns_by_region.map((r) => r.campaigns), SERIES[0]) }] },
          options: makeBarOpts((v) => v, "campaigns_by_region"),
          plugins: [barValuePlugin((v) => v)]
        });
      }
      const c2El = $("#c2");
      if (c2El) {
        makeChart(c2El, {
          type: "bar",
          data: {
            labels: ch.spend_by_region.map((r) => r.region),
            datasets: [
              { label: "Approved Budget", ...bar(ch.spend_by_region.map((r) => r.approved_budget), SERIES[0]), barPercentage: .9, categoryPercentage: .72 },
              { label: "Actual Spend", ...bar(ch.spend_by_region.map((r) => r.spend), SERIES[1]), barPercentage: .9, categoryPercentage: .72 }
            ]
          },
          options: {
            ...makeBarOpts(axisInr, "spend_by_region"),
            plugins: {
              tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${F.inr(c.raw)}` } }
            }
          },
          plugins: [barValuePlugin(F.inr)]
        });
      }
    } catch (e) {
      console.error("Dashboard chart draw error:", e);
    }
  }
  await load();
});

/* ================================================================ CAMPAIGNS LIST */
route("campaigns", async (page) => {
  page.innerHTML = setHead({ title: "Campaigns", sub: "Every request, its approval state and where it is stuck.", actions: NOVA.perms.create_campaign ? `<a class="btn primary" href="#/create">+ Create campaign</a>` : "" }) + `<div id="fbar"></div><div class="panel"><div class="pb" style="padding-bottom:8px"><input type="search" id="csearch" placeholder="Search by ID, name, product or requester" style="max-width:380px" aria-label="Search campaigns"></div><div class="pb flush table-wrap" id="clist">${loading()}</div></div>`;
  const fb = filterBar("campaigns", ["region", "campaign_type", "channel", "status", "approval_status", "date_from", "date_to"], () => load());
  $("#fbar").innerHTML = fb.html; fb.bind($("#fbar"));
  let rows = [];
  function draw() {
    const q = ($("#csearch").value || "").toLowerCase();
    const r = rows.filter((c) => !q || [c.Campaign_ID, c.Campaign_Name, c.Product, c.Requester_Name].join(" ").toLowerCase().includes(q));
    $("#clist").innerHTML = r.length ? `<table class="table"><thead><tr><th>ID</th><th>Campaign</th><th>Region</th><th class="right">Proposed Budget</th><th class="right">Actual Spend</th><th class="right">Realized Revenue</th><th class="right">ROAS</th><th>Approval Status</th><th>Execution</th><th class="center">Actions</th></tr></thead><tbody>${r.map((c) => {
      const sp = c.Actual_Spend ? F.inr(c.Actual_Spend) : "—";
      const rev = c.Revenue ? `<b style="color:var(--good);">${F.inr(c.Revenue)}</b>` : "—";
      const roas = c.ROAS != null ? `<b class="${c.ROAS >= 1 ? "pos-text" : "neg-text"}">${F.x(c.ROAS)}</b>` : "—";
      const hasActuals = c.Actual_Spend != null || c.Revenue != null;
      const isEligible = ["Fully Approved", "Ready for Execution", "Executed"].includes(c.Approval_Status) || ["Ready for Execution", "Executed"].includes(c.Execution_Status) || hasActuals;
      const actBtn = isEligible
        ? `<button class="btn small outline" data-act-rev="${esc(c.Campaign_ID)}">${hasActuals ? "Edit Revenue" : "+ Record Revenue"}</button>`
        : `<button class="btn small outline muted" data-act-rev="${esc(c.Campaign_ID)}">+ Revenue</button>`;
      return `<tr class="click" data-id="${esc(c.Campaign_ID)}" tabindex="0"><td class="cid">${esc(c.Campaign_ID)}</td><td class="name">${esc(c.Campaign_Name || "(untitled draft)")}<div class="small muted" style="font-weight:400">${esc(c.Product || "")} · ${esc(c.Requester_Name)}</div></td><td>${esc(c.Region)}</td><td class="num right">${F.inr(c.Proposed_Budget)}</td><td class="num right">${sp}</td><td class="num right">${rev}</td><td class="num right">${roas}</td><td>${pill(c.Approval_Status)}</td><td>${pill(c.Execution_Status)}</td><td class="center">${actBtn}</td></tr>`;
    }).join("")}</tbody></table>` : emptyState("No campaigns match", "Try clearing a filter.");
    $$("tr.click", $("#clist")).forEach((tr) => { const go = () => (location.hash = `#/campaign/${tr.dataset.id}`); tr.onclick = go; tr.onkeydown = (e) => e.key === "Enter" && go(); });
    $$("[data-act-rev]", $("#clist")).forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const cid = btn.dataset.actRev;
        const targetCampaign = rows.find(x => x.Campaign_ID === cid);
        actualsModal(targetCampaign, null, () => load());
      };
    });
  }
  async function load() { rows = await GET("/api/campaigns", NOVA.filters.campaigns); draw(); }
  $("#csearch").oninput = draw;
  await load();
});

/* ================================================================ DECISION MODAL (shared) */
function decisionModal(kind, cid, name, done) {
  const cfg = { approve: ["Approve campaign", "good", "Approve", "Optional comment for the audit trail", false], reject: ["Reject campaign", "danger", "Reject campaign", "Reason for rejection (required)", true], revise: ["Send back for revision", "warn", "Send back", "What must the requester change? (required)", true] }[kind];
  openModal({
    title: `${cfg[0]} · ${cid}`,
    body: `<p style="margin-bottom:10px"><b>${esc(name)}</b></p><div class="field"><label for="dec-c">${cfg[3]}</label><textarea id="dec-c" rows="4"></textarea><div class="err" id="dec-err"></div></div>${kind === "approve" ? `<p class="small muted" style="margin-top:10px">Your decision is written to the approval log and audit trail and cannot be edited afterwards.</p>` : ""}`,
    footer: `<button class="btn" data-close>Cancel</button><button class="btn ${cfg[1]}" id="dec-go">${cfg[2]}</button>`,
    onMount: (m, close) => {
      $("#dec-go", m).onclick = async () => {
        const comments = $("#dec-c", m).value.trim();
        if (cfg[4] && !comments) { const f = $("#dec-c", m).closest(".field"); f.classList.add("invalid"); $("#dec-err", m).textContent = "Please enter a comment"; return; }
        const btn = $("#dec-go", m); btn.disabled = true;
        try {
          const r = await POST(`/api/campaigns/${cid}/${kind}`, { comments });
          close();
          if (kind === "approve") toast(r.final ? "Fully approved" : "Approved", r.final ? `${cid} passed the governance check and is ${r.campaign.Execution_Status}.` : `${cid} moved to ${r.next_approver}.`, "good");
          else toast(kind === "reject" ? "Campaign rejected" : "Sent back for revision", `${cid} - requester has been notified.`, "warn");
          refreshPending(); done && done(r);
        } catch (e) { btn.disabled = false; fail(e, "Decision not recorded"); }
      };
    },
  });
}

/* ================================================================ CAMPAIGN DETAIL */
route("campaign", async (page, cid) => {
  let d;
  try { d = await GET(`/api/campaigns/${encodeURIComponent(cid)}`); } catch (e) { page.innerHTML = `<div class="banner bad">${esc(e.error)}</div>`; return; }
  const c = d.campaign, g = d.governance, me = NOVA.me;
  const mine = c.Requester_ID === me.User_ID;
  const editable = mine && ["Draft", "Validation Failed", "Rejected", "Rework Required"].includes(c.Approval_Status);
  const myTurn = c.Approval_Status === "Pending Approval" && d.route.some((s) => s.state === "current" && s.role === me.Role && (me.Role !== "Regional Manager" || me.Region === c.Region)) && !mine;
  const acts = [`<button class="btn" id="a-chat">💬 Chat with Team</button>`];
  if (editable) acts.push(`<a class="btn primary" href="#/edit/${esc(c.Campaign_ID)}">Edit${c.Approval_Status === "Draft" || c.Approval_Status === "Validation Failed" ? " and submit" : " and resubmit"}</a>`);
  if (myTurn) acts.push(`<button class="btn good" data-act="approve">Approve</button><button class="btn warn" data-act="revise">Send back</button><button class="btn danger" data-act="reject">Reject</button>`);
  if (NOVA.perms.dispatch && c.Execution_Status === "Not Ready") acts.push(`<button class="btn" id="a-dispatch" title="Runs the governance check; blocked unless fully approved">Dispatch to execution team</button>`);
  if (NOVA.perms.execute && c.Execution_Status === "Ready for Execution") acts.push(`<button class="btn primary" id="a-exec">Mark as executed</button>`);
  if (c.Approval_Status === "Fully Approved" || c.Execution_Status === "Ready for Execution" || c.Execution_Status === "Executed") {
    acts.push(`<button class="btn outline" id="a-actuals">+ Record Revenue & ROAS</button>`);
  }
  const p = d.performance;
  const banners = [];
  if (d.validation_errors.length && c.Approval_Status === "Validation Failed") banners.push(`<div class="banner bad"><div><b>Validation failed - request returned to the requester.</b> Fix these fields and submit again:<ul>${d.validation_errors.map((e) => `<li>${esc(e.message)}</li>`).join("")}</ul></div></div>`);
  if (c.Approval_Status === "Rejected") banners.push(`<div class="banner bad"><div><b>Rejected.</b> Execution is blocked. Reason: ${esc(c.Rejection_Reason)}</div></div>`);
  if (c.Approval_Status === "Rework Required") banners.push(`<div class="banner warn"><div><b>Sent back for revision.</b> Execution is blocked until it is fixed and approved again. Reviewer comment: ${esc(c.Rejection_Reason)}</div></div>`);
  const cyc = d.approval_cycle_minutes;
  
  let perfHtml = "";
  if (p && (p.Revenue > 0 || p.Actual_Spend > 0)) {
    const isProfit = (p.ROAS || 0) >= 1.0;
    perfHtml = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
        <span class="pill ${isProfit ? "good" : "bad"}" style="font-size:13px; font-weight:700;">${isProfit ? "PROFITABLE / SUCCESS" : "LOW RETURN / LOSS"} (ROAS ${F.x(p.ROAS)})</span>
        <button class="btn small outline" id="a-actuals-inner">Edit Financial Results</button>
      </div>
      <div class="kv-strip" style="margin-bottom:14px">
        <div class="kv"><div class="l">Actual Spend</div><div class="v">${F.inr(p.Actual_Spend, true)}</div></div>
        <div class="kv"><div class="l">Realized Revenue</div><div class="v" style="color:var(--good);">${F.inr(p.Revenue, true)}</div></div>
        <div class="kv"><div class="l">Return on Ad Spend</div><div class="v">${F.x(p.ROAS)}</div></div>
      </div>
      <table class="table"><tbody>
        <tr><td>Actual Marketing Spend</td><td class="num right"><b>${F.inr(p.Actual_Spend)}</b></td></tr>
        <tr><td>Total Realized Revenue Earned</td><td class="num right"><b style="color:var(--good);">${F.inr(p.Revenue)}</b></td></tr>
        <tr><td>ROAS (revenue ÷ spend)</td><td class="num right"><b>${F.x(p.ROAS)}</b></td></tr>
        <tr><td>Net Profit / Return</td><td class="num right ${p.Revenue - p.Actual_Spend >= 0 ? "pos-text" : "neg-text"}"><b>${F.inr(p.Revenue - p.Actual_Spend)}</b></td></tr>
      </tbody></table>`;
  } else {
    perfHtml = `
      <div style="padding:24px; background:#f8fafc; border:1px dashed #cbd5e1; border-radius:8px; text-align:center;">
        <h4 style="margin:0 0 6px 0; color:var(--text); font-size:15px;">Enter Campaign Financial Results & ROAS</h4>
        <p class="small muted" style="margin-bottom:16px;">Record realized revenue earned upon campaign completion to calculate Return on Ad Spend (ROAS) and evaluate success.</p>
        <button class="btn primary" id="a-actuals-inner">+ Enter Realized Revenue & Spend</button>
      </div>`;
  }

  page.innerHTML = `<div style="margin-bottom:6px"><a href="#/campaigns" class="small">← All campaigns</a></div>
    ${setHead({ title: c.Campaign_Name || "(untitled draft)", sub: `<span class="cid">${esc(c.Campaign_ID)}</span> · ${esc(c.Region)} · requested by ${esc(c.Requester_Name)} on ${F.date(c.Submission_Date)}<div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">${pill(c.Approval_Status)} ${pill(c.Execution_Status)}${cyc != null ? `<span class="pill good">Approved in ${cyc < 1 ? "under 1 min" : F.mins(cyc)}</span>` : ""}</div>`, actions: acts.join("") })}
    <div class="grid" style="gap:16px">${banners.join("")}
    <div class="panel"><div class="ph"><h3>Approval route</h3><span class="note">${d.route.length ? `${c.Approval_Level} level${c.Approval_Level > 1 ? "s" : ""} required · revision ${c.Revision_No}` : ""}</span></div><div class="pb">${routeLine(d.route)}</div></div>
    <div class="panel"><div class="ph"><h3>Governance check</h3><span class="note">Execution is only possible when this reads FULLY COMPLIANT</span></div><div class="pb">${governanceCard(g)}</div></div>
    <div class="grid g2" style="align-items:start">
      <div class="panel"><div class="ph"><h3>Request details</h3></div><div class="pb"><dl class="deflist">
        <dt>Product</dt><dd>${esc(c.Product)}</dd><dt>Campaign type</dt><dd>${esc(c.Campaign_Type)}</dd><dt>Objective</dt><dd>${esc(c.Objective)}</dd>
        <dt>Target audience</dt><dd>${esc(c.Target_Audience)}</dd><dt>Channels</dt><dd>${esc(c.Marketing_Channel)}</dd>
        <dt>Dates</dt><dd>${F.date(c.Start_Date)} → ${F.date(c.End_Date)}</dd><dt>Proposed budget</dt><dd><b>${F.inr(c.Proposed_Budget)}</b></dd>
        <dt>Expected leads</dt><dd>${F.num(c.Expected_Leads)}</dd><dt>Expected conversions</dt><dd>${F.num(c.Expected_Conversions)}</dd><dt>Expected revenue</dt><dd>${F.inr(c.Expected_Revenue)}</dd>
        <dt>Description</dt><dd>${esc(c.Campaign_Description)}</dd><dt>Creative</dt><dd>${c.Creative_Link ? `<a href="${esc(c.Creative_Link)}" target="_blank" rel="noopener noreferrer">${esc(c.Creative_Link)}</a>` : "—"}</dd></dl></div></div>
      <div class="panel"><div class="ph"><h3>Campaign Financial Outcomes & ROAS</h3></div><div class="pb">${perfHtml}</div></div>
    </div>
    <div class="grid g2" style="align-items:start">
      <div class="panel"><div class="ph"><h3>Approval log</h3><span class="note">append-only</span></div><div class="pb flush table-wrap">${d.approval_log.length ? `<table class="table"><thead><tr><th>Level</th><th>Approver</th><th>Decision</th><th>When</th></tr></thead><tbody>${d.approval_log.map((a) => `<tr><td>${a.Approval_Level}</td><td>${esc(a.Approver_Name)}<div class="small muted">${esc(a.Approver_Role)} · rev ${a.Revision_No}</div>${a.Comments ? `<div class="small">“${esc(a.Comments)}”</div>` : ""}</td><td>${pill(a.Decision, a.Decision === "Approved" ? "good" : a.Decision === "Rejected" ? "bad" : "warn")}</td><td class="small num">${F.dt(a.Decision_Date)}</td></tr>`).join("")}</tbody></table>` : emptyState("No decisions yet")}</div></div>
      <div class="panel"><div class="ph"><h3>Audit trail</h3><span class="note">${d.audit.length} events</span></div><div class="pb"><ul class="timeline">${d.audit.map((a) => { const k = /Rejected|Blocked|Unauthorized|Out-of-sequence|Duplicate/.test(a.Action) ? "bad" : /Granted|Approved|Dispatched|Executed|Compliant/.test(a.Action) ? "good" : /Sent Back|Modified/.test(a.Action) ? "warn" : ""; return `<li class="${k}"><div class="tt">${esc(a.Action)}</div><div class="tm">${F.dt(a.Timestamp)} · ${esc(a.User)}${a.Previous_Status !== a.New_Status && a.New_Status ? ` · ${esc(a.Previous_Status || "—")} → ${esc(a.New_Status)}` : ""}</div>${a.Details ? `<div class="td">${esc(a.Details)}</div>` : ""}</li>`; }).join("")}</ul></div></div>
    </div></div>`;

  const reload = () => renderRoute();
  $$("[data-act]", page).forEach((b) => (b.onclick = () => decisionModal(b.dataset.act, c.Campaign_ID, c.Campaign_Name, reload)));
  const run = (sel, fn, okTitle, okMsg) => { const b = $(sel, page); if (b) b.onclick = async () => { b.disabled = true; try { const r = await fn(); toast(okTitle, okMsg ? okMsg(r) : "", "good"); reload(); } catch (e) { b.disabled = false; fail(e); reload.pending = 1; } }; };
  run("#a-dispatch", () => POST(`/api/campaigns/${c.Campaign_ID}/dispatch`), "Dispatched", () => "Execution team notified.");
  run("#a-exec", () => POST(`/api/campaigns/${c.Campaign_ID}/execute`), "Campaign executed", () => "Lead tracking is now open.");
  const ac = $("#a-chat", page); if (ac) ac.onclick = () => openChatModal(c.Campaign_ID);
  const aa = $("#a-actuals", page); if (aa) aa.onclick = () => actualsModal(c, p, reload);
  const aainner = $("#a-actuals-inner", page); if (aainner) aainner.onclick = () => actualsModal(c, p, reload);
});

/* shared modals used by detail + lead + performance views */
function actualsModal(c, p, done) {
  openModal({
    title: `Record Campaign Results · ${c.Campaign_ID}`,
    body: `<p class="small muted" style="margin-bottom:12px">Enter the final outcomes after campaign execution is complete. The system will automatically calculate Conversion Rate and ROAS.</p>
    <div class="form-grid">
      <div class="field s3"><label>Actual Spend (₹)</label><input type="number" id="act-sp" min="0" value="${p ? p.Actual_Spend : c.Proposed_Budget}"></div>
      <div class="field s3"><label>Total Realized Revenue (₹)</label><input type="number" id="act-rv" min="0" value="${p ? p.Revenue : c.Expected_Revenue}"></div>
      <div class="field s3"><label>Total Leads Generated</label><input type="number" id="act-ld" min="0" value="${p ? p.Leads : c.Expected_Leads}"></div>
      <div class="field s3"><label>Total Conversions</label><input type="number" id="act-cv" min="0" value="${p ? p.Conversions : c.Expected_Conversions}"></div>
    </div>
    <div id="act-err" class="banner bad hidden" style="margin-top:12px"></div>`,
    footer: `<button class="btn" data-close>Cancel</button><button class="btn primary" id="act-go">Save Campaign Results</button>`,
    onMount: (mm, close) => {
      $("#act-go", mm).onclick = async () => {
        try {
          const sp = $("#act-sp", mm).value;
          const rv = $("#act-rv", mm).value;
          const ld = $("#act-ld", mm).value;
          const cv = $("#act-cv", mm).value;
          await POST(`/api/campaigns/${c.Campaign_ID}/actuals`, { actual_spend: sp, actual_revenue: rv, leads: ld, conversions: cv });
          close(); toast("Results saved", "Actual campaign performance recorded.", "good"); done && done();
        } catch (e) { const b = $("#act-err", mm); b.textContent = e.error || String(e); b.classList.remove("hidden"); }
      };
    },
  });
}
function leadModal(c, done) {
  const m = NOVA.meta, sources = [...c.Marketing_Channel.split("+").map((x) => x.trim()), "Organic / Referral"];
  openModal({
    title: `Add lead · ${c.Campaign_ID}`,
    body: `<div class="form-grid"><div class="field s3"><label>Lead source</label><select id="l-src">${sources.map((s) => `<option>${esc(s)}</option>`).join("")}</select></div><div class="field s3"><label>Lead date</label><input type="date" id="l-date" value="${new Date().toISOString().slice(0, 10)}"></div>
    <div class="field s3"><label>Customer segment</label><select id="l-seg">${m.segments.map((s) => `<option>${esc(s)}</option>`).join("")}</select></div><div class="field s3"><label>Lead score (0-100)</label><input type="number" id="l-score" min="0" max="100" value="70"><div class="hint">Score ≥ 60 counts as a qualified lead</div></div>
    <div class="field s3"><label>Lead status</label><select id="l-st">${m.lead_statuses.map((s) => `<option>${esc(s)}</option>`).join("")}</select></div><div class="field s3"><label>Conversion status</label><select id="l-cs">${m.conversion_statuses.map((s) => `<option>${esc(s)}</option>`).join("")}</select></div>
    <div class="field s3"><label>Sales assigned</label><input type="text" id="l-sales" placeholder="e.g. Manish Gupta"></div><div class="field s3"><label>Revenue (₹, converted leads only)</label><input type="number" id="l-rev" min="0" value="0"></div></div><div id="l-err" class="banner bad hidden" style="margin-top:12px"></div>`,
    footer: `<button class="btn" data-close>Cancel</button><button class="btn primary" id="l-go">Save lead</button>`,
    onMount: (mm, close) => { $("#l-go", mm).onclick = async () => {
      try { const r = await POST(`/api/campaigns/${c.Campaign_ID}/leads`, { Lead_Source: $("#l-src", mm).value, Lead_Date: $("#l-date", mm).value, Customer_Segment: $("#l-seg", mm).value, Lead_Score: $("#l-score", mm).value, Lead_Status: $("#l-st", mm).value, Conversion_Status: $("#l-cs", mm).value, Sales_Assigned: $("#l-sales", mm).value, Revenue: $("#l-rev", mm).value }); close(); toast("Lead saved", `${r.lead_id} added; performance recalculated.`, "good"); done && done(); }
      catch (e) { const b = $("#l-err", mm); b.textContent = e.error; b.classList.remove("hidden"); } }; },
  });
}
function perfModal(c, p, done) {
  openModal({
    title: `Update ad-platform numbers · ${c.Campaign_ID}`,
    body: `<p class="small muted" style="margin-bottom:12px">Leads, qualified leads, conversions and revenue come from lead data automatically. CPL, conversion rate, ROAS and ROI are formulas.</p><div class="form-grid"><div class="field s2"><label>Actual spend (₹)</label><input type="number" id="p-sp" min="0" value="${p ? p.Actual_Spend : 0}"></div><div class="field s2"><label>Impressions</label><input type="number" id="p-im" min="0" value="${p ? p.Impressions : 0}"></div><div class="field s2"><label>Clicks</label><input type="number" id="p-cl" min="0" value="${p ? p.Clicks : 0}"></div></div><div id="p-err" class="banner bad hidden" style="margin-top:12px"></div>`,
    footer: `<button class="btn" data-close>Cancel</button><button class="btn primary" id="p-go">Save</button>`,
    onMount: (mm, close) => { $("#p-go", mm).onclick = async () => {
      try { const r = await POST(`/api/campaigns/${c.Campaign_ID}/performance`, { actual_spend: $("#p-sp", mm).value, impressions: $("#p-im", mm).value, clicks: $("#p-cl", mm).value }); close(); toast("Performance updated", (r.warnings || []).join(" · "), r.warnings && r.warnings.length ? "warn" : "good"); done && done(); }
      catch (e) { const b = $("#p-err", mm); b.textContent = e.error; b.classList.remove("hidden"); } }; },
  });
}
