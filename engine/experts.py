"""Combinatorial ticket heuristics for the Eurojackpot lab.

Every generator sees only a past-only ``StateView``. None of these
methods changes the jackpot chance of a single ticket; they only pick
different regions of the combination space. Learned weights are
exploratory scoring, not an edge.

StateView keys (all past-only — never a held-out draw):

    n, euro_pool, main_c, euro_c, main_last, euro_last,
    prev_mains, prev_euros, recent_mains, pair,
    ewma_main, ewma_euro, sum_lo, sum_hi

Mains are 5 distinct integers in 1..50. Euros are 2 distinct integers
in 1..euro_pool. Every public pick returns sorted lists.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, Mapping, Sequence

MAIN_POOL = 50
MAIN_DRAWN = 5
EURO_DRAWN = 2
N_MAIN_FEATURES = 12
N_EURO_FEATURES = 6

# Integrator contract: length-12 main feature ids, stable order.
FEATURE_IDS = [
    "intercept",
    "freq",
    "ewma",
    "overdue",
    "recent20",
    "repeat_prev",
    "odd",
    "low_1_25",
    "decade",
    "pair_affinity",
    "freq_z",
    "never_seen",
]

FEATURE_LABELS_SK = [
    "Absolútny člen",
    "Frekvencia",
    "EWMA (horúce)",
    "Omeškanie",
    "Výskyt v posledných 20",
    "Zopakované z minula",
    "Nepárne",
    "Nízke 1–25",
    "Dekáda",
    "Párová väzba",
    "Z-skóre frekvencie",
    "Ešte nepadlo",
]

# Subset of FEATURE_IDS used by phi_euro (length 6).
EURO_FEATURE_IDS = [
    "intercept",
    "freq",
    "ewma",
    "overdue",
    "repeat_prev",
    "odd",
]

EURO_FEATURE_LABELS_SK = [
    "Absolútny člen",
    "Frekvencia",
    "EWMA (horúce)",
    "Omeškanie",
    "Zopakované z minula",
    "Nepárne",
]

assert len(FEATURE_IDS) == len(FEATURE_LABELS_SK) == N_MAIN_FEATURES
assert len(EURO_FEATURE_IDS) == len(EURO_FEATURE_LABELS_SK) == N_EURO_FEATURES


# ---------------------------------------------------------------------------
# Feature maps (past-only)
# ---------------------------------------------------------------------------

def phi_main(state: Mapping, k: int) -> list[float]:
    """Length-12 feature vector for main ball ``k`` in 1..50."""
    n = int(state["n"])
    c = _at(state["main_c"], k, 0.0)
    last = _at(state["main_last"], k, -1)
    ewma = float(_at(state["ewma_main"], k, 0.0))
    prev = state.get("prev_mains") or []
    recent = state.get("recent_mains") or []

    freq = float(c) / n if n > 0 else 0.0
    ago = _ago(last, n)
    overdue = ago / n if n > 0 else 0.0
    recent20 = _recent_hit_rate(recent, k)
    repeat_prev = 1.0 if k in prev else 0.0
    odd = 1.0 if (k % 2) else 0.0
    low = 1.0 if k <= 25 else 0.0
    decade = ((k - 1) // 10) / 4.0
    pair_aff = _pair_affinity(state, k)
    freq_z = _freq_z(c, n, drawn=MAIN_DRAWN, pool=MAIN_POOL)
    never = 1.0 if last < 0 else 0.0

    return [
        1.0,
        freq,
        ewma,
        overdue,
        recent20,
        repeat_prev,
        odd,
        low,
        decade,
        pair_aff,
        freq_z,
        never,
    ]


def phi_euro(state: Mapping, k: int) -> list[float]:
    """Length-6 feature vector for euro ball ``k`` in 1..euro_pool."""
    n = int(state["n"])
    c = _at(state["euro_c"], k, 0.0)
    last = _at(state["euro_last"], k, -1)
    ewma = float(_at(state["ewma_euro"], k, 0.0))
    prev = state.get("prev_euros") or []

    freq = float(c) / n if n > 0 else 0.0
    ago = _ago(last, n)
    overdue = ago / n if n > 0 else 0.0
    repeat_prev = 1.0 if k in prev else 0.0
    odd = 1.0 if (k % 2) else 0.0
    return [1.0, freq, ewma, overdue, repeat_prev, odd]


def logits(weights: Sequence[float], phis: Sequence[Sequence[float]]) -> list[float]:
    """Dot product ``weights · phi`` for each feature vector in ``phis``."""
    w = [float(x) for x in weights]
    out: list[float] = []
    for phi in phis:
        s = 0.0
        for i, p in enumerate(phi):
            if i < len(w):
                s += w[i] * float(p)
        out.append(s)
    return out


def _apply_repel(scores: Sequence[float], state: Mapping, penalty: float = 1.15) -> list[float]:
    """Down-rank balls already used in this round's earlier tickets."""
    repel = set(state.get("repel") or [])
    if not repel:
        return list(scores)
    return [float(s) - (penalty if (i + 1) in repel else 0.0) for i, s in enumerate(scores)]


