"use strict";

const $ = (id) => document.getElementById(id);
const EXAMPLES = [
  "What is retrieval-augmented generation and what are its limits?",
  "How do server-sent events work?",
  "Explain how containers differ from virtual machines",
  "What are the pros and cons of running language models locally?",
];
const state = { controller: null, markdown: "", pending: null, modes: [] };

function backend() {
  const typed = $("backend").value.trim().replace(/\/+$/, "");
  if (typed) return typed;
  return location.protocol.startsWith("http") ? location.origin : "http://localhost:8080";
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* ---- tiny, XSS-safe Markdown renderer: everything is escaped first ---- */
function inline(text) {
  let t = esc(text);
  t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  t = t.replace(/\[(\d+(?:,\s*\d+)*)\]/g, (m, ids) =>
    ids.split(/,\s*/).map((id) => `<a class="cite" href="#src-${id}">[${id}]</a>`).join(""));
  return t;
}

function renderMarkdown(md) {
  let html = "", para = [], inList = false;
  const flush = () => { if (para.length) { html += "<p>" + inline(para.join(" ")) + "</p>"; para = []; } };
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (const raw of md.split("\n")) {
    const line = raw.trimEnd();
    let m;
    if (!line.trim()) { flush(); closeList(); continue; }
    if ((m = line.match(/^(#{1,4})\s+(.*)$/))) {
      flush(); closeList();
      const level = Math.min(m[1].length + 1, 5);
      html += `<h${level}>${inline(m[2])}</h${level}>`;
      continue;
    }
    if ((m = line.match(/^\s*[-*]\s+(.*)$/))) {
      flush();
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(m[1])}</li>`;
      continue;
    }
    closeList();
    para.push(line.trim());
  }
  flush(); closeList();
  return html;
}

/* ---- UI helpers ---- */
function setStatus(text) { $("status").textContent = text || ""; }
function showError(msg) { const e = $("error"); e.textContent = msg; e.hidden = !msg; }
function setRunning(on) {
  $("start").disabled = on;
  $("stop").disabled = !on;
}
function resetOutput() {
  showError("");
  for (const id of ["progress", "findings-card", "report-card", "clarify-panel"]) $(id).hidden = true;
  $("log").innerHTML = ""; $("findings").innerHTML = ""; $("report").innerHTML = ""; $("sources").innerHTML = "";
  $("plan").hidden = true; $("plan").innerHTML = "";
  document.querySelectorAll("#stages li").forEach((li) => li.className = "");
  state.markdown = "";
}
function addLog(text, url) {
  const li = document.createElement("li");
  if (url && /^https?:\/\//.test(url)) {
    const a = document.createElement("a");
    a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = text;
    li.appendChild(a);
  } else {
    li.textContent = text;
  }
  const log = $("log");
  log.appendChild(li);
  log.scrollTop = log.scrollHeight;
}
function markStage(stage) {
  let seen = false;
  document.querySelectorAll("#stages li").forEach((li) => {
    if (li.dataset.stage === stage) { li.className = "active"; seen = true; }
    else li.className = seen ? "" : "done";
  });
}

/* ---- event handling ---- */
function onEvent(ev) {
  switch (ev.type) {
    case "session_start":
      $("progress").hidden = false;
      setStatus(`Running (${ev.engine || ev.mode}, search: ${ev.search || "?"})`);
      break;
    case "stage_start":
      markStage(ev.stage); addLog(ev.content);
      break;
    case "research_step":
      if (ev.questions) {
        $("plan").hidden = false;
        $("plan").innerHTML = "<strong>Research plan</strong><ol>" + ev.questions.map((q) => `<li>${esc(q)}</li>`).join("") + "</ol>";
      }
      addLog(ev.content, ev.url);
      break;
    case "research_finding": {
      $("findings-card").hidden = false;
      const d = document.createElement("div");
      d.className = "finding";
      d.innerHTML = `<h3>${esc(ev.question || "Finding")}</h3><p>${inline(ev.content)}</p>`;
      $("findings").appendChild(d);
      break;
    }
    case "research_complete": {
      document.querySelectorAll("#stages li").forEach((li) => li.className = "done");
      state.markdown = ev.content;
      const body = ev.content.split(/\n## Sources\b/)[0];
      $("report").innerHTML = renderMarkdown(body);
      $("sources").innerHTML = (ev.sources || []).map((s) => {
        const link = /^https?:\/\//.test(s.url) ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>` : esc(s.title);
        return `<li id="src-${s.id}" value="${s.id}">${link}</li>`;
      }).join("");
      $("report-card").hidden = false;
      $("report-card").scrollIntoView({ behavior: "smooth", block: "start" });
      setStatus("Done");
      break;
    }
    case "error":
      showError(ev.content);
      setStatus("Stopped");
      break;
  }
}

async function streamResearch(payload, signal) {
  const res = await fetch(backend() + "/research/stream", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal,
  });
  if (!res.ok) {
    let detail = "";
    try { const j = await res.json(); detail = Array.isArray(j.detail) ? "Please check your input." : j.detail; } catch (e) { /* ignore */ }
    throw new Error(detail || `Request failed (HTTP ${res.status})`);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of block.split("\n")) {
        if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)));
      }
    }
  }
}

