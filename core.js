/* Core: API client, formatting, shared components, router, shell, login. */
const NOVA = (window.NOVA = { me: null, perms: {}, meta: null, charts: [], filters: {}, pending: 0, demoUsers: [] });

/* ---------------------------------------------------------------- helpers */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qs = (o) => Object.entries(o || {}).filter(([, v]) => v !== "" && v != null).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");

const F = {
  inr(n, compact = false) {
    if (n == null || isNaN(n)) return "—";
    n = Number(n);
    if (compact) {
      const a = Math.abs(n), s = n < 0 ? "-" : "";
      if (a >= 1e7) return `${s}₹${(a / 1e7).toFixed(2)} Cr`;
      if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(2)} L`;
    }
    return "₹" + Math.round(n).toLocaleString("en-IN");
  },
  inr2(n) { return n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); },
  num(n) { return n == null || isNaN(n) ? "—" : Math.round(Number(n)).toLocaleString("en-IN"); },
  pct(x, d = 1) { return x == null || isNaN(x) ? "—" : (x * 100).toFixed(d) + "%"; },
  x(n) { return n == null ? "—" : Number(n).toFixed(2) + "x"; },
  date(s) { if (!s) return "—"; const d = new Date(String(s).replace(" ", "T")); return isNaN(d) ? s : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }); },
  dt(s) { if (!s) return "—"; const d = new Date(String(s).replace(" ", "T")); return isNaN(d) ? s : d.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }); },
  mins(m) {
    if (m == null) return "—";
    m = Math.round(m);
    if (m < 60) return `${m} min`;
    if (m < 1440) return `${Math.floor(m / 60)}h ${m % 60}m`;
    return `${Math.floor(m / 1440)}d ${Math.floor((m % 1440) / 60)}h`;
  },
  month(m) { const [y, mo] = m.split("-"); return new Date(+y, +mo - 1, 1).toLocaleDateString("en-IN", { month: "short", year: "2-digit" }); },
};

const PILL = {
  "Fully Approved": "good", "Pending Approval": "warn", "Rejected": "bad", "Rework Required": "warn", "Draft": "neutral", "Validation Failed": "bad",
  "Not Ready": "neutral", "Ready for Execution": "info", "Executed": "good", "Approved": "good",
  "Approved ": "good", "Sent Back": "warn",
};
const pill = (label, kind) => `<span class="pill ${kind || PILL[label] || "neutral"}">${esc(label)}</span>`;
const GOVKIND = { compliant: "good", pending: "warn", blocked: "bad", violation: "bad" };

const ICON = {
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
  grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
  plus: '<circle cx="12" cy="12" r="8.5"/><path d="M12 8v8M8 12h8"/>',
  check: '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 12.3l2.5 2.5 4.6-5"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  users: '<circle cx="9" cy="9" r="3"/><path d="M3.5 19c.4-3 2.6-4.5 5.5-4.5s5.1 1.5 5.5 4.5"/><path d="M15.5 6.2a3 3 0 010 5.6M17 14.8c1.9.5 3 1.9 3.3 4.2"/>',
  chart: '<path d="M4 20V5M4 20h16"/><path d="M8 16v-4M12.5 16V8M17 16v-6"/>',
  shield: '<path d="M12 3.5l7 2.6v5.6c0 4-2.8 7.3-7 8.8-4.2-1.5-7-4.8-7-8.8V6.1z"/><path d="M8.8 12l2.4 2.4 4-4.4"/>',
  gauge: '<path d="M4.5 16a7.5 7.5 0 1115 0"/><path d="M12 16l3.5-5"/><circle cx="12" cy="16" r="1"/>',
  file: '<path d="M7 3.5h7l4 4V20.5H7z"/><path d="M14 3.5v4h4M9.5 12h6M9.5 15.5h6"/>',
  out: '<path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h9"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
};
const icon = (n) => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${ICON[n] || ""}</svg>`;

/* ---------------------------------------------------------------- toast / modal */
function toast(title, msg = "", kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<b>${esc(title)}</b>${msg ? `<div>${esc(msg)}</div>` : ""}`;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), kind === "bad" ? 9000 : 5200);
}
function openModal({ title, body, footer = "", wide = false, cls = "", onMount }) {
  const root = $("#modal-root");
  const back = document.createElement("div");
  back.className = "modal-back";
  back.innerHTML = `<div class="modal ${wide ? "wide" : ""} ${cls}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="mh"><h3>${esc(title)}</h3><button class="btn ghost small" data-close aria-label="Close">✕</button></div><div class="mb">${body}</div>${footer ? `<div class="mf">${footer}</div>` : ""}</div>`;
  root.appendChild(back);
  const close = () => back.remove();
  back.addEventListener("click", (e) => { if (e.target === back || e.target.closest("[data-close]")) close(); });
  const esc_ = (e) => { if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc_); } };
  document.addEventListener("keydown", esc_);
  onMount && onMount(back, close);
  return close;
}

