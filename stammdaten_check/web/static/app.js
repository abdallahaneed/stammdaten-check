// Stammdaten-Check dashboard. Plain JS, no framework, no build step.
// Every value from the data goes through textContent, never innerHTML.
"use strict";

const ICON = {
  upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/></svg>',
  download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
  flask: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 3h6"/><path d="M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3"/></svg>',
};

const STATUSES = [
  ["open", "Open"], ["accepted", "Accepted"], ["fixed", "Fixed"], ["false_positive", "False positive"],
];
const STATUS_LABEL = Object.fromEntries(STATUSES);
const SEVERITIES = ["blocker", "error", "warning", "info"];
const OBJECTS = ["customer", "vendor", "material", "contact"];
const PAGE = 50;

let RULES = {};          // id -> {title, description, paths}
let current = null;      // run summary on screen

// ---------- small helpers ----------

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;            // only used for our own icons
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function icon(name) {
  return h("span", { html: ICON[name], style: "display:inline-flex" });
}

function pref(key, value) {
  try {
    if (value === undefined) return localStorage.getItem("sdc." + key) || "";
    localStorage.setItem("sdc." + key, value);
  } catch (_) { return ""; }
}

function toast(text, isError = false) {
  const t = document.getElementById("toast");
  t.textContent = text;
  t.className = "toast" + (isError ? " err" : "");
  t.setAttribute("role", isError ? "alert" : "status");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), isError ? 6000 : 2500);
}

async function api(method, path, body, form = false) {
  const headers = { "X-User": pref("who") || "unknown" };
  const key = pref("apikey");
  if (key) headers["X-API-Key"] = key;
  const opts = { method, headers };
  if (body !== undefined) {
    if (form) opts.body = body;
    else { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  }
  const res = await fetch("/api/v1" + path, opts);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data?.error?.message
      || (Array.isArray(data?.detail) ? data.detail.map(d => d.msg).join(", ") : "")
      || `request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function sevBadge(s) { return h("span", { class: `badge sev-${s}` }, s); }
function statusDot(s) { return h("span", { class: `st st-${s}` }, STATUS_LABEL[s] || s); }
function fmtDate(iso) {
  try { return new Date(iso).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" }); }
  catch (_) { return iso; }
}
function busy(btn, on, label) {
  btn.disabled = on;
  if (on) { btn.dataset.label = btn.textContent; btn.replaceChildren(h("span", { class: "spinner" }), label || "Working"); }
  else if (btn.dataset.label) { btn.textContent = btn.dataset.label; }
}

// ---------- router ----------

const view = document.getElementById("view");

async function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  view.replaceChildren(h("div", { class: "empty" }, h("span", { class: "spinner" })));
  try {
    if (parts[0] === "runs" && parts[1]) await runPage(Number(parts[1]), parts[2] || "overview");
    else await runsPage();
  } catch (e) {
    view.replaceChildren(h("div", { class: "card empty", role: "alert" }, e.message, " ",
      h("a", { href: "#/" }, "Back to runs")));
  }
  window.scrollTo(0, 0);
}

// ---------- runs page ----------

async function runsPage() {
  const runs = await api("GET", "/runs");
  const table = runs.length
    ? h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["Run", "Label", "Path", "Source", "Created", "Findings", "Open"]
          .map((t, i) => h("th", { class: i >= 5 ? "num" : null, scope: "col" }, t)))),
        h("tbody", {}, runs.map(r => h("tr", {
            class: "clickable", tabindex: "0",
            onclick: () => (location.hash = `#/runs/${r.id}`),
            onkeydown: e => e.key === "Enter" && (location.hash = `#/runs/${r.id}`),
          },
          h("td", { class: "mono" }, `#${r.id}`), h("td", {}, r.label), h("td", {}, r.path),
          h("td", { class: "muted" }, r.source), h("td", { class: "muted" }, fmtDate(r.createdAt)),
          h("td", { class: "num" }, r.findings), h("td", { class: "num" }, r.open ?? 0))))))
    : h("div", { class: "empty" }, "No runs yet. Upload extracts or start with sample data.");

  view.replaceChildren(
    h("div", { class: "page-h" },
      h("div", {}, h("h1", {}, "Runs"),
        h("p", { class: "muted", style: "margin:4px 0 0" },
          "Each run checks one set of SAP table extracts. Findings stay here until the departments have worked through them.")),
    ),
    h("div", { class: "grid runs-layout" },
      h("section", { class: "card", "aria-label": "Runs" }, table),
      newRunCard()),
  );
}

