# Track 8 — Resultados evaluación humana (AB test)

> Ronda 1: 2026-08-11, Antonio, 60 pares (15 clips × 4 pares).
> Ronda 2 (decisión): 3 oyentes (Antonio, Matina, victoria) × 5 pares difíciles
> (HTML autocontenido, orden y lados aleatorizados por oyente) → `media/ab_csv/`.
> Votos servidor: `.auto/human/votes.csv` (local).

## Condiciones (todas normalizadas a -16 LUFS)

- **A** = original · **B** = DF2 · **C** = DF2 + master (preset youtube) · **D** = DF3

## Preferencia por par (n=15 cada uno)

| Par | Gana lado izq. | Gana lado der. | Empate |
|---|---|---|---|
| **B vs C** (¿aporta el master?) | B=DF2: 27% | **C=DF2+master: 47%** | 27% |
| **B vs D** (DF2 vs DF3) | B=DF2: 13% | **D=DF3: 40%** | 47% |
| **C vs D** (master vs DF3) | **C: 33%** | D=DF3: 20% | 47% |
| **A vs C** (original vs producto) | A=original: 7% | **C=DF2+master: 80%** | 13% |

## MOS medio por condición

| Condición | MOS | n |
|---|---|---|
| A = original | **1.93** | 15 |
| B = DF2 | 2.87 | 30 |
| C = DF2 + master | **3.07** | 45 |
| D = DF3 | 3.07 | 30 |

## Lectura honesta

- **El producto vende**: DF2+master vs original = **80% preferencia** (y MOS 1.93 → 3.07).
- **El master aporta, pero el umbral ≥60% NO se cumple aún** (47% vs 27% con 27% de
  empates, n=15, 1 oyente). Si los empates cuentan como "no peor", C ≥ B en 74%.
- Los empates altos (27-47%) son esperables: en clips ya limpios el master solo
  añade loudness/consistencia; la diferencia se nota en clips difíciles
  (susurros, grito, conversación con ruido) — donde C gana con MOS superior
  (p.ej. test_pc4_martina y test_pc5_conversacion: MOS 1 para DF2 vs 3 para C).
- **DF3 suena subjetivamente mejor que DF2** (40% vs 13%) pese a perder en PESQ
  sintético — y a que en el benchmark real degradó test_pc4_martina a casi
  silencio (TP -80 dB). Candidato a re-evaluar con más oyentes.

## Decisión #12 — RESUELTA ✅ (2026-08-11, ronda 2)

Test de 5 pares difíciles (susurros, grito, metro, agua, conversación baja) con
**3 oyentes** (Antonio, Matina, victoria), orden y lados A/B aleatorizados:

| Oyente | n | C (DF2+master) | B (DF2) | Empate | MOS C vs B |
|---|---|---|---|---|---|
| Antonio | 15 | 8 (53%) | 4 (27%) | 3 | 3.20 vs 3.00 |
| Matina | 5 | 3 (60%) | 1 (20%) | 1 | 3.0 vs 3.0 |
| victoria | 5 | 4 (80%) | 1 (20%) | 0 | 3.0 vs 3.0 |
| **TOTAL** | **25** | **15 (60%)** | **6 (24%)** | **4 (16%)** | 3.12 vs 3.00 |

- **Umbral `DF2+master ≥ DF2 en ≥60%`: ✅ CUMPLIDO (60% exacto, n=25)**.
- Criterio alternativo (C ≥ B incl. empates): **76%**.
- Por clip (los 5 difíciles): C gana en 4 de 5 (pc5 3/3, martina 2C+1tie,
  chorros 2C+1tie, grito 2C+1B); **B gana 3/3 en `test_metros`** (ruido de
  metro constante) — el punto débil del master: ruido estacionario ancho de
  banda. Recomendación: para ese tipo de audio, DF2 solo o preset `bad-room`.

**Conclusión**: el pipeline DF2+master queda **validado como diferencial de
producto** (60% ≥ 60% + 80% vs original en ronda 1 + MOS superior).

## Cómo reproducir

```bash
.venv-ims/Scripts/python.exe ui/server.py 8770   # -> ab-player.html, dropdown de pares
# votos -> .auto/human/votes.csv (analisis con el script de la conversacion)
```
