# Audit kompletnosti — Eurojackpot 2012-03-23 až 2026-09-15

**Verdikt: kompletné. 990 / 990 žrebov. Nechýba ani jeden.**

Dnes je 16. 9. 2026 (streda). Posledný publikovaný žreb je utorok **15. 9. 2026**. Piatok 18. 9. 2026 ešte neprebehol — oficiálne API ho nemá, a v datasete tiež nie je. To je správne.

## Ako sa dá dokázať, že nechýba žreb

Eurojackpot má pevný kalendár:

1. Prvý žreb: **piatok 23. 3. 2012**. Piatok pred ním (16. 3. 2012) oficiálne API vracia prázdny výsledok — žreb neexistuje.
2. Do 18. 3. 2022 vrátane: **iba piatky**. Žiadny zrušený piatok, ani Vianoce / Silvester.
3. Od **25. 3. 2022**: nové pravidlá 2 z 12. Prvý utorok je **29. 3. 2022**. Utorok 22. 3. 2022 oficiálne API prázdne — žreb neexistuje.
4. Odvtedy: utorok + piatok, medzera medzi žrebmi je vždy 3 alebo 4 dni.

Spočítané od nuly, bez API:

| Rok | Žrebov | Prečo práve toľko |
|---|---|---|
| 2012 | 41 | piatky od 23. 3. do 28. 12. |
| 2013 | 52 | každý piatok |
| 2014 | 52 | každý piatok |
| 2015 | 52 | každý piatok |
| 2016 | 53 | 1. 1. 2016 bol piatok |
| 2017 | 52 | každý piatok |
| 2018 | 52 | každý piatok |
| 2019 | 52 | každý piatok |
| 2020 | 52 | každý piatok |
| 2021 | 53 | 1. 1. 2021 bol piatok |
| 2022 | 92 | 11 piatkov do 18. 3. + utorok/piatok od 25. 3. |
| 2023 | 104 | utorok + piatok |
| 2024 | 105 | priestupný rok, začína utorkom, končí utorkom |
| 2025 | 104 | utorok + piatok |
| 2026 | 74 | 2. 1. 2026 – 15. 9. 2026 |
| **Spolu** | **990** | |

Dataset má presne tieto dátumy. Nula chýbajúcich, nula navyše.

## Krížové overenie zdrojov (dátumy)

Každý zdroj nižšie má **tých istých 990 dátumov**, rok po roku identické počty:

| Zdroj | Dátumy | Čísla |
|---|---|---|
| Oficiálne API eurojackpot.com / WestLotto (990 JSON súborov) | 990/990 | 990/990 platných 5+2 |
| Kalendárne pravidlo (piatok / utorok) | 990/990 | — |
| Oficiálny WestLotto Excel 2012–2021 | 511/511 | 511/511 zhoda |
| JackpotStat archív 2012–2026 | 990/990 | **990/990 zhoda čísiel** |
| euroj.eu | 990/990 | 988/990 |
| lotostatistika.com.hr (tá istá rodina ako euroj.eu) | 990/990 | 988/990 |

Dva rozdiely na euroj.eu / lotostatistika **nie sú chýbajúce žreby**. Sú to preklepy na ich stránke. Oficiálne API, WestLotto Excel, JackpotStat aj LottoROI majú:

- 17. 1. 2014: `4, 7, 17, 25, 29 + 2, 4` (euroj.eu malo 15 namiesto 17)
- 24. 1. 2025: `2, 9, 16, 46, 47 + 3, 9` (euroj.eu malo 1 namiesto 2)

## Hranice, ktoré musia byť prázdne

Overené priamym dopytom na oficiálne API:

- 16. 3. 2012 (piatok pred štartom) — žiadny žreb
- 23. 3. 2012 — prvý žreb `5, 8, 21, 37, 46 + 6, 8`
- 22. 3. 2022 (utorok pred zavedením utorkov) — žiadny žreb
- 25. 3. 2022 — prvý žreb 2 z 12
- 29. 3. 2022 — prvý utorňajší žreb
- 15. 9. 2026 — posledný publikovaný žreb `5, 6, 10, 27, 42 + 1, 8`
- 18. 9. 2026 (najbližší piatok) — ešte neprebehol

## Kontrola súborov API

Všetkých 990 súborov `raw/api/YYYY-MM-DD.json`:

- `head.datum` sa zhoduje s názvom súboru
- 5 unikátnych hlavných čísiel v rozsahu 1–50
- 2 unikátne euročísla
- 12 výherných tried pri každom žrebe

## Záver

Nie je možné, že v datasete chýba historický žreb: každý piatok od 23. 3. 2012 a každý utorok od 29. 3. 2022 až do 15. 9. 2026 má oficiálny výsledok, a štyri nezávislé archívy hlásia ten istý zoznam 990 dátumov.

SHA-256 súboru `data/eurojackpot_draws.csv`:

`879844417f940edf36a755b342b87b08d9a9ac2e949b2f3c7b6fed61cb4fa4f2`