function newRunCard() {
  const file = h("input", { type: "file", accept: ".zip", class: "sr-only", id: "zip" });
  const fileName = h("span", { class: "mono" }, "");
  const drop = h("label", { class: "dropzone", for: "zip" },
    icon("upload"), h("strong", {}, "Choose a zip with CSV extracts"),
    h("span", {}, "kna1.csv, lfa1.csv, lfbk.csv, tiban.csv ..."), fileName);
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, () => drop.classList.remove("over")));
  drop.addEventListener("drop", e => { e.preventDefault(); file.files = e.dataTransfer.files; fileName.textContent = file.files[0]?.name || ""; });
  file.addEventListener("change", () => (fileName.textContent = file.files[0]?.name || ""));

  const path = h("select", { id: "path" },
    h("option", { value: "both" }, "Both"),
    h("option", { value: "brownfield" }, "Brownfield (system conversion)"),
    h("option", { value: "greenfield" }, "Greenfield (new implementation)"));
  const label = h("input", { id: "label", maxlength: "80", placeholder: "e.g. Export 27.10." });
  const seed = h("input", { id: "seed", type: "number", value: "42", style: "width:90px" });

  async function start(sample, btn) {
    const fd = new FormData();
    fd.append("path", path.value);
    fd.append("label", label.value);
    if (sample) { fd.append("sample", "true"); fd.append("seed", seed.value || "42"); }
    else {
      if (!file.files[0]) return toast("Choose a zip file first", true);
      fd.append("file", file.files[0]);
    }
    busy(btn, true, "Checking");
    try {
      const run = await api("POST", "/runs", fd, true);
      location.hash = `#/runs/${run.id}`;
    } catch (e) { toast(e.message, true); busy(btn, false); }
  }

  const go = h("button", { class: "btn primary", onclick: e => start(false, e.currentTarget) }, "Check extracts");
  const sampleBtn = h("button", { class: "btn", onclick: e => start(true, e.currentTarget) }, icon("flask"), "Generate sample run");

  return h("section", { class: "card", "aria-labelledby": "nr" },
    h("div", { class: "card-h" }, h("h2", { id: "nr" }, "New run")),
    h("div", { class: "card-b grid", style: "gap:12px" },
      file, drop,
      h("label", { class: "field", for: "path" }, "Migration path", path),
      h("label", { class: "field", for: "label" }, "Label", label),
      go,
      h("div", { class: "divider" }, "or try it"),
      h("div", { class: "row", style: "align-items:flex-end" }, h("label", { class: "field", for: "seed" }, "Seed", seed), sampleBtn),
      h("p", { class: "muted", style: "margin:0;font-size:12px" },
        "Sample runs use invented data with planted errors. Nothing real.")));
}

// ---------- run page ----------

async function runPage(id, tab) {
  if (!Object.keys(RULES).length) {
    (await api("GET", "/rules")).forEach(r => (RULES[r.id] = r));
  }
  current = await api("GET", `/runs/${id}`);
  const r = current;

  const tabs = [["overview", "Overview"], ["worklist", "Worklist"], ["duplicates", "Duplicates"]];
  const body = h("div", {});

  view.replaceChildren(
    h("div", { class: "page-h" },
      h("div", {},
        h("a", { href: "#/", class: "btn ghost", style: "padding-left:0" }, icon("back"), "All runs"),
        h("h1", {}, r.label),
        h("p", { class: "muted", style: "margin:4px 0 0" },
          `Run #${r.id}, ${r.path}, ${r.source}, ${fmtDate(r.createdAt)}`)),
      h("span", { class: "spacer" }),
      h("a", { class: "btn", href: `/api/v1/runs/${r.id}/report` }, icon("download"), "Excel worklist"),
      h("button", { class: "btn", "aria-label": "Delete run", onclick: () => deleteRun(r.id) }, icon("trash"))),
    kpis(r),
    h("div", { class: "tabs", role: "tablist" }, tabs.map(([k, t]) =>
      h("button", { class: "tab", role: "tab", "aria-selected": String(k === tab),
                    onclick: () => (location.hash = `#/runs/${r.id}/${k}`) }, t))),
    body,
  );

  if (tab === "worklist") await worklist(body, r.id);
  else if (tab === "duplicates") await duplicates(body, r.id);
  else overview(body, r);
}

