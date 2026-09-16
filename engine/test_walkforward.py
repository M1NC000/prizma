"""Invariants for the sequential self-improving lab."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "web" / "assets" / "learning.json"


def main() -> None:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    steps = payload["steps"]
    assert len(steps) == 990, len(steps)
    assert steps[0]["id"] == 1 and steps[0]["d"] == "2012-03-23"
    assert steps[-1]["id"] == 990 and steps[-1]["d"] == "2026-09-15"
    assert steps[0]["am"] == [5, 8, 21, 37, 46]
    assert steps[-1]["am"] == [5, 6, 10, 27, 42]
    ids = [s["id"] for s in steps]
    assert ids == list(range(1, 991))
    for s in steps:
        assert len(s["t"]) == 20, s["id"]
        seen = set()
        for t in s["t"]:
            assert len(t["m"]) == 5 and len(set(t["m"])) == 5
            assert len(t["e"]) == 2 and len(set(t["e"])) == 2
            assert max(t["m"]) <= 50 and min(t["m"]) >= 1
            assert max(t["e"]) <= s["ep"]
            assert t["hm"] == sorted(set(t["m"]) & set(s["am"]))
            assert t["he"] == sorted(set(t["e"]) & set(s["ae"]))
            assert t["c"] == f"{t['nm']}+{t['ne']}"
            key = (tuple(t["m"]), tuple(t["e"]))
            seen.add(key)
        assert len({tuple(t["m"]) for t in s["t"]}) == 20, s["id"]
        assert s["s"]["m"] == sum(t["nm"] for t in s["t"])
        assert s["s"]["rm"] >= 0
        assert "l" in s and len(s["l"]) > 40
        assert len(s["w"]) == 12
        assert abs(sum(s["h"]) - 1) < 0.03
        assert len(s["h"]) == 20
    nxt = payload["next"]["tickets"]
    assert len(nxt) == 20
    mains = [tuple(t["m"]) for t in nxt]
    assert len(set(mains)) == 20, mains
    for i, a in enumerate(nxt):
        for j, b in enumerate(nxt):
            if i >= j:
                continue
            share = len(set(a["m"]) & set(b["m"]))
            assert share < 4, (a["x"], b["x"], a["m"], b["m"], share)
    assert payload["meta"]["tickets_per_draw"] == 20
    assert payload["next"]["draw"] == "2026-09-18"
    avg = payload["summary"]["avg_main_per_ticket"]
    assert 0.40 < avg < 0.60, avg
    print("ok", len(steps), "steps; 20 tickets; avg ticket", avg, "delta", payload["summary"]["delta_vs_random"])


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("FAIL", e)
        sys.exit(1)
