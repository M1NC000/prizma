#!/usr/bin/env bash
# Prizma local lab — double-click start.command on a Mac, or run ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

need_python() {
  echo
  echo "Chýba Python 3.11 alebo novší."
  echo "Na MacBooku s čipom Apple (M1–M5) nainštaluj Homebrew Python:"
  echo
  echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
  echo "  brew install python@3.12"
  echo
  echo "Potom znova spusti tento súbor."
  exit 1
}

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    PY="$c"
    break
  fi
done
[ -n "$PY" ] || need_python

ver="$("$PY" -c 'import sys; print(sys.version_info.major * 100 + sys.version_info.minor)')"
if [ "$ver" -lt 311 ]; then
  echo "Našiel som $($PY --version), treba 3.11+."
  need_python
fi

arch="$("$PY" -c 'import platform; print(platform.machine())')"
echo "Python $($PY --version | awk '{print $2}') · $arch"

if [ ! -d .venv ]; then
  echo "Prvé spustenie: vytváram .venv a inštalujem knižnice (1–2 min)…"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

export PYTHONPATH="$(pwd)"
python - <<'PY'
from pathlib import Path
from engine.paths import draws_csv
import pandas as pd

csv = draws_csv()
assert csv.exists(), f"chýba {csv}"
n = len(pd.read_csv(csv))
assert n == 990, n
learn = Path("web/assets/learning.json")
assert learn.exists(), "chýba web/assets/learning.json — walk-forward ešte nie je v balíku"
print(f"Dáta OK — {n} žrebov, laboratórium pripravené.")
PY

HOST="${PRIZMA_HOST:-127.0.0.1}"
PORT="${PRIZMA_PORT:-8765}"
URL="http://${HOST}:${PORT}"

echo
echo "Prizma beží na  ${URL}"
echo "Nechaj toto okno otvorené. Zastavenie: Ctrl+C"
echo

if command -v open >/dev/null 2>&1; then
  (sleep 1.3 && open "$URL") &
elif command -v xdg-open >/dev/null 2>&1; then
  (sleep 1.3 && xdg-open "$URL") &
fi

exec python -m uvicorn server.app:app --host "$HOST" --port "$PORT"
