# Prizma — laboratórium Eurojackpotu

Lokálna webová aplikácia nad **990 oficiálnymi žrebmi** (23. 3. 2012 – 15. 9. 2026).
Frekvencie, testy náhody, walk-forward laboratórium s 20 tiketmi na kolo.

Toto **nezvyšuje** šancu na jackpot. Pri aktuálnych pravidlách je 5+2 stále **1 : 139 838 160**.

Pripravené na **MacBook Pro s čipom Apple Silicon** (M1–M5, vrátane základného M5). Knižnice idú natívne ako `arm64`, Rosetta netreba.

## Inštalácia na Macu (raz)

### 1. Python 3.12

Ak ešte nemáš Homebrew:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Na čipe M5 po inštalácii Homebrew doplň PATH (príkaz ti vypíše sám; typicky):

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Potom:

```bash
brew install python@3.12
python3.12 --version
```

Má to vypísať `3.12.x`. Ak `python3 -c 'import platform; print(platform.machine())'` vráti `arm64`, si na natívnom čipe. Ak `x86_64`, otvor Terminal.app z `/Applications` (nie cez Rosettu).

### 2. Stiahni projekt

```bash
git clone https://github.com/bielikmilan226-hue/prizma.git
cd prizma
```

Alebo v GitHub Desktop: **File → Clone repository → prizma**.

### 3. Spusti

**Najpohodlnejšie:** vo Findri dvojklik na `start.command`.
Ak macOS povie, že aplikáciu nejde otvoriť, klikni pravým → **Otvoriť**.

Alebo v Termináli:

```bash
chmod +x start.sh start.command
./start.sh
```

Prvé spustenie vytvorí `.venv` a stiahne knižnice (asi 1–2 minúty, ~150 MB).
Potom sa otvorí prehliadač na [http://127.0.0.1:8765](http://127.0.0.1:8765).

Okno Terminálu nechaj otvorené. Zastavenie: **Ctrl+C**.

Ďalšie spustenia sú už rýchle — znova `./start.sh` alebo dvojklik.

## Čo v aplikácii je

| Záložka | Obsah |
|---|---|
| Prehľad | posledné žreby, jackpot, chi-kvadrát |
| Čísla | frekvencia, omeškanie, FDR po érach |
| Vzory | páry, súčty, tvary |
| Testy náhody | rovnomernosť, utorok vs piatok |
| Self-improving | krokovač 1→990, 20 tiketov, mutácie, ďalší žreb |
| Predikcia | laboratórne tikety (nie sľub výhry) |
| Archív | všetky žreby |
| Metodika | ako sa počíta |

Dáta sú už v balíku (`data/` + `web/assets/learning.json`). Walk-forward 990 kôl **nemusíš** prerátavať.

## Voliteľné príkazy

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD"

python engine/test_learner_invariants.py
python engine/test_walkforward.py
python engine/compute.py     # prerátaj analysis.json
python engine/learner.py     # znova 990 kôl (cca 40 s)
```

## Požiadavky

- macOS na Apple Silicon (M1–M5) alebo Intel
- Python **3.11+** (odporúčaný 3.12 z Homebrew)
- internet len na prvé `pip install`
- prehliadač Safari alebo Chrome
- disk: kód + dáta ~12 MB, po `.venv` cca 150–200 MB

Windows/Linux: rovnaké `./start.sh` (na Linuxe sa prehliadač otvorí cez `xdg-open`, ak je k dispozícii).

## Dáta

Oficiálne výsledky WestLotto / eurojackpot.com. Popis stĺpcov: `data/DATA_DICTIONARY.md`. Audit kompletnosti 990/990: `data/COMPLETENESS_AUDIT.md`.

Éry sa **nesmú** miešať pri frekvenciách:

| `era` | Obdobie | Euro |
|---|---|---|
| `2of8_friday` | 2012–2014 | 2 z 8 |
| `2of10_friday` | 2014–2022 | 2 z 10 |
| `2of12_tue_fri` | 2022–teraz | 2 z 12 · utorok+piatok |

## Licencia

Kód: MIT. Výsledky žrebovania sú verejné oficiálne dáta.