# ---------------------------------------------------------------------------
# Ticket generators
# ---------------------------------------------------------------------------

def pick_score(state: Mapping, w_main: Sequence[float], w_euro: Sequence[float], rng) -> tuple[list[int], list[int]]:
    """Gumbel-top-k sample without replacement from learned logits."""
    main_phis = [phi_main(state, k) for k in range(1, MAIN_POOL + 1)]
    main_scores = _apply_repel(logits(w_main, main_phis), state)
    mains = _gumbel_top_k(main_scores, MAIN_DRAWN, rng)

    pool = int(state["euro_pool"])
    euro_phis = [phi_euro(state, k) for k in range(1, pool + 1)]
    euro_scores = logits(w_euro, euro_phis)
    euros = _gumbel_top_k(euro_scores, EURO_DRAWN, rng)
    return sorted(mains), sorted(euros)


def pick_typical(state: Mapping, rng) -> tuple[list[int], list[int]]:
    """Balanced shape: odd in {2,3}, low(1-25) in {2,3}, sum in [sum_lo,sum_hi],
    consecutive pairs <= 1. 400 retries then a uniform ticket.
    """
    pool = int(state["euro_pool"])
    lo = int(state["sum_lo"])
    hi = int(state["sum_hi"])
    for _ in range(400):
        m = sorted(rng.sample(range(1, MAIN_POOL + 1), MAIN_DRAWN))
        odd = sum(x % 2 for x in m)
        low = sum(x <= 25 for x in m)
        consec = sum(1 for a, b in zip(m, m[1:]) if b == a + 1)
        if odd in (2, 3) and low in (2, 3) and lo <= sum(m) <= hi and consec <= 1:
            return m, sorted(rng.sample(range(1, pool + 1), EURO_DRAWN))
    return (
        sorted(rng.sample(range(1, MAIN_POOL + 1), MAIN_DRAWN)),
        sorted(rng.sample(range(1, pool + 1), EURO_DRAWN)),
    )


def pick_pairs(state: Mapping, rng) -> tuple[list[int], list[int]]:
    """Start at a count-weighted hot main, then greedily add the number with
    the highest co-occurrence versus the set so far. Ties broken by ``rng``.
    """
    counts = state["main_c"]
    pair = state["pair"]
    nums = list(range(1, MAIN_POOL + 1))
    weights = [max(float(_at(counts, k, 0.0)), 0.0) for k in nums]
    start = _weighted_choice(rng, nums, weights)

    picked = [start]
    remaining = [k for k in nums if k != start]
    while len(picked) < MAIN_DRAWN and remaining:
        best = None
        cand: list[int] = []
        for x in remaining:
            s = 0
            for y in picked:
                s += _pair_count(pair, x, y)
            if best is None or s > best:
                best = s
                cand = [x]
            elif s == best:
                cand.append(x)
        chosen = cand[rng.randrange(len(cand))]
        picked.append(chosen)
        remaining.remove(chosen)

    euros = _weighted_without_replacement(
        rng,
        list(range(1, int(state["euro_pool"]) + 1)),
        [max(float(_at(state["euro_c"], k, 0.0)), 0.0) for k in range(1, int(state["euro_pool"]) + 1)],
        EURO_DRAWN,
    )
    return sorted(picked), sorted(euros)


def pick_overdue(state: Mapping, rng) -> tuple[list[int], list[int]]:
    """Longest since last seen. If ``n == 0`` every ball is equal, so random."""
    n = int(state["n"])
    pool = int(state["euro_pool"])
    if n == 0:
        return (
            sorted(rng.sample(range(1, MAIN_POOL + 1), MAIN_DRAWN)),
            sorted(rng.sample(range(1, pool + 1), EURO_DRAWN)),
        )

    def main_ago(k: int) -> int:
        return _ago(_at(state["main_last"], k, -1), n)

    def euro_ago(k: int) -> int:
        return _ago(_at(state["euro_last"], k, -1), n)

    mains = _rank_take(range(1, MAIN_POOL + 1), main_ago, MAIN_DRAWN, rng)
    euros = _rank_take(range(1, pool + 1), euro_ago, EURO_DRAWN, rng)
    return sorted(mains), sorted(euros)