/* ---------------------------------------------------------------- api */
async function api(method, url, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(url, opt); } catch (e) { throw { error: "Cannot reach the server. Is app.py still running?", status: 0 }; }
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-json */ }
  if (res.status === 401 && NOVA.me) { NOVA.me = null; boot(); throw { error: "Session expired - please sign in", status: 401 }; }
  if (!res.ok) throw { ...(data || { error: res.statusText }), status: res.status };
  return data;
}
const GET = (u, p) => api("GET", p ? `${u}?${qs(p)}` : u);
const POST = (u, b) => api("POST", u, b || {});
const PUT = (u, b) => api("PUT", u, b || {});
function fail(e, title = "Action blocked") { toast(title, e.error || String(e), "bad"); }

/* ---------------------------------------------------------------- charts */
function destroyCharts() { NOVA.charts.forEach((c) => c.destroy()); NOVA.charts = []; }
function chartDefaults() {
  if (!window.Chart || chartDefaults.done) return;
  chartDefaults.done = true;
  const C = Chart.defaults;
  C.font.family = "Inter, sans-serif";
  C.font.size = 12;
  C.color = "#64748b";
  C.borderColor = "#f1f5f9";
  C.maintainAspectRatio = false;
  C.animation = { duration: 350 };
  C.plugins.legend.display = false;
  C.plugins.tooltip.backgroundColor = "#0f172a";
  C.plugins.tooltip.padding = 10;
  C.plugins.tooltip.cornerRadius = 6;
  C.plugins.tooltip.titleFont = { weight: "600" };
}
function makeChart(canvas, config) {
  chartDefaults();
  const c = new Chart(canvas, config);
  NOVA.charts.push(c);
  return c;
}
const SERIES = ["#2563eb", "#ea580c", "#16a34a", "#d97706", "#ec4899"];

/* ---------------------------------------------------------------- shared components */
function routeLine(route, opts = {}) {
  if (!route || !route.length) return `<div class="muted small">No approval route yet - it is created when the request passes validation.</div>`;
  const stops = route.map((s) => {
    const mark = s.state === "done" ? "✓" : s.state === "stopped" ? "✕" : s.level;
    const sub = s.state === "done" ? `${esc(s.decided_by)}<div class="when">${F.dt(s.decided_at)}</div>`
      : s.state === "stopped" ? `${esc(s.decision)} by ${esc(s.decided_by)}<div class="when">${F.dt(s.decided_at)}</div>`
      : s.state === "current" ? `<b style="color:var(--warn)">Waiting: ${esc(s.assigned || "")}</b>` : esc(s.assigned || "");
    return `<div class="stop ${s.state}"><div class="dot">${mark}</div><div class="role">${esc(s.role)}</div><div class="who">${sub}</div></div>`;
  }).join("");
  const allDone = route.every((s) => s.state === "done");
  const end = `<div class="stop end terminus ${allDone ? "done" : ""}"><div class="dot">${allDone ? "✓" : "★"}</div><div class="role">${allDone ? "Fully approved" : "Governance gate"}</div><div class="who">${allDone ? "Released to execution" : "Execution locked"}</div></div>`;
  return `<div class="route">${stops}${end}</div>`;
}

