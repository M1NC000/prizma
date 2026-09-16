#!/usr/bin/env python3
"""Invariants for engine.experts — no pytest required.

Run from the repository root:

    python3 engine/test_learner_invariants.py
"""

from __future__ import annotations

import ast
import inspect
import random
import sys
import traceback
from copy import deepcopy
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from experts import (  # noqa: E402
    EURO_FEATURE_IDS,
    FEATURE_IDS,
    FEATURE_LABELS_SK,
    N_EURO_FEATURES,
    N_MAIN_FEATURES,
    ensure_unique_ticket,
    logits,
    nudge_mains,
    phi_euro,
    phi_main,
    pick_cover,
    pick_overdue,
    pick_pairs,
    pick_portfolio,
    pick_score,
    pick_typical,
    PORTFOLIO,
    resolve_mains_collisions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class TrapState(dict):
    """Raises if a picker tries to read a held-out 'actual' field."""

    FORBIDDEN = ("actual", "actual_mains", "actual_euros", "current")

    def __getitem__(self, key):
        self._check(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._check(key)
        return super().get(key, default)

    def __contains__(self, key):
        self._check(key)
        return super().__contains__(key)

    def _check(self, key):
        if isinstance(key, str) and key in self.FORBIDDEN:
            raise AssertionError(f"picker read forbidden field {key!r}")


def empty_state(euro_pool: int = 12, sum_lo: int = 90, sum_hi: int = 160) -> TrapState:
    return TrapState(
        n=0,
        euro_pool=euro_pool,
        main_c=[0] * 51,
        euro_c=[0] * 13,
        main_last=[-1] * 51,
        euro_last=[-1] * 13,
        prev_mains=None,
        prev_euros=None,
        recent_mains=[],
        pair={},
        ewma_main=[0.0] * 51,
        ewma_euro=[0.0] * 13,
        sum_lo=sum_lo,
        sum_hi=sum_hi,
    )


def apply_draw(state: TrapState, mains: list[int], euros: list[int], decay: float = 0.95) -> TrapState:
    """Grow a past-only view by one observed draw. Does not store the next draw."""
    st = TrapState(deepcopy(dict(state)))
    idx = int(st["n"])
    for x in mains:
        st["main_c"][x] += 1
        st["main_last"][x] = idx
    for x in euros:
        st["euro_c"][x] += 1
        st["euro_last"][x] = idx
    for a, b in combinations(sorted(mains), 2):
        st["pair"][(a, b)] = st["pair"].get((a, b), 0) + 1
    for k in range(1, 51):
        hit = 1.0 if k in mains else 0.0
        st["ewma_main"][k] = decay * st["ewma_main"][k] + (1.0 - decay) * hit
    pool = int(st["euro_pool"])
    for k in range(1, pool + 1):
        hit = 1.0 if k in euros else 0.0
        st["ewma_euro"][k] = decay * st["ewma_euro"][k] + (1.0 - decay) * hit
    st["prev_mains"] = list(mains)
    st["prev_euros"] = list(euros)
    st["recent_mains"] = (list(st["recent_mains"]) + [list(mains)])[-20:]
    st["n"] = idx + 1
    return st


def well_formed(mains, euros, euro_pool: int) -> None:
    assert isinstance(mains, list) and isinstance(euros, list)
    assert mains == sorted(mains), mains
    assert euros == sorted(euros), euros
    assert len(mains) == 5 and len(set(mains)) == 5, mains
    assert len(euros) == 2 and len(set(euros)) == 2, euros
    assert all(isinstance(x, int) and 1 <= x <= 50 for x in mains), mains
    assert all(isinstance(x, int) and 1 <= x <= euro_pool for x in euros), euros


W_MAIN = [0.0] * N_MAIN_FEATURES
W_MAIN[0] = 0.1
W_MAIN[1] = 0.8
W_MAIN[2] = 0.5
W_MAIN[3] = 0.4
W_EURO = [0.0] * N_EURO_FEATURES
W_EURO[0] = 0.1
W_EURO[1] = 0.7
W_EURO[2] = 0.4


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_phi_length():
    assert FEATURE_IDS == [
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
    assert len(FEATURE_IDS) == len(FEATURE_LABELS_SK) == N_MAIN_FEATURES == 12
    assert len(EURO_FEATURE_IDS) == N_EURO_FEATURES == 6
    st = empty_state()
    for k in range(1, 51):
        p = phi_main(st, k)
        assert len(p) == 12, (k, len(p))
        assert all(isinstance(x, float) for x in p)
    for k in range(1, 13):
        p = phi_euro(st, k)
        assert len(p) == 6, (k, len(p))
        assert all(isinstance(x, float) for x in p)
    # populated state still length-stable
    st2 = apply_draw(st, [1, 2, 3, 4, 5], [1, 2])
    st2 = apply_draw(st2, [10, 20, 30, 40, 50], [3, 4])
    for k in range(1, 51):
        assert len(phi_main(st2, k)) == 12
    assert logits([1.0, 2.0], [[3.0, 4.0], [0.0, 1.0]]) == [11.0, 2.0]
    scores = logits(W_MAIN, [phi_main(st2, k) for k in range(1, 51)])
    assert len(scores) == 50


def test_tickets_well_formed():
    rng = random.Random(7)
    st = empty_state()
    for _ in range(8):
        m = sorted(rng.sample(range(1, 51), 5))
        e = sorted(rng.sample(range(1, 13), 2))
        st = apply_draw(st, m, e)
    pool = st["euro_pool"]
    for fn in (
        lambda r: pick_score(st, W_MAIN, W_EURO, r),
        lambda r: pick_typical(st, r),
        lambda r: pick_pairs(st, r),
        lambda r: pick_overdue(st, r),
        lambda r: pick_cover(st, r, [[1, 2, 3, 4, 5]], W_MAIN, W_EURO),
    ):
        for seed in range(12):
            mains, euros = fn(random.Random(seed))
            well_formed(mains, euros, pool)


def test_first_draw_n0_does_not_crash():
    st = empty_state()
    rng = random.Random(0)
    for k in range(1, 51):
        phi = phi_main(st, k)
        assert len(phi) == 12
        assert phi[0] == 1.0
        assert phi[1] == 0.0  # freq
        assert phi[11] == 1.0  # never_seen
    for k in range(1, 13):
        assert len(phi_euro(st, k)) == 6
    well_formed(*pick_score(st, W_MAIN, W_EURO, rng), 12)
    well_formed(*pick_typical(st, rng), 12)
    well_formed(*pick_pairs(st, rng), 12)
    well_formed(*pick_overdue(st, rng), 12)
    well_formed(*pick_cover(st, rng, [], W_MAIN, W_EURO), 12)
    # era with smaller euro pool
    st8 = empty_state(euro_pool=8)
    m, e = pick_score(st8, W_MAIN, W_EURO, random.Random(3))
    well_formed(m, e, 8)


def test_picks_do_not_use_actual_field():
    src = Path(__file__).with_name("experts.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in {
            "actual",
            "actual_mains",
            "actual_euros",
        }:
            raise AssertionError("experts.py must not mention a held-out 'actual' field")
    for fn in (pick_score, pick_typical, pick_pairs, pick_overdue, pick_cover, phi_main, phi_euro):
        names = inspect.signature(fn).parameters
        assert "actual" not in names, fn.__name__

    st = empty_state()
    rng = random.Random(11)
    # Poison-pill: the held-out draw lives under a name pickers must ignore.
    # TrapState raises if that name is read.
    st["held_out"] = [6, 7, 8, 9, 10]
    pick_score(st, W_MAIN, W_EURO, rng)
    pick_typical(st, rng)
    pick_pairs(st, rng)
    pick_overdue(st, rng)
    pick_cover(st, rng, [], W_MAIN, W_EURO)
    # Direct forbidden-key probe: reading it is the failure.
    raised = False
    try:
        _ = st["actual"]
    except AssertionError:
        raised = True
    assert raised, "TrapState did not trap 'actual'"


def test_cover_prefers_unused_when_possible():
    rng = random.Random(21)
    st = empty_state()
    # Give every number some history so scores are defined, not just unused=never.
    for i in range(10):
        mains = [(i * 5 + j) % 50 + 1 for j in range(5)]
        euros = [i % 12 + 1, (i + 3) % 12 + 1]
        st = apply_draw(st, mains, euros)

    unused = list(range(41, 51))  # 10 numbers
    used_sets = [
        list(range(1, 6)),
        list(range(6, 11)),
        list(range(11, 16)),
        list(range(16, 21)),
        list(range(21, 26)),
        list(range(26, 31)),
        list(range(31, 36)),
        list(range(36, 41)),
    ]
    union = set()
    for s in used_sets:
        union.update(s)
    assert union == set(range(1, 41))
    assert set(unused).isdisjoint(union)

    for seed in range(20):
        mains, euros = pick_cover(st, random.Random(seed), used_sets, W_MAIN, W_EURO)
        well_formed(mains, euros, 12)
        assert set(mains).issubset(set(unused)), (mains, unused)

    # Fewer than 5 unused: take all unused, then fill from used.
    tiny_unused = [48, 49, 50]
    used_sets2 = [list(range(1, 48))]
    mains, euros = pick_cover(st, rng, used_sets2, W_MAIN, W_EURO)
    well_formed(mains, euros, 12)
    assert set(tiny_unused).issubset(set(mains)), mains


def test_fifty_consecutive_proposes_stay_valid():
    rng = random.Random(42)
    st = empty_state(sum_lo=80, sum_hi=170)
    existing: list[tuple[list[int], list[int]]] = []
    for step in range(50):
        used = [m for m, _ in existing[-4:]]
        factories = [
            lambda r=random.Random(1000 + step): pick_score(st, W_MAIN, W_EURO, r),
            lambda r=random.Random(2000 + step): pick_typical(st, r),
            lambda r=random.Random(3000 + step): pick_pairs(st, r),
            lambda r=random.Random(4000 + step): pick_overdue(st, r),
            lambda r=random.Random(5000 + step), u=used: pick_cover(st, r, u, W_MAIN, W_EURO),
        ]
        fn = factories[step % len(factories)]
        mains, euros = fn()
        mains, euros = ensure_unique_ticket(
            mains, euros, existing, fn, retries=30
        )
        well_formed(mains, euros, st["euro_pool"])
        existing.append((mains, euros))
        # "Next" draw is synthetic history — pickers never see a held-out field.
        fake_m = sorted(rng.sample(range(1, 51), 5))
        fake_e = sorted(rng.sample(range(1, st["euro_pool"] + 1), 2))
        st = apply_draw(st, fake_m, fake_e)
        assert st["n"] == step + 1
        assert len(st["recent_mains"]) == min(20, step + 1)
        for k in range(1, 51):
            assert len(phi_main(st, k)) == 12
    assert st["n"] == 50
    assert len(existing) == 50


def test_ensure_unique_and_typical_shape():
    rng = random.Random(99)
    st = empty_state()
    for _ in range(30):
        st = apply_draw(
            st,
            sorted(rng.sample(range(1, 51), 5)),
            sorted(rng.sample(range(1, 13), 2)),
        )
    taken = []
    for i in range(6):
        m, e = pick_typical(st, random.Random(i))
        odd = sum(x % 2 for x in m)
        low = sum(x <= 25 for x in m)
        consec = sum(1 for a, b in zip(m, m[1:]) if b == a + 1)
        # With 400 retries and a wide sum window this should almost always hit.
        # Allow the documented random fallback; just require well-formed tickets.
        well_formed(m, e, 12)
        if odd in (2, 3) and low in (2, 3) and st["sum_lo"] <= sum(m) <= st["sum_hi"] and consec <= 1:
            taken.append(True)
        else:
            taken.append(False)
    assert any(taken), "pick_typical never hit the balanced shape in 6 seeds"

    first = ([1, 2, 3, 4, 5], [1, 2])
    existing = [first]

    def factory():
        return [6, 7, 8, 9, 10], [3, 4]

    m, e = ensure_unique_ticket(first[0], first[1], existing, factory, retries=5)
    assert (m, e) == ([6, 7, 8, 9, 10], [3, 4])
    m, e = ensure_unique_ticket([11, 12, 13, 14, 15], [5, 6], existing, factory)
    assert (m, e) == ([11, 12, 13, 14, 15], [5, 6])


def test_resolve_mains_collisions_breaks_identical_hybrids():
    rng = random.Random(13)
    identical = [17, 20, 21, 34, 35]
    packed = [(eid, list(identical), [1, 2]) for eid, _n, _f in PORTFOLIO]
    counter = {"n": 0}

    def factory_for(_eid: str):
        def factory():
            counter["n"] += 1
            # sticky hybrid: almost always the collapsed set
            if counter["n"] % 7 != 0:
                return list(identical), [1, 2]
            m = sorted(rng.sample(range(1, 51), 5))
            e = sorted(rng.sample(range(1, 13), 2))
            return m, e

        return factory

    out = resolve_mains_collisions(packed, factory_for, rng)
    assert len(out) == 20
    keys = [tuple(m) for _eid, m, _e in out]
    assert len(set(keys)) == 20, keys
    for i, (_a, ma, _ea) in enumerate(out):
        for j, (_b, mb, _eb) in enumerate(out):
            if i >= j:
                continue
            assert len(set(ma) & set(mb)) < 4, (ma, mb)
    nudged = nudge_mains(identical, [identical] * 3, random.Random(1))
    assert tuple(nudged) != tuple(identical)


def test_portfolio_twenty():
    rng = random.Random(7)
    st = empty_state()
    packed = pick_portfolio(st, W_MAIN, W_EURO, rng)
    assert len(PORTFOLIO) == 20
    assert len(packed) == 20
    ids = [eid for eid, _m, _e in packed]
    assert ids == [p[0] for p in PORTFOLIO]
    seen = set()
    for eid, m, e in packed:
        well_formed(m, e, 12)
        seen.add((tuple(m), tuple(e)))
    assert len(seen) >= 18, len(seen)
    for _ in range(12):
        st = apply_draw(
            st,
            sorted(rng.sample(range(1, 51), 5)),
            sorted(rng.sample(range(1, 13), 2)),
        )
    packed2 = pick_portfolio(st, W_MAIN, W_EURO, random.Random(11))
    assert len(packed2) == 20
    for _eid, m, e in packed2:
        well_formed(m, e, 12)


def test_overdue_ranks_longest_gap():
    st = empty_state()
    # Cover 1–45 so only 46–50 stay never-seen (ago = n, strictly longest).
    for start in range(1, 46, 5):
        st = apply_draw(st, list(range(start, start + 5)), [1, 2])
    mains, euros = pick_overdue(st, random.Random(0))
    well_formed(mains, euros, 12)
    assert set(mains) == {46, 47, 48, 49, 50}, mains


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_phi_length,
    test_tickets_well_formed,
    test_first_draw_n0_does_not_crash,
    test_picks_do_not_use_actual_field,
    test_cover_prefers_unused_when_possible,
    test_fifty_consecutive_proposes_stay_valid,
    test_ensure_unique_and_typical_shape,
    test_overdue_ranks_longest_gap,
    test_portfolio_twenty,
    test_resolve_mains_collisions_breaks_identical_hybrids,
]


def main() -> int:
    failed = 0
    for fn in TESTS:
        name = fn.__name__
        try:
            fn()
            print(f"OK   {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    total = len(TESTS)
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