function kpis(r) {
  const sev = r.bySeverity || {};
  return h("div", { class: "grid kpis", id: "kpis" },
    [...r.readiness].sort((a, b) => OBJECTS.indexOf(a.object) - OBJECTS.indexOf(b.object)).map(o => {
      const delta = Math.round((o.readinessNow - o.readinessThen) * 10) / 10;
      return h("div", { class: "card kpi" },
        h("div", { class: "label" }, `${o.object} readiness`),
        h("div", { class: "value" }, `${o.readinessNow.toFixed(1)} %`),
        h("div", { class: "delta muted" + (delta > 0 ? " up" : "") },
          delta > 0 ? `+${delta} since run (${o.readinessThen.toFixed(1)} %)` : `as found ${o.readinessThen.toFixed(1)} %`),
        h("div", { class: "muted", style: "font-size:12px" }, `${o.recordsOpen} of ${o.total} records with open findings`),
        h("div", { class: "meter", role: "img", "aria-label": `${o.readinessNow} percent` },
          h("span", { style: `width:${Math.max(0, o.readinessNow)}%` })));
    }),
    h("div", { class: "card kpi" },
      h("div", { class: "label" }, "Findings by severity"),
      h("div", { class: "grid", style: "grid-template-columns:repeat(2,1fr);gap:6px;margin-top:8px" },
        SEVERITIES.map(s => h("div", { class: "row", style: "gap:6px" }, sevBadge(s),
          h("span", { class: "num" }, sev[s] || 0))))));
}

async function refreshKpis(id) {
  current = await api("GET", `/runs/${id}`);
  document.getElementById("kpis")?.replaceWith(kpis(current));
}

async function deleteRun(id) {
  if (!confirm("Delete this run with all findings and history?")) return;
  try { await api("DELETE", `/runs/${id}`); toast("Run deleted"); location.hash = "#/"; }
  catch (e) { toast(e.message, true); }
}

// ---------- overview tab ----------

function overview(body, r) {
  const colors = { open: "var(--st-open)", accepted: "var(--st-accepted)", fixed: "var(--st-fixed)", falsePositive: "var(--st-fp)" };
  const legend = h("div", { class: "legend" },
    [["open", "Open"], ["accepted", "Accepted"], ["fixed", "Fixed"], ["falsePositive", "False positive"]]
      .map(([k, t]) => h("span", {}, h("i", { style: `background:${colors[k]}` }), t)));

  const rows = r.progress.map(p => {
    const rule = RULES[p.rule] || { title: "" };
    const bar = h("div", { class: "stack", role: "img",
      "aria-label": `${p.open} open, ${p.accepted} accepted, ${p.fixed} fixed, ${p.falsePositive} false positive` },
      ["open", "accepted", "fixed", "falsePositive"].map(k =>
        h("span", { style: `width:${(100 * p[k]) / p.total}%;background:${colors[k]}`, title: `${k}: ${p[k]}` })));
    return h("tr", { class: "clickable", tabindex: "0", title: rule.description,
        onclick: () => openWorklist(r.id, { rule: p.rule }),
        onkeydown: e => e.key === "Enter" && openWorklist(r.id, { rule: p.rule }) },
      h("td", { class: "mono" }, p.rule), h("td", {}, rule.title),
      h("td", { class: "muted" }, (rule.paths || []).join(", ")),
      h("td", { class: "num" }, p.total), h("td", {}, bar), h("td", { class: "num" }, `${p.donePct} %`));
  });

  body.replaceChildren(h("section", { class: "card" },
    h("div", { class: "card-h" }, h("h2", {}, "Clearing progress per rule"), h("span", { class: "spacer", style: "flex:1" }), legend),
    h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Rule", "Check", "Path", "Findings", "Status", "Done"]
        .map((t, i) => h("th", { scope: "col", class: [3, 5].includes(i) ? "num" : null }, t)))),
      h("tbody", {}, rows)))));
}

function openWorklist(id, filters) {
  sessionFilters = { ...filters };
  location.hash = `#/runs/${id}/worklist`;
}

// ---------- worklist tab ----------

let sessionFilters = {};

