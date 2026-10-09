// Task Reminder sidebar panel — vanilla web component (no build step).
// Talks to the integration over the HA websocket (task_reminder/* commands).

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const STATUS_ICON = {
  notifying: "mdi:bell-ring",
  snoozed: "mdi:alarm-snooze",
  armed: "mdi:timer-sand",
  held: "mdi:pause-circle-outline",
};
const OUTCOME = {
  done: ["mdi:check-circle-outline", "Done"],
  dismissed: ["mdi:close-circle-outline", "Dismissed"],
  expired: ["mdi:clock-alert-outline", "Missed"],
  cancelled: ["mdi:cancel", "Cancelled"],
};
const PIPS = ["Phone", "Alexa", "All devices", "Keeps going"];
const DURATIONS = [
  [30, "30 min"],
  [60, "1 h"],
  [120, "2 h"],
  [240, "4 h"],
  [480, "8 h"],
];
const PRESETS = [1, 5, 10, 30, 60];

const sameDay = (a, b) => a.toDateString() === b.toDateString();

const fmtTime = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  const t = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  const now = new Date();
  if (sameDay(d, now)) return t;
  const tomorrow = new Date(now.getTime() + 864e5);
  if (sameDay(d, tomorrow)) return `tomorrow ${t}`;
  return `${d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })} ${t}`;
};

const fmtDay = (isoDay) => {
  if (!isoDay) return "";
  const d = new Date(isoDay + "T12:00:00");
  const now = new Date();
  if (sameDay(d, now)) return "today";
  if (sameDay(d, new Date(now.getTime() + 864e5))) return "tomorrow";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
};

// "in 12 min" / "3 min ago", re-evaluated every second by the panel's ticker.
const fmtRel = (iso) => {
  if (!iso) return "";
  const diff = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
  const s = Math.abs(diff);
  let text;
  if (s < 5) return "now";
  if (s < 60) text = `${s} s`;
  else if (s < 600) text = `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
  else if (s < 3600) text = `${Math.round(s / 60)} min`;
  else if (s < 86400) text = `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
  else text = `${Math.round(s / 86400)} d`;
  return diff > 0 ? `in ${text}` : `${text} ago`;
};

const rel = (iso) => `<span class="rel" data-ts="${esc(iso)}">${esc(fmtRel(iso))}</span>`;

class TaskReminderPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = { ready: false, tasks: [] };
    this._form = { title: "", minutes: "" };
    this._silenceMode = "silent";
    this._toast = "";
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._connect();
  }
  set narrow(v) {
    this._narrow = v;
    this._render();
  }
  set panel(v) {}

  async _connect() {
    this._render();
    try {
      this._unsub = await this._hass.connection.subscribeMessage(
        (msg) => {
          if (!msg.ready && this._data.ready) return; // transient (integration reloading)
          this._data = msg;
          this._render();
        },
        { type: "task_reminder/subscribe" }
      );
    } catch (e) {
      this._data = { ready: false, tasks: [], error: e.message || String(e) };
      this._render();
    }
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._connect();
    this._ticker = setInterval(() => this._tick(), 1000);
  }
  disconnectedCallback() {
    if (this._unsub) this._unsub();
    this._unsub = null;
    clearInterval(this._ticker);
  }

  // Live countdowns: update the text only, never the layout.
  _tick() {
    for (const el of this.shadowRoot.querySelectorAll(".rel")) {
      const text = fmtRel(el.dataset.ts);
      if (el.textContent !== text) el.textContent = text;
    }
  }

  async _call(msg, ok) {
    try {
      const result = await this._hass.callWS(msg);
      if (ok) this._say(ok);
      return result;
    } catch (e) {
      this._say(e.message || String(e));
    }
  }

  _say(text) {
    this._toast = text;
    this._render();
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this._toast = "";
      this._render();
    }, 4000);
  }

  // ---------- rendering ----------
  _render() {
    if (!this.shadowRoot) return;
    const active = this.shadowRoot.activeElement;
    const focusId = active && active.id;
    const caret = active && active.selectionStart;
    const openSilence = this.shadowRoot.querySelector("details.silence")?.open;
    const d = this._data;
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        ${this._narrow ? `<ha-menu-button></ha-menu-button>` : ""}
        <div class="title">Tasks</div>
        ${d.room ? `<div class="where" title="Where reminders are announced first"><ha-icon icon="mdi:map-marker"></ha-icon> ${esc(d.room)}</div>` : ""}
      </div>
      <div class="content">
        ${
          !d.ready
            ? `<div class="empty">${d.error ? esc(d.error) : "Task Reminder isn't set up yet. Add the integration first."}</div>`
            : this._renderBody(d)
        }
      </div>
      ${this._toast ? `<div class="toast">${esc(this._toast)}</div>` : ""}
    `;
    const silence = this.shadowRoot.querySelector("details.silence");
    if (silence && openSilence) silence.open = true;
    if (focusId) {
      const el = this.shadowRoot.getElementById(focusId);
      if (el) {
        el.focus();
        if (caret != null && el.setSelectionRange) el.setSelectionRange(caret, caret);
      }
    }
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) {
      menu.hass = this._hass;
      menu.narrow = this._narrow;
    }
    this._bind();
  }

  _renderBody(d) {
    const by = (status) => d.tasks.filter((t) => t.status === status);
    const needs = by("notifying");
    const snoozed = by("snoozed").sort((a, b) => (a.next_at || "").localeCompare(b.next_at || ""));
    const armed = by("armed").sort((a, b) => (a.due_at || "9").localeCompare(b.due_at || "9"));
    const held = by("held");
    const comingUp = armed.length + (d.upcoming || []).length;
    const nothing = !d.tasks.length;
    return `
      ${this._renderSilenceBanner(d.silence)}
      ${this._renderQuick(d)}
      ${nothing ? this._renderEmpty() : ""}
      ${this._lane("Needs you", needs.length, needs.map((t) => this._renderTask(t)).join(""), "now")}
      ${this._lane("Snoozed", snoozed.length, snoozed.map((t) => this._renderTask(t)).join(""))}
      ${this._lane(
        "Coming up",
        comingUp,
        armed.map((t) => this._renderTask(t)).join("") +
          (d.upcoming || []).map((u) => this._renderUpcoming(u)).join("")
      )}
      ${this._lane("On hold", held.length, held.map((t) => this._renderTask(t, d)).join(""))}
      ${this._renderSilenceControls(d.silence)}
      ${this._renderHistory(d.history || [])}
    `;
  }

  _lane(title, count, html, accent = "") {
    if (!count) return "";
    return `
      <section class="lane">
        <div class="lane-title ${accent}"><span>${esc(title)}</span><span class="count">${count}</span></div>
        <div class="list">${html}</div>
      </section>`;
  }

  _renderEmpty() {
    return `
      <div class="empty big">
        <div class="empty-orb"><ha-icon icon="mdi:check-all"></ha-icon></div>
        <div class="empty-title">All clear</div>
        <div>Nothing is running. Start something above.</div>
      </div>`;
  }

  _renderSilenceBanner(s) {
    if (!s || s.mode === "off") return "";
    const silent = s.mode === "silent";
    return `
      <div class="banner">
        <div class="orb sm"><ha-icon icon="${silent ? "mdi:volume-off" : "mdi:bell-cancel-outline"}"></ha-icon></div>
        <div class="info">
          <div class="name">${silent ? "Silent" : "No critical alerts"} until ${esc(fmtTime(s.until))}</div>
          <div class="line">${
            silent
              ? "Nothing is sent; reminders wait and arrive when this ends."
              : "Reminders still arrive, but never as critical alerts."
          } Ends ${rel(s.until)}.</div>
        </div>
        <button data-act="silence-off"><ha-icon icon="mdi:bell-ring-outline"></ha-icon> End now</button>
      </div>`;
  }

  _renderQuick(d) {
    const f = this._form;
    return `
      <div class="hero">
        <div class="hero-text">
          <div class="hero-label">Quick reminder</div>
          <div class="quick">
            <input id="q-title" type="text" placeholder="Egg timer, call the plumber…" value="${esc(f.title)}" maxlength="120" />
            <input id="q-minutes" type="number" inputmode="decimal" min="0" placeholder="minutes" value="${esc(f.minutes)}" />
            <button class="primary" data-act="remind" ${f.title.trim() ? "" : "disabled"}>
              <ha-icon icon="mdi:bell-plus-outline"></ha-icon> Remind me</button>
          </div>
          <div class="chips">
            ${PRESETS.map((m) => `<button class="chip ${String(f.minutes) === String(m) ? "on" : ""}" data-act="preset" data-minutes="${m}">${m < 60 ? m + " min" : "1 h"}</button>`).join("")}
            <span class="help">empty = right now</span>
          </div>
        </div>
        ${
          (d.types || []).length
            ? `<div class="hero-start">
                <div class="hero-label">Start a task</div>
                <div class="chips">
                  ${d.types.map((t) => `<button class="chip start" data-act="start" data-type="${esc(t.key)}"><ha-icon icon="mdi:play"></ha-icon> ${esc(t.name)}</button>`).join("")}
                </div>
              </div>`
            : ""
        }
      </div>`;
  }

  _statusLine(t) {
    if (t.status === "notifying") {
      const ago = t.last_notified_at ? `Reminded ${rel(t.last_notified_at)}` : "Due now";
      const next = t.next_at ? ` · next ${rel(t.next_at)}` : "";
      return ago + next;
    }
    if (t.status === "snoozed") return `Back ${rel(t.next_at)} (${esc(fmtTime(t.next_at))})`;
    if (t.status === "armed") {
      if (t.due_at) return `Due ${rel(t.due_at)} (${esc(fmtTime(t.due_at))})`;
      return "Waiting for it to finish";
    }
    if (t.status === "held") {
      if (t.held_reason === "silent") return `Silent mode: delivered ${t.next_at ? rel(t.next_at) : "when it ends"}`;
      if (t.held_reason === "quiet") return `Quiet hours: reminds ${t.next_at ? `${rel(t.next_at)} (${esc(fmtTime(t.next_at))})` : "later"}`;
      if (t.held_reason === "away") return "You're away: reminds when you're home";
      return "On hold";
    }
    return "";
  }

  _renderTask(t) {
    const pips = Math.min(t.level, PIPS.length);
    const snoozeLabel = t.snooze_next ? `Snooze ${t.snooze_next} min` : "";
    const badges = [];
    if (t.keeps_going) badges.push(`<span class="badge fin">keeps going</span>`);
    if (t.snooze_total && t.snooze_count)
      badges.push(`<span class="badge">snoozed ${t.snooze_count}/${t.snooze_total}</span>`);
    if (t.held_reason === "silent") badges.push(`<span class="badge auto">silent</span>`);
    if (t.held_reason === "quiet") badges.push(`<span class="badge soon">quiet hours</span>`);
    if (t.held_reason === "away") badges.push(`<span class="badge warn">away</span>`);
    const typeLine = t.type === "ad_hoc" ? "Reminder" : t.type_name;
    const canAct = t.status === "notifying" || t.status === "snoozed" || t.status === "held" || t.status === "armed";
    return `
      <div class="card task ${esc(t.status)} ${t.keeps_going ? "going" : ""}">
        <div class="row">
          <div class="orb ${esc(t.status)}"><ha-icon icon="${STATUS_ICON[t.status] || "mdi:bell"}"></ha-icon></div>
          <div class="info">
            <div class="name">${esc(t.title)} ${badges.join(" ")}</div>
            <div class="line">${this._statusLine(t)}</div>
            <div class="meta">
              <span>${esc(typeLine)}</span>
              ${
                t.level
                  ? `<span class="pips" title="Reminder ${t.level}: ${esc(PIPS[pips - 1])}">${PIPS.map((p, i) => `<i class="${i < pips ? "on" : ""}"></i>`).join("")}</span><span>${esc(PIPS[pips - 1])}</span>`
                  : ""
              }
            </div>
          </div>
          <div class="actions">
            ${
              t.snooze_next && (t.status === "notifying")
                ? `<button data-act="snooze" data-id="${esc(t.id)}"><ha-icon icon="mdi:alarm-snooze"></ha-icon> ${esc(snoozeLabel)}</button>`
                : ""
            }
            ${t.status === "armed" ? `<button data-act="cancel" data-id="${esc(t.id)}" title="Drop it before it is due"><ha-icon icon="mdi:close"></ha-icon> Cancel</button>` : ""}
            ${t.dismissable && t.status !== "armed" && canAct ? `<button data-act="dismiss" data-id="${esc(t.id)}" title="End without doing it"><ha-icon icon="mdi:close"></ha-icon> Dismiss</button>` : ""}
            <button class="primary" data-act="done" data-id="${esc(t.id)}"><ha-icon icon="mdi:check"></ha-icon> Done</button>
          </div>
        </div>
      </div>`;
  }

  _renderUpcoming(u) {
    const starts = u.starts_on === u.collection ? "starts that day" : `starts ${fmtDay(u.starts_on)}${u.due_time ? ` at ${esc(u.due_time)}` : ""}`;
    return `
      <div class="card ghost">
        <div class="row">
          <div class="orb ghost"><ha-icon icon="mdi:calendar-clock"></ha-icon></div>
          <div class="info">
            <div class="name">${esc(u.name)}</div>
            <div class="line">Collection ${esc(fmtDay(u.collection))} · ${esc(starts)}</div>
          </div>
        </div>
      </div>`;
  }

  _renderSilenceControls(s) {
    const on = s && s.mode !== "off";
    return `
      <details class="silence">
        <summary><ha-icon icon="mdi:volume-off"></ha-icon> ${on ? "Change silencing" : "Silence reminders"}</summary>
        <div class="silence-body">
          <div class="seg">
            <button class="${this._silenceMode === "silent" ? "on" : ""}" data-act="silence-mode" data-mode="silent">Silent</button>
            <button class="${this._silenceMode === "no_critical" ? "on" : ""}" data-act="silence-mode" data-mode="no_critical">No critical alerts</button>
          </div>
          <div class="help">${
            this._silenceMode === "silent"
              ? "Nothing is sent. Reminders pile up and arrive when it ends (e.g. while teaching)."
              : "Reminders still arrive but never as critical alerts (e.g. cinema, wedding)."
          } It always ends: pick for how long.</div>
          <div class="chips">
            ${DURATIONS.map(([m, label]) => `<button class="chip" data-act="silence" data-minutes="${m}">${label}</button>`).join("")}
          </div>
        </div>
      </details>`;
  }

  _renderHistory(items) {
    if (!items.length) return "";
    return `
      <details class="history">
        <summary><ha-icon icon="mdi:history"></ha-icon> Recently finished</summary>
        <div class="hist">
          ${items
            .map((h) => {
              const [icon, label] = OUTCOME[h.outcome] || ["mdi:help-circle-outline", h.outcome];
              return `<div class="hist-row ${esc(h.outcome)}"><ha-icon icon="${icon}"></ha-icon><span class="hname">${esc(h.title)}</span><span class="muted0">${esc(label)} ${rel(h.at)}</span></div>`;
            })
            .join("")}
        </div>
      </details>`;
  }

  // ---------- interaction ----------
  _bind() {
    const root = this.shadowRoot;
    const title = root.getElementById("q-title");
    const minutes = root.getElementById("q-minutes");
    if (title)
      title.addEventListener("input", () => {
        this._form.title = title.value;
        const btn = root.querySelector('[data-act="remind"]');
        if (btn) btn.disabled = !title.value.trim();
      });
    if (minutes)
      minutes.addEventListener("input", () => {
        this._form.minutes = minutes.value;
        for (const c of root.querySelectorAll('[data-act="preset"]'))
          c.classList.toggle("on", c.dataset.minutes === minutes.value);
      });
    if (title)
      title.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && this._form.title.trim()) this._remind();
      });
    for (const el of root.querySelectorAll("[data-act]")) {
      el.addEventListener("click", () => this._act(el));
    }
  }

  async _remind() {
    const msg = { type: "task_reminder/remind", title: this._form.title.trim() };
    if (this._form.minutes !== "" && Number(this._form.minutes) > 0) msg.minutes = Number(this._form.minutes);
    const done = await this._call(msg);
    if (done) {
      const timer = msg.minutes ? ` in ${msg.minutes} min` : " now";
      this._form = { title: "", minutes: "" };
      this._say(`Reminder set${timer}`);
    }
  }

  async _act(el) {
    const { act, id } = el.dataset;
    if (act === "done") await this._call({ type: "task_reminder/done", task_id: id });
    else if (act === "snooze") await this._call({ type: "task_reminder/snooze", task_id: id });
    else if (act === "cancel") await this._call({ type: "task_reminder/cancel", task_id: id });
    else if (act === "dismiss") await this._call({ type: "task_reminder/dismiss", task_id: id });
    else if (act === "start") await this._call({ type: "task_reminder/start", task_type: el.dataset.type }, "Started");
    else if (act === "remind") await this._remind();
    else if (act === "preset") {
      this._form.minutes = el.dataset.minutes;
      this._render();
    } else if (act === "silence-mode") {
      this._silenceMode = el.dataset.mode;
      this._render();
      const d = this.shadowRoot.querySelector("details.silence");
      if (d) d.open = true;
    } else if (act === "silence") {
      const until = new Date(Date.now() + Number(el.dataset.minutes) * 60000).toISOString();
      await this._call({ type: "task_reminder/silence", mode: this._silenceMode, until }, "Silencing on");
    } else if (act === "silence-off") {
      await this._call({ type: "task_reminder/silence", mode: "off" }, "Silencing ended");
    }
  }
}

const STYLE = `
  :host { display:block; height:100%; overflow:auto; background: var(--primary-background-color); color: var(--primary-text-color);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
  .toolbar { display:flex; align-items:center; height:56px; padding:0 12px; gap:8px; position:sticky; top:0; z-index:3;
             background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff);
             border-bottom: 1px solid var(--divider-color); }
  .title { font-size:20px; font-weight:400; margin-left:4px; flex:1; }
  .where { display:inline-flex; align-items:center; gap:4px; font-size:13px; padding:3px 10px 3px 6px; border-radius:14px;
           background: rgba(255,255,255,.16); }
  .where ha-icon { --mdc-icon-size: 16px; }
  .content { max-width: 900px; margin: 0 auto; padding: 16px; box-sizing:border-box; }
  ha-icon { --mdc-icon-size: 20px; }
  button { font: inherit; border-radius: 18px; border: 1px solid var(--divider-color); background: var(--card-background-color);
           color: var(--primary-text-color); padding: 7px 14px; cursor:pointer; display:inline-flex; align-items:center; gap:6px; white-space:nowrap; }
  button:hover:not(:disabled) { border-color: var(--secondary-text-color); }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  button:disabled { opacity:.45; cursor: default; }
  .lane { margin-bottom: 26px; }
  .lane-title { display:flex; align-items:center; gap:8px; margin: 0 4px 8px; font-size:12px; text-transform:uppercase;
                letter-spacing:.08em; color: var(--secondary-text-color); }
  .lane-title.now { color: #ee4b2b; }
  .count { font-size:11px; padding:0 7px; border-radius:9px; background: rgba(127,127,127,.2); letter-spacing:0; }
  .list { display:flex; flex-direction:column; gap:8px; }

  .hero { display:flex; flex-wrap:wrap; gap:16px 28px; align-items:flex-end; justify-content:space-between;
          background: linear-gradient(135deg, rgba(255,176,79,.16), rgba(238,75,43,.10)), var(--card-background-color);
          border-radius: 12px; padding: 14px 16px; margin-bottom: 22px; border: 1px solid var(--divider-color);
          box-shadow: var(--ha-card-box-shadow, none); }
  .hero-text { flex: 1 1 380px; min-width: 0; }
  .hero-label { font-size:12px; text-transform:uppercase; letter-spacing:.08em; color: var(--secondary-text-color); margin-bottom:8px; }
  .quick { display:flex; gap:8px; flex-wrap:wrap; }
  .quick input { padding: 9px 12px; border-radius: 10px; border: 1px solid var(--divider-color); font: inherit;
                 background: var(--primary-background-color); color: var(--primary-text-color); box-sizing:border-box; min-width:0; }
  .quick input[type=text] { flex: 1 1 200px; }
  .quick input[type=number] { width: 132px; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-top:8px; }
  .chip { padding: 4px 12px; font-size: 13px; border-radius: 14px; }
  .chip.on { background: rgba(238,75,43,.16); border-color: #ee4b2b; }
  .chip.start { padding-left: 8px; }
  .chip ha-icon { --mdc-icon-size: 16px; }
  .help { color: var(--secondary-text-color); font-size: 12px; }
  .hero-start { flex: 0 1 auto; }

  .card { background: var(--card-background-color); border-radius: 12px; border: 1px solid var(--divider-color);
          box-shadow: var(--ha-card-box-shadow, none); position: relative; overflow: hidden; }
  .card.task::before { content:""; position:absolute; left:0; top:0; bottom:0; width:4px; background: var(--divider-color); }
  .card.notifying::before { background: linear-gradient(#ffb04f, #ee4b2b); }
  .card.notifying { border-color: rgba(238,75,43,.55); }
  .card.going { border-color: #ee4b2b; box-shadow: 0 0 0 1px rgba(238,75,43,.35), var(--ha-card-box-shadow, none); }
  .card.snoozed::before { background: var(--primary-color); }
  .card.armed::before { background: #4caf50; }
  .card.held::before { background: #9c27b0; }
  .card.ghost { border-style: dashed; background: transparent; box-shadow: none; }
  .row { display:flex; align-items:center; gap:12px; padding: 12px 12px 12px 16px; flex-wrap: wrap; }
  .info { flex: 1 1 220px; min-width:0; }
  .name { font-size: 16px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  .line { color: var(--primary-text-color); opacity:.85; font-size: 14px; margin-top:3px; }
  .meta { color: var(--secondary-text-color); font-size: 12px; margin-top:4px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  .actions { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-left:auto; }
  .rel { font-variant-numeric: tabular-nums; }

  .orb { width:40px; height:40px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex:none;
         background: rgba(127,127,127,.18); color: var(--secondary-text-color); position:relative; }
  .orb.sm { width:34px; height:34px; }
  .orb.notifying { background: linear-gradient(135deg, #ffb04f, #ee4b2b); color:#fff; }
  .orb.notifying::after { content:""; position:absolute; inset:-4px; border-radius:50%; border:2px solid #ee4b2b; opacity:0;
                          animation: ring 1.8s ease-out infinite; }
  .orb.snoozed { background: rgba(3,169,244,.2); color: var(--primary-color); }
  .orb.armed { background: rgba(76,175,80,.2); color:#4caf50; }
  .orb.held { background: rgba(156,39,176,.2); color:#ba68c8; }
  .orb.ghost { background: transparent; border:1px dashed var(--divider-color); }
  @keyframes ring { 0% { transform: scale(.85); opacity:.7; } 100% { transform: scale(1.35); opacity:0; } }
  @media (prefers-reduced-motion: reduce) { .orb.notifying::after { animation:none; } }

  .pips { display:inline-flex; gap:3px; }
  .pips i { width:14px; height:5px; border-radius:3px; background: rgba(127,127,127,.3); }
  .pips i.on { background: linear-gradient(90deg, #ffb04f, #ee4b2b); }
  .badge { font-size: 11px; padding: 1px 8px; border-radius: 10px; background: rgba(127,127,127,.2); color: var(--secondary-text-color); }
  .badge.soon { background: rgba(3,169,244,.18); color: var(--primary-color); }
  .badge.auto { background: rgba(156,39,176,.18); color: #ce93d8; }
  .badge.warn { background: rgba(255,152,0,.15); color: var(--warning-color, #ff9800); }
  .badge.fin { background: rgba(238,75,43,.16); color: #ff8a65; }

  .banner { display:flex; align-items:center; gap:12px; flex-wrap:wrap; padding: 10px 14px; margin-bottom: 14px; border-radius: 12px;
            background: rgba(156,39,176,.12); border: 1px solid rgba(156,39,176,.4); }
  .banner .orb { background: rgba(156,39,176,.25); color:#ce93d8; }

  details { margin-bottom: 14px; }
  summary { cursor:pointer; color: var(--secondary-text-color); font-size: 13px; display:flex; align-items:center; gap:8px;
            padding: 6px 4px; list-style:none; }
  summary::-webkit-details-marker { display:none; }
  summary:hover { color: var(--primary-text-color); }
  .silence-body { background: var(--card-background-color); border:1px solid var(--divider-color); border-radius:12px; padding: 12px 14px; margin-top:4px; }
  .seg { display:inline-flex; border:1px solid var(--divider-color); border-radius:18px; overflow:hidden; margin-bottom:8px; }
  .seg button { border:none; border-radius:0; background:none; }
  .seg button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .hist { display:flex; flex-direction:column; margin-top:4px; }
  .hist-row { display:flex; align-items:center; gap:10px; padding: 6px 8px; font-size: 14px; border-radius: 8px; }
  .hist-row:nth-child(odd) { background: rgba(127,127,127,.07); }
  .hist-row ha-icon { --mdc-icon-size: 18px; color: var(--secondary-text-color); }
  .hist-row.done ha-icon { color: #4caf50; }
  .hist-row.expired ha-icon { color: var(--warning-color, #ff9800); }
  .hname { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .muted0 { color: var(--secondary-text-color); font-size: 12px; }

  .empty { color: var(--secondary-text-color); padding: 24px; text-align:center; }
  .empty.big { padding: 36px 24px 44px; }
  .empty-orb { width:64px; height:64px; margin: 0 auto 12px; border-radius:50%; display:flex; align-items:center; justify-content:center;
               background: linear-gradient(135deg, rgba(255,176,79,.25), rgba(238,75,43,.2)); color:#ee4b2b; }
  .empty-orb ha-icon { --mdc-icon-size: 32px; }
  .empty-title { font-size: 18px; color: var(--primary-text-color); margin-bottom: 4px; }
  .toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); background: #323232; color:#fff;
           padding: 10px 18px; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,.3); z-index: 10; max-width: 90vw; }
  @media (max-width: 700px) {
    .content { padding: 10px; }
    .actions { width:100%; margin-left:0; justify-content:flex-end; }
    .quick input[type=number] { width: 110px; }
  }
`;

if (!customElements.get("task-reminder-panel")) customElements.define("task-reminder-panel", TaskReminderPanel);