async function runResearch(payload) {
  resetOutput();
  setRunning(true);
  setStatus("Connecting...");
  state.controller = new AbortController();
  try {
    await streamResearch(payload, state.controller.signal);
  } catch (e) {
    if (e.name === "AbortError") setStatus("Stopped");
    else { showError(e.message || String(e)); setStatus(""); }
  } finally {
    setRunning(false);
    state.controller = null;
  }
}

function currentPayload() {
  const query = $("query").value.trim();
  if (query.length < 3) { showError("Please type a research question (at least 3 characters)."); return null; }
  const payload = { query, mode: $("mode").value, depth: $("depth").value };
  const model = $("model").value.trim();
  if (model) payload.model = model;
  return payload;
}

async function onStart() {
  const payload = currentPayload();
  if (!payload) return;
  if ($("clarify").checked && payload.mode !== "extractive") {
    resetOutput(); setRunning(true); setStatus("Thinking about your question...");
    try {
      const r = await fetch(backend() + "/research/clarify", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: payload.query, mode: payload.mode, model: payload.model }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "Could not ask clarifying questions.");
      if (j.questions && j.questions.length) {
        state.pending = payload;
        $("clarify-questions").innerHTML = j.questions.map((q, i) =>
          `<label for="cq${i}">${esc(q)}</label><input id="cq${i}" data-q="${esc(q)}" placeholder="Your answer (optional)">`).join("");
        $("clarify-panel").hidden = false;
        setRunning(false); setStatus("");
        return;
      }
    } catch (e) {
      showError(e.message || String(e)); setRunning(false); setStatus("");
      return;
    }
    setRunning(false);
  }
  runResearch(payload);
}

function onClarifyGo() {
  const payload = state.pending;
  if (!payload) return;
  const parts = [];
  document.querySelectorAll("#clarify-questions input").forEach((inp) => {
    if (inp.value.trim()) parts.push(`Q: ${inp.dataset.q}\nA: ${inp.value.trim()}`);
  });
  if (parts.length) payload.context = parts.join("\n").slice(0, 2000);
  state.pending = null;
  runResearch(payload);
}

/* ---- setup ---- */
async function loadModels() {
  const sel = $("mode");
  try {
    const r = await fetch(backend() + "/models");
    const j = await r.json();
    state.modes = j.modes;
    sel.innerHTML = j.modes.map((m) =>
      `<option value="${esc(m.id)}">${esc(m.label)}${m.available ? "" : " (not detected)"}</option>`).join("");
    const ollama = j.modes.find((m) => m.id === "ollama");
    if (ollama && ollama.available) { sel.value = "ollama"; }
    syncModels();
  } catch (e) {
    sel.innerHTML = '<option value="extractive">No model (extractive, works offline)</option>';
    showError("Cannot reach the backend at " + backend() + ". Start it first (see README).");
  }
}
function syncModels() {
  const m = state.modes.find((x) => x.id === $("mode").value);
  $("model-list").innerHTML = (m && m.models ? m.models : []).map((n) => `<option value="${esc(n)}">`).join("");
  $("model").placeholder = m && m.default ? m.default : "default";
  $("model").disabled = !m || m.id === "extractive";
  $("clarify").disabled = !m || m.id === "extractive";
  if ($("clarify").disabled) $("clarify").checked = false;
}

function init() {
  $("backend").value = localStorage.getItem("dr-backend") || "";
  $("backend").addEventListener("change", () => { localStorage.setItem("dr-backend", $("backend").value.trim()); showError(""); loadModels(); });
  $("examples").innerHTML = EXAMPLES.map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join("");
  $("examples").addEventListener("click", (e) => { if (e.target.classList.contains("chip")) $("query").value = e.target.textContent; });
  $("mode").addEventListener("change", syncModels);
  $("start").addEventListener("click", onStart);
  $("stop").addEventListener("click", () => state.controller && state.controller.abort());
  $("clarify-go").addEventListener("click", onClarifyGo);
  $("clarify-skip").addEventListener("click", () => { const p = state.pending; state.pending = null; if (p) runResearch(p); });
  $("copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(state.markdown); setStatus("Copied"); } catch (e) { setStatus("Copy failed"); }
  });
  $("download").addEventListener("click", () => {
    const blob = new Blob([state.markdown], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "research-report.md"; a.click();
    URL.revokeObjectURL(a.href);
  });
  $("query").addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") onStart(); });
  loadModels();
}
document.addEventListener("DOMContentLoaded", init);
