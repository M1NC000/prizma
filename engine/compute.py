"""Prizma statistical engine for complete Eurojackpot history.

All frequency work is era-aware. Uniformity tests use the exact
hypergeometric draw model: each main ball has p = 5/50 per draw,
each euro ball has p = 2/euro_pool.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

try:
    from engine.paths import ROOT, data_dir
except ImportError:
    from paths import ROOT, data_dir  # type: ignore

DATA = data_dir()
OUT = ROOT / "web" / "assets"

ERA_LABEL = {
    "2of8_friday": "2012–2014 · 2 z 8 · piatok",
    "2of10_friday": "2014–2022 · 2 z 10 · piatok",
    "2of12_tue_fri": "2022–teraz · 2 z 12 · utorok+piatok",
    "current": "Aktuálne pravidlá (2 z 12)",
    "all": "Celá história (pozor: zmiešané pravidlá)",
}

JACKPOT_ODDS = {
    8: math.comb(50, 5) * math.comb(8, 2),
    10: math.comb(50, 5) * math.comb(10, 2),
    12: math.comb(50, 5) * math.comb(12, 2),
}


def load_draws() -> pd.DataFrame:
    df = pd.read_csv(DATA / "eurojackpot_draws.csv", parse_dates=["draw_date"])
    df["mains"] = df.apply(
        lambda r: [int(r[f"main_n{i}"]) for i in range(1, 6)], axis=1
    )
    df["euros"] = df.apply(lambda r: [int(r["euro_e1"]), int(r["euro_e2"])], axis=1)
    return df.sort_values("draw_id").reset_index(drop=True)


def subset(df: pd.DataFrame, era: str) -> pd.DataFrame:
    if era == "all":
        return df
    if era == "current":
        return df[df["era"] == "2of12_tue_fri"].reset_index(drop=True)
    return df[df["era"] == era].reset_index(drop=True)


def euro_pool_of(df: pd.DataFrame) -> int:
    return int(df["euro_pool_size"].iloc[-1]) if len(df) else 12


def bh_fdr(pvals: list[float]) -> list[float]:
    n = len(pvals)
    order = np.argsort(pvals)
    q = np.empty(n)
    prev = 1.0
    for rank, idx in enumerate(order[::-1], start=0):
        i = n - rank
        prev = min(prev, pvals[idx] * n / i)
        q[idx] = prev
    return [float(min(1.0, x)) for x in q]


def prize_probabilities(euro_pool: int) -> list[dict]:
    total = math.comb(50, 5) * math.comb(euro_pool, 2)
    rows = []
    for k in range(5, -1, -1):
        for e in range(2, -1, -1):
            if k == 0 and e < 2:
                continue
            if k == 1 and e != 2:
                continue
            if k == 2 and e == 0:
                continue
            ways_m = math.comb(5, k) * math.comb(45, 5 - k) if 5 - k <= 45 else 0
            ways_e = math.comb(2, e) * math.comb(euro_pool - 2, 2 - e)
            if 5 - k > 45 or 2 - e > euro_pool - 2:
                ways = 0
            else:
                ways = ways_m * ways_e
            code = f"{k}+{e}"
            if ways == 0:
                continue
            rows.append(
                {
                    "match_code": code,
                    "ways": ways,
                    "probability": ways / total,
                    "odds_one_in": round(total / ways),
                }
            )
    # keep official 12 classes only
    official = {
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
    return [r for r in rows if r["match_code"] in official]


def ball_stats(series_of_lists, pool: int, drawn: int) -> list[dict]:
    n = len(series_of_lists)
    counts = Counter()
    last_seen = {i: None for i in range(1, pool + 1)}
    gaps = defaultdict(list)
    for idx, nums in enumerate(series_of_lists):
        for x in nums:
            if last_seen[x] is not None:
                gaps[x].append(idx - last_seen[x])
            counts[x] += 1
            last_seen[x] = idx
    p = drawn / pool
    expected = n * p
    variance = n * p * (1 - p)  # Bernoulli per draw (presence), good approximation
    rows = []
    pvals = []
    for num in range(1, pool + 1):
        c = counts.get(num, 0)
        z = (c - expected) / math.sqrt(variance) if variance > 0 else 0.0
        # two-sided binomial test
        pval = float(stats.binomtest(c, n, p, alternative="two-sided").pvalue)
        overdue = n - 1 - last_seen[num] if last_seen[num] is not None else n
        exp_gap = 1 / p
        rows.append(
            {
                "number": num,
                "count": c,
                "expected": round(expected, 3),
                "delta": round(c - expected, 3),
                "z": round(z, 3),
                "p_value": pval,
                "frequency": round(c / n, 6) if n else 0,
                "last_seen_ago": overdue,
                "expected_gap": round(exp_gap, 2),
                "avg_gap": round(float(np.mean(gaps[num])), 2) if gaps[num] else None,
                "max_gap": int(max(gaps[num])) if gaps[num] else overdue,
                "overdue_ratio": round(overdue / exp_gap, 3) if exp_gap else None,
            }
        )
        pvals.append(pval)
    qvals = bh_fdr(pvals)
    for row, q in zip(rows, qvals):
        row["q_value"] = q
        row["significant_fdr"] = bool(q < 0.05)
    return rows


def pair_stats(series_of_lists, pool: int, drawn: int, top: int = 15) -> dict:
    n = len(series_of_lists)
    # P(specific pair both drawn) = C(pool-2, drawn-2) / C(pool, drawn)
    p_pair = math.comb(pool - 2, drawn - 2) / math.comb(pool, drawn)
    expected = n * p_pair
    counts = Counter()
    for nums in series_of_lists:
        for a, b in combinations(sorted(nums), 2):
            counts[(a, b)] += 1
    ranked = []
    for (a, b), c in counts.most_common():
        ranked.append(
            {
                "a": a,
                "b": b,
                "count": c,
                "expected": round(expected, 3),
                "delta": round(c - expected, 3),
                "ratio": round(c / expected, 3) if expected else None,
            }
        )
    never = []
    all_pairs = math.comb(pool, 2)
    observed_pairs = len(counts)
    return {
        "possible_pairs": all_pairs,
        "observed_pairs": observed_pairs,
        "unseen_pairs": all_pairs - observed_pairs,
        "pair_probability": p_pair,
        "expected_per_pair": round(expected, 4),
        "hottest": ranked[:top],
        "coldest_seen": sorted(ranked, key=lambda r: r["count"])[:top],
    }


def pattern_rows(df: pd.DataFrame) -> dict:
    odd = Counter()
    low = Counter()
    consec = Counter()
    sums = []
    decades = Counter()
    repeat_prev = 0
    prev = None
    for nums in df["mains"]:
        o = sum(x % 2 for x in nums)
        l = sum(x <= 25 for x in nums)
        c = sum(1 for a, b in zip(nums, nums[1:]) if b == a + 1)
        odd[o] += 1
        low[l] += 1
        consec[c] += 1
        sums.append(sum(nums))
        for x in nums:
            decades[x // 10 if x < 50 else 4] += 1
        if prev is not None:
            repeat_prev += len(set(nums) & set(prev))
        prev = nums
    n = len(df)
    return {
        "odd_even": [{"odd": k, "even": 5 - k, "count": odd[k]} for k in range(6)],
        "low_high": [{"low_1_25": k, "high_26_50": 5 - k, "count": low[k]} for k in range(6)],
        "consecutive_pairs": [{"pairs": k, "count": consec[k]} for k in range(5)],
        "sum": {
            "mean": round(float(np.mean(sums)), 2),
            "median": round(float(np.median(sums)), 2),
            "std": round(float(np.std(sums)), 2),
            "min": int(min(sums)),
            "max": int(max(sums)),
            "histogram": _hist(sums, bins=range(15, 246, 10)),
        },
        "decades": [
            {
                "label": lab,
                "count": int(decades[i]),
                "share": round(decades[i] / (n * 5), 4),
            }
            for i, lab in enumerate(["1–9", "10–19", "20–29", "30–39", "40–50"])
        ],
        "avg_overlap_with_previous": round(repeat_prev / max(n - 1, 1), 4),
        "expected_overlap_with_previous": round(25 / 49, 4),
    }


def _hist(values, bins) -> list[dict]:
    bins = list(bins)
    counts, edges = np.histogram(values, bins=bins)
    out = []
    for c, a, b in zip(counts, edges[:-1], edges[1:]):
        out.append({"from": int(a), "to": int(b) - 1, "count": int(c)})
    return out


def chi_square_uniform(ball_rows: list[dict], n_draws: int, drawn: int, pool: int) -> dict:
    observed = [r["count"] for r in ball_rows]
    expected = [n_draws * drawn / pool] * pool
    chi2, p = stats.chisquare(observed, expected)
    return {
        "chi2": round(float(chi2), 4),
        "df": pool - 1,
        "p_value": float(p),
        "interpretation": (
            "Rozdelenie je zlučiteľné s čistou náhodou (p ≥ 0.05)."
            if p >= 0.05
            else "Odchýlka od rovnomernosti je štatisticky nápadná pred korekciou. Pozri FDR na jednotlivých číslach."
        ),
    }


def weekday_test(df: pd.DataFrame) -> dict | None:
    if "Tuesday" not in set(df["weekday_name"]) or "Friday" not in set(df["weekday_name"]):
        return None
    tue = df[df["weekday_name"] == "Tuesday"]
    fri = df[df["weekday_name"] == "Friday"]
    # compare mean main sum
    tstat, p = stats.ttest_ind(
        [sum(x) for x in tue["mains"]],
        [sum(x) for x in fri["mains"]],
        equal_var=False,
    )
    return {
        "tuesday_draws": int(len(tue)),
        "friday_draws": int(len(fri)),
        "tuesday_mean_sum": round(float(np.mean([sum(x) for x in tue["mains"]])), 2),
        "friday_mean_sum": round(float(np.mean([sum(x) for x in fri["mains"]])), 2),
        "t_stat": round(float(tstat), 3),
        "p_value": float(p),
        "interpretation": (
            "Utorok vs piatok sa v sume hlavných čísiel nelíši (p ≥ 0.05)."
            if p >= 0.05
            else "Priemerná suma sa medzi utorkom a piatkom líši na hladine 5 % — overiť, či nejde o náhodný výkyv."
        ),
    }


def jackpot_geometry(df: pd.DataFrame, euro_pool: int) -> dict:
    hits = df["jackpot_won"].astype(bool).tolist()
    streaks = []
    run = 0
    for h in hits:
        if h:
            streaks.append(run)
            run = 0
        else:
            run += 1
    if run:
        streaks.append(run)  # current open rollover as unfinished, keep separately
    p = 1 / JACKPOT_ODDS[euro_pool]
    # empirical hit rate among these draws is not 1/odds because many tickets exist;
    # jackpot_won is about whether ANY ticket won, which depends on tickets sold.
    return {
        "jackpots_won": int(df["jackpot_won"].sum()),
        "hit_rate": round(float(df["jackpot_won"].mean()), 4),
        "mean_advertised": round(float(df["advertised_jackpot_eur"].mean()), 0),
        "max_advertised": float(df["advertised_jackpot_eur"].max()),
        "open_rollover_draws": run,
        "theoretical_single_ticket_p": p,
        "theoretical_single_ticket_odds": JACKPOT_ODDS[euro_pool],
    }


def combination_uniqueness(df: pd.DataFrame) -> dict:
    mains = [tuple(x) for x in df["mains"]]
    full = [tuple(m) + tuple(e) for m, e in zip(df["mains"], df["euros"])]
    return {
        "unique_main_sets": len(set(mains)),
        "repeated_main_sets": len(mains) - len(set(mains)),
        "unique_full_tickets": len(set(full)),
        "repeated_full_tickets": len(full) - len(set(full)),
    }


def anomalies(main_rows: list[dict], euro_rows: list[dict], combos: dict) -> list[dict]:
    findings = []
    for r in main_rows:
        if r["q_value"] < 0.05:
            findings.append(
                {
                    "severity": "high",
                    "title": f"Hlavné číslo {r['number']} prežíva FDR filter",
                    "detail": (
                        f"Padlo {r['count']}× pri očakávaní {r['expected']}, "
                        f"z={r['z']}, q={r['q_value']:.4f}."
                    ),
                }
            )
    for r in euro_rows:
        if r["q_value"] < 0.05:
            findings.append(
                {
                    "severity": "high",
                    "title": f"Euročíslo {r['number']} prežíva FDR filter",
                    "detail": (
                        f"Padlo {r['count']}× pri očakávaní {r['expected']}, "
                        f"z={r['z']}, q={r['q_value']:.4f}."
                    ),
                }
            )
    if combos["repeated_full_tickets"] == 0:
        findings.append(
            {
                "severity": "info",
                "title": "Žiadna plná kombinácia sa nikdy nezopakovala",
                "detail": "5+2 sa v histórii nevyskytla dvakrát. Pri priestore 139 miliónov kombinácií je to očakávané.",
            }
        )
    overdue = sorted(main_rows, key=lambda r: r["overdue_ratio"] or 0, reverse=True)[:3]
    for r in overdue:
        if (r["overdue_ratio"] or 0) >= 3:
            findings.append(
                {
                    "severity": "watch",
                    "title": f"Číslo {r['number']} je ťažko omeškané",
                    "detail": (
                        f"Nešlo {r['last_seen_ago']} žrebov, očakávaná medzera je "
                        f"{r['expected_gap']}. Pri náhode sú dlhé medzery bežné."
                    ),
                }
            )
    if not any(f["severity"] == "high" for f in findings):
        findings.insert(
            0,
            {
                "severity": "ok",
                "title": "Žiadna odchýlka neprežila korekciu na mnohonásobné testy",
                "detail": (
                    "Po Benjamini–Hochberg FDR na 50 hlavných + euročíslach "
                    "nie je dôkaz, že by nejaká guľa bola systematicky iná."
                ),
            },
        )
    return findings


def pick_ticket(history: pd.DataFrame, strategy: str, rng: random.Random) -> tuple[list[int], list[int]]:
    euro_pool = euro_pool_of(history)
    if strategy == "random":
        return sorted(rng.sample(range(1, 51), 5)), sorted(rng.sample(range(1, euro_pool + 1), 2))
    if strategy == "balanced":
        for _ in range(400):
            m = sorted(rng.sample(range(1, 51), 5))
            odd = sum(x % 2 for x in m)
            low = sum(x <= 25 for x in m)
            consec = sum(1 for a, b in zip(m, m[1:]) if b == a + 1)
            if odd in (2, 3) and low in (2, 3) and 90 <= sum(m) <= 160 and consec <= 1:
                return m, sorted(rng.sample(range(1, euro_pool + 1), 2))
        return sorted(rng.sample(range(1, 51), 5)), sorted(rng.sample(range(1, euro_pool + 1), 2))

    mains_hist = history["mains"].tolist()
    euros_hist = history["euros"].tolist()
    main_rows = ball_stats(mains_hist, 50, 5)
    euro_rows = ball_stats(euros_hist, euro_pool, 2)

    def take(rows, key, reverse, k, pool, field_n=14):
        ranked = [r["number"] for r in sorted(rows, key=lambda r: r[key], reverse=reverse)]
        source = ranked[: max(k, min(field_n, len(ranked)))]
        if len(source) >= k:
            return sorted(rng.sample(source, k))
        picked = list(source)
        while len(picked) < k:
            x = rng.randint(1, pool)
            if x not in picked:
                picked.append(x)
        return sorted(picked)

    if strategy == "hot":
        return take(main_rows, "count", True, 5, 50), take(euro_rows, "count", True, 2, euro_pool)
    if strategy == "cold":
        return take(main_rows, "count", False, 5, 50), take(euro_rows, "count", False, 2, euro_pool)
    if strategy == "overdue":
        return (
            take(main_rows, "last_seen_ago", True, 5, 50),
            take(euro_rows, "last_seen_ago", True, 2, euro_pool),
        )
    if strategy == "lab":
        picked = take(main_rows, "count", True, 2, 50, 10)
        for x in take(main_rows, "last_seen_ago", True, 6, 50, 12):
            if x not in picked:
                picked.append(x)
            if len(picked) == 4:
                break
        while len(picked) < 5:
            x = rng.randint(1, 50)
            if x not in picked:
                picked.append(x)
        euros = take(euro_rows, "count", True, 1, euro_pool, 6)
        for x in take(euro_rows, "last_seen_ago", True, 3, euro_pool, 6):
            if x not in euros:
                euros.append(x)
            if len(euros) == 2:
                break
        while len(euros) < 2:
            x = rng.randint(1, euro_pool)
            if x not in euros:
                euros.append(x)
        return sorted(picked), sorted(euros)
    return pick_ticket(history, "random", rng)


def score_ticket(mains, euros, actual_m, actual_e) -> dict:
    km = len(set(mains) & set(actual_m))
    ke = len(set(euros) & set(actual_e))
    return {"main": km, "euro": ke, "code": f"{km}+{ke}"}


def backtest(df: pd.DataFrame, warmup: int = 80, seed: int = 7) -> dict:
    """Walk-forward: ticket from past-only data, scored on the next draw."""
    strategies = ["random", "hot", "cold", "overdue", "balanced", "lab"]
    strat_seed = {"random": 0, "hot": 11, "cold": 23, "overdue": 37, "balanced": 41, "lab": 53}
    out = {}
    n = len(df)
    if n <= warmup + 10:
        warmup = max(20, n // 3)
    for strat in strategies:
        rng = random.Random(seed + strat_seed[strat])
        scores = []
        prize = 0
        for i in range(warmup, n):
            hist = df.iloc[:i]
            m, e = pick_ticket(hist, strat, rng)
            sc = score_ticket(m, e, df.iloc[i]["mains"], df.iloc[i]["euros"])
            scores.append(sc)
            # rough prize units: jackpot=1e6 points, down to consolation
            prize += _fake_ev(sc["main"], sc["euro"])
        codes = Counter(s["code"] for s in scores)
        out[strat] = {
            "trials": len(scores),
            "avg_main_matches": round(float(np.mean([s["main"] for s in scores])), 4),
            "avg_euro_matches": round(float(np.mean([s["euro"] for s in scores])), 4),
            "jackpots": codes.get("5+2", 0),
            "five_plus_one": codes.get("5+1", 0),
            "any_prize_codes": int(
                sum(
                    v
                    for k, v in codes.items()
                    if k
                    in {
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
                )
            ),
            "code_histogram": dict(sorted(codes.items())),
            "relative_ev_index": round(prize / max(len(scores), 1), 4),
        }
    # expected main matches for random ticket = 5 * 5 / 50 = 0.5
    out["_baseline"] = {
        "expected_avg_main_matches": 0.5,
        "expected_avg_euro_matches": round(2 * 2 / euro_pool_of(df), 4),
        "note": "Walk-forward používa len minulosť. Žiadna stratégia by nemala systematicky prekonať náhodu.",
    }
    return out


def _fake_ev(k, e) -> float:
    table = {
        (5, 2): 1_000_000,
        (5, 1): 500_000,
        (5, 0): 100_000,
        (4, 2): 5000,
        (4, 1): 300,
        (4, 0): 100,
        (3, 2): 150,
        (3, 1): 20,
        (3, 0): 16,
        (2, 2): 20,
        (2, 1): 10,
        (1, 2): 10,
    }
    return table.get((k, e), 0)


def analyze_era(df: pd.DataFrame, era_key: str) -> dict:
    euro_pool = euro_pool_of(df)
    n = len(df)
    main_rows = ball_stats(df["mains"].tolist(), 50, 5)
    euro_rows = ball_stats(df["euros"].tolist(), euro_pool, 2)
    combos = combination_uniqueness(df)
    patterns = pattern_rows(df)
    chi_m = chi_square_uniform(main_rows, n, 5, 50)
    chi_e = chi_square_uniform(euro_rows, n, 2, euro_pool)
    wd = weekday_test(df)
    jack = jackpot_geometry(df, euro_pool)
    pairs = pair_stats(df["mains"].tolist(), 50, 5)
    euro_pairs = pair_stats(df["euros"].tolist(), euro_pool, 2, top=10)
    prizes = prize_probabilities(euro_pool)
    findings = anomalies(main_rows, euro_rows, combos)
    first = df.iloc[0]["draw_date"].date().isoformat()
    last_date = df.iloc[-1]["draw_date"].date().isoformat()
    return {
        "key": era_key,
        "label": ERA_LABEL.get(era_key, era_key),
        "draws": n,
        "first": first,
        "last": last_date,
        "euro_pool": euro_pool,
        "jackpot_odds": JACKPOT_ODDS[euro_pool],
        "main_balls": main_rows,
        "euro_balls": euro_rows,
        "pairs": pairs,
        "euro_pairs": euro_pairs,
        "patterns": patterns,
        "chi_square_main": chi_m,
        "chi_square_euro": chi_e,
        "weekday": wd,
        "jackpot": jack,
        "combinations": combos,
        "prize_odds": prizes,
        "anomalies": findings,
        "hottest_main": sorted(main_rows, key=lambda r: r["count"], reverse=True)[:10],
        "coldest_main": sorted(main_rows, key=lambda r: r["count"])[:10],
        "overdue_main": sorted(main_rows, key=lambda r: r["last_seen_ago"], reverse=True)[:10],
        "hottest_euro": sorted(euro_rows, key=lambda r: r["count"], reverse=True)[:euro_pool],
        "overdue_euro": sorted(euro_rows, key=lambda r: r["last_seen_ago"], reverse=True)[:euro_pool],
    }


def compact_draws(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "id": int(r["draw_id"]),
                "date": r["draw_date"].date().isoformat(),
                "year": int(r["year"]),
                "dow": r["weekday_name"],
                "era": r["era"],
                "m": r["mains"],
                "e": r["euros"],
                "jackpot": float(r["advertised_jackpot_eur"]) if pd.notna(r["advertised_jackpot_eur"]) else None,
                "won": bool(r["jackpot_won"]),
                "stake": float(r["stake_eur"]) if pd.notna(r["stake_eur"]) else None,
            }
        )
    return rows


def yearly(df: pd.DataFrame) -> list[dict]:
    out = []
    for year, g in df.groupby("year"):
        out.append(
            {
                "year": int(year),
                "draws": int(len(g)),
                "jackpots": int(g["jackpot_won"].sum()),
                "avg_sum": round(float(np.mean([sum(x) for x in g["mains"]])), 2),
                "avg_jackpot": round(float(g["advertised_jackpot_eur"].mean()), 0),
            }
        )
    return out


def build() -> dict:
    df = load_draws()
    eras = {}
    for key in ["current", "2of12_tue_fri", "2of10_friday", "2of8_friday", "all"]:
        part = subset(df, key)
        eras[key] = analyze_era(part, key)
        if key == "current":
            eras[key]["backtest"] = backtest(part, warmup=80, seed=42)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Oficiálne výsledky Eurojackpot 2012-03-23 — 2026-09-15, 990 žrebov",
        "disclaimer": (
            "Eurojackpot je spravodlivá mechanická náhoda. Minulé výsledky "
            "nemenia šancu budúceho žrebu. Predikcia je laboratórny nástroj, nie sľub výhry."
        ),
        "totals": {
            "draws": int(len(df)),
            "first": df.iloc[0]["draw_date"].date().isoformat(),
            "last": df.iloc[-1]["draw_date"].date().isoformat(),
            "jackpots_won": int(df["jackpot_won"].sum()),
            "current_odds": JACKPOT_ODDS[12],
            "next_draw": str(df.iloc[-1]["next_draw_date"])[:10],
            "next_jackpot": float(df.iloc[-1]["next_jackpot_eur"]),
        },
        "yearly": yearly(df),
        "eras": eras,
        "draws": compact_draws(df),
        "latest": compact_draws(df.tail(12)),
    }
    return payload


def generate_tickets(era_key: str, strategy: str, n: int = 10, seed: int = 1) -> dict:
    df = subset(load_draws(), era_key if era_key != "current" else "current")
    rng = random.Random(seed)
    tickets = []
    for i in range(n):
        m, e = pick_ticket(df, strategy, rng)
        tickets.append(
            {
                "mains": m,
                "euros": e,
                "odd": sum(x % 2 for x in m),
                "low": sum(x <= 25 for x in m),
                "sum": sum(m),
                "consecutive": sum(1 for a, b in zip(m, m[1:]) if b == a + 1),
            }
        )
    euro_pool = euro_pool_of(df)
    odds_txt = f"{JACKPOT_ODDS[euro_pool]:,}".replace(",", " ")
    return {
        "strategy": strategy,
        "era": era_key,
        "n": n,
        "jackpot_odds": JACKPOT_ODDS[euro_pool],
        "tickets": tickets,
        "disclaimer": (
            f"Každý tiket má pri aktuálnych pravidlách šancu 1 : {odds_txt} na 5+2. "
            "Stratégia nemení túto šancu, len vyberá inú oblasť kombinatorického priestoru."
        ),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = build()
    path = OUT / "analysis.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print("wrote", path, "bytes", path.stat().st_size)
    print("draws", payload["totals"]["draws"], "current chi2 p", payload["eras"]["current"]["chi_square_main"]["p_value"])
    bt = payload["eras"]["current"]["backtest"]
    for k, v in bt.items():
        if k.startswith("_"):
            continue
        print(k, "avg_main", v["avg_main_matches"], "ev", v["relative_ev_index"])


if __name__ == "__main__":
    main()