def pick_cover(
    state: Mapping,
    rng,
    used_sets: list[list[int]],
    w_main: Sequence[float],
    w_euro: Sequence[float],
) -> tuple[list[int], list[int]]:
    """Prefer mains outside the union of ``used_sets``, ranked by learned score."""
    used = set()
    for s in used_sets or []:
        used.update(s)

    main_scores = logits(w_main, [phi_main(state, k) for k in range(1, MAIN_POOL + 1)])
    unused = [k for k in range(1, MAIN_POOL + 1) if k not in used]
    used_nums = [k for k in range(1, MAIN_POOL + 1) if k in used]

    def score_of(k: int) -> float:
        return main_scores[k - 1]

    picked = _rank_take(unused, score_of, MAIN_DRAWN, rng)
    if len(picked) < MAIN_DRAWN:
        picked.extend(_rank_take(used_nums, score_of, MAIN_DRAWN - len(picked), rng))

    pool = int(state["euro_pool"])
    euro_scores = logits(w_euro, [phi_euro(state, k) for k in range(1, pool + 1)])
    euros = _gumbel_top_k(euro_scores, EURO_DRAWN, rng)
    return sorted(picked[:MAIN_DRAWN]), sorted(euros)


def pick_score_temp(
    state: Mapping,
    w_main: Sequence[float],
    w_euro: Sequence[float],
    rng,
    temp: float = 1.0,
) -> tuple[list[int], list[int]]:
    """Gumbel-top-k with temperature. temp→0 is greedy, temp>1 explores."""
    t = max(0.12, float(temp))
    main_phis = [phi_main(state, k) for k in range(1, MAIN_POOL + 1)]
    main_scores = _apply_repel([s / t for s in logits(w_main, main_phis)], state)
    mains = _gumbel_top_k(main_scores, MAIN_DRAWN, rng)
    pool = int(state["euro_pool"])
    euro_phis = [phi_euro(state, k) for k in range(1, pool + 1)]
    euro_scores = [s / t for s in logits(w_euro, euro_phis)]
    euros = _gumbel_top_k(euro_scores, EURO_DRAWN, rng)
    return sorted(mains), sorted(euros)


def pick_typical_shape(
    state: Mapping,
    rng,
    *,
    sum_lo: int | None = None,
    sum_hi: int | None = None,
    odd: tuple[int, ...] = (2, 3),
    low: tuple[int, ...] = (2, 3),
    consec_max: int = 1,
) -> tuple[list[int], list[int]]:
    pool = int(state["euro_pool"])
    lo = int(state["sum_lo"] if sum_lo is None else sum_lo)
    hi = int(state["sum_hi"] if sum_hi is None else sum_hi)
    lo, hi = min(lo, hi), max(lo, hi)
    for _ in range(500):
        m = sorted(rng.sample(range(1, MAIN_POOL + 1), MAIN_DRAWN))
        if sum(x % 2 for x in m) not in odd:
            continue
        if sum(x <= 25 for x in m) not in low:
            continue
        if sum(1 for a, b in zip(m, m[1:]) if b == a + 1) > consec_max:
            continue
        if not (lo <= sum(m) <= hi):
            continue
        return m, sorted(rng.sample(range(1, pool + 1), EURO_DRAWN))
    return pick_typical(state, rng)


def pick_pairs_rare(state: Mapping, rng) -> tuple[list[int], list[int]]:
    """Anti-pair: greedy toward the rarest co-occurrences."""
    pool = int(state["euro_pool"])
    if int(state["n"]) < 8:
        return pick_typical(state, rng)
    nums = list(range(1, MAIN_POOL + 1))
    start = nums[rng.randrange(len(nums))]
    picked = [start]
    remaining = [k for k in nums if k != start]
    pair = state.get("pair") or {}
    while len(picked) < MAIN_DRAWN and remaining:
        best = None
        cand: list[int] = []
        for x in remaining:
            s = 0
            for y in picked:
                s += _pair_count(pair, x, y)
            if best is None or s < best:
                best = s
                cand = [x]
            elif s == best:
                cand.append(x)
        chosen = cand[rng.randrange(len(cand))]
        picked.append(chosen)
        remaining.remove(chosen)
    euros = sorted(rng.sample(range(1, pool + 1), EURO_DRAWN))
    return sorted(picked), euros


def pick_due(state: Mapping, rng) -> tuple[list[int], list[int]]:
    """Closest to the memoryless expected gap (10 mains, pool/2 euros)."""
    n = int(state["n"])
    pool = int(state["euro_pool"])
    if n == 0:
        return pick_typical(state, rng)

    def closeness(last, expected: float) -> float:
        ago = _ago(last, n)
        return -abs(ago - expected)

    mains = _rank_take(
        range(1, MAIN_POOL + 1),
        lambda k: closeness(_at(state["main_last"], k, -1), 10.0),
        MAIN_DRAWN,
        rng,
    )
    euros = _rank_take(
        range(1, pool + 1),
        lambda k: closeness(_at(state["euro_last"], k, -1), pool / 2.0),
        EURO_DRAWN,
        rng,
    )
    return sorted(mains), sorted(euros)


