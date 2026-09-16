const TITLES = {
  overview: ["Laboratórium", "Prehľad"],
  numbers: ["Frekvencia a omeškanie", "Čísla"],
  patterns: ["Štruktúra žrebov", "Vzory"],
  tests: ["Štatistická rigoróznosť", "Testy náhody"],
  learn: ["Walk-forward 1 → 990", "Self-improving"],
  predict: ["Laboratórne tikety", "Predikcia"],
  archive: ["990 oficiálnych žrebov", "Archív"],
  method: ["Ako čítať výsledky", "Metodika"],
};

const STRAT = {
  random: "Náhodný",
  hot: "Horúce",
  cold: "Studené",
  overdue: "Omeškané",
  balanced: "Vyvážený",
  lab: "Lab mix",
};

let DATA = null;
let eraKey = "current";
let view = "overview";
let selectedBall = null;
const charts = {};
let predictStrategy = "lab";

const $ = (id) => document.getElementById(id);
const era = () => DATA.eras[eraKey];
const fmt = (n, d = 0) =>
  Number(n).toLocaleString("sk-SK", { maximumFractionDigits: d, minimumFractionDigits: d });
const odds = (n) => "1 : " + fmt(n);

function zColor(z) {
  const t = Math.max(-1, Math.min(1, z / 2.2));
  if (t >= 0) {
    const a = 0.12 + t * 0.72;
    return `rgba(215, 176, 122, ${a})`;
  }
  const a = 0.12 + -t * 0.55;
  return `rgba(138, 167, 199, ${a})`;
}

function killCharts() {
  Object.values(charts).forEach((c) => c.destroy());
  Object.keys(charts).forEach((k) => delete charts[k]);
}

function barChart(id, labels, values, color = "#d7b07a") {
  const ctx = document.getElementById(id);
  if (!ctx || !window.Chart) return;
  charts[id] = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: color, borderWidth: 0, borderRadius: 6 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8d99a8", maxRotation: 0 }, grid: { display: false } },
        y: { ticks: { color: "#8d99a8" }, grid: { color: "rgba(42,51,64,0.7)" } },
      },
    },
  });
}

function lineChart(id, labels, values) {
  const ctx = document.getElementById(id);
  if (!ctx || !window.Chart) return;
  charts[id] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          data: values,
          borderColor: "#d7b07a",
          backgroundColor: "rgba(215,176,122,0.12)",
          fill: true,
          tension: 0.25,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8d99a8", maxTicksLimit: 12 }, grid: { display: false } },
        y: { ticks: { color: "#8d99a8" }, grid: { color: "rgba(42,51,64,0.7)" } },
      },
    },
  });
}

function balls(m, e) {
  return (
    `<span class="balls">` +
    m.map((n) => `<span class="ball main">${n}</span>`).join("") +
    `<span class="muted">+</span>` +
    e.map((n) => `<span class="ball euro">${n}</span>`).join("") +
    `</span>`
  );
}

function renderHonesty() {
  const e = era();
  const mix =
    eraKey === "all"
      ? " Toto obdobie mieša tri sady pravidiel — na predikciu použi aktuálnu éru."
      : "";
  $("honesty").textContent =
    DATA.disclaimer +
    ` Jedna stávka na 5+2 má šancu ${odds(e.jackpot_odds)}.` +
    mix;
  $("nextChip").textContent = `Ďalší žreb ${DATA.totals.next_draw} · jackpot ${fmt(
    DATA.totals.next_jackpot / 1e6,
    0
  )} mil. €`;
}