function governanceCard(g, { compact = false } = {}) {
  if (!g) return "";
  const mk = { pass: "✓", pending: "", blocked: "✕", fail: "!" };
  const items = g.items.map((i) => `<li><span class="mk ${i.status}">${mk[i.status]}</span><div><div class="t">${esc(i.label)}</div><div class="d">${esc(i.detail)}</div></div></li>`).join("");
  return `<div class="gov"><div><ul class="checks">${items}</ul></div>
    <div><div class="stamp ${g.state}"><small>GOVERNANCE STATUS</small>${esc(g.label).replace(" - ", "<br>")}</div>
    <div class="small muted" style="margin-top:12px">Campaign <b class="cid">${esc(g.campaign_id)}</b><br>Approval: ${esc(g.approval_status)}<br>Execution: ${esc(g.execution_status)}</div></div></div>`;
}

function emptyState(title, text) { return `<div class="empty"><b>${esc(title)}</b>${esc(text || "")}</div>`; }
function loading() { return `<div class="loading"><span class="spin"></span> Loading…</div>`; }
function setHead({ title, sub = "", actions = "", cls = "" }) {
  return `<div class="page-head"><div class="grow"><h1 class="${cls}">${esc(title)}</h1>${sub ? `<div class="sub">${sub}</div>` : ""}</div>${actions ? `<div class="act-bar">${actions}</div>` : ""}</div>`;
}

/** Filter bar bound to NOVA.filters[key]; Power BI style deep bidirectional cross-filtering. */
function filterBar(key, fields, onChange) {
  const f = (NOVA.filters[key] = NOVA.filters[key] || {});
  const m = NOVA.meta;
  const opt = (arr, cur, all = "All") => `<option value="">${all}</option>` + arr.map((x) => { const v = typeof x === "string" ? x : x.v; const l = typeof x === "string" ? x : x.l; return `<option value="${esc(v)}" ${cur === v ? "selected" : ""}>${esc(l)}</option>`; }).join("");

  function getMatchingCampaigns(excludeKey) {
    if (!m || !m.campaigns) return [];
    return m.campaigns.filter((c) => {
      if (excludeKey !== "region" && f.region && c.Region !== f.region) return false;
      if (excludeKey !== "campaign" && f.campaign && c.Campaign_ID !== f.campaign) return false;
      if (excludeKey !== "campaign_type" && f.campaign_type && c.Campaign_Type !== f.campaign_type) return false;
      if (excludeKey !== "channel" && f.channel && !(c.Marketing_Channel || "").includes(f.channel)) return false;
      if (excludeKey !== "status" && f.status && c.Pipeline_Stage !== f.status) return false;
      if (excludeKey !== "approval_status" && f.approval_status && c.Approval_Status !== f.approval_status) return false;
      if (excludeKey !== "date_from" && f.date_from && c.Start_Date < f.date_from) return false;
      if (excludeKey !== "date_to" && f.date_to && c.Start_Date > f.date_to) return false;
      return true;
    });
  }

  const defs = {
    region: ["Region", () => `<select data-f="region">${opt(m.regions, f.region)}</select>`],
    campaign: ["Campaign", () => `<select data-f="campaign">${opt(m.campaigns.map((c) => ({ v: c.Campaign_ID, l: `${c.Campaign_ID} · ${c.Campaign_Name}`.slice(0, 48) })), f.campaign)}</select>`, "wide"],
    campaign_type: ["Campaign type", () => `<select data-f="campaign_type">${opt(m.campaign_types, f.campaign_type)}</select>`],
    channel: ["Marketing channel", () => `<select data-f="channel">${opt(m.channels, f.channel)}</select>`],
    status: ["Campaign status", () => `<select data-f="status">${opt(m.pipeline_stages, f.status)}</select>`],
    approval_status: ["Approval status", () => `<select data-f="approval_status">${opt(m.approval_statuses, f.approval_status)}</select>`],
    date_from: ["Starts from", () => `<input type="date" data-f="date_from" value="${esc(f.date_from || "")}">`],
    date_to: ["Starts until", () => `<input type="date" data-f="date_to" value="${esc(f.date_to || "")}">`],
  };

  const html = `<div class="filters" role="search" aria-label="Filters">${fields.map((k) => `<div class="field ${defs[k][2] || ""}"><label>${defs[k][0]}</label>${defs[k][1]()}</div>`).join("")}<button class="btn small" data-reset>Clear filters</button></div>`;

  function syncDropdowns(root, triggeredBy) {
    if (!m || !m.campaigns) return;

    if (triggeredBy === "campaign" && f.campaign) {
      const match = m.campaigns.find((c) => c.Campaign_ID === f.campaign);
      if (match) {
        if (match.Region) f.region = match.Region;
        if (match.Campaign_Type) f.campaign_type = match.Campaign_Type;
        if (match.Approval_Status) f.approval_status = match.Approval_Status;
        if (match.Pipeline_Stage) f.status = match.Pipeline_Stage;
      }
    }

    fields.forEach((k) => {
      const el = $(`[data-f="${k}"]`, root);
      if (!el || el.tagName !== "SELECT") return;

      if (k === "region") {
        el.innerHTML = opt(m.regions || [], f.region);
      } else if (k === "campaign") {
        const availCampaigns = getMatchingCampaigns(k);
        const list = (availCampaigns.length ? availCampaigns : (m.campaigns || [])).map((c) => ({
          v: c.Campaign_ID,
          l: `${c.Campaign_ID} · ${c.Campaign_Name}`.slice(0, 48)
        }));
        el.innerHTML = opt(list, f.campaign);
      } else if (k === "campaign_type") {
        el.innerHTML = opt(m.campaign_types || [], f.campaign_type);
      } else if (k === "channel") {
        el.innerHTML = opt(m.channels || [], f.channel);
      } else if (k === "approval_status") {
        el.innerHTML = opt(m.approval_statuses || [], f.approval_status);
      } else if (k === "status") {
        el.innerHTML = opt(m.pipeline_stages || [], f.status);
      }
    });
  }

  return {
    html,
    bind(root) {
      syncDropdowns(root, null);

      $$("[data-f]", root).forEach((el) => el.addEventListener("change", () => {
        const fieldName = el.dataset.f;
        f[fieldName] = el.value;
        syncDropdowns(root, fieldName);
        onChange(f);
      }));

      const rbtn = $("[data-reset]", root);
      if (rbtn) {
        rbtn.addEventListener("click", () => {
          Object.keys(f).forEach((k) => delete f[k]);
          $$("[data-f]", root).forEach((el) => (el.value = ""));
          syncDropdowns(root, "reset");
          onChange(f);
        });
      }
    },
  };
}