async function worklist(body, runId) {
  const f = { rule: "", severity: "", object: "", status: "", q: "", offset: 0, ...sessionFilters };
  sessionFilters = {};
  const selected = new Set();

  const ruleSel = h("select", { id: "f-rule" }, h("option", { value: "" }, "All rules"),
    Object.values(RULES).map(r => h("option", { value: r.id }, `${r.id} ${r.title}`)));
  const sevSel = h("select", { id: "f-sev" }, h("option", { value: "" }, "All"), SEVERITIES.map(s => h("option", { value: s }, s)));
  const objSel = h("select", { id: "f-obj" }, h("option", { value: "" }, "All"), OBJECTS.map(s => h("option", { value: s }, s)));
  const stSel = h("select", { id: "f-st" }, h("option", { value: "" }, "All"), STATUSES.map(([v, t]) => h("option", { value: v }, t)));
  const q = h("input", { id: "f-q", type: "search", placeholder: "Number, text ..." });
  ruleSel.value = f.rule; sevSel.value = f.severity; objSel.value = f.object; stSel.value = f.status; q.value = f.q;

  const tbody = h("tbody");
  const pager = h("div", { class: "pager" });
  const all = h("input", { type: "checkbox", "aria-label": "Select all on this page" });
  const bulk = bulkBar(runId, selected, () => load());

  for (const [el, key] of [[ruleSel, "rule"], [sevSel, "severity"], [objSel, "object"], [stSel, "status"]]) {
    el.addEventListener("change", () => { f[key] = el.value; f.offset = 0; load(); });
  }
  let t;
  q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { f.q = q.value.trim(); f.offset = 0; load(); }, 250); });
  all.addEventListener("change", () => {
    tbody.querySelectorAll("input[type=checkbox]").forEach(cb => { cb.checked = all.checked; cb.dispatchEvent(new Event("change")); });
  });

  async function load() {
    const params = new URLSearchParams({ limit: PAGE, offset: f.offset });
    for (const k of ["rule", "severity", "object", "status", "q"]) if (f[k]) params.set(k, f[k]);
    tbody.replaceChildren(h("tr", {}, h("td", { colspan: "9", class: "empty" }, h("span", { class: "spinner" }))));
    const page = await api("GET", `/runs/${runId}/findings?${params}`);
    selected.clear(); all.checked = false; bulk.update();

    if (!page.data.length) {
      tbody.replaceChildren(h("tr", {}, h("td", { colspan: "9", class: "empty" }, "Nothing matches these filters.")));
    } else {
      tbody.replaceChildren(...page.data.map(row => findingRow(row, runId, selected, bulk)));
    }
    const { total, offset, limit, hasMore } = page.pagination;
    pager.replaceChildren(
      h("span", { class: "muted" }, total ? `${offset + 1} to ${Math.min(offset + limit, total)} of ${total}` : "0 findings"),
      h("div", { class: "row" },
        h("button", { class: "btn", disabled: offset === 0, onclick: () => { f.offset = Math.max(0, offset - limit); load(); } }, "Previous"),
        h("button", { class: "btn", disabled: !hasMore, onclick: () => { f.offset = offset + limit; load(); } }, "Next")));
  }

  body.replaceChildren(
    h("div", { class: "filters" },
      h("label", { class: "field", for: "f-rule" }, "Rule", ruleSel),
      h("label", { class: "field", for: "f-sev" }, "Severity", sevSel),
      h("label", { class: "field", for: "f-obj" }, "Object", objSel),
      h("label", { class: "field", for: "f-st" }, "Status", stSel),
      h("label", { class: "field grow", for: "f-q" }, "Search", q)),
    h("section", { class: "card" },
      h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {},
          h("th", { scope: "col" }, all),
          ["Severity", "Rule", "Object", "Number", "Field", "Finding", "Status", "Owner"].map(t => h("th", { scope: "col" }, t)))),
        tbody)),
      pager),
    bulk.el);
  await load();
}