function renderOverview() {
  const e = era();
  const latest = DATA.latest
    .slice()
    .reverse()
    .map(
      (d) =>
        `<div class="archive-row"><span class="mono muted">#${d.id}</span><span>${d.date}</span><span class="muted">${
          d.dow === "Friday" ? "Pia" : "Uto"
        }</span>${balls(d.m, d.e)}<span class="${d.won ? "pos" : "muted"}">${
          d.won ? "jackpot" : "rollover"
        }</span></div>`
    )
    .join("");
  const findings = e.anomalies
    .map((f) => `<div class="finding ${f.severity}"><b>${f.title}</b>${f.detail}</div>`)
    .join("");
  $("view-overview").innerHTML = `
    <div class="grid grid-4">
      <article class="card stat"><div class="label">Žrebov v období</div><div class="value">${fmt(e.draws)}</div><div class="sub">${e.first} → ${e.last}</div></article>
      <article class="card stat"><div class="label">Jackpot 5+2</div><div class="value">${odds(e.jackpot_odds)}</div><div class="sub">${e.label}</div></article>
      <article class="card stat"><div class="label">Padnuté jackpoty</div><div class="value">${fmt(e.jackpot.jackpots_won)}</div><div class="sub">hit rate ${fmt(e.jackpot.hit_rate * 100, 1)} %</div></article>
      <article class="card stat"><div class="label">Chi-kvadrát p</div><div class="value">${e.chi_square_main.p_value.toFixed(3)}</div><div class="sub">hlavné čísla vs rovnomernosť</div></article>
    </div>
    <div class="grid grid-2" style="margin-top:16px">
      <article class="card">
        <h2>Posledné žreby</h2>
        ${latest}
      </article>
      <article class="card">
        <h2>Nálezová správa</h2>
        ${findings}
      </article>
    </div>
    <article class="card" style="margin-top:16px">
        <h2>Žreby po rokoch</h2>
      <div class="canvas-wrap"><canvas id="yearChart"></canvas></div>
    </article>`;
  lineChart(
    "yearChart",
    DATA.yearly.map((y) => String(y.year)),
    DATA.yearly.map((y) => y.draws)
  );
}