/* ---------------------------------------------------------------- router + shell */
const ROUTES = {};
function route(name, fn) { ROUTES[name] = fn; }
function navTo(h) { if (location.hash === h) renderRoute(); else location.hash = h; }

const NAV = [
  { id: "demo", label: "Executive Demo", icon: "spark", roles: "*" },
  { id: "dashboard", label: "Dashboard", icon: "grid", roles: "*" },
  { id: "campaigns", label: "Campaigns", icon: "list", roles: "*" },
  { id: "create", label: "Create Campaign", icon: "plus", roles: ["Regional Marketing Executive"] },
  { id: "approvals", label: "Pending Approvals", icon: "check", roles: ["Regional Manager", "Marketing Manager", "Marketing Head", "Business Head"], badge: true },
  { id: "history", label: "Approval History", icon: "clock", roles: "*" },
  { id: "governance", label: "Governance Gate", icon: "shield", roles: "*" },
  { id: "reports", label: "Reports", icon: "file", roles: "*" },
];
const TITLES = { demo: "Executive Demo", dashboard: "Dashboard", campaigns: "Campaigns", create: "Create Campaign", edit: "Edit Campaign", campaign: "Campaign", approvals: "Pending Approvals", history: "Approval History", governance: "Governance Gate", reports: "Reports" };

function initials(n) { return n.split(" ").map((x) => x[0]).slice(0, 2).join(""); }