def pick_ewma_hot(state: Mapping, rng) -> tuple[list[int], list[int]]:
    pool = int(state["euro_pool"])
    mains = _rank_take(
        range(1, MAIN_POOL + 1),
        lambda k: float(_at(state["ewma_main"], k, 0.0)),
        MAIN_DRAWN,
        rng,
    )
    euros = _rank_take(
        range(1, pool + 1),
        lambda k: float(_at(state["ewma_euro"], k, 0.0)),
        EURO_DRAWN,
        rng,
    )
    return sorted(mains), sorted(euros)


def pick_cold(state: Mapping, rng) -> tuple[list[int], list[int]]:
    pool = int(state["euro_pool"])
    mains = _rank_take(
        range(1, MAIN_POOL + 1),
        lambda k: -float(_at(state["main_c"], k, 0)),
        MAIN_DRAWN,
        rng,
    )
    euros = _rank_take(
        range(1, pool + 1),
        lambda k: -float(_at(state["euro_c"], k, 0)),
        EURO_DRAWN,
        rng,
    )
    return sorted(mains), sorted(euros)


def pick_thompson(state: Mapping, rng) -> tuple[list[int], list[int]]:
    """Beta-Bernoulli posterior Thompson sampling. Prior Beta(1, 9) ⇒ E[p]=0.1."""
    n = int(state["n"])
    pool = int(state["euro_pool"])
    mains = _rank_take(
        range(1, MAIN_POOL + 1),
        lambda k: _beta_sample(
            rng,
            1.0 + float(_at(state["main_c"], k, 0)),
            9.0 + max(0.0, n - float(_at(state["main_c"], k, 0))),
        ),
        MAIN_DRAWN,
        rng,
    )
    p_e = 2 / max(pool, 2)
    a0 = 1.0
    b0 = max(1.0, (1.0 - p_e) / p_e)
    euros = _rank_take(
        range(1, pool + 1),
        lambda k: _beta_sample(
            rng,
            a0 + float(_at(state["euro_c"], k, 0)),
            b0 + max(0.0, n - float(_at(state["euro_c"], k, 0))),
        ),
        EURO_DRAWN,
        rng,
    )
    return sorted(mains), sorted(euros)


def pick_spectral(state: Mapping, rng) -> tuple[list[int], list[int]]:
    """Leading eigenvector of the co-occurrence graph (power iteration)."""
    dim = MAIN_POOL
    pair = state.get("pair") or {}
    a = [[0.05 if i == j else 0.0 for j in range(dim)] for i in range(dim)]
    for i in range(dim):
        for j in range(i + 1, dim):
            c = float(_pair_count(pair, i + 1, j + 1))
            a[i][j] = a[j][i] = c
    v = [0.5 + rng.random() for _ in range(dim)]
    for _ in range(14):
        nv = [sum(a[i][j] * v[j] for j in range(dim)) for i in range(dim)]
        nrm = math.sqrt(sum(x * x for x in nv)) or 1.0
        v = [x / nrm for x in nv]
    mains = _rank_take(range(1, dim + 1), lambda k: abs(v[k - 1]), MAIN_DRAWN, rng)
    pool = int(state["euro_pool"])
    euros = _rank_take(
        range(1, pool + 1),
        lambda k: float(_at(state["euro_c"], k, 0)),
        EURO_DRAWN,
        rng,
    )
    return sorted(mains), sorted(euros)


def pick_markov_repel(
    state: Mapping, w_main: Sequence[float], w_euro: Sequence[float], rng
) -> tuple[list[int], list[int]]:
    prev = set(state.get("prev_mains") or [])
    scores = logits(w_main, [phi_main(state, k) for k in range(1, MAIN_POOL + 1)])
    for k in prev:
        scores[k - 1] -= 2.4
    mains = _gumbel_top_k(scores, MAIN_DRAWN, rng)
    pool = int(state["euro_pool"])
    prev_e = set(state.get("prev_euros") or [])
    e_scores = logits(w_euro, [phi_euro(state, k) for k in range(1, pool + 1)])
    for k in prev_e:
        if 1 <= k <= pool:
            e_scores[k - 1] -= 1.6
    euros = _gumbel_top_k(e_scores, EURO_DRAWN, rng)
    return sorted(mains), sorted(euros)


def pick_markov_stick(
    state: Mapping, w_main: Sequence[float], w_euro: Sequence[float], rng
) -> tuple[list[int], list[int]]:
    prev = list(state.get("prev_mains") or [])
    keep = rng.sample(prev, min(2, len(prev))) if prev else []
    scores = logits(w_main, [phi_main(state, k) for k in range(1, MAIN_POOL + 1)])
    rest = _rank_take(
        [k for k in range(1, MAIN_POOL + 1) if k not in keep],
        lambda k: scores[k - 1],
        MAIN_DRAWN - len(keep),
        rng,
    )
    pool = int(state["euro_pool"])
    prev_e = list(state.get("prev_euros") or [])
    e_keep = rng.sample(prev_e, 1) if prev_e else []
    e_scores = logits(w_euro, [phi_euro(state, k) for k in range(1, pool + 1)])
    e_rest = _rank_take(
        [k for k in range(1, pool + 1) if k not in e_keep],
        lambda k: e_scores[k - 1],
        EURO_DRAWN - len(e_keep),
        rng,
    )
    return sorted(keep + rest), sorted(e_keep + e_rest)