function findingRow(row, runId, selected, bulk) {
  const cb = h("input", { type: "checkbox", "aria-label": `Select finding ${row.id}` });
  const tr = h("tr", { class: "clickable" });
  cb.addEventListener("click", e => e.stopPropagation());
  cb.addEventListener("change", () => {
    cb.checked ? selected.add(row.id) : selected.delete(row.id);
    tr.classList.toggle("selected", cb.checked);
    bulk.update();
  });

  const st = h("select", { "aria-label": "Status", onclick: e => e.stopPropagation() },
    STATUSES.map(([v, t]) => h("option", { value: v }, t)));
  st.value = row.status;
  st.addEventListener("change", async () => {
    let comment;
    if (st.value === "false_positive") {
      comment = prompt("Why is this a false positive?");
      if (!comment) { st.value = row.status; return; }
    }
    try {
      const upd = await api("PATCH", `/findings/${row.id}`, { status: st.value, comment });
      row.status = upd.status;
      toast(`${row.key}: ${STATUS_LABEL[upd.status]}`);
      refreshKpis(runId);
    } catch (e) { st.value = row.status; toast(e.message, true); }
  });

  tr.addEventListener("click", () => openDrawer(row.id, runId));
  tr.append(
    h("td", {}, cb), h("td", {}, sevBadge(row.severity)), h("td", { class: "mono" }, row.rule),
    h("td", {}, row.object), h("td", { class: "mono" }, row.key), h("td", { class: "mono muted" }, row.field),
    h("td", { class: "msg" }, row.message), h("td", {}, st), h("td", { class: "muted" }, row.owner || ""));
  return tr;
}

function bulkBar(runId, selected, reload) {
  const count = h("strong");
  const st = h("select", { "aria-label": "New status" }, h("option", { value: "" }, "Status ..."),
    STATUSES.map(([v, t]) => h("option", { value: v }, t)));
  const owner = h("input", { placeholder: "Owner", "aria-label": "Owner", style: "width:120px" });
  const apply = h("button", { class: "btn primary" }, "Apply");
  const el = h("div", { class: "bulkbar hidden", role: "region", "aria-label": "Bulk actions" },
    count, st, owner, apply,
    h("button", { class: "btn ghost", style: "color:#fff", onclick: () => reload() }, "Clear"));

  apply.addEventListener("click", async () => {
    const body = { ids: [...selected] };
    if (st.value) body.status = st.value;
    if (owner.value.trim()) body.owner = owner.value.trim();
    if (!body.status && !body.owner) return toast("Pick a status or an owner", true);
    if (body.status === "false_positive") {
      body.comment = prompt("Why are these false positives?");
      if (!body.comment) return;
    }
    busy(apply, true);
    try {
      const r = await api("PATCH", "/findings", body);
      toast(`${r.updated} findings updated`);
      st.value = ""; owner.value = "";
      await reload();
      refreshKpis(runId);
    } catch (e) { toast(e.message, true); }
    busy(apply, false);
  });

  return {
    el,
    update() {
      el.classList.toggle("hidden", selected.size === 0);
      count.textContent = `${selected.size} selected`;
    },
  };
}

// ---------- detail drawer ----------

async function openDrawer(id, runId) {
  const f = await api("GET", `/findings/${id}`);
  const rule = RULES[f.rule] || {};
  const status = h("select", { id: "d-st" }, STATUSES.map(([v, t]) => h("option", { value: v }, t)));
  status.value = f.status;
  const owner = h("input", { id: "d-owner", value: f.owner || "", maxlength: "80" });
  const comment = h("textarea", { id: "d-comment", maxlength: "1000" });
  comment.value = f.comment || "";
  const save = h("button", { class: "btn primary" }, "Save");

  const scrim = h("div", { class: "scrim" });
  const drawer = h("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-labelledby": "d-title" },
    h("div", { class: "card-h" },
      sevBadge(f.severity), h("h2", { id: "d-title" }, `${f.rule} ${rule.title || ""}`),
      h("span", { style: "flex:1" }),
      h("button", { class: "btn ghost", "aria-label": "Close", onclick: close }, icon("close"))),
    h("div", { class: "card-b" },
      h("dl", { class: "kv" },
        h("dt", {}, "Object"), h("dd", {}, f.object),
        h("dt", {}, "Number"), h("dd", { class: "mono" }, f.key),
        f.related ? [h("dt", {}, "Related"), h("dd", { class: "mono" }, f.related)] : null,
        h("dt", {}, "Field"), h("dd", { class: "mono" }, f.field),
        h("dt", {}, "Finding"), h("dd", {}, f.message),
        h("dt", {}, "What to do"), h("dd", {}, f.fix)),
      rule.description ? h("p", { class: "muted", style: "font-size:13px" }, rule.description) : null,
      h("div", { class: "grid", style: "gap:10px" },
        h("label", { class: "field", for: "d-st" }, "Status", status),
        h("label", { class: "field", for: "d-owner" }, "Owner", owner),
        h("label", { class: "field", for: "d-comment" }, "Comment", comment),
        h("div", {}, save)),
      h("h2", { style: "margin-top:20px" }, "History"),
      f.history.length
        ? h("ul", { class: "history" }, f.history.map(e => h("li", {},
            h("span", { class: "muted" }, fmtDate(e.at)), " ", h("strong", {}, e.changedBy), " ",
            `${STATUS_LABEL[e.oldStatus] || e.oldStatus} to ${STATUS_LABEL[e.newStatus] || e.newStatus}`,
            e.comment ? h("div", { class: "muted" }, e.comment) : null)))
        : h("p", { class: "muted" }, "No changes yet.")));

  function close() { scrim.remove(); drawer.remove(); document.removeEventListener("keydown", onKey); }
  function onKey(e) { if (e.key === "Escape") close(); }
  scrim.addEventListener("click", close);
  document.addEventListener("keydown", onKey);

  save.addEventListener("click", async () => {
    busy(save, true);
    try {
      await api("PATCH", `/findings/${id}`, { status: status.value, owner: owner.value, comment: comment.value });
      toast("Saved");
      close();
      refreshKpis(runId);
      if (location.hash.endsWith("/worklist")) route();
    } catch (e) { toast(e.message, true); busy(save, false); }
  });

  document.body.append(scrim, drawer);
  requestAnimationFrame(() => drawer.classList.add("open"));
  status.focus();
}