function renderShell() {
  const u = NOVA.me;
  const nav = NAV.filter((n) => n.roles === "*" || n.roles.includes(u.Role)).map((n) =>
    `<a href="#/${n.id}" data-nav="${n.id}">${icon(n.icon)}<span>${n.label}</span>${n.badge ? `<span class="badge hidden" id="pend-badge">0</span>` : ""}</a>`).join("");
  const sw = NOVA.demoUsers.length ? `<div class="field" style="width:230px"><select id="switch-user" aria-label="Switch demo user"><option value="">Switch user (demo)…</option>${NOVA.demoUsers.map((d) => `<option value="${esc(d.Email)}">${esc(d.Name)} - ${esc(d.Role)}${d.Region !== "All" ? " (" + esc(d.Region) + ")" : ""}</option>`).join("")}</select></div>` : "";
  $("#root").innerHTML = `<div class="app"><aside class="sidebar"><div class="brand"><div class="mark"><svg width="28" height="28" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#2563eb"/><path d="M8 21l5-10 4 7 3-5 4 8" fill="none" stroke="#ffffff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg><div class="name">MARKETING<br>OPERATIONS</div></div><div class="co">Nova Consumer Brands Pvt. Ltd.</div></div><nav class="nav" aria-label="Main">${nav}</nav><div class="side-foot">Nova Marketing Governance v2.4<br>Enterprise Operations Console</div></aside>
  <div class="main"><header class="topbar"><div class="crumb" id="crumb"></div><div class="spacer"></div>${sw}<div class="userchip"><div class="avatar">${esc(initials(u.Name))}</div><div class="who"><b>${esc(u.Name)}</b><span>${esc(u.Role)}${u.Region !== "All" ? " · " + esc(u.Region) : ""}</span></div><button class="btn small" id="signout">Sign out</button></div></header><main class="page" id="page"></main></div><button class="chat-float-btn" id="open-chat-btn" title="Open Team Chat">${icon("chat")} <span>Team Chat</span><span class="badge hidden" id="chat-badge" style="background:#e53935;color:#fff;border-radius:10px;padding:2px 6px;font-size:11px;margin-left:4px;">0</span></button></div>`;
  $("#signout").onclick = async () => { await POST("/api/logout"); NOVA.me = null; boot(); };
  const btnChat = $("#open-chat-btn");
  if (btnChat) btnChat.onclick = () => openChatModal();
  const sel = $("#switch-user");
  if (sel) sel.onchange = async () => {
    if (!sel.value) return;
    try { const r = await POST("/api/demo/switch", { email: sel.value }); applyMe(r); renderShell(); const ok = canSee(currentRouteName()); if (!ok) location.hash = "#/dashboard"; renderRoute(); toast(`Now signed in as ${r.user.Name}`, r.user.Role, "good"); }
    catch (e) { fail(e); }
  };
  checkUnreadChat();
}

let lastUnreadMsgId = 0;
async function checkUnreadChat() {
  if (!NOVA.me) return;
  try {
    const res = await GET("/api/messages/unread");
    const b = $("#chat-badge");
    if (b) {
      if (res.count > 0) {
        b.textContent = res.count;
        b.classList.remove("hidden");
      } else {
        b.classList.add("hidden");
      }
    }
    if (res.latest && res.latest.Message_ID > lastUnreadMsgId) {
      if (lastUnreadMsgId > 0) {
        toast(`💬 New Message from ${res.latest.Sender_Name}`, res.latest.Content, "good");
      }
      lastUnreadMsgId = res.latest.Message_ID;
    }
  } catch (e) {
    /* ignore */
  }
}
setInterval(checkUnreadChat, 4000);

