# Dátový slovník

## `eurojackpot_draws.csv` / hárok `draws`

| Stĺpec | Typ | Popis |
|---|---|---|
| `draw_id` | int | Poradie žrebu od 1 (23. 3. 2012) |
| `draw_date` | date ISO | Dátum žrebu `YYYY-MM-DD` |
| `year` | int | Kalendárny rok |
| `month` | int | Mesiac 1–12 |
| `iso_week` | int | ISO týždeň |
| `weekday_name` | string | `Tuesday` alebo `Friday` |
| `api_incomplete_flag` | bool | Oficiálny príznak `fehlenDaten`. Pri 4 žreboch v 2025 je true, ale čísla aj kvóty sú kompletné |
| `era` | string | `2of8_friday`, `2of10_friday`, `2of12_tue_fri` |
| `draw_frequency` | string | `Friday` alebo `Tuesday+Friday` |
| `formula` | string | Oficiálny vzorec, napr. `5 aus 50 und 2 aus 12` |
| `main_pool_size` | int | Vždy 50 |
| `euro_pool_size` | int | 8, 10 alebo 12 podľa éry |
| `main_n1` … `main_n5` | int | Hlavné čísla **vzostupne** |
| `euro_e1`, `euro_e2` | int | Euročísla **vzostupne** |
| `main_numbers_draw_order` | string | Poradie, v akom padli hlavné čísla, oddelené čiarkou |
| `euro_numbers_draw_order` | string | Poradie euročísel |
| `stake_eur` | float | Celoeurópsky stávkový objem v EUR |
| `advertised_jackpot_eur` | float | Jackpot ohlásený pred žrebom. Žreb 1 = 10 000 000 EUR (štartovací jackpot). Ďalšie = `next_jackpot` predchádzajúceho žrebu |
| `jackpot_won` | bool | Padol jackpot (trieda 5+2 mala aspoň 1 výhercu) |
| `jackpot_winners` | int | Počet výhercov 5+2 |
| `jackpot_share_eur` | float | Výhra na jedného jackpotového výhercu; prázdne, ak jackpot nepadol |
| `jackpot_total_paid_eur` | float | `jackpot_winners * jackpot_share_eur` |
| `next_draw_date` | date | Dátum nasledujúceho žrebu |
| `next_jackpot_eur` | float | Jackpot ohlásený na nasledujúci žreb |
| `total_winners` | int | Súčet výhercov vo všetkých 12 triedach |
| `total_payout_eur` | float | Súčet vyplatených kvót (winners × payout) vo všetkých triedach |

## `eurojackpot_prize_tiers.csv`

Jedna riadka = jedna výherná trieda jedného žrebu (vždy 12 riadkov na žreb).

| Stĺpec | Popis |
|---|---|
| `draw_id`, `draw_date` | Väzba na žreb |
| `prize_class` | Oficiálne číslo triedy 1–12 v **danom čase** |
| `match_code` | Stabilný kód zhody: `5+2`, `5+1`, `5+0`, `4+2`, `4+1`, `4+0`, `3+2`, `3+1`, `3+0`, `2+2`, `2+1`, `1+2` |
| `description_en` | Anglický popis z oficiálneho API |
| `short_label` | Krátky popis, napr. `5 + 2` |
| `winners` | Počet výhercov v triede |
| `payout_eur` | Kvóta na jedného výhercu v EUR (0 ak trieda nebola obsadená / jackpot roloval) |
| `total_paid_eur` | `winners * payout_eur` |

Pri historickom porovnaní **vždy používaj `match_code`**. Trieda 6 bola napr. `4+0` do marca 2022 a `3+2` potom.

## `eurojackpot_analysis.csv`

Predpočítané znaky hlavných čísiel a euročísel: súčet, min/max/rozsah, počet nepárnych/párnych, nízke (1–25) / vysoké (26–50), počet susedných dvojíc, počet čísiel v dekádach 1–10 … 41–50, súčet euročísel.

## `eurojackpot_number_frequency.csv`

Frekvencia každého čísla **v rámci éry**. `ball_type` je `main` alebo `euro`. `frequency` = počet výskytov / počet žrebov v ére.

## `eurojackpot_regional_winners.csv`

Regionálne `aufteilung` z oficiálneho API, typicky pre vyššie triedy. Nie je to kompletné pre každú triedu každého žrebu.

## `eurojackpot_yearly_summary.csv`

Agregácia po kalendárnom roku: počet žrebov, padnuté jackpoty, priemerný a celkový stávkový objem, priemerný a maximálny inzerovaný jackpot.
