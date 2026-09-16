"""Sequential self-improving Eurojackpot lab.

Walk-forward from draw 1 to draw N with ZERO leakage:
for each draw i twenty tickets are built only from draws 1..i-1,
then scored against the official result i, then the model updates.

Twenty mathematical experts submit one ticket each (temperature ladder,
Bayesian Thompson, spectral co-occurrence, Markov, shape filters, coverage).
Feature weights (per-ticket perceptron + L2 toward uniform) and Hedge
expert weights adapt after every round. A frozen random shadow portfolio
of 20 tickets is scored in parallel.

This does not change the 5+2 odds.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from engine.experts import (
        EURO_FEATURE_IDS,
        FEATURE_IDS,
        FEATURE_LABELS_SK as FEATURE_LABELS,
        PORTFOLIO,
        phi_euro as experts_phi_euro,
        phi_main as experts_phi_main,
        pick_hybrid,
        pick_named,
        pick_portfolio,
        resolve_mains_collisions,
    )
except ImportError:  # script run from engine/
    from experts import (  # type: ignore
        EURO_FEATURE_IDS,
        FEATURE_IDS,
        FEATURE_LABELS_SK as FEATURE_LABELS,
        PORTFOLIO,
        phi_euro as experts_phi_euro,
        phi_main as experts_phi_main,
        pick_hybrid,
        pick_named,
        pick_portfolio,
        resolve_mains_collisions,
    )

try:
    from engine.paths import ROOT, draws_csv
except ImportError:
    from paths import ROOT, draws_csv  # type: ignore

DATA = draws_csv()
OUT = ROOT / "web" / "assets" / "learning.json"

EXPERTS = [{"id": i, "name": n, "formula": f} for i, n, f in PORTFOLIO]
EXPERT_IDS = [e["id"] for e in EXPERTS]
N_TICKETS = len(EXPERT_IDS)
assert N_TICKETS == 20

ETA_W = 0.06
ETA_EURO = 0.045
ETA_HEDGE = 0.07
HEDGE_MIX = 0.12
L2 = 0.004
W_CLIP = 2.8
EWMA_A = 0.06
ROLL = 50


def load_draws() -> pd.DataFrame:
    df = pd.read_csv(DATA, parse_dates=["draw_date"])
    df["mains"] = df.apply(lambda r: [int(r[f"main_n{i}"]) for i in range(1, 6)], axis=1)
    df["euros"] = df.apply(lambda r: [int(r["euro_e1"]), int(r["euro_e2"])], axis=1)
    return df.sort_values("draw_id").reset_index(drop=True)


class State:
    """Sufficient statistics of the PAST only."""

    def __init__(self) -> None:
        self.n = 0
        self.main_c = [0] * 51
        self.euro_c = [0] * 13
        self.main_last = [-1] * 51
        self.euro_last = [-1] * 13
        self.prev_mains: list[int] | None = None
        self.prev_euros: list[int] | None = None
        self.recent: deque[list[int]] = deque(maxlen=20)
        self.pair: dict[tuple[int, int], int] = defaultdict(int)
        self.ewma_main = [0.1] * 51
        self.ewma_euro = [0.0] * 13
        self.sum_lo = 90
        self.sum_hi = 160
        self.sum_window: deque[int] = deque(maxlen=30)
        self.w = np.zeros(len(FEATURE_IDS), dtype=float)
        self.w_euro = np.zeros(len(EURO_FEATURE_IDS), dtype=float)
        self.hedge = np.ones(len(EXPERT_IDS), dtype=float) / len(EXPERT_IDS)
        self.skill = [deque(maxlen=40) for _ in EXPERT_IDS]
        self.mutate_map: dict[str, tuple[str, str]] = {}
        self.mutation_log: list[dict] = []

    def view(self, euro_pool: int) -> dict:
        return {
            "n": self.n,
            "euro_pool": euro_pool,
            "main_c": self.main_c,
            "euro_c": self.euro_c,
            "main_last": self.main_last,
            "euro_last": self.euro_last,
            "prev_mains": self.prev_mains,
            "prev_euros": self.prev_euros,
            "recent_mains": list(self.recent),
            "pair": self.pair,
            "ewma_main": self.ewma_main,
            "ewma_euro": self.ewma_euro,
            "sum_lo": self.sum_lo,
            "sum_hi": self.sum_hi,
        }

    def observe(self, mains: list[int], euros: list[int], euro_pool: int) -> None:
        idx = self.n
        for a, b in _pairs(mains):
            self.pair[(a, b)] += 1
        for k in range(1, 51):
            hit = 1.0 if k in mains else 0.0
            self.ewma_main[k] = (1 - EWMA_A) * self.ewma_main[k] + EWMA_A * hit
            if hit:
                self.main_c[k] += 1
                self.main_last[k] = idx
        p_e = 2 / max(euro_pool, 2)
        for k in range(1, euro_pool + 1):
            if self.ewma_euro[k] == 0.0 and self.n == 0:
                self.ewma_euro[k] = p_e
            hit = 1.0 if k in euros else 0.0
            self.ewma_euro[k] = (1 - EWMA_A) * self.ewma_euro[k] + EWMA_A * hit
            if hit:
                self.euro_c[k] += 1
                self.euro_last[k] = idx
        self.recent.append(list(mains))
        self.prev_mains = list(mains)
        self.prev_euros = list(euros)
        self.sum_window.append(sum(mains))
        if len(self.sum_window) >= 12:
            med = float(np.median(self.sum_window))
            # slowly chase the empirical centre without collapsing the band
            centre = 0.7 * 125 + 0.3 * med
            half = 35
            self.sum_lo = int(max(60, centre - half))
            self.sum_hi = int(min(190, centre + half))
        self.n += 1

    def maybe_mutate(self, draw_id: int) -> None:
        """Replace chronically weak slots with a hybrid of the current top two."""
        if self.n < 80:
            return
        means = [float(np.mean(s)) if s else 0.5 for s in self.skill]
        order = sorted(range(len(EXPERT_IDS)), key=lambda i: means[i])
        best = [EXPERT_IDS[i] for i in order[-3:][::-1]]
        med = float(np.median(means))
        protected = {"cover", "score_greedy", "typical"}
        # drop recovered mutants
        for eid in list(self.mutate_map):
            idx = EXPERT_IDS.index(eid)
            if means[idx] >= med - 0.01:
                del self.mutate_map[eid]
                self.mutation_log.append(
                    {"i": draw_id, "slot": eid, "action": "restore", "via": None}
                )
        worst = [EXPERT_IDS[i] for i in order if EXPERT_IDS[i] not in protected][:3]
        pairs = [
            (best[0], best[1]),
            (best[0], best[2] if len(best) > 2 else best[1]),
            (best[1], best[2] if len(best) > 2 else best[0]),
        ]
        for k, eid in enumerate(worst):
            idx = EXPERT_IDS.index(eid)
            if means[idx] >= med - 0.04:
                continue
            pair = pairs[k % 3]
            if eid in pair:
                pair = tuple(x for x in best if x != eid)[:2]
                if len(pair) < 2:
                    continue
            prev = self.mutate_map.get(eid)
            if prev != pair:
                self.mutate_map[eid] = pair
                self.mutation_log.append(
                    {"i": draw_id, "slot": eid, "action": "hybrid", "via": f"{pair[0]}+{pair[1]}"}
                )


def _pairs(nums: list[int]) -> list[tuple[int, int]]:
    s = sorted(nums)
    return [(s[i], s[j]) for i in range(len(s)) for j in range(i + 1, len(s))]


def phi_main(st: State, k: int, euro_pool: int = 12) -> np.ndarray:
    return np.array(experts_phi_main(st.view(euro_pool), k), dtype=float)


def phi_euro(st: State, k: int, euro_pool: int) -> np.ndarray:
    return np.array(experts_phi_euro(st.view(euro_pool), k), dtype=float)


def propose_portfolio(st: State, euro_pool: int, rng: random.Random) -> list[dict]:
    view = st.view(euro_pool)
    packed = pick_portfolio(view, st.w, st.w_euro, rng)
    rebuilt: list[tuple[str, list[int], list[int]]] = []
    for eid, m, e in packed:
        mut = st.mutate_map.get(eid)
        if mut:
            m, e = pick_hybrid(view, st.w, st.w_euro, rng, mut[0], mut[1])
        rebuilt.append((eid, m, e))

    def factory_for(eid: str):
        mut = st.mutate_map.get(eid)
        if mut:
            return lambda: pick_hybrid(view, st.w, st.w_euro, rng, mut[0], mut[1])
        used = [mm for _eid, mm, _ee in rebuilt]
        return lambda: pick_named(eid, view, st.w, st.w_euro, rng, used)

    rebuilt = resolve_mains_collisions(rebuilt, factory_for, rng)
    tickets = []
    for eid, m, e in rebuilt:
        item = {"x": eid, "m": m, "e": e}
        mut = st.mutate_map.get(eid)
        if mut:
            item["mut"] = f"{mut[0]}+{mut[1]}"
        tickets.append(item)
    return tickets


def random_portfolio(euro_pool: int, rng: random.Random, n: int = N_TICKETS) -> list[tuple[list[int], list[int]]]:
    out = []
    seen = set()
    for _ in range(n):
        for _try in range(40):
            m = tuple(sorted(rng.sample(range(1, 51), 5)))
            e = tuple(sorted(rng.sample(range(1, euro_pool + 1), 2)))
            if (m, e) not in seen:
                seen.add((m, e))
                out.append((list(m), list(e)))
                break
    return out


def score_ticket(m, e, am, ae) -> dict:
    hm = sorted(set(m) & set(am))
    he = sorted(set(e) & set(ae))
    return {
        "hm": hm,
        "he": he,
        "nm": len(hm),
        "ne": len(he),
        "c": f"{len(hm)}+{len(he)}",
    }


def _prize(code: str) -> bool:
    return code in {
        "5+2",
        "5+1",
        "5+0",
        "4+2",
        "4+1",
        "4+0",
        "3+2",
        "3+1",
        "3+0",
        "2+2",
        "2+1",
        "1+2",
    }


def update_weights(st: State, tickets: list[dict], am: list[int], ae: list[int], euro_pool: int) -> None:
    """Per-ticket perceptron so a 20-ticket cover set does not drown the gradient."""
    drawn_m = set(am)
    drawn_e = set(ae)
    grad = np.zeros_like(st.w)
    g_e = np.zeros_like(st.w_euro)
    n_t = max(len(tickets), 1)
    for t in tickets:
        picked_m = set(t["m"])
        picked_e = set(t["e"])
        for k in range(1, 51):
            phi = phi_main(st, k, euro_pool)
            if k in drawn_m and k in picked_m:
                grad += phi
            elif k in drawn_m and k not in picked_m:
                grad += 0.35 * phi
            elif k not in drawn_m and k in picked_m:
                grad -= 0.85 * phi
        for k in range(1, euro_pool + 1):
            phi = phi_euro(st, k, euro_pool)
            if k in drawn_e and k in picked_e:
                g_e += phi
            elif k in drawn_e and k not in picked_e:
                g_e += 0.35 * phi
            elif k not in drawn_e and k in picked_e:
                g_e -= 0.85 * phi
    st.w += ETA_W * (grad / n_t)
    st.w -= L2 * st.w
    st.w = np.clip(st.w, -W_CLIP, W_CLIP)
    st.w[0] *= 0.5

    st.w_euro += ETA_EURO * (g_e / n_t)
    st.w_euro -= L2 * st.w_euro
    st.w_euro = np.clip(st.w_euro, -W_CLIP, W_CLIP)
    st.w_euro[0] *= 0.5

    rewards = np.array([t["nm"] + 0.4 * t["ne"] for t in tickets], dtype=float)
    centered = rewards - rewards.mean()
    eta_t = ETA_HEDGE / math.sqrt(max(1, st.n))
    st.hedge *= np.exp(eta_t * centered)
    st.hedge = np.clip(st.hedge, 1e-6, None)
    st.hedge /= st.hedge.sum()
    st.hedge = (1.0 - HEDGE_MIX) * st.hedge + HEDGE_MIX / len(st.hedge)


def lesson_sk(step_id: int, tickets: list[dict], am, ae, s: dict, st: State, prev_w: np.ndarray) -> str:
    best = max(tickets, key=lambda t: (t["nm"], t["ne"]))
    names = {e["id"]: e["name"] for e in EXPERTS}
    union = {x for t in tickets for x in t["m"]}
    missed = [x for x in am if x not in union]
    hit_all = [x for x in am if x in union]
    dw = st.w - prev_w
    top_feat = int(np.argmax(np.abs(dw[1:]))) + 1
    feat = FEATURE_LABELS[top_feat]
    direction = "zvýšila" if dw[top_feat] > 0 else "znížila"

    bits = []
    if step_id == 1:
        bits.append("Štart bez histórie: tikety z čistej kombinatoriky a Gumbel výberu.")
    bits.append(
        f"Najlepší expert {names.get(best['x'], best['x'])} trafil {best['nm']} hlavných a {best['ne']} euro ({best['c']})."
    )
    bits.append(
        f"Dvadsiatka tiketov spolu {s['m']} hlavných zásahov (unikátne {s['u']}/5, pokrytie bazéna {s.get('cov', '?')}/50), tieň náhody {s['rm']}."
    )
    if missed:
        bits.append(f"Na žiadnom tikete neboli {', '.join(map(str, missed))} — tie ťahajú črty smerom k sebe.")
    else:
        bits.append(f"Všetky padnuté hlavné ({', '.join(map(str, hit_all))}) boli aspoň na jednom z 20 tiketov.")
    if s["m"] < s["rm"]:
        bits.append("Náhoda bola v tomto kole lepšia; Hedge trestá slabších expertov.")
    elif s["m"] > s["rm"]:
        bits.append("Model prekonal tieň náhody v tomto kole — ešte to nie je dôkaz hrany.")
    bits.append(f"Najväčší posun váhy: {feat} sa {direction}.")
    by_id = {t["x"]: t for t in tickets}
    od = by_id.get("overdue")
    sc = by_id.get("score") or by_id.get("score_greedy")
    th = by_id.get("thompson")
    if od and sc:
        if od["nm"] > sc["nm"]:
            bits.append("Omeškané dnes prebili naučený skór — to je často šťastie, nie dlh.")
        elif od["nm"] < sc["nm"]:
            bits.append("Naučený skór trafil viac ako omeškané; gambler’s fallacy v tomto kole nepomohla.")
    if th and sc and th["nm"] > sc["nm"]:
        bits.append("Thompsonov bandit dnes prebil bodový skór — posterior vzorka mala šťastie.")
    return " ".join(bits)


def _linreg_p(ys: list[float]) -> tuple[float, float]:
    n = len(ys)
    if n < 30:
        return 0.0, 1.0
    x = np.arange(n, dtype=float)
    y = np.array(ys, dtype=float)
    xm, ym = x.mean(), y.mean()
    varx = ((x - xm) ** 2).sum()
    if varx <= 0:
        return 0.0, 1.0
    slope = ((x - xm) * (y - ym)).sum() / varx
    intercept = ym - slope * xm
    pred = intercept + slope * x
    resid = y - pred
    dof = n - 2
    sse = (resid ** 2).sum()
    se = math.sqrt(sse / dof / varx) if dof > 0 else 1.0
    t = slope / se if se > 0 else 0.0
    # two-sided p from normal approximation
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2))))
    return float(slope), float(min(1.0, p))


def run() -> dict:
    df = load_draws()
    st = State()
    rng = random.Random(20120323)
    rng_shadow = random.Random(990990)

    steps = []
    curve = []
    weight_path = []
    skill_path = []
    model_hist: list[int] = []
    rand_hist: list[int] = []
    best_codes: Counter[str] = Counter()
    prize_tickets = 0
    prize_rounds = 0
    total_main = 0
    total_unique = 0
    total_rand = 0
    total_tickets_main = 0

    for i, row in df.iterrows():
        draw_id = int(row["draw_id"])
        euro_pool = int(row["euro_pool_size"])
        am = list(map(int, row["mains"]))
        ae = list(map(int, row["euros"]))
        prev_w = st.w.copy()

        tickets = propose_portfolio(st, euro_pool, rng)
        shadow = random_portfolio(euro_pool, rng_shadow)

        scored = []
        round_m = 0
        round_e = 0
        union: set[int] = set()
        covered: set[int] = set()
        for t in tickets:
            sc = score_ticket(t["m"], t["e"], am, ae)
            t.update(sc)
            scored.append(t)
            round_m += sc["nm"]
            round_e += sc["ne"]
            union |= set(sc["hm"])
            covered |= set(t["m"])
            best_codes[sc["c"]] += 1
            total_tickets_main += sc["nm"]
            if _prize(sc["c"]):
                prize_tickets += 1
        rand_m = sum(len(set(m) & set(am)) for m, _e in shadow)
        best = max(scored, key=lambda t: (t["nm"], t["ne"]))
        if any(_prize(t["c"]) for t in scored):
            prize_rounds += 1

        s = {
            "m": round_m,
            "e": round_e,
            "u": len(union),
            "b": best["c"],
            "rm": rand_m,
            "cov": len(covered),
        }
        update_weights(st, scored, am, ae, euro_pool)
        for t in scored:
            st.skill[EXPERT_IDS.index(t["x"])].append(t["nm"] + 0.4 * t["ne"])
        text = lesson_sk(draw_id, scored, am, ae, s, st, prev_w)

        compact_t = []
        for t in scored:
            row_t = {
                "x": t["x"],
                "m": t["m"],
                "e": t["e"],
                "hm": t["hm"],
                "he": t["he"],
                "c": t["c"],
                "nm": t["nm"],
                "ne": t["ne"],
            }
            if t.get("mut"):
                row_t["mut"] = t["mut"]
            compact_t.append(row_t)
        active_mut = {k: f"{a}+{b}" for k, (a, b) in st.mutate_map.items()}
        steps.append(
            {
                "id": draw_id,
                "d": row["draw_date"].date().isoformat(),
                "era": row["era"],
                "ep": euro_pool,
                "am": am,
                "ae": ae,
                "t": compact_t,
                "s": s,
                "l": text,
                "w": [round(float(x), 4) for x in st.w],
                "h": [round(float(x), 4) for x in st.hedge],
                "mut": active_mut or None,
            }
        )

        model_hist.append(round_m)
        rand_hist.append(rand_m)
        total_main += round_m
        total_unique += len(union)
        total_rand += rand_m

        wstart = max(0, len(model_hist) - ROLL)
        curve.append(
            {
                "i": draw_id,
                "rm": round(float(np.mean(model_hist[wstart:])), 4),
                "rr": round(float(np.mean(rand_hist[wstart:])), 4),
                "u": round(float(np.mean([x["s"]["u"] for x in steps[wstart:]])), 4),
            }
        )
        if draw_id == 1 or draw_id % 10 == 0 or draw_id == len(df):
            weight_path.append({"i": draw_id, "w": [round(float(x), 4) for x in st.w]})
            skill_path.append(
                {
                    "i": draw_id,
                    "s": [
                        round(float(np.mean(q)), 4) if q else 0.5 for q in st.skill
                    ],
                }
            )

        st.observe(am, ae, euro_pool)
        st.maybe_mutate(draw_id)

    n = len(df)
    # p-value must use raw per-round hits. Rolling-50 means are autocorrelated
    # and manufacture tiny "significant" slopes from noise.
    slope, slope_p = _linreg_p([float(x) for x in model_hist])
    expert_stats = {}
    for eid in EXPERT_IDS:
        ms = [t["nm"] for stt in steps for t in stt["t"] if t["x"] == eid]
        es = [t["ne"] for stt in steps for t in stt["t"] if t["x"] == eid]
        expert_stats[eid] = {
            "avg_main": round(float(np.mean(ms)), 4),
            "avg_euro": round(float(np.mean(es)), 4),
            "tickets": len(ms),
        }
    peak = max(steps, key=lambda x: (x["s"]["m"], x["s"]["u"]))
    cover5 = [x["id"] for x in steps if x["s"]["u"] == 5]
    phases = []
    chunk = max(1, n // 10)
    for p in range(10):
        a = p * chunk
        b = n if p == 9 else min(n, (p + 1) * chunk)
        block = steps[a:b]
        if not block:
            continue
        avg_m = float(np.mean([x["s"]["m"] for x in block]))
        avg_r = float(np.mean([x["s"]["rm"] for x in block]))
        # dominant lesson tag from hedge movement
        hs = np.mean([x["h"] for x in block], axis=0)
        champ = EXPERTS[int(np.argmax(hs))]["name"]
        worst = EXPERTS[int(np.argmin(hs))]["name"]
        delta = avg_m - avg_r
        verb = "nad náhodou" if delta > 0.05 else ("pod náhodou" if delta < -0.05 else "tesne s náhodou")
        phases.append(
            {
                "a": block[0]["id"],
                "b": block[-1]["id"],
                "avg_m": round(avg_m, 3),
                "avg_r": round(avg_r, 3),
                "best": max(block, key=lambda x: x["s"]["m"])["s"]["b"],
                "lesson": (
                    f"Žreby {block[0]['id']}–{block[-1]['id']}: Ø {avg_m:.2f} vs náhoda {avg_r:.2f} ({verb}). "
                    f"Hedge drží {champ}, najslabší {worst}."
                ),
            }
        )

    # next draw tickets from the trained state (after last observe)
    last = df.iloc[-1]
    next_pool = 12
    next_draw = str(last["next_draw_date"])[:10]
    next_jackpot = float(last["next_jackpot_eur"]) if pd.notna(last["next_jackpot_eur"]) else None
    why = {i: f for i, _n, f in PORTFOLIO}
    nxt = propose_portfolio(st, next_pool, random.Random(20260918))
    next_tickets = []
    for t in nxt:
        item = {"x": t["x"], "m": t["m"], "e": t["e"], "why": why.get(t["x"], "")}
        if t.get("mut"):
            item["mut"] = t["mut"]
            item["why"] = f"Mutant {t['mut']}. " + item["why"]
        next_tickets.append(item)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disclaimer": (
            "Walk-forward bez úniku budúcnosti: tiket na žreb i vzniká len z 1…i−1. "
            "Dvadsiatka stávok nemení šancu 1 : 139 838 160 na 5+2. Učenie mení, KTORÉ kombinácie "
            "posielame, nie pravdepodobnosť osudia. Tieň náhody ide bok po boku."
        ),
        "meta": {
            "draws": n,
            "tickets_per_draw": N_TICKETS,
            "first": df.iloc[0]["draw_date"].date().isoformat(),
            "last": df.iloc[-1]["draw_date"].date().isoformat(),
            "next_draw": next_draw,
            "next_jackpot": next_jackpot,
        },
        "experts": EXPERTS,
        "features": [{"id": i, "label": l} for i, l in zip(FEATURE_IDS, FEATURE_LABELS)],
        "summary": {
            "total_main_hits": int(total_main),
            "avg_main_per_ticket": round(total_tickets_main / (n * N_TICKETS), 4),
            "avg_main_per_round": round(total_main / n, 4),
            "avg_unique_mains": round(total_unique / n, 4),
            "random_per_ticket": 0.5,
            "random_per_round": round(total_rand / n, 4),
            "expected_random_per_round": round(0.5 * N_TICKETS, 2),
            "best_code_counts": dict(best_codes.most_common()),
            "any_prize_tickets": prize_tickets,
            "any_prize_rounds": prize_rounds,
            "delta_vs_random": round(total_main / n - total_rand / n, 4),
            "slope_roll50": round(slope, 6),
            "slope_p": round(slope_p, 4),
            "final_weights": [round(float(x), 4) for x in st.w],
            "final_hedge": [round(float(x), 4) for x in st.hedge],
            "expert_stats": expert_stats,
            "peak_round": {"id": peak["id"], "date": peak["d"], "mains": peak["s"]["m"], "unique": peak["s"]["u"]},
            "full_cover_rounds": cover5[:20],
            "full_cover_count": len(cover5),
            "mutations": len(st.mutation_log),
            "mutation_log": st.mutation_log[-40:],
            "ranking": sorted(
                (
                    {
                        "id": eid,
                        "name": next(e["name"] for e in EXPERTS if e["id"] == eid),
                        **expert_stats[eid],
                    }
                    for eid in EXPERT_IDS
                ),
                key=lambda r: -r["avg_main"],
            ),
        },
        "curve": curve,
        "weight_path": weight_path,
        "skill_path": skill_path,
        "steps": steps,
        "phases": phases,
        "next": {
            "draw": next_draw,
            "jackpot": next_jackpot,
            "tickets": next_tickets,
            "weights": [round(float(x), 4) for x in st.w],
            "hedge": [round(float(x), 4) for x in st.hedge],
            "rationale": (
                "Týchto 20 konfigurácií je výstup 2. vrstvy: spoločné pokrytie, "
                "diverzifikácia duplicít a online mutácia slabých slotov hybridom top expertov. "
                "Žiadna z nich nemá inú šancu na 5+2 ako ktorýkoľvek iný tiket."
            ),
        },
    }
    return payload


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = run()
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    s = payload["summary"]
    print("wrote", OUT, "bytes", OUT.stat().st_size)
    print("draws", payload["meta"]["draws"])
    print("avg_main_per_round", s["avg_main_per_round"], "random", s["random_per_round"], "delta", s["delta_vs_random"])
    print("avg_main_per_ticket", s["avg_main_per_ticket"], "theory 0.5")
    print("best_codes_top", list(s["best_code_counts"].items())[:8])
    print("slope_roll50", s["slope_roll50"], "p", s["slope_p"])
    print("hedge", s["final_hedge"])
    print("next", payload["next"]["draw"], [(t["x"], t["m"], t["e"]) for t in payload["next"]["tickets"]])


if __name__ == "__main__":
    main()
