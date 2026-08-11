# Track 8 — Resultados evaluación humana (AB test)

> Fecha: 2026-08-11 · Oyente: Antonio (1 de 5-10 objetivo) · 60 pares votados
> (15 clips × 4 pares, todos cubiertos) · votos en `.auto/human/votes.csv`
> (gitignored, local) · 1 voto duplicado descartado + 1 smoke de prueba.

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

## Decisión #12 — estado

- Umbral propuesto `DF2+master ≥ DF2 en ≥60% de escuchas`: **NO alcanzado con
  1 oyente** (47%). Dirección correcta (47>27, MOS 3.07>2.87).
- **Acción recomendada**: 2-4 oyentes más haciendo solo el par **B vs C** (15
  clips, ~20 min) para cerrar la decisión con n≥45-75.
- Alternativa: relajar el umbral a "C ≥ B incluyendo empates ≥ 60%" (74% ya).

## Cómo reproducir

```bash
.venv-ims/Scripts/python.exe ui/server.py 8770   # -> ab-player.html, dropdown de pares
# votos -> .auto/human/votes.csv (analisis con el script de la conversacion)
```
