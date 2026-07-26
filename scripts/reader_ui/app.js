const $ = (sel) => document.querySelector(sel);

const state = {
  overview: null,
  chapter: null,
  view: "read",
  activeN: null,
};

function slugName(id) {
  if (!id) return "";
  if (id === "ENV") return "环境";
  if (id === "NARRATION") return "旁白";
  const i = id.indexOf(".");
  return i >= 0 ? id.slice(i + 1).replaceAll("_", " ") : id;
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

function badge(status) {
  const s = status || "none";
  return `<span class="badge ${esc(s)}">${esc(s)}</span>`;
}

function renderRail() {
  const ov = state.overview;
  $("#logline").textContent = ov.logline || "（无 seed.logline）";
  $("#rail-foot").textContent = ov.walk_root || "";
  const ol = $("#chapters");
  if (!ov.chapters.length) {
    ol.innerHTML = `<li class="empty" style="padding:0.5rem;color:#7f8b96">还没有章节产物</li>`;
    return;
  }
  ol.innerHTML = ov.chapters
    .map(
      (c) => `
      <li>
        <button type="button" data-n="${c.n}" class="${c.n === state.activeN ? "active" : ""}">
          <span class="ch-id">c${c.n} ${badge(c.status)}</span>
          <span class="ch-theme">${esc(c.theme || "（无 theme）")}</span>
        </button>
      </li>`
    )
    .join("");
  ol.querySelectorAll("button[data-n]").forEach((btn) => {
    btn.addEventListener("click", () => openChapter(Number(btn.dataset.n)));
  });
}

function beatHtml(b) {
  const who = `${esc(slugName(b.owner))} · ${esc(b.beat_id || "")}`;
  if (b.type === "dialogue" && b.dialogue) {
    return `<div class="beat dialogue">
      <div class="who">${who}</div>
      <div class="line"><strong>${esc(slugName(b.owner))}</strong>：${esc(b.dialogue.line)}</div>
      ${b.dialogue.subtext ? `<div class="subtext">潜台词：${esc(b.dialogue.subtext)}</div>` : ""}
    </div>`;
  }
  if (b.type === "thought" && b.thought) {
    return `<div class="beat thought">
      <div class="who">${who}</div>
      （${esc(b.thought.inner)}）
    </div>`;
  }
  const text = b.action?.stage || "";
  return `<div class="beat action">
    <div class="who">${who}</div>
    ${esc(text)}
  </div>`;
}

function renderScript(ch) {
  const el = $("#script");
  if (ch.blocked || !ch.script) {
    el.innerHTML = `
      <header class="chapter-head">
        <p class="kicker">c${ch.n} ${badge("blocked")}</p>
        <h1>本章未入库</h1>
        <p class="sub">Consistency Gate 挂起，ScriptStore 无此章。右侧可看违规。</p>
      </header>`;
    return;
  }
  const s = ch.script;
  const scenes = (s.scenes || [])
    .map((sc) => {
      const beats = (sc.beats || []).map(beatHtml).join("");
      return `<section class="scene">
        <header class="scene-head">
          <h2>${esc(sc.scene_id)} · ${esc(slugName(sc.location))}</h2>
          <p class="scene-meta">POV ${esc(slugName(sc.pov))}
            · cast ${(sc.cast || []).map((c) => esc(slugName(c.char))).join(" / ") || "—"}</p>
          <p class="scene-goal"><strong>目标</strong> ${esc(sc.goal || "—")}<br/>
            <strong>冲突</strong> ${esc(sc.conflict || "—")}</p>
        </header>
        ${beats || `<p class="empty">本场无拍</p>`}
      </section>`;
    })
    .join("");

  el.innerHTML = `
    <header class="chapter-head">
      <p class="kicker">${esc(s.chapter)} · ${esc(s.volume || "")} ${badge(s.consistency_status)}</p>
      <h1>${esc(s.theme || "（无 theme）")}</h1>
      <p class="sub">${esc(s.tone || "")}</p>
    </header>
    ${scenes || `<p class="empty">无场次</p>`}`;
}

function renderSide(ch) {
  const plan = ch.plan;
  const planEl = $("#side-plan");
  if (!plan) {
    planEl.innerHTML = `<p class="muted">无 plan.json</p>`;
  } else {
    const advances = (plan.thread_advances || [])
      .map((t) => `<li><code>${esc(t.thread_id)}</code> — ${esc(t.intent || "")}</li>`)
      .join("");
    const fs = (plan.foreshadow_ops || [])
      .map((f) => `<li><code>${esc(f.fs_id)}</code> ${esc(f.op)} <span class="muted">(${esc(f.reason || "")})</span></li>`)
      .join("");
    const beats = (plan.story_beats || [])
      .map((b) => `<li>${esc(b.seq)}. ${esc(b.gist || "")}</li>`)
      .join("");
    planEl.innerHTML = `
      <p><strong>目标</strong><br/>${esc(plan.chapter_goal || "—")}</p>
      <p style="margin-top:0.6rem"><strong>主线</strong></p>
      <ul>${advances || "<li class='muted'>无</li>"}</ul>
      <p style="margin-top:0.6rem"><strong>伏笔</strong></p>
      <ul>${fs || "<li class='muted'>无</li>"}</ul>
      <p style="margin-top:0.6rem"><strong>桥段</strong></p>
      <ul>${beats || "<li class='muted'>无</li>"}</ul>`;
  }

  const vios = ch.violations || [];
  const vioEl = $("#side-vios");
  if (!vios.length) {
    vioEl.innerHTML = `<p class="muted">无违规（或尚未写出）</p>`;
  } else {
    vioEl.innerHTML = vios
      .map((v) => {
        const sev = (v.severity || "").toLowerCase();
        const cls = sev === "block" ? "block" : sev === "advisory" ? "advisory" : "";
        const where = v.locus?.beat || v.locus?.scene || "";
        return `<div class="vio ${cls}">
          <div class="meta">${esc(v.severity)} / ${esc(v.category)} ${esc(where)} · ${esc(v.resolution || "")}</div>
          <div>${esc(v.message)}</div>
          ${v.suggestion ? `<div class="muted">建议：${esc(v.suggestion)}</div>` : ""}
        </div>`;
      })
      .join("");
  }

  const trace = ch.trace || [];
  $("#side-trace").innerHTML = trace.length
    ? trace.map((t) => `<div class="trace-line">${esc(t)}</div>`).join("")
    : `<p class="muted">无 trace</p>`;
}

async function openChapter(n) {
  state.activeN = n;
  state.view = "read";
  setView("read");
  renderRail();
  $("#script").innerHTML = `<p class="empty">加载 c${n}…</p>`;
  try {
    const ch = await api(`/api/chapters/${n}`);
    state.chapter = ch;
    renderScript(ch);
    renderSide(ch);
  } catch (e) {
    $("#script").innerHTML = `<p class="empty">加载失败：${esc(e.message)}</p>`;
  }
}

function renderGenesis(g) {
  const el = $("#genesis");
  const seed = g.seed || {};
  const l0 = g.l0 || {};
  const l1 = g.l1 || {};
  const l2 = g.l2 || {};
  const world = g.world || [];
  const spine = l2.volume_spine || {};
  const beats = (l2.chapter_beats || [])
    .map(
      (b) => `<div class="beat-card">
        <div class="seq">#${esc(b.planned_seq)} · ${esc(b.touches_spine)} · pov ${(b.pov_focus || []).map(slugName).map(esc).join("/")}</div>
        <div class="event">${esc(b.event)}</div>
        <div class="muted" style="margin-top:0.25rem;font-size:0.8rem">
          inherits: ${(b.inherits || []).map(esc).join(", ") || "—"}
          · leaves: ${(b.leaves_open || []).map(esc).join(", ") || "—"}
        </div>
      </div>`
    )
    .join("");

  el.innerHTML = `
    <h1>创世</h1>
    <p class="lead">${esc(seed.logline || "（无 seed）")}</p>

    <div class="block">
      <h2>Seed</h2>
      <div class="chips">${(seed.genre || []).map((x) => `<span class="chip">${esc(x)}</span>`).join("")}
        ${(seed.tone || []).map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</div>
      <p><strong>终局意图</strong><br/>${esc(seed.ending_intent || "—")}</p>
      <p style="margin-top:0.5rem"><strong>主角意图</strong></p>
      <ul>${(seed.protagonist_intent || []).map((x) => `<li>${esc(x)}</li>`).join("") || "<li>—</li>"}</ul>
    </div>

    <div class="block">
      <h2>L0</h2>
      <p>${esc(l0.logline || "—")}</p>
      <p style="margin-top:0.4rem" class="muted">${esc(l0.core_dramatic_question || "")}</p>
    </div>

    <div class="block">
      <h2>L1 主线 / 伏笔</h2>
      <p><strong>主线</strong></p>
      <ul>${(l1.threads || []).map((t) => `<li><code>${esc(t.thread_id)}</code> ${esc(t.desc || "")}</li>`).join("") || "<li>—</li>"}</ul>
      <p style="margin-top:0.5rem"><strong>伏笔</strong></p>
      <ul>${(l1.foreshadow_map || []).map((f) => `<li><code>${esc(f.fs_id)}</code> ${esc(f.desc || "")}</li>`).join("") || "<li>—</li>"}</ul>
    </div>

    <div class="block">
      <h2>L2 卷脊骨</h2>
      <p><strong>卷目标</strong> ${esc(l2.goal || "—")}</p>
      <ul>
        <li>pressure：${esc(spine.shared_pressure || "—")}</li>
        <li>inciting：${esc(spine.inciting || "—")}</li>
        <li>midpoint：${esc(spine.midpoint || "—")}</li>
        <li>climax：${esc(spine.climax || "—")}</li>
      </ul>
      <p style="margin-top:0.75rem"><strong>章事件链</strong></p>
      <div class="beat-chain">${beats || "<p class='muted'>—</p>"}</div>
    </div>

    <div class="block">
      <h2>World（${world.length}）</h2>
      <ul>${world.slice(0, 40).map((w) =>
        `<li><code>${esc(w.entity_id)}</code> ${esc(w.canonical_name || "")}
          <span class="muted">— ${esc((w.definition || "").slice(0, 80))}</span></li>`
      ).join("") || "<li>—</li>"}</ul>
    </div>

    <div class="block">
      <h2>Store 计数</h2>
      <div class="chips">
        ${Object.entries(g.store_counts || {}).map(([k, v]) =>
          `<span class="chip">${esc(k)} ${esc(v)}</span>`
        ).join("")}
      </div>
    </div>`;
}

function setView(name) {
  state.view = name;
  $("#view-read").hidden = name !== "read";
  $("#view-genesis").hidden = name !== "genesis";
  $("#nav-read").classList.toggle("active", name === "read");
  $("#nav-genesis").classList.toggle("active", name === "genesis");
}

async function openGenesis() {
  setView("genesis");
  $("#genesis").innerHTML = `<p class="empty">加载创世…</p>`;
  try {
    renderGenesis(await api("/api/genesis"));
  } catch (e) {
    $("#genesis").innerHTML = `<p class="empty">加载失败：${esc(e.message)}</p>`;
  }
}

async function boot() {
  $("#nav-read").addEventListener("click", () => setView("read"));
  $("#nav-genesis").addEventListener("click", () => openGenesis());
  try {
    state.overview = await api("/api/overview");
    renderRail();
    setView("read");
    if (state.overview.chapters.length) {
      await openChapter(state.overview.chapters[0].n);
    } else {
      $("#script").innerHTML = `<p class="empty">还没有 chapters/。先跑 walk auto。</p>`;
    }
  } catch (e) {
    $("#logline").textContent = `加载失败：${e.message}`;
  }
}

boot();