def pick_decade(
    state: Mapping, w_main: Sequence[float], w_euro: Sequence[float], rng
) -> tuple[list[int], list[int]]:
    """One ball from each decade 1–9, 10–19, 20–29, 30–39, 40–50."""
    scores = logits(w_main, [phi_main(state, k) for k in range(1, MAIN_POOL + 1)])
    buckets: list[list[int]] = [[], [], [], [], []]
    for k in range(1, MAIN_POOL + 1):
        buckets[min(4, (k - 1) // 10)].append(k)
    mains = [max(bucket, key=lambda k: (scores[k - 1], rng.random())) for bucket in buckets]
    pool = int(state["euro_pool"])
    euros = _gumbel_top_k(
        logits(w_euro, [phi_euro(state, k) for k in range(1, pool + 1)]),
        EURO_DRAWN,
        rng,
    )
    return sorted(mains), sorted(euros)


def pick_last_digit(
    state: Mapping, w_main: Sequence[float], w_euro: Sequence[float], rng
) -> tuple[list[int], list[int]]:
    scores = logits(w_main, [phi_main(state, k) for k in range(1, MAIN_POOL + 1)])
    order = sorted(range(1, MAIN_POOL + 1), key=lambda k: (-scores[k - 1], rng.random()))
    picked: list[int] = []
    used_d: set[int] = set()
    for k in order:
        d = k % 10
        if d in used_d and len(picked) < 4:
            continue
        picked.append(k)
        used_d.add(d)
        if len(picked) == MAIN_DRAWN:
            break
    if len(picked) < MAIN_DRAWN:
        for k in order:
            if k not in picked:
                picked.append(k)
            if len(picked) == MAIN_DRAWN:
                break
    pool = int(state["euro_pool"])
    euros = sorted(rng.sample(range(1, pool + 1), EURO_DRAWN))
    return sorted(picked), euros


def pick_spread(state: Mapping, rng) -> tuple[list[int], list[int]]:
    """Wide range (max−min ≥ 32) with a typical odd/low shape."""
    pool = int(state["euro_pool"])
    for _ in range(400):
        m = sorted(rng.sample(range(1, MAIN_POOL + 1), MAIN_DRAWN))
        if m[-1] - m[0] < 32:
            continue
        if sum(x % 2 for x in m) not in (2, 3):
            continue
        return m, sorted(rng.sample(range(1, pool + 1), EURO_DRAWN))
    return pick_typical(state, rng)


def _beta_sample(rng, a: float, b: float) -> float:
    aa = max(float(a), 1e-4)
    bb = max(float(b), 1e-4)
    x = rng.gammavariate(aa, 1.0)
    y = rng.gammavariate(bb, 1.0)
    s = x + y
    return x / s if s > 0 else 0.5


PORTFOLIO = [
    ("score_greedy", "Skór greedy", "Gumbel-top-5 pri T=0,45 — takmer argmax naučených logitov."),
    ("score", "Skór T=1", "Štandardný Gumbel na w·φ."),
    ("score_explore", "Skór explorácia", "Vysoká teplota T=2,2 — širší výber z naučeného modelu."),
    ("typical", "Tvarový modus", "2–3 nepárne, 2–3 nízke, adaptívny súčet, ≤1 sused."),
    ("typical_high", "Vysoký súčet", "Tvarový filter v pásme medián+."),
    ("typical_low", "Nízky súčet", "Tvarový filter v pásme medián−."),
    ("pairs", "Graf párov", "Greedy na empirických dvojiciach."),
    ("pairs_rare", "Vzácne páry", "Greedy k najmenej videným dvojiciam."),
    ("overdue", "Omeškané", "Najdlhšia medzera — gambler’s fallacy expert."),
    ("due", "Splatné gap", "Najbližšie k očakávanej medzere 10 (pamäťová nula)."),
    ("ewma_hot", "EWMA horúce", "Exponenciálne vážená recencia."),
    ("cold", "Studené", "Najnižší empirický počet."),
    ("thompson", "Thompson", "Beta(1+c, 9+n−c) vzorkovanie — Bayesian bandit."),
    ("spectral", "Spektrálny graf", "Vedúci vlastný vektor matice spoluvýskytu."),
    ("markov_repel", "Markov odpud", "Penalizuje čísla z minulého žrebu."),
    ("markov_stick", "Markov lepidlo", "Drží 2 čísla z minulého ťahu, zvyšok podľa skóre."),
    ("decade", "Dekádový rozptyl", "Jedno číslo z každej desiatky 1–9 … 40–50."),
    ("odd_heavy", "Nepárny tlak", "4–5 nepárnych v tvare inak typickom."),
    ("last_digit", "Koncové cifry", "Rôzne posledné číslice, radené logitom."),
    ("cover", "Max pokrytie", "Doplňa čísla mimo zjednotenia 19 súrodencov."),
]


def pick_named(
    eid: str,
    state: Mapping,
    w_main: Sequence[float],
    w_euro: Sequence[float],
    rng,
    used_mains: list[list[int]] | None = None,
) -> tuple[list[int], list[int]]:
    lo = int(state["sum_lo"])
    hi = int(state["sum_hi"])
    if eid == "score_greedy":
        return pick_score_temp(state, w_main, w_euro, rng, 0.45)
    if eid == "score":
        return pick_score(state, w_main, w_euro, rng)
    if eid == "score_explore":
        return pick_score_temp(state, w_main, w_euro, rng, 2.2)
    if eid == "typical":
        return pick_typical(state, rng)
    if eid == "typical_high":
        return pick_typical_shape(state, rng, sum_lo=lo + 18, sum_hi=hi + 28)
    if eid == "typical_low":
        return pick_typical_shape(state, rng, sum_lo=max(45, lo - 28), sum_hi=hi - 18)
    if eid == "pairs":
        return pick_pairs(state, rng)
    if eid == "pairs_rare":
        return pick_pairs_rare(state, rng)
    if eid == "overdue":
        return pick_overdue(state, rng)
    if eid == "due":
        return pick_due(state, rng)
    if eid == "ewma_hot":
        return pick_ewma_hot(state, rng)
    if eid == "cold":
        return pick_cold(state, rng)
    if eid == "thompson":
        return pick_thompson(state, rng)
    if eid == "spectral":
        return pick_spectral(state, rng)
    if eid == "markov_repel":
        return pick_markov_repel(state, w_main, w_euro, rng)
    if eid == "markov_stick":
        return pick_markov_stick(state, w_main, w_euro, rng)
    if eid == "decade":
        return pick_decade(state, w_main, w_euro, rng)
    if eid == "odd_heavy":
        return pick_typical_shape(state, rng, odd=(4, 5), consec_max=2)
    if eid == "last_digit":
        return pick_last_digit(state, w_main, w_euro, rng)
    if eid == "spread":
        return pick_spread(state, rng)
    return pick_cover(state, rng, used_mains or [], w_main, w_euro)


def pick_hybrid(
    state: Mapping,
    w_main: Sequence[float],
    w_euro: Sequence[float],
    rng,
    id_a: str,
    id_b: str,
) -> tuple[list[int], list[int]]:
    """3 numbers from expert A, fill from expert B — online mutant of a weak slot."""
    ma, ea = pick_named(id_a, state, w_main, w_euro, rng)
    mb, eb = pick_named(id_b, state, w_main, w_euro, rng)
    picked: list[int] = []
    for x in ma + mb:
        if x not in picked:
            picked.append(x)
        if len(picked) == MAIN_DRAWN:
            break
    pool = int(state["euro_pool"])
    while len(picked) < MAIN_DRAWN:
        x = rng.randint(1, MAIN_POOL)
        if x not in picked:
            picked.append(x)
    euros: list[int] = []
    for x in ea + eb:
        if x not in euros and 1 <= x <= pool:
            euros.append(x)
        if len(euros) == EURO_DRAWN:
            break
    while len(euros) < EURO_DRAWN:
        x = rng.randint(1, pool)
        if x not in euros:
            euros.append(x)
    return sorted(picked), sorted(euros)


def diversify_portfolio(
    state: Mapping,
    w_main: Sequence[float],
    w_euro: Sequence[float],
    rng,
    packed: list[tuple[str, list[int], list[int]]],
) -> list[tuple[str, list[int], list[int]]]:
    """Resample tickets that share ≥4 mains with a sibling (keep cover last)."""
    out = list(packed)
    for _ in range(5):
        swapped = False
        n = len(out)
        for j in range(n - 1):  # don't retouch cover
            mj = set(out[j][1])
            clash = False
            for i in range(n):
                if i == j:
                    continue
                if len(mj & set(out[i][1])) >= 4:
                    clash = True
                    break
            if not clash:
                continue
            union_others: set[int] = set()
            bag = []
            for k, (_eid, m, e) in enumerate(out):
                if k != j:
                    union_others |= set(m)
                    bag.append((m, e))
            st2 = dict(state)
            st2["repel"] = union_others
            eid = out[j][0]

            def factory(eid=eid, st2=st2, bag=bag):
                return pick_named(eid, st2, w_main, w_euro, rng, [list(union_others)])

            m, e = factory()
            m, e = ensure_unique_ticket(m, e, bag, factory, retries=16)
            if len(set(m) & mj) >= 4:
                m = nudge_mains(m, [x[1] for k, x in enumerate(out) if k != j], rng)
            if len(set(m) & mj) < 4 or len(set(m) & union_others) < len(mj & union_others):
                out[j] = (eid, m, e)
                swapped = True
        if not swapped:
            break
    return out


def pick_portfolio(
    state: Mapping,
    w_main: Sequence[float],
    w_euro: Sequence[float],
    rng,
) -> list[tuple[str, list[int], list[int]]]:
    """Twenty tickets with sequential repel, then Jaccard diversify."""
    bag: list[tuple[list[int], list[int]]] = []
    out: list[tuple[str, list[int], list[int]]] = []
    for i, (eid, _name, _formula) in enumerate(PORTFOLIO):
        st = dict(state)
        if i >= 6:
            st["repel"] = {x for m, _e in bag for x in m}
        used = [m for m, _e in bag]

        def factory(eid=eid, st=st, used=used):
            return pick_named(eid, st, w_main, w_euro, rng, used)

        m, e = factory()
        m, e = ensure_unique_ticket(m, e, bag, factory, retries=24)
        bag.append((m, e))
        out.append((eid, m, e))
    return diversify_portfolio(state, w_main, w_euro, rng, out)


def ensure_unique_ticket(
    mains: Sequence[int],
    euros: Sequence[int],
    existing: Iterable,
    factory: Callable[[], tuple[list[int], list[int]]],
    retries: int = 30,
) -> tuple[list[int], list[int]]:
    """Return ``(mains, euros)`` unless that full ticket is already in ``existing``.

    On collision, call ``factory()`` up to ``retries`` times. If every retry
    collides, the original ticket is returned (caller may still accept a dup).
    """
    keys = _existing_keys(existing)
    key = _ticket_key(mains, euros)
    if key not in keys:
        return sorted(mains), sorted(euros)
    for _ in range(retries):
        m, e = factory()
        cand = _ticket_key(m, e)
        if cand not in keys:
            return sorted(m), sorted(e)
    return sorted(mains), sorted(euros)


def nudge_mains(
    mains: Sequence[int],
    others: Sequence[Sequence[int]],
    rng,
    min_share: int = 4,
) -> list[int]:
    """Swap balls until this set shares < ``min_share`` with every sibling.

    Last resort fills from unused numbers so a sticky factory cannot collapse
    the whole portfolio onto one 5-set (the hybrid-mutation failure mode).
    """
    m = sorted(int(x) for x in mains)
    others_sets = [set(int(x) for x in o) for o in others]
    taken = {tuple(sorted(int(x) for x in o)) for o in others}
    n_replace = max(1, MAIN_DRAWN - (min_share - 1))

    def ok(cand: Sequence[int]) -> bool:
        key = tuple(sorted(cand))
        if key in taken:
            return False
        s = set(cand)
        return all(len(s & o) < min_share for o in others_sets)

    if ok(m):
        return m
    for _ in range(100):
        cand = list(m)
        order = list(range(len(cand)))
        rng.shuffle(order)
        for i in order[:n_replace]:
            for _try in range(16):
                x = rng.randint(1, MAIN_POOL)
                if x not in cand:
                    cand[i] = x
                    break
        cand = sorted(set(int(x) for x in cand))
        if len(cand) < MAIN_DRAWN:
            continue
        if ok(cand):
            return cand
    used: set[int] = set()
    for o in others:
        used |= set(int(x) for x in o)
    unused = [k for k in range(1, MAIN_POOL + 1) if k not in used]
    cand = list(m)
    replaced = 0
    for i, x in enumerate(cand):
        if replaced >= n_replace:
            break
        if unused and any(x in o for o in others_sets):
            cand[i] = unused.pop(0)
            replaced += 1
    cand = sorted(set(int(x) for x in cand))
    k = 1
    while len(cand) < MAIN_DRAWN:
        if k not in cand:
            cand.append(k)
        k += 1
    out = sorted(cand)[:MAIN_DRAWN]
    if ok(out):
        return out
    pool = unused + [k for k in range(1, MAIN_POOL + 1) if k not in unused]
    forced: list[int] = []
    for x in pool:
        if x in forced:
            continue
        trial = forced + [x]
        if len(trial) < MAIN_DRAWN or ok(trial):
            forced.append(x)
        if len(forced) == MAIN_DRAWN:
            return sorted(forced)
    return out


def resolve_mains_collisions(
    packed: list[tuple[str, list[int], list[int]]],
    factory_for: Callable[[str], Callable[[], tuple[list[int], list[int]]]],
    rng,
    min_share: int = 4,
    passes: int = 6,
) -> list[tuple[str, list[int], list[int]]]:
    """Resample / nudge tickets that share ≥ ``min_share`` mains with a sibling."""
    out = [(eid, list(m), list(e)) for eid, m, e in packed]
    for _ in range(passes):
        swapped = False
        for j, (eid, m, e) in enumerate(out):
            others_m = [om for i, (_eid, om, _oe) in enumerate(out) if i != j]
            if not any(len(set(m) & set(om)) >= min_share for om in others_m):
                continue
            factory = factory_for(eid)
            nm, ne = factory()
            bag = [(om, oe) for i, (_eid, om, oe) in enumerate(out) if i != j]
            nm, ne = ensure_unique_ticket(nm, ne, bag, factory, retries=16)
            nm = nudge_mains(nm, others_m, rng, min_share=min_share)
            out[j] = (eid, nm, ne)
            swapped = True
        if not swapped:
            break
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _at(seq, k: int, default=0):
    try:
        if k < 0 or k >= len(seq):
            return default
        return seq[k]
    except (TypeError, IndexError):
        return default


def _ago(last, n: int) -> int:
    last_i = int(last) if last is not None else -1
    if n <= 0:
        return 0
    if last_i < 0:
        return n
    return n - 1 - last_i


def _recent_hit_rate(recent: Sequence[Sequence[int]], k: int) -> float:
    if not recent:
        return 0.0
    hits = 0
    for draw in recent:
        if k in draw:
            hits += 1
    return hits / len(recent)


def _pair_count(pair: Mapping, a: int, b: int) -> int:
    if a == b:
        return 0
    lo, hi = (a, b) if a < b else (b, a)
    if (lo, hi) in pair:
        return int(pair[(lo, hi)])
    # Tolerate string keys in case a caller JSON-round-tripped the map.
    for key in ((hi, lo), f"{lo},{hi}", f"{lo}, {hi}"):
        if key in pair:
            return int(pair[key])
    return 0


def _pair_affinity(state: Mapping, k: int) -> float:
    """Mean co-occurrence of ``k`` with other mains, scaled by draws."""
    n = int(state["n"])
    if n <= 0:
        return 0.0
    pair = state.get("pair") or {}
    total = 0
    for j in range(1, MAIN_POOL + 1):
        if j == k:
            continue
        total += _pair_count(pair, k, j)
    # Each draw that contains k contributes 4 partners.
    return total / (4.0 * n)


def _freq_z(count, n: int, drawn: int, pool: int) -> float:
    if n <= 0:
        return 0.0
    p = drawn / pool
    expected = n * p
    var = n * p * (1.0 - p)
    if var <= 0:
        return 0.0
    z = (float(count) - expected) / math.sqrt(var)
    return math.tanh(z / 3.0)


def _gumbel(rng) -> float:
    u = rng.random()
    u = min(max(u, 1e-12), 1.0 - 1e-12)
    return -math.log(-math.log(u))


def _gumbel_top_k(scores: Sequence[float], k: int, rng) -> list[int]:
    """Numbers are 1-indexed to match ball labels; ``scores[i]`` is ball i+1."""
    keyed = [(float(s) + _gumbel(rng), i) for i, s in enumerate(scores)]
    keyed.sort(reverse=True)
    return [i + 1 for _, i in keyed[:k]]


def _weighted_choice(rng, items: Sequence[int], weights: Sequence[float]) -> int:
    total = 0.0
    for w in weights:
        total += max(float(w), 0.0)
    if total <= 0.0:
        return items[rng.randrange(len(items))]
    r = rng.random() * total
    acc = 0.0
    chosen = items[-1]
    for item, w in zip(items, weights):
        acc += max(float(w), 0.0)
        if r <= acc:
            return item
    return chosen


def _weighted_without_replacement(
    rng, items: list[int], weights: list[float], k: int
) -> list[int]:
    pool = list(items)
    w = [max(float(x), 0.0) for x in weights]
    out: list[int] = []
    take = min(k, len(pool))
    for _ in range(take):
        x = _weighted_choice(rng, pool, w)
        idx = pool.index(x)
        out.append(x)
        pool.pop(idx)
        w.pop(idx)
    return out


def _rank_take(candidates: Iterable[int], score_fn, k: int, rng) -> list[int]:
    decorated = [(float(score_fn(x)), rng.random(), x) for x in candidates]
    decorated.sort(reverse=True)
    return [x for _, _, x in decorated[:k]]


def _ticket_key(mains: Sequence[int], euros: Sequence[int]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    return (tuple(sorted(mains)), tuple(sorted(euros)))


def _existing_keys(existing: Iterable) -> set[tuple[tuple[int, ...], tuple[int, ...]]]:
    keys: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
    if existing is None:
        return keys
    for item in existing:
        if isinstance(item, dict):
            keys.add(_ticket_key(item["mains"], item["euros"]))
        else:
            m, e = item[0], item[1]
            keys.add(_ticket_key(m, e))
    return keys