function heat(rows, selected) {
  return `<div class="heatmap">${rows
    .map((r) => {
      const sel = selected === r.number ? " selected" : "";
      return `<button class="cell${sel}" data-n="${r.number}" style="background:${zColor(
        r.z
      )}" title="${r.number}: ${r.count}×, z=${r.z}">${r.number}</button>`;
    })
    .join("")}</div>`;
}

function ballDetail(rows, n, kind) {
  const r = rows.find((x) => x.number === n);
  if (!r) return `<div class="detail muted">Klikni na číslo v mriežke.</div>`;
  const tone = r.z > 0.6 ? "pos" : r.z < -0.6 ? "neg" : "muted";
  return `<div class="detail">
    <b>${kind} ${r.number}</b>
    <p>Padlo <span class="mono">${r.count}</span>× pri očakávaní ${fmt(r.expected, 1)}.
    z = <span class="${tone}">${r.z}</span>, p = ${r.p_value.toFixed(3)}, FDR q = ${r.q_value.toFixed(3)}.</p>
    <p>Naposledy pred <span class="mono">${r.last_seen_ago}</span> žrebmi.
    Očakávaná medzera ${r.expected_gap}, priemerná ${r.avg_gap ?? "—"}.
    ${r.significant_fdr ? "Toto číslo prežíva FDR 5 %." : "Po korekcii na 50 testov nie je významné."}</p>
  </div>`;
}

function renderNumbers() {
  const e = era();
  selectedBall = selectedBall || e.overdue_main[0].number;
  $("view-numbers").innerHTML = `
    <div class="grid grid-2">
      <article class="card">
        <h2>Hlavné 1–50</h2>
        <p class="muted">Farba je z-skóre voči p = 5/50. Zlato = častejšie, oceľ = vzácnejšie.</p>
        ${heat(e.main_balls, selectedBall)}
        <div id="mainDetail" style="margin-top:12px">${ballDetail(e.main_balls, selectedBall, "Hlavné")}</div>
      </article>
      <article class="card">
        <h2>Euro 1–${e.euro_pool}</h2>
        ${heat(e.euro_balls, null)}
        <div class="grid" style="grid-template-columns:1fr 1fr;margin-top:16px">
          <div>
            <h3>Najčastejšie</h3>
            <table>${e.hottest_main
              .map(
                (r) =>
                  `<tr><td class="mono">${r.number}</td><td>${r.count}×</td><td class="${
                    r.z >= 0 ? "pos" : "neg"
                  }">z ${r.z}</td></tr>`
              )
              .join("")}</table>
          </div>
          <div>
            <h3>Najdlhšie čakajú</h3>
            <table>${e.overdue_main
              .map(
                (r) =>
                  `<tr><td class="mono">${r.number}</td><td>${r.last_seen_ago} žrebov</td><td class="muted">${r.overdue_ratio}× gap</td></tr>`
              )
              .join("")}</table>
          </div>
        </div>
      </article>
    </div>
    <article class="card" style="margin-top:16px">
      <h2>Euročísla — počty</h2>
      <div class="canvas-wrap"><canvas id="euroChart"></canvas></div>
    </article>`;
  barChart(
    "euroChart",
    e.euro_balls.map((r) => String(r.number)),
    e.euro_balls.map((r) => r.count),
    "#7eb8a8"
  );
  $("view-numbers").querySelectorAll(".heatmap .cell").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedBall = Number(btn.dataset.n);
      render();
    });
  });
}

function renderPatterns() {
  const e = era();
  const p = e.patterns;
  $("view-patterns").innerHTML = `
    <div class="grid grid-3">
      <article class="card">
        <h2>Párne / nepárne</h2>
        <div class="canvas-wrap"><canvas id="oddChart"></canvas></div>
      </article>
      <article class="card">
        <h2>Nízke 1–25 / vysoké 26–50</h2>
        <div class="canvas-wrap"><canvas id="lowChart"></canvas></div>
      </article>
      <article class="card">
        <h2>Susedné dvojice</h2>
        <div class="canvas-wrap"><canvas id="conChart"></canvas></div>
      </article>
    </div>
    <div class="grid grid-2" style="margin-top:16px">
      <article class="card">
        <h2>Súčet hlavných čísiel</h2>
        <p class="muted">Priemer ${fmt(p.sum.mean, 1)}, medián ${fmt(p.sum.median, 1)}, rozsah ${p.sum.min}–${p.sum.max}.</p>
        <div class="canvas-wrap"><canvas id="sumChart"></canvas></div>
      </article>
      <article class="card">
        <h2>Najčastejšie páry</h2>
        <p class="muted">Očakávanie jedného konkrétneho páru: ${fmt(e.pairs.expected_per_pair, 2)}×. Nevidených párov: ${fmt(e.pairs.unseen_pairs)} z ${fmt(e.pairs.possible_pairs)}.</p>
        <table>
          <tr><th>Pár</th><th>Počet</th><th>Δ</th></tr>
          ${e.pairs.hottest
            .slice(0, 12)
            .map(
              (r) =>
                `<tr><td class="mono">${r.a}–${r.b}</td><td>${r.count}</td><td class="${
                  r.delta >= 0 ? "pos" : "neg"
                }">${r.delta > 0 ? "+" : ""}${fmt(r.delta, 1)}</td></tr>`
            )
            .join("")}
        </table>
      </article>
    </div>
    <article class="card" style="margin-top:16px">
      <h2>Prekrytie s predchádzajúcim žrebom</h2>
      <p>Priemer spoločných hlavných čísiel: <span class="mono">${p.avg_overlap_with_previous}</span>.
      Teória (hypergeometrická): <span class="mono">${p.expected_overlap_with_previous}</span>.
      Ak by sa čísla „držali“, toto by bolo vyššie. Nie je.</p>
    </article>`;
  barChart(
    "oddChart",
    p.odd_even.map((r) => `${r.odd} nepár`),
    p.odd_even.map((r) => r.count)
  );
  barChart(
    "lowChart",
    p.low_high.map((r) => `${r.low_1_25} níz`),
    p.low_high.map((r) => r.count),
    "#8aa7c7"
  );
  barChart(
    "conChart",
    p.consecutive_pairs.map((r) => `${r.pairs} pár.`),
    p.consecutive_pairs.map((r) => r.count),
    "#7eb8a8"
  );
  barChart(
    "sumChart",
    p.sum.histogram.map((h) => String(h.from)),
    p.sum.histogram.map((h) => h.count)
  );
}

function renderTests() {
  const e = era();
  const bt = e.backtest;
  const rows = bt
    ? Object.entries(bt)
        .filter(([k]) => !k.startsWith("_"))
        .map(
          ([k, v]) =>
            `<tr><td>${STRAT[k] || k}</td><td class="mono">${v.avg_main_matches}</td><td class="mono">${
              v.avg_euro_matches
            }</td><td class="mono">${v.jackpots}</td><td class="mono">${v.any_prize_codes}</td><td class="mono">${
              v.relative_ev_index
            }</td><td class="muted">${v.trials} žrebov</td></tr>`
        )
        .join("")
    : "";
  $("view-tests").innerHTML = `
    <div class="grid grid-2">
      <article class="card">
        <h2>Rovnomernosť gúľ</h2>
        <p>Chi-kvadrát na 50 hlavných: χ² = ${e.chi_square_main.chi2}, df = ${e.chi_square_main.df},
        p = <b>${e.chi_square_main.p_value.toFixed(3)}</b>.</p>
        <p>${e.chi_square_main.interpretation}</p>
        <p>Euročísla: p = ${e.chi_square_euro.p_value.toFixed(3)}. ${e.chi_square_euro.interpretation}</p>
        <p class="muted">FDR-významných hlavných čísiel: ${e.main_balls.filter((r) => r.significant_fdr).length} / 50.</p>
      </article>
      <article class="card">
        <h2>Utorok vs piatok</h2>
        ${
          e.weekday
            ? `<p>${e.weekday.tuesday_draws} utorkov, ${e.weekday.friday_draws} piatkov.
            Priemerná suma ${e.weekday.tuesday_mean_sum} vs ${e.weekday.friday_mean_sum}.
            t = ${e.weekday.t_stat}, p = ${e.weekday.p_value.toFixed(3)}.</p><p>${e.weekday.interpretation}</p>`
            : "<p>V tomto období sa žrebuje len v piatok.</p>"
        }
        <p>Unikátne pätice: ${fmt(e.combinations.unique_main_sets)} / ${fmt(e.draws)}.
        Opakovaná plná kombinácia 5+2: ${e.combinations.repeated_full_tickets}.</p>
      </article>
    </div>
    <article class="card" style="margin-top:16px">
      <h2>Walk-forward backtest stratégií</h2>
      <p class="muted">Každý tiket sa skladá len z histórie pred daným žrebom, potom sa spáruje s reálnym výsledkom. Očakávaný priemer hlavných zásahov pri náhode je 0,50.</p>
      ${
        bt
          ? `<table><tr><th>Stratégia</th><th>Ø hlavné</th><th>Ø euro</th><th>5+2</th><th>výherné triedy</th><th>EV index</th><th></th></tr>${rows}</table>
             <p>${bt._baseline.note}</p>`
          : "<p>Backtest je spočítaný pre aktuálne pravidlá.</p>"
      }
    </article>
    <article class="card" style="margin-top:16px">
      <h2>Teoretické šance jednej stávky</h2>
      <table><tr><th>Zhoda</th><th>Pravdepodobnosť</th><th>1 ku</th></tr>
      ${e.prize_odds
        .map(
          (r) =>
            `<tr><td class="mono">${r.match_code}</td><td class="mono">${r.probability.toExponential(3)}</td><td class="mono">${fmt(
              r.odds_one_in
            )}</td></tr>`
        )
        .join("")}
      </table>
    </article>`;
}

function renderPredict() {
  const e = era();
  const bt = DATA.eras.current.backtest;
  $("view-predict").innerHTML = `
    <div class="warn">Toto nie je veštenie. Každý tiket má šancu ${odds(
      e.jackpot_odds
    )} na jackpot, bez ohľadu na to, či ide o horúce, studené alebo „vyvážené“ čísla. Backtest to potvrdzuje: náhoda drží krok so všetkými filtrami.</div>
    <div class="toolbar" id="stratBar" style="margin-top:16px">
      ${Object.entries(STRAT)
        .map(
          ([k, lab]) =>
            `<button data-s="${k}" class="${k === predictStrategy ? "active" : ""}">${lab}</button>`
        )
        .join("")}
      <button class="btn primary" id="genBtn">Vygenerovať 8 tiketov</button>
    </div>
    <div class="grid grid-2">
      <article class="card">
        <h2>Laboratórne tikety</h2>
        <div id="ticketBox" class="muted">Vyber stratégiu a vygeneruj tikety pre ďalší žreb ${DATA.totals.next_draw}.</div>
      </article>
      <article class="card">
        <h2>Čo ktorá stratégia robí</h2>
        <p><b>Náhodný</b> — čistý výber, referenčná šanca.</p>
        <p><b>Horúce / studené</b> — čísla s najvyšším / najnižším počtom v zvolenom období.</p>
        <p><b>Omeškané</b> — čísla, ktoré najdlhšie nešli. Gambler’s fallacy: medzera nemení p.</p>
        <p><b>Vyvážený</b> — 2–3 nepárne, 2–3 nízke, súčet 90–160, max. 1 susedný pár. Filtruje tvary, nie šancu.</p>
        <p><b>Lab mix</b> — 2 horúce, 2 omeškané, 1 náhodné. Hybrid na štúdium, nie na výhodu.</p>
        ${
          bt
            ? `<p class="muted" style="margin-top:12px">Walk-forward Ø hlavné zásahy: náhoda ${bt.random.avg_main_matches}, lab ${bt.lab.avg_main_matches}, horúce ${bt.hot.avg_main_matches}. Teória 0,50.</p>`
            : ""
        }
      </article>
    </div>`;
  $("stratBar").querySelectorAll("button[data-s]").forEach((b) => {
    b.addEventListener("click", () => {
      predictStrategy = b.dataset.s;
      render();
    });
  });
  $("genBtn").addEventListener("click", generateTickets);
}

async function generateTickets() {
  const box = $("ticketBox");
  box.textContent = "Počítam…";
  try {
    const url = `/api/tickets?strategy=${predictStrategy}&era=${eraKey}&n=8&seed=${Date.now() % 100000}`;
    const res = await fetch(url);
    const data = await res.json();
    box.innerHTML =
      `<p class="muted">${data.disclaimer}</p>` +
      data.tickets
        .map(
          (t, i) =>
            `<div class="ticket"><div><span class="muted">#${i + 1}</span> ${balls(t.mains, t.euros)}</div>
             <div class="muted mono">Σ ${t.sum} · nepár ${t.odd} · níz ${t.low} · sused ${t.consecutive}</div></div>`
        )
        .join("");
  } catch (err) {
    box.textContent = "Generovanie zlyhalo: " + err.message;
  }
}

function renderArchive() {
  $("view-archive").innerHTML = `
    <article class="card">
      <div class="toolbar">
        <input id="q" type="search" placeholder="Hľadaj dátum alebo čísla, napr. 11 20 31" />
      </div>
      <div id="archList"></div>
    </article>`;
  const drawList = (filter = "") => {
    const parts = filter.trim().split(/\s+/).filter(Boolean);
    const nums = parts.map((x) => Number(x)).filter((x) => x > 0);
    const text = filter.toLowerCase();
    const rows = DATA.draws
      .filter((d) => {
        if (eraKey !== "all" && eraKey !== "current" && d.era !== eraKey) return false;
        if (eraKey === "current" && d.era !== "2of12_tue_fri") return false;
        if (!filter) return true;
        const blob = `${d.date} ${d.m.join(" ")} ${d.e.join(" ")} #${d.id}`;
        if (text && blob.includes(text.replace(/\s+/g, " "))) return true;
        if (nums.length && nums.every((n) => d.m.includes(n) || d.e.includes(n))) return true;
        return false;
      })
      .slice()
      .reverse()
      .slice(0, 80);
    $("archList").innerHTML =
      `<p class="muted">${rows.length} zobrazených (najnovšie hore)</p>` +
      rows
        .map(
          (d) =>
            `<div class="archive-row"><span class="mono muted">#${d.id}</span><span>${d.date}</span><span class="muted">${
              d.dow === "Friday" ? "Pia" : "Uto"
            }</span>${balls(d.m, d.e)}<span class="${d.won ? "pos" : "muted"}">${fmt(
              (d.jackpot || 0) / 1e6,
              0
            )} mil.</span></div>`
        )
        .join("");
  };
  drawList("");
  $("q").addEventListener("input", (ev) => drawList(ev.target.value));
}

