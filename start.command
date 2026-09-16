#!/bin/bash
# Dvojklik v Findri na Macu. Nechaj okno otvorené, kým laboratórium používaš.
cd "$(dirname "$0")" || exit 1
chmod +x ./start.sh 2>/dev/null || true
./start.sh
status=$?
if [ "$status" -ne 0 ]; then
  echo
  echo "Niečo sa nepodarilo (kód $status)."
  echo "Okno zatvoríš Enterom."
  read -r _
fi
