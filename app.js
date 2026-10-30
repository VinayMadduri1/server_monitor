"use strict";

const REFRESH_MS = 5000;
const $ = (id) => document.getElementById(id);

let token = null;
let role = null;
let chart = null;
let timer = null;

/* ---------- API helper ---------- */

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = "Bearer " + token;
  const resp = await fetch("/api" + path, { ...options, headers });
  if (resp.status === 401 && token) {
    logout();               // token expired or invalid
    throw new Error("Session expired");
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || "Request failed");
  return data;
}

/* ---------- auth ---------- */

function saveSession(data) {
  token = data.token;
  role = data.role;
  try { sessionStorage.setItem("session", JSON.stringify({ token, role, username: data.username })); } catch (_) {}
  $("whoami").textContent = data.username + " (" + data.role + ")";
}

function logout() {
  token = null;
  role = null;
  clearInterval(timer);
  try { sessionStorage.removeItem("session"); } catch (_) {}
  $("dash-view").hidden = true;
  $("login-view").hidden = false;
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("login-error").textContent = "";
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: $("username").value, password: $("password").value }),
    });
    saveSession(data);
    $("password").value = "";
    startDashboard();
  } catch (err) {
    $("login-error").textContent = err.message;
  }
});

$("logout").addEventListener("click", logout);

/* ---------- rendering ---------- */

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function setStat(id, value, threshold) {
  const el = $(id);
  el.textContent = value;
  el.classList.toggle("hot", threshold !== undefined && parseFloat(value) > threshold);
}

async function refreshStats(thresholds) {
  try {
    const m = await api("/metrics/latest");
    setStat("stat-cpu", m.cpu.toFixed(1) + "%", thresholds.cpu);
    setStat("stat-memory", m.memory.toFixed(1) + "%", thresholds.memory);
    setStat("stat-disk", m.disk.toFixed(1) + "%", thresholds.disk);
    setStat("stat-load", m.load1.toFixed(2));
    setStat("stat-procs", String(m.proc_count));
  } catch (_) { /* collector may not have produced a sample yet */ }
}

async function refreshChart() {
  const rows = await api("/metrics/history?minutes=" + $("range").value);
  chart.data.labels = rows.map((r) => fmtTime(r.ts));
  chart.data.datasets[0].data = rows.map((r) => r.cpu);
  chart.data.datasets[1].data = rows.map((r) => r.memory);
  chart.data.datasets[2].data = rows.map((r) => r.disk);
  chart.update("none");
}

async function refreshProcesses() {
  const rows = await api("/processes?sort=" + $("proc-sort").value);
  const body = $("proc-body");
  body.replaceChildren();
  for (const p of rows) {
    const tr = document.createElement("tr");
    for (const value of [p.pid, p.name, p.cpu.toFixed(1), p.memory.toFixed(1)]) {
      const td = document.createElement("td");
      td.textContent = value;       // textContent, never innerHTML: process names are untrusted
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

async function refreshAlerts() {
  const alerts = await api("/alerts");
  const list = $("alert-list");
  list.replaceChildren();
  $("no-alerts").hidden = alerts.length > 0;
  for (const a of alerts) {
    const li = document.createElement("li");
    li.className = a.acknowledged ? "acked" : "open";

    const text = document.createElement("span");
    text.textContent = a.message;
    const when = document.createElement("span");
    when.className = "when";
    when.textContent = new Date(a.ts * 1000).toLocaleString();
    text.appendChild(when);
    li.appendChild(text);

    if (role === "admin" && !a.acknowledged) {
      const btn = document.createElement("button");
      btn.className = "secondary";
      btn.textContent = "Acknowledge";
      btn.addEventListener("click", async () => {
        await api("/alerts/" + a.id + "/ack", { method: "POST" });
        refreshAlerts();
      });
      li.appendChild(btn);
    }
    list.appendChild(li);
  }
}

async function loadThresholds() {
  const t = await api("/thresholds");
  $("th-cpu").value = t.cpu;
  $("th-memory").value = t.memory;
  $("th-disk").value = t.disk;
  return t;
}

$("threshold-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/thresholds", {
      method: "PUT",
      body: JSON.stringify({
        cpu: Number($("th-cpu").value),
        memory: Number($("th-memory").value),
        disk: Number($("th-disk").value),
      }),
    });
    $("th-note").textContent = "Thresholds saved.";
  } catch (err) {
    $("th-note").textContent = err.message;
  }
});

/* ---------- lifecycle ---------- */

function buildChart() {
  if (chart) chart.destroy();
  const line = (label, color) => ({ label, data: [], borderColor: color, backgroundColor: color, borderWidth: 2, pointRadius: 0, tension: 0.25 });
  chart = new Chart($("chart"), {
    type: "line",
    data: { labels: [], datasets: [line("CPU %", "#2563eb"), line("Memory %", "#d97706"), line("Disk %", "#059669")] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: { y: { min: 0, max: 100 }, x: { ticks: { maxTicksLimit: 8 } } },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

async function tick() {
  try {
    const thresholds = await api("/thresholds");
    await Promise.all([refreshStats(thresholds), refreshChart(), refreshProcesses(), refreshAlerts()]);
  } catch (_) { /* a failed refresh is retried on the next tick */ }
}

async function startDashboard() {
  $("login-view").hidden = true;
  $("dash-view").hidden = false;
  const isAdmin = role === "admin";
  $("th-save").disabled = !isAdmin;
  for (const id of ["th-cpu", "th-memory", "th-disk"]) $(id).disabled = !isAdmin;
  $("th-note").textContent = isAdmin ? "" : "Read-only: only admins can change thresholds.";

  buildChart();
  await loadThresholds();
  await tick();
  clearInterval(timer);
  timer = setInterval(tick, REFRESH_MS);
}

$("range").addEventListener("change", refreshChart);
$("proc-sort").addEventListener("change", refreshProcesses);

// Restore a session after page refresh (cleared when the tab closes).
try {
  const saved = JSON.parse(sessionStorage.getItem("session") || "null");
  if (saved && saved.token) {
    token = saved.token;
    role = saved.role;
    $("whoami").textContent = saved.username + " (" + saved.role + ")";
    startDashboard().catch(logout);
  }
} catch (_) {}