function openChatModal(campaignId = null, recipientName = null) {
  let activeCid = campaignId || "";
  let activeRecipient = recipientName || "Governance Assistant";

  openModal({
    title: "Regional Communication Chat",
    wide: true,
    cls: "chat-modal-view",
    body: `
      <div class="chat-container">
        <div class="chat-sidebar">
          <div class="chat-sidebar-header">
            <b>Select Contact / Bot</b>
          </div>
          <div class="chat-contact-list" id="chat-contacts">
            <div class="chat-loading"><span class="spin"></span> Loading contacts...</div>
          </div>
        </div>
        <div class="chat-main">
          <div class="chat-header">
            <div class="chat-recipient-name" id="chat-header-title">Chat with ${esc(activeRecipient)}</div>
            ${activeCid ? `<div class="chat-campaign-tag"><span class="pill info">${esc(activeCid)}</span></div>` : ""}
          </div>
          <div class="chat-messages" id="chat-msg-list">
            <div class="chat-loading"><span class="spin"></span> Loading messages...</div>
          </div>
          <div class="chat-input-bar">
            <input type="text" id="chat-input" placeholder="Type a message to ${esc(activeRecipient)}..." autocomplete="off">
            <button class="btn primary" id="chat-send">Send</button>
          </div>
        </div>
      </div>
    `,
    footer: `<button class="btn" data-close>Close</button>`,
    onMount: (modalEl, close) => {
      const msgList = $("#chat-msg-list", modalEl);
      const input = $("#chat-input", modalEl);
      const sendBtn = $("#chat-send", modalEl);
      const titleEl = $("#chat-header-title", modalEl);

      let currentRecipient = activeRecipient;
      let currentRecipientId = null;
      let pollTimer = null;

      async function renderContacts() {
        let convs = [];
        try {
          convs = await GET("/api/messages/conversations");
        } catch (e) {
          /* fallback */
        }
        const convMap = {};
        convs.forEach(c => convMap[c.contact_name] = c);

        const allContacts = [
          { Name: "Governance Assistant", Role: "AI Assistant", Region: "All", isBot: true },
          ...(NOVA.demoUsers || []).filter(u => u.Email !== NOVA.me.Email)
        ];

        allContacts.sort((a, b) => {
          const ca = convMap[a.Name] || { unread_count: 0, last_timestamp: "" };
          const cb = convMap[b.Name] || { unread_count: 0, last_timestamp: "" };
          if (ca.unread_count !== cb.unread_count) return cb.unread_count - ca.unread_count;
          if (ca.last_timestamp !== cb.last_timestamp) return (cb.last_timestamp || "").localeCompare(ca.last_timestamp || "");
          return a.Name.localeCompare(b.Name);
        });

        const contactsContainer = $("#chat-contacts", modalEl);
        if (contactsContainer) {
          contactsContainer.innerHTML = allContacts.map(u => {
            const info = convMap[u.Name];
            const unread = info ? info.unread_count : 0;
            const lastMsg = info ? info.last_message : "";
            const isActive = currentRecipient === u.Name;
            return `
              <div class="chat-contact ${isActive ? "active" : ""}" data-name="${esc(u.Name)}" data-id="${u.User_ID || ""}" data-role="${esc(u.Role)}">
                <div class="chat-avatar ${u.isBot ? "bot" : ""}">${u.isBot ? "🤖" : esc(initials(u.Name))}</div>
                <div class="chat-contact-info" style="flex:1; min-width:0;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <b style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${esc(u.Name)}</b>
                    ${unread > 0 ? `<span class="unread-pill" style="background:#e53935; color:#fff; border-radius:10px; padding:2px 6px; font-size:10px; font-weight:700;">${unread}</span>` : ""}
                  </div>
                  <span class="small muted" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block;">
                    ${lastMsg ? esc(lastMsg) : `${esc(u.Role)} ${u.Region && u.Region !== "All" ? "· " + esc(u.Region) : ""}`}
                  </span>
                </div>
              </div>
            `;
          }).join("");

          $$("#chat-contacts .chat-contact", modalEl).forEach(item => {
            item.onclick = () => {
              $$("#chat-contacts .chat-contact", modalEl).forEach(c => c.classList.remove("active"));
              item.classList.add("active");
              currentRecipient = item.dataset.name;
              currentRecipientId = item.dataset.id || null;
              titleEl.textContent = `Chat with ${currentRecipient}`;
              input.placeholder = `Type a message to ${currentRecipient}...`;
              loadChat();
            };
          });
        }
      }

      async function loadChat() {
        try {
          const params = { contact: currentRecipient };
          if (activeCid) params.campaign_id = activeCid;
          const msgs = await GET("/api/messages", params);
          renderMessages(msgs);
          await POST("/api/messages/read", { contact: currentRecipient });
          const b = $("#chat-badge");
          if (b) b.classList.add("hidden");
          renderContacts();
        } catch (e) {
          msgList.innerHTML = `<div class="banner bad">Could not load chat messages</div>`;
        }
      }

      function renderMessages(msgs) {
        if (!msgs || !msgs.length) {
          msgList.innerHTML = `<div class="empty-chat">No messages yet. Send a message to start the conversation!</div>`;
          return;
        }
        msgList.innerHTML = msgs.map(m => {
          const isMine = m.Sender_ID === NOVA.me.User_ID || m.Sender_Name === NOVA.me.Name;
          return `
            <div class="chat-bubble-wrap ${isMine ? "mine" : "theirs"}">
              <div class="chat-bubble-sender">${esc(m.Sender_Name)} (${esc(m.Sender_Role)})</div>
              <div class="chat-bubble">${esc(m.Content)}</div>
              <div class="chat-bubble-time">${F.dt(m.Timestamp)}</div>
            </div>
          `;
        }).join("");
        msgList.scrollTop = msgList.scrollHeight;
      }

      async function send() {
        const txt = input.value.trim();
        if (!txt) return;
        input.value = "";
        sendBtn.disabled = true;
        try {
          await POST("/api/messages", {
            content: txt,
            campaign_id: activeCid || null,
            recipient_id: currentRecipientId,
            recipient_name: currentRecipient
          });
          await loadChat();
        } catch (e) {
          fail(e, "Message failed");
        } finally {
          sendBtn.disabled = false;
          input.focus();
        }
      }

      $$("#chat-contacts .chat-contact", modalEl).forEach(item => {
        item.onclick = () => {
          $$("#chat-contacts .chat-contact", modalEl).forEach(c => c.classList.remove("active"));
          item.classList.add("active");
          currentRecipient = item.dataset.name;
          currentRecipientId = item.dataset.id || null;
          titleEl.textContent = `Chat with ${currentRecipient}`;
          input.placeholder = `Type a message to ${currentRecipient}...`;
          loadChat();
        };
      });

      sendBtn.onclick = send;
      input.onkeydown = (e) => { if (e.key === "Enter") send(); };

      loadChat();
      pollTimer = setInterval(loadChat, 3000);

      // Clean up poll timer when modal is closed
      const observer = new MutationObserver(() => {
        if (!document.body.contains(modalEl)) {
          clearInterval(pollTimer);
          observer.disconnect();
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }
  });
}
function canSee(name) { const n = NAV.find((x) => x.id === name); if (!n) return true; return n.roles === "*" || n.roles.includes(NOVA.me.Role); }
function currentRouteName() { return (location.hash.replace(/^#\//, "").split("/")[0]) || "dashboard"; }

async function refreshPending() {
  if (!NOVA.me || !NAV.find((n) => n.id === "approvals").roles.includes(NOVA.me.Role)) return;
  try { const p = await GET("/api/approvals/pending"); NOVA.pending = p.length; const b = $("#pend-badge"); if (b) { b.textContent = p.length; b.classList.toggle("hidden", !p.length); } } catch (e) { /* ignore */ }
}

async function renderRoute() {
  if (!NOVA.me) return;
  destroyCharts();
  const parts = location.hash.replace(/^#\//, "").split("/");
  let name = parts[0] || "dashboard";
  if (!ROUTES[name]) name = "dashboard";
  if (!canSee(name)) name = "dashboard";
  $$("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === (name === "campaign" || name === "edit" ? "campaigns" : name)));
  $("#crumb").textContent = TITLES[name] || "";
  const page = $("#page");
  page.innerHTML = loading();
  window.scrollTo(0, 0);
  try { await ROUTES[name](page, decodeURIComponent(parts.slice(1).join("/"))); }
  catch (e) { page.innerHTML = `<div class="banner bad"><div><b>Could not load this page.</b><br>${esc(e.error || e.message || e)}</div></div>`; console.error(e); }
  refreshPending();
}

function applyMe(r) { NOVA.me = r.user; NOVA.perms = r.permissions; NOVA.experience = r.experience; }

async function loadMeta() { NOVA.meta = await GET("/api/meta"); }

/* ---------------------------------------------------------------- login */
function renderLogin() {
  const groups = {};
  NOVA.demoUsers.forEach((u) => (groups[u.Role] = groups[u.Role] || []).push(u));
  const order = ["Regional Marketing Executive", "Regional Manager", "Marketing Manager", "Marketing Head", "Business Head", "Execution Team"];
  const quick = NOVA.demoUsers.length ? `<div style="margin-top:20px; border-top:1px solid #e2e8f0; padding-top:16px"><div class="small muted" style="margin-bottom:10px; font-weight:600; text-transform:uppercase; letter-spacing:0.04em">Quick Demo Sign-in</div><div class="demo-users">${order.flatMap((r) => (groups[r] || []).filter((u) => r !== "Regional Marketing Executive" && r !== "Regional Manager" ? true : u.Region === "Delhi NCR")).map((u) => `<button data-email="${esc(u.Email)}"><b>${esc(u.Name)}</b><span>${esc(u.Role)}${u.Region !== "All" ? " · " + esc(u.Region) : ""}</span></button>`).join("")}</div></div>` : "";
  $("#root").innerHTML = `<div class="login"><div class="l" style="background:#f8fafc; border-right:1px solid #e2e8f0; padding:56px;"><div><svg width="36" height="36" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#2563eb"/><path d="M8 21l5-10 4 7 3-5 4 8" fill="none" stroke="#ffffff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></div><div style="margin-top:40px"><h1 style="font-size:30px; font-weight:700; color:#0f172a; letter-spacing:-0.02em; line-height:1.2;">Nova Marketing Governance</h1><p style="color:#475569; font-size:14.5px; margin-top:14px; line-height:1.6; max-width:44ch;">Automated campaign validation, budget-driven approval workflows, governance gate enforcement, and campaign performance analytics.</p><div class="flow" style="margin-top:32px"><span>Request</span><span>Validation</span><span>Approval</span><span>Governance</span><span>Dispatch</span><span>Leads</span><span>Dashboard</span></div></div><div class="small" style="color:#64748b; margin-top:40px">Nova Consumer Brands Pvt. Ltd. · Enterprise Portal</div></div>
  <div class="r" style="padding:48px 56px;"><h2 style="font-size:22px; font-weight:700; color:#0f172a">Sign in</h2><p class="small muted" style="margin-bottom:20px">Enter your work credentials to access your dashboard.</p><form id="login-form" novalidate><div class="field"><label for="em">Work E-mail</label><input id="em" type="email" autocomplete="username" placeholder="aman.sharma@novabrands.in"></div><div class="field"><label for="pw">Password</label><input id="pw" type="password" autocomplete="current-password" placeholder="••••••••"></div><div id="login-err" class="banner bad hidden"></div><button class="btn primary" type="submit" style="justify-content:center;padding:10px;font-weight:600">Sign in</button></form>${quick}</div></div>`;
  const doLogin = async (email, pw) => {
    try { const r = await POST("/api/login", { email, password: pw }); await afterLogin(r); }
    catch (e) { const b = $("#login-err"); b.textContent = e.error || "Sign-in failed"; b.classList.remove("hidden"); }
  };
  $("#login-form").onsubmit = (ev) => { ev.preventDefault(); doLogin($("#em").value.trim(), $("#pw").value); };
  $$(".demo-users button").forEach((b) => (b.onclick = async () => { try { const r = await POST("/api/demo/switch", { email: b.dataset.email }); await afterLogin(r); } catch (e) { fail(e); } }));
}
async function afterLogin(r) {
  applyMe(r);
  await loadMeta();
  renderShell();
  if (!location.hash || location.hash === "#/") location.hash = "#/demo";
  renderRoute();
}

async function boot() {
  try { NOVA.demoUsers = await GET("/api/demo/users"); } catch (e) { NOVA.demoUsers = []; }
  const me = await GET("/api/me");
  if (me.user) { applyMe(me); await loadMeta(); renderShell(); if (!location.hash || location.hash === "#/") location.hash = "#/demo"; renderRoute(); }
  else renderLogin();
}
window.addEventListener("hashchange", () => { if (NOVA.me) renderRoute(); });

// Clicking a link to the page you are already on should refresh it (e.g. "Create another" after a submit).
document.addEventListener("click", (e) => {
  const a = e.target.closest && e.target.closest('a[href^="#/"]');
  if (a && NOVA.me && a.getAttribute("href") === location.hash) { e.preventDefault(); renderRoute(); }
});