let LEARN = null;

async function loadLearn() {
  if (LEARN) return LEARN;
  try {
    LEARN = await fetch("/assets/learning.json").then((r) => {
      if (!r.ok) throw new Error("learning.json " + r.status);
      return r.json();
    });
  } catch (err) {
    LEARN = { error: String(err) };
  }
  return LEARN;
}

function renderLearn() {
  const root = $("view-learn");
  if (typeof window.renderLearnView === "function" && LEARN && !LEARN.error) {
    window.renderLearnView(LEARN, { killCharts, charts, fmt, balls });
    return;
  }
  if (!LEARN) {
    root.innerHTML = `<article class="card"><p class="muted">Načítavam 990 kôl učenia…</p></article>`;
    loadLearn().then(() => {
      if (view === "learn") render();
    });
    return;
  }
  if (LEARN.error) {
    root.innerHTML = `<article class="card"><p class="warn">Walk-forward ešte nie je pripravený: ${LEARN.error}</p></article>`;
    return;
  }
  const s = LEARN.summary;
  const nxt = (LEARN.next?.tickets || [])
    .map(
      (t) =>
        `<div class="ticket"><div><span class="muted">${t.x}</span> ${balls(t.m, t.e)}</div><div class="muted">${t.why || ""}</div></div>`
    )
    .join("");
  root.innerHTML = `
    <div class="warn">${LEARN.disclaimer}</div>
    <div class="grid grid-4" style="margin-top:16px">
      <article class="card stat"><div class="label">Kôl</div><div class="value">${fmt(LEARN.meta.draws)}</div><div class="sub">5 tiketov pred každým žrebom</div></article>
      <article class="card stat"><div class="label">Ø zásahy / kolo</div><div class="value">${s.avg_main_per_round}</div><div class="sub">náhoda ${s.random_per_round} · Δ ${s.delta_vs_random}</div></article>
      <article class="card stat"><div class="label">Ø na tiket</div><div class="value">${s.avg_main_per_ticket}</div><div class="sub">teória 0,50</div></article>
      <article class="card stat"><div class="label">Ďalší žreb</div><div class="value">${LEARN.meta.next_draw.slice(5)}</div><div class="sub">${LEARN.meta.next_draw}</div></article>
    </div>
    <article class="card" style="margin-top:16px">
      <h2>Päť konfigurácií na ${LEARN.next.draw}</h2>
      ${nxt}
    </article>
    <article class="card" style="margin-top:16px">
      <h2>Krokovač sa načíta z learn.js</h2>
      <p class="muted">Kompletné 990 kôl je v dátach. Rozšírené UI (krivka, váhy, krok po kroku) sa pripojí automaticky.</p>
    </article>`;
}

