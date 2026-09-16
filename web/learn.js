/* Prizma walk-forward lab. Slovak UI. Honesty first. */
(function () {
  "use strict";

  const ERA = {
    "2of8_friday": "2012–2014 · 2 z 8 · piatok",
    "2of10_friday": "2014–2022 · 2 z 10 · piatok",
    "2of12_tue_fri": "2022–teraz · 2 z 12 · utorok+piatok",
  };
  const WCOLORS = [
    "#d7b07a",
    "#7eb8a8",
    "#d98984",
    "#8aa7c7",
    "#f1d7a6",
    "#5e8f82",
    "#c9a06a",
    "#a8c4d8",
    "#e8c9a0",
    "#9d7a9c",
    "#6b8f71",
    "#c47c6c",
  ];

  const learnCharts = {};
  const state = {
    data: null,
    idx: 0,
    helpers: null,
    fetching: null,
  };

  const $ = (id) => document.getElementById(id);
  const rootEl = () => $("view-learn");
  const visible = () => {
    const el = rootEl();
    return !!(el && !el.classList.contains("hidden"));
  };

  const esc = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const fmt = (n, d = 0) => {
    if (state.helpers && typeof state.helpers.fmt === "function") {
      return state.helpers.fmt(n, d);
    }
    return Number(n).toLocaleString("sk-SK", {
      maximumFractionDigits: d,
      minimumFractionDigits: d,
    });
  };

  const fmtDate = (iso) => {
    if (!iso) return "—";
    const [y, m, d] = String(iso).slice(0, 10).split("-");
    if (!y) return esc(iso);
    return `${Number(d)}. ${Number(m)}. ${y}`;
  };

  const mil = (n) => (n == null ? "—" : `${fmt(n / 1e6, 0)} mil. €`);

  function codeRank(c) {
    const [m, e] = String(c || "0+0").split("+").map(Number);
    return (m || 0) * 10 + (e || 0);
  }

  function bestEver(counts) {
    let best = "0+0";
    let n = 0;
    Object.entries(counts || {}).forEach(([c, k]) => {
      if (codeRank(c) > codeRank(best) || (codeRank(c) === codeRank(best) && k > n)) {
        best = c;
        n = k;
      }
    });
    return { code: best, n };
  }

  function codeClass(c) {
    const r = codeRank(c);
    if (r >= 20) return "ok";
    if (r >= 10) return "mid";
    return "";
  }

  function expertName(id) {
    const ex = (state.data?.experts || []).find((e) => e.id === id);
    return ex ? ex.name : id;
  }

  function destroyCharts() {
    Object.keys(learnCharts).forEach((k) => {
      try {
        learnCharts[k].destroy();
      } catch {
        /* ignore */
      }
      delete learnCharts[k];
    });
    const shared = state.helpers && state.helpers.charts;
    if (shared) {
      ["learnCurve", "learnWeights"].forEach((k) => {
        if (shared[k]) {
          try {
            shared[k].destroy();
          } catch {
            /* ignore */
          }
          delete shared[k];
        }
      });
    }
  }

  const cursorPlugin = {
    id: "prizmaLearnCursor",
    afterDatasetsDraw(chart) {
      const x = chart.$cursorX;
      if (x == null || !chart.chartArea) return;
      const scale = chart.scales.x;
      const px = scale.getPixelForValue(x);
      if (!Number.isFinite(px)) return;
      const { top, bottom } = chart.chartArea;
      const ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = "rgba(215, 176, 122, 0.5)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(px, top);
      ctx.lineTo(px, bottom);
      ctx.stroke();
      ctx.restore();
    },
  };

  function chartDefaults() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#171d26",
          borderColor: "#2a3340",
          borderWidth: 1,
          titleColor: "#f1d7a6",
          bodyColor: "#e7edf5",
          padding: 10,
        },
      },
      scales: {
        x: {
          ticks: { color: "#8d99a8", maxTicksLimit: 10, font: { family: "IBM Plex Sans" } },
          grid: { display: false },
        },
        y: {
          ticks: { color: "#8d99a8", font: { family: "IBM Plex Sans" } },
          grid: { color: "rgba(42,51,64,0.7)" },
        },
      },
    };
  }

  function downsample(arr, maxN) {
    if (!arr || arr.length <= maxN) return arr || [];
    const step = Math.ceil(arr.length / maxN);
    const out = [];
    for (let i = 0; i < arr.length; i += step) out.push(arr[i]);
    const last = arr[arr.length - 1];
    if (out[out.length - 1] !== last) out.push(last);
    return out;
  }

  function paintCharts() {
    if (!window.Chart || !state.data) return;
    if (!window.__prizmaLearnCursor) {
      Chart.register(cursorPlugin);
      window.__prizmaLearnCursor = true;
    }
    Chart.defaults.font.family = "IBM Plex Sans, sans-serif";
    const curveEl = $("learnCurve");
    const wEl = $("learnWeights");
    if (!curveEl || !wEl) return;

    if (learnCharts.learnCurve && learnCharts.learnCurve.canvas !== curveEl) destroyCharts();
    if (learnCharts.learnWeights && learnCharts.learnWeights.canvas !== wEl) destroyCharts();

    const data = state.data;
    const share = (id, inst) => {
      learnCharts[id] = inst;
      if (state.helpers && state.helpers.charts) state.helpers.charts[id] = inst;
    };

    if (!learnCharts.learnCurve) {
      const curve = data.curve || [];
      const inst = new Chart(curveEl, {
        type: "line",
        data: {
          labels: curve.map((c) => c.i),
          datasets: [
            {
              label: "Model",
              data: curve.map((c) => c.rm),
              borderColor: "#d7b07a",
              backgroundColor: "rgba(215,176,122,0.10)",
              fill: true,
              tension: 0.22,
              pointRadius: 0,
              borderWidth: 1.8,
            },
            {
              label: "Náhodný tieň",
              data: curve.map((c) => c.rr),
              borderColor: "#8aa7c7",
              backgroundColor: "transparent",
              fill: false,
              tension: 0.22,
              pointRadius: 0,
              borderWidth: 1.5,
              borderDash: [5, 4],
            },
          ],
        },
        options: chartDefaults(),
      });
      share("learnCurve", inst);
    }

    if (!learnCharts.learnWeights) {
      const path = downsample(data.weight_path || [], 160);
      const feats = data.features || [];
      const inst = new Chart(wEl, {
        type: "line",
        data: {
          labels: path.map((p) => p.i),
          datasets: feats.map((f, i) => ({
            label: f.label,
            data: path.map((p) => (p.w || [])[i]),
            borderColor: WCOLORS[i % WCOLORS.length],
            backgroundColor: "transparent",
            tension: 0.18,
            pointRadius: 0,
            borderWidth: 1.4,
          })),
        },
        options: {
          ...chartDefaults(),
          plugins: {
            ...chartDefaults().plugins,
            legend: {
              display: true,
              position: "bottom",
              labels: {
                color: "#8d99a8",
                boxWidth: 10,
                boxHeight: 2,
                font: { size: 10, family: "IBM Plex Sans" },
                padding: 10,
              },
            },
          },
        },
      });
      share("learnWeights", inst);
    }

    syncCursors();
  }

  function syncCursors() {
    const step = currentStep();
    if (!step) return;
    const curve = learnCharts.learnCurve;
    if (curve) {
      const labels = curve.data.labels || [];
      const ix = labels.findIndex((l) => Number(l) === step.id);
      curve.$cursorX = ix >= 0 ? ix : state.idx;
      curve.update("none");
    }
    const w = learnCharts.learnWeights;
    if (w) {
      const labels = w.data.labels || [];
      let best = 0;
      labels.forEach((l, i) => {
        if (Number(l) <= step.id) best = i;
      });
      w.$cursorX = best;
      w.update("none");
    }
  }

  function currentStep() {
    const steps = state.data?.steps || [];
    return steps[state.idx] || null;
  }

  function clampIdx(i) {
    const n = (state.data?.steps || []).length;
    if (!n) return 0;
    return Math.max(0, Math.min(n - 1, i));
  }

  function setIdx(i, fromInput) {
    state.idx = clampIdx(i);
    paintStep();
    syncCursors();
    if (!fromInput) {
      const range = $("learnRange");
      const num = $("learnNum");
      const step = currentStep();
      if (range && step) {
        range.value = String(step.id);
        range.style.setProperty("--pct", pctOf(step.id));
      }
      if (num && step && document.activeElement !== num) num.value = String(step.id);
    }
  }

  function pctOf(id) {
    const n = state.data?.meta?.draws || (state.data?.steps || []).length || 1;
    return `${((id - 1) / Math.max(1, n - 1)) * 100}%`;
  }

  function hitsOf(ticket, am, ae) {
    const hm = Array.isArray(ticket.hm)
      ? ticket.hm
      : (ticket.m || []).filter((n) => (am || []).includes(n));
    const he = Array.isArray(ticket.he)
      ? ticket.he
      : (ticket.e || []).filter((n) => (ae || []).includes(n));
    return { hm, he };
  }

  function balls(nums, kind, hitSet, missMode) {
    return (nums || [])
      .map((n) => {
        const hit = hitSet && hitSet.has(n);
        const extra = missMode ? " miss" : hit ? " hit" : "";
        return `<span class="ball ${kind}${extra}">${n}</span>`;
      })
      .join("");
  }

  function weightBars(weights, features) {
    const w = weights || [];
    const maxAbs = Math.max(2.8, ...w.map((x) => Math.abs(x || 0)), 0.01);
    return (features || [])
      .map((f, i) => {
        const v = w[i] || 0;
        const pct = (Math.abs(v) / maxAbs) * 50;
        const side = v >= 0 ? "pos" : "neg";
        const style = v >= 0 ? `left:50%;width:${pct}%` : `right:50%;width:${pct}%`;
        return `<div class="wbar" title="${esc(f.label)}">
          <span class="wbar-lab">${esc(f.label)}</span>
          <div class="wbar-track"><i class="${side}" style="${style}"></i></div>
          <span class="wbar-val mono">${fmt(v, 2)}</span>
        </div>`;
      })
      .join("");
  }

  function missSets(step) {
    const coveredM = new Set();
    const coveredE = new Set();
    (step.t || []).forEach((t) => {
      (t.m || []).forEach((n) => coveredM.add(n));
      (t.e || []).forEach((n) => coveredE.add(n));
    });
    return {
      m: (step.am || []).filter((n) => !coveredM.has(n)),
      e: (step.ae || []).filter((n) => !coveredE.has(n)),
    };
  }

  function paintStep() {
    const host = $("learnStepBody");
    const step = currentStep();
    if (!host || !step) return;
    const miss = missSets(step);
    const s = step.s || {};
    const delta = (s.m || 0) - (s.rm || 0);
    const dCls = delta > 0 ? "pos" : delta < 0 ? "neg" : "muted";
    const bestNm = Math.max(0, ...(step.t || []).map((t) => t.nm || 0));

    const tickets = (step.t || [])
      .map((t) => {
        const { hm, he } = hitsOf(t, step.am, step.ae);
        const hitM = new Set(hm);
        const hitE = new Set(he);
        const isBest = t.nm === bestNm && bestNm > 0;
        const mut = t.mut
          ? `<span class="mut-badge" title="Online hybrid">mut ${esc(t.mut)}</span>`
          : "";
        return `<div class="learn-ticket${isBest ? " best" : ""}">
          <div class="expert">
            <b>${esc(expertName(t.x))}</b>
            <span class="muted mono">${esc(t.x)}</span>
            ${mut}
          </div>
          <span class="balls">${balls(t.m, "main", hitM)}${`<span class="muted">+</span>`}${balls(
            t.e,
            "euro",
            hitE
          )}</span>
          <span class="code ${codeClass(t.c)}">${esc(t.c)}</span>
        </div>`;
      })
      .join("");

    const missHtml =
      miss.m.length || miss.e.length
        ? `<span class="balls">${balls(miss.m, "main", null, true)}${
            miss.e.length ? `<span class="muted">+</span>` : ""
          }${balls(miss.e, "euro", null, true)}</span>`
        : `<span class="empty">Všetky padnuté čísla boli aspoň na jednom tikete.</span>`;

    host.innerHTML = `
      <div class="learn-actual">
        <span class="mono muted">#${step.id}</span>
        <span class="date-lg">${fmtDate(step.d)}</span>
        <span class="era-chip">${esc(ERA[step.era] || step.era)} · euro ${step.ep}</span>
        <span class="balls" title="Skutočný žreb">${balls(step.am, "main")}<span class="muted">+</span>${balls(
          step.ae,
          "euro"
        )}</span>
      </div>
      <div class="ticket-grid">${tickets}</div>
      <div class="learn-meta-grid">
        <div class="learn-lesson">
          <h3>Lekcia kola</h3>
          <p>${esc(step.l)}</p>
          <div class="learn-round-stats">
            <span>Model Σ hlavné <b>${fmt(s.m)}</b></span>
            <span>Náhodný tieň <b>${fmt(s.rm)}</b></span>
            <span class="${dCls}">Δ <b>${delta > 0 ? "+" : ""}${fmt(delta)}</b></span>
            <span>Unikátne <b>${fmt(s.u)}</b>/5</span>
            <span>Pokrytie <b>${fmt(s.cov || 0)}</b>/50</span>
            <span>Najlepší kód <b>${esc(s.b)}</b></span>
          </div>
          <div style="margin-top:14px">
            <h3>Mimo všetkých tiketov</h3>
            <div class="miss-list">${missHtml}</div>
          </div>
        </div>
        <div class="learn-side">
          <h3>Váhy po aktualizácii</h3>
          ${weightBars(step.w, state.data.features)}
          <h3 style="margin-top:14px">Hedge v tomto kole</h3>
          ${hedgePills(step.h, true)}
        </div>
      </div>`;

    const n = state.data.meta?.draws || (state.data.steps || []).length;
    const meta = $("learnRangeMeta");
    if (meta) {
      meta.innerHTML = `<span>Žreb <b>${fmtDate(step.d)}</b></span><span class="mono">${step.id} / ${n}</span>`;
    }
    document.querySelectorAll(".phase-table tbody tr").forEach((tr) => {
      const a = Number(tr.dataset.a);
      const b = Number(tr.dataset.b);
      tr.classList.toggle("active", step.id >= a && step.id <= b);
    });

    const first = $("learnFirst");
    const prev = $("learnPrev");
    const next = $("learnNext");
    const last = $("learnLast");
    if (first) first.disabled = state.idx === 0;
    if (prev) prev.disabled = state.idx === 0;
    if (next) next.disabled = state.idx >= n - 1;
    if (last) last.disabled = state.idx >= n - 1;
  }

  function hedgePills(h, compact) {
    const experts = state.data?.experts || [];
    const vals = h || [];
    const max = Math.max(0.0001, ...vals);
    return `<div class="hedge-pills">
      ${experts
        .map((ex, i) => {
          const p = vals[i] || 0;
          const lead = p === max && p > 0;
          return `<div class="hedge-pill${lead ? " lead" : ""}" title="${esc(ex.formula)}">
            <div class="hedge-pill-top">
              <span class="hedge-name">${esc(ex.name)}</span>
              <span class="hedge-val">${fmt(p * 100, compact ? 1 : 2)} %</span>
            </div>
            <div class="hedge-bar"><i style="width:${Math.max(1.5, p * 100)}%"></i></div>
          </div>`;
        })
        .join("")}
    </div>`;
  }

  function emptyHtml(kind, err) {
    if (kind === "loading") {
      return `<article class="card learn-empty">
        <div class="learn-pulse" aria-hidden="true"></div>
        <p class="kicker">Walk-forward</p>
        <h2>Načítavam 990 kôl</h2>
        <p>Sekvenčný zápisník sa práve skladá. Toto nie je sľub výhry — len záznam, čo model vedel pred každým žrebom.</p>
      </article>`;
    }
    return `<article class="card learn-empty">
      <p class="kicker">Walk-forward</p>
      <h2>Laboratórium ešte nie je pripravené</h2>
      <p>Súbor <span class="mono">learning.json</span> chýba alebo sa nepodarilo načítať.
      Walk-forward sa počíta mimo prehliadača. Šanca 5+2 ostáva 1 : 139 838 160.${
        err ? ` <span class="muted">(${esc(err)})</span>` : ""
      }</p>
    </article>`;
  }

  function shellHtml(data) {
    const s = data.summary || {};
    const meta = data.meta || {};
    const nxt = data.next || {};
    const best = bestEver(s.best_code_counts);
    const delta = s.delta_vs_random || 0;
    const dCls = delta > 0 ? "pos" : delta < 0 ? "neg" : "gold";
    const n = meta.draws || (data.steps || []).length || 990;
    const step = data.steps?.[state.idx] || data.steps?.[n - 1];
    const startId = step ? step.id : n;

    const nextTickets = (nxt.tickets || [])
      .map((t) => {
        const mut = t.mut
          ? `<span class="mut-badge" title="Online hybrid">mut ${esc(t.mut)}</span>`
          : "";
        return `<div class="next-ticket">
          <div class="expert">
            <b>${esc(expertName(t.x))}</b>
            <span class="muted mono">${esc(t.x)}</span>
            ${mut}
          </div>
          <div>
            <span class="balls">${balls(t.m, "main")}<span class="muted">+</span>${balls(t.e, "euro")}</span>
            <div class="why">${esc(t.why || "")}</div>
          </div>
        </div>`;
      })
      .join("");

    const phases = (data.phases || [])
      .map((p) => {
        const dd = (p.avg_m || 0) - (p.avg_r || 0);
        const cls = dd > 0 ? "pos" : dd < 0 ? "neg" : "muted";
        return `<tr data-a="${p.a}" data-b="${p.b}">
          <td class="mono">${p.a}–${p.b}</td>
          <td class="mono">${fmt(p.avg_m, 2)}</td>
          <td class="mono">${fmt(p.avg_r, 2)}</td>
          <td class="mono ${cls}">${dd > 0 ? "+" : ""}${fmt(dd, 2)}</td>
          <td class="mono">${esc(p.best)}</td>
          <td class="lesson-cell">${esc(p.lesson)}</td>
        </tr>`;
      })
      .join("");

    const rankRows = (s.ranking || [])
      .map(
        (r, i) => `<tr>
          <td class="mono">${i + 1}</td>
          <td>${esc(r.name)}</td>
          <td class="mono">${fmt(r.avg_main, 3)}</td>
          <td class="mono">${fmt(r.avg_euro, 3)}</td>
        </tr>`
      )
      .join("");
    const mutN = s.mutations || 0;
    const slope = s.slope_roll50;
    const slopeTxt =
      slope == null
        ? ""
        : `Sklon surových zásahov na kolo ${slope >= 0 ? "+" : ""}${fmt(slope, 5)} (p = ${fmt(
            s.slope_p,
            3
          )}). Rolling priemer by klamal významnosťou — toto je šum, nie hrana.`;

    return `
      <p class="learn-banner">${esc(data.disclaimer)} Toto <b>nezvyšuje</b> šancu na jackpot — je to sekvenčné laboratórium.</p>

      <div class="learn-kpis">
        <article class="card stat">
          <div class="label">Kôl</div>
          <div class="value">${fmt(n)}</div>
          <div class="sub">${fmtDate(meta.first)} → ${fmtDate(meta.last)} · ${meta.tickets_per_draw || 5} tiketov / kolo</div>
        </article>
        <article class="card stat">
          <div class="label">Ø zásahy 20 tiketov</div>
          <div class="value">${fmt(s.avg_main_per_round, 2)}</div>
          <div class="sub">náhodný tieň ${fmt(s.random_per_round, 2)} · teória ${fmt(
            s.expected_random_per_round || 10,
            2
          )}</div>
        </article>
        <article class="card stat">
          <div class="label">Najlepší match kód</div>
          <div class="value gold">${esc(best.code)}</div>
          <div class="sub">${fmt(best.n)}× za ${fmt(n)} kôl · nikdy 5+2</div>
        </article>
        <article class="card stat">
          <div class="label">Δ vs náhoda</div>
          <div class="value ${dCls}">${delta > 0 ? "+" : ""}${fmt(delta, 3)}</div>
          <div class="sub">Ø na tiket ${fmt(s.avg_main_per_ticket, 3)} vs 0,50</div>
        </article>
        <article class="card stat">
          <div class="label">Mutácie slotov</div>
          <div class="value">${fmt(mutN)}</div>
          <div class="sub">slabý expert → hybrid top-2 (online)</div>
        </article>
      </div>

      <article class="card">
        <div class="learn-chart-head">
          <div>
            <h2>Krivka učenia</h2>
            <p class="muted">Kĺzavý súčet 50 kôl — hlavné zásahy modelu vs náhodný tieň. ${esc(slopeTxt)}</p>
          </div>
          <div class="learn-legend">
            <span><i class="lg-model"></i>Model</span>
            <span><i class="lg-rand"></i>Náhodný tieň</span>
          </div>
        </div>
        <div class="canvas-wrap learn-canvas"><canvas id="learnCurve"></canvas></div>
      </article>

      <div class="learn-split">
        <article class="card">
          <h2>Evolúcia váh</h2>
          <p class="muted">Perceptrón na črtách čísla. Záporné váhy tlačia črtu preč; kladné ju ťahajú.</p>
          <div class="canvas-wrap learn-canvas"><canvas id="learnWeights"></canvas></div>
        </article>
        <article class="card">
          <h2>Hedge expertov</h2>
          <p class="muted">Konečné pravdepodobnosti po 990 aktualizáciách. Hedge mieša 20 expertov, nestrihá osudie.</p>
          ${hedgePills(s.final_hedge || nxt.hedge)}
        </article>
      </div>

      <article class="learn-step card" id="learnStep">
        <p class="learn-step-kicker">Krokovač · šípky ← →</p>
        <h2>Čo model vedel pred žrebom</h2>
        <p class="muted">Tikety vznikajú z histórie 1…i−1. Až potom sa porovnajú s reálnym ťahom. Únik budúcnosti je vylúčený.</p>
        <div class="learn-controls">
          <div class="learn-btns">
            <button type="button" id="learnFirst" title="Prvý žreb" aria-label="Prvý žreb">⏮</button>
            <button type="button" id="learnPrev" title="Predošlý" aria-label="Predošlý žreb">◀</button>
          </div>
          <div class="learn-range-wrap">
            <div class="learn-range-meta" id="learnRangeMeta"></div>
            <input class="learn-range" id="learnRange" type="range" min="1" max="${n}" value="${startId}"
              aria-label="Index žrebu" style="--pct:${pctOf(startId)}" />
          </div>
          <div class="learn-btns" style="justify-content:flex-end">
            <button type="button" id="learnNext" title="Ďalší" aria-label="Ďalší žreb">▶</button>
            <button type="button" id="learnLast" title="Posledný žreb" aria-label="Posledný žreb">⏭</button>
            <label class="learn-jump">kolo
              <input id="learnNum" type="number" min="1" max="${n}" value="${startId}" />
            </label>
          </div>
        </div>
        <div id="learnStepBody"></div>
      </article>

      <article class="card">
        <h2>Ďalší žreb ${fmtDate(nxt.draw || meta.next_draw)}</h2>
        <p class="next-rationale">${esc(nxt.rationale || "")} Jackpot ${mil(nxt.jackpot || meta.next_jackpot)}.</p>
        <div class="next-draw-grid">${nextTickets}</div>
      </article>

      <article class="card">
        <h2>Rebríček 20 expertov</h2>
        <p class="muted">Priemerné zásahy na tiket po 990 walk-forward kolách. Teória 0,50. Odchýlky v desatinách sú šum, nie hrana.</p>
        <table class="phase-table">
          <thead><tr><th>#</th><th>Expert</th><th>Ø hlavné</th><th>Ø euro</th></tr></thead>
          <tbody>${rankRows}</tbody>
        </table>
      </article>

      <article class="card">
        <h2>Desať fáz</h2>
        <p class="muted">Bloková suma: priemerné hlavné zásahy modelu vs tieň. Klikni riadok a skokovač preskočí na začiatok fázy.</p>
        <table class="phase-table">
          <thead>
            <tr>
              <th>Žreby</th>
              <th>Ø model</th>
              <th>Ø náhoda</th>
              <th>Δ</th>
              <th>Best</th>
              <th>Lekcia</th>
            </tr>
          </thead>
          <tbody>${phases}</tbody>
        </table>
      </article>

      <article class="card learn-method">
        <h2>Metodika laboratória</h2>
        <p><b>Walk-forward, bez úniku.</b> Pred žrebom i smie model vidieť len ťahy 1…i−1. Dvadsiatka expertov (teplotný rebrík skóre, Thompsonov bandit, spektrálny graf párov, Markov, tvarové filtre, dekádový rozptyl, max pokrytie) navrhne po jednom tikete. Až potom sa spočítajú zásahy.</p>
        <p><b>2. vrstva.</b> Po 6. tikete v kole sa čísla už použité penalizujú (spoločné pokrytie). Tikety, ktoré zdieľajú ≥4 hlavné, sa prestrelia. Po 80 kolách sa chronicky slabý slot mutuje na hybrid dvoch aktuálne najlepších expertov — vždy len z minulosti.</p>
        <p><b>Náhodný tieň</b> beží bok po boku s rovnakými 20 tiketmi. Očakávaný súčet hlavných zásahov je 10,0. Ak by existoval ťažiteľný vzor, krivka modelu by sa od tieňa odlepila nahor. Jackpot 5+2 ostáva 1 : 139 838 160.</p>
      </article>
    `;
  }

  function bind() {
    const range = $("learnRange");
    const num = $("learnNum");
    const go = (id) => {
      const steps = state.data.steps || [];
      const ix = steps.findIndex((s) => s.id === id);
      setIdx(ix >= 0 ? ix : id - 1);
    };

    $("learnFirst")?.addEventListener("click", () => setIdx(0));
    $("learnPrev")?.addEventListener("click", () => setIdx(state.idx - 1));
    $("learnNext")?.addEventListener("click", () => setIdx(state.idx + 1));
    $("learnLast")?.addEventListener("click", () => setIdx((state.data.steps || []).length - 1));

    range?.addEventListener("input", (ev) => {
      const id = Number(ev.target.value);
      range.style.setProperty("--pct", pctOf(id));
      if (num) num.value = String(id);
      go(id);
    });
    num?.addEventListener("change", (ev) => {
      const id = Number(ev.target.value);
      go(id);
      if (range && state.data.steps[state.idx]) {
        range.value = String(state.data.steps[state.idx].id);
        range.style.setProperty("--pct", pctOf(state.data.steps[state.idx].id));
      }
    });

    document.querySelectorAll(".phase-table tbody tr").forEach((tr) => {
      tr.addEventListener("click", () => go(Number(tr.dataset.a)));
    });
  }

  function showEmpty(kind, err) {
    const root = rootEl();
    if (!root) return;
    destroyCharts();
    root.innerHTML = emptyHtml(kind, err);
    delete root.dataset.built;
  }

  function mount(data) {
    const root = rootEl();
    if (!root || !data || data.error) return;
    const n = (data.steps || []).length;
    if (!root.dataset.built || root.dataset.n !== String(n)) {
      state.idx = n ? n - 1 : 0;
    } else if (state.idx >= n) {
      state.idx = Math.max(0, n - 1);
    }
    destroyCharts();
    root.innerHTML = `<div class="learn-lab">${shellHtml(data)}</div>`;
    root.dataset.built = "1";
    root.dataset.n = String(n);
    bind();
    paintStep();
    paintCharts();
  }

  async function loadJson() {
    if (state.data && !state.data.error) return state.data;
    if (state.fetching) return state.fetching;
    state.fetching = fetch("/assets/learning.json")
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then((d) => {
        state.data = d;
        return d;
      })
      .catch((err) => {
        state.data = { error: String(err.message || err) };
        return state.data;
      })
      .finally(() => {
        state.fetching = null;
      });
    return state.fetching;
  }

  /**
   * Public renderer.
   * @param {object} [LEARN]
   * @param {object} [helpers]  optional { fmt, charts, balls } from app.js
   */
  function renderLearn(LEARN, helpers) {
    const root = rootEl();
    if (!root) return;
    if (helpers) state.helpers = helpers;

    const incoming = LEARN && !LEARN.error ? LEARN : null;
    if (incoming) {
      state.data = incoming;
      mount(incoming);
      return;
    }
    if (LEARN && LEARN.error) {
      showEmpty("empty", LEARN.error);
      return;
    }
    if (state.data && !state.data.error) {
      mount(state.data);
      return;
    }
    showEmpty("loading");
    loadJson().then((d) => {
      if (!rootEl()) return;
      if (!d || d.error) showEmpty("empty", d && d.error);
      else mount(d);
    });
  }

  function onKey(ev) {
    if (!visible()) return;
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    const tag = (ev.target && ev.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (ev.key === "ArrowLeft") {
      ev.preventDefault();
      setIdx(state.idx - 1);
    } else if (ev.key === "ArrowRight") {
      ev.preventDefault();
      setIdx(state.idx + 1);
    } else if (ev.key === "Home") {
      ev.preventDefault();
      setIdx(0);
    } else if (ev.key === "End") {
      ev.preventDefault();
      setIdx((state.data?.steps || []).length - 1);
    }
  }

  function boot() {
    window.renderLearn = renderLearn;
    window.renderLearnView = function (LEARN, helpers) {
      renderLearn(LEARN, helpers);
    };
    document.addEventListener("keydown", onKey);
    window.addEventListener("hashchange", () => {
      if (location.hash.replace(/^#/, "") === "learn") {
        document.querySelector('#nav button[data-view="learn"]')?.click();
      }
    });
    const root = rootEl();
    if (root && !root.classList.contains("hidden")) {
      renderLearn(window.LEARN);
    } else if (location.hash.replace(/^#/, "") === "learn") {
      document.querySelector('#nav button[data-view="learn"]')?.click();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