// ---------- duplicates tab ----------

async function duplicates(body, runId) {
  const pairs = await api("GET", `/runs/${runId}/duplicate-pairs`);
  const filter = h("select", { id: "dup-st" },
    h("option", { value: "open" }, "Open"), h("option", { value: "" }, "All"),
    STATUSES.filter(([v]) => v !== "open").map(([v, t]) => h("option", { value: v }, t)));
  const list = h("div");
  const fields = [["NAME1", "Name"], ["NAME2", "Name 2"], ["STRAS", "Street"], ["PSTLZ", "Postal code"],
                  ["ORT01", "City"], ["LAND1", "Country"], ["STCEG", "VAT ID"]];

  function render() {
    const shown = pairs.filter(p => !filter.value || p.status === filter.value);
    if (!shown.length) return list.replaceChildren(h("div", { class: "card empty" }, "No pairs with this status."));
    list.replaceChildren(...shown.map(p => {
      const decide = async (status) => {
        let comment = "";
        if (status === "false_positive") {
          comment = prompt("Why are these two different companies?");
          if (!comment) return;
        }
        try {
          await api("PATCH", `/findings/${p.findingId}`, { status, comment });
          p.status = status;
          toast(status === "accepted" ? "Marked as duplicate" : "Marked as different companies");
          render();
          refreshKpis(runId);
        } catch (e) { toast(e.message, true); }
      };
      return h("section", { class: "card pair" },
        h("div", { class: "card-h" },
          h("span", { class: "score", title: "match score, 0 to 100" }, `Score ${p.score.toFixed(0)}`), sevBadge(p.severity),
          h("span", { class: "muted" }, `${p.object}, ${p.reasons.join(", ")}`),
          h("span", { style: "flex:1" }), statusDot(p.status)),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, h("th", {}, ""), h("th", { class: "mono" }, p.a.id), h("th", { class: "mono" }, p.b.id))),
          h("tbody", {}, fields.map(([k, t]) => {
            const diff = (p.a[k] || "") !== (p.b[k] || "");
            return h("tr", {}, h("th", { scope: "row" }, t),
              h("td", { class: diff ? "diff" : null }, p.a[k] || ""),
              h("td", { class: diff ? "diff" : null }, p.b[k] || ""));
          })))),
        h("div", { class: "card-b row" },
          h("button", { class: "btn primary", onclick: () => decide("accepted") }, "Same company, merge"),
          h("button", { class: "btn", onclick: () => decide("false_positive") }, "Different companies")));
    }));
  }

  filter.addEventListener("change", render);
  body.replaceChildren(
    h("div", { class: "filters" },
      h("label", { class: "field", for: "dup-st" }, "Status", filter),
      h("p", { class: "muted", style: "margin:0 0 6px" }, "Highlighted cells differ between the two records.")),
    list);
  render();
}

// ---------- start ----------

for (const id of ["who", "apikey"]) {
  const el = document.getElementById(id);
  el.value = pref(id);
  el.addEventListener("change", () => pref(id, el.value.trim()));
}
window.addEventListener("hashchange", route);
route();