function renderMethod() {
  $("view-method").innerHTML = `
    <article class="card">
      <h2>Čo Prizma meria</h2>
      <p>Dataset: ${DATA.source}. Analýza je vždy viazaná na éru, lebo eurobazén sa menil z 8 na 10 a na 12 a od 25. 3. 2022 pribudol utorok.</p>
      <p>Každé hlavné číslo má v žrebe pravdepodobnosť 5/50. Euročíslo 2 / veľkosť bazéna. Binomický test a chi-kvadrát merajú odchýlku od tohto modelu. Na 50+12 testoch sa p-hodnoty korigujú Benjamini–Hochberg FDR, inak by „významné“ čísla vznikali samé od seba.</p>
        <p>Pred žrebom i smie laboratórium vidieť len 1…i−1. Dvadsiatka matematických tiketov, zásahy, perceptrón, Hedge, ďalší žreb. Únik budúcnosti je vylúčený. Tieň náhody (tiež 20 tiketov) beží vedľa.</p>
      <p>Predikcia je walk-forward: tiket sa skladá z minulosti a až potom sa porovná s budúcim žrebom. Ak by existoval ťažiteľný vzor, lab/hot/overdue by mali vyšší priemerný zásah ako náhoda. V dátach to nevidia.</p>
      <p>Jackpot 5+2 pri 2 z 12: ${odds(DATA.totals.current_odds)}. To sa stratégiou nemení.</p>
    </article>
    <article class="card" style="margin-top:16px">
      <h2>Čo tu zámerne nie je</h2>
      <p>Žiadny sľub výhry, žiadne „garantované čísla“, žiadna numerológia dátumu narodenia. Ak niečo vyzerá ako vzor (dlhá pauza čísla 32, horúca 11), Prizma to ukáže aj s tým, že po FDR to nie je dôkaz zaujatosti osudia.</p>
    </article>`;
}

const RENDER = {
  overview: renderOverview,
  numbers: renderNumbers,
  patterns: renderPatterns,
  tests: renderTests,
  learn: renderLearn,
  predict: renderPredict,
  archive: renderArchive,
  method: renderMethod,
};

function render() {
  killCharts();
  const [kicker, title] = TITLES[view];
  $("kicker").textContent = kicker;
  $("title").textContent = title;
  renderHonesty();
  document.querySelectorAll(".view").forEach((el) => el.classList.add("hidden"));
  $(`view-${view}`).classList.remove("hidden");
  RENDER[view]();
}

async function init() {
  DATA = await fetch("/assets/analysis.json").then((r) => r.json());
  loadLearn();
  document.querySelectorAll("#nav button").forEach((b) => {
    b.addEventListener("click", () => {
      view = b.dataset.view;
      document.querySelectorAll("#nav button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      render();
    });
  });
  $("era").addEventListener("change", (ev) => {
    eraKey = ev.target.value;
    selectedBall = null;
    render();
  });
  render();
}

init().catch((err) => {
  document.querySelector("main").insertAdjacentHTML(
    "afterbegin",
    `<p class="warn">Nepodarilo sa načítať analýzu: ${err.message}</p>`
  );
});
