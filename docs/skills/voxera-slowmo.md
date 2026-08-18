# voxera-slowmo — slow motion (y fast motion) de vídeo

> Mirror en repo del skill del agente (`project:improve-my-sound:voxera-slowmo`).
> Canonical: skill store local de pi; este archivo versiona el conocimiento en el repo.

## When to Use

Aplicar slow motion (factor < 1) o fast motion (factor > 1) a vídeos con
`voxera video slowmo`, o segmentos de vídeo (`--at S:E`), diagnosticar
timestamps desalineados, o replicar el efecto de slow motion de Premiere/
After Effects sin GPU. El slow motion es el efecto con **mayor soporte
académico** para percepción de calidad en vídeo de producto/demo:
JMR N=27,227.

## Procedure

1. Comando:
   `PYTHONPATH=src python -m voxera.cli video slowmo IN -o OUT [--factor F] [--at S:E] [--interpolate none|minterpolate] [--dry-run]`.
   Defaults: factor 0.5 (2x más lento); interpolación none; CRF 18; AAC 192k.

2. Factor semántica: multiplicador de velocidad. `0.5` = 2x más lento,
   `0.25` = 4x más lento, `2.0` = 2x más rápido. Rango `[0.125, 4.0]`.

3. **Clip completo** (sin `--at`): un solo paso ffmpeg.
   - Vídeo: `setpts=PTS/{factor}` — re-escala timestamps, `fps=` fuerza
     el frame rate de salida para mantener fps.
   - Audio: cadena de `atempo` (rango por stage `[0.5, 100]`; para
     `factor < 0.5` se encadenan N stages con `stage = factor**(1/n) >= 0.5`).
   - Si no hay pista de audio: `-an` (vídeo only).

4. **Segmento** (`--at S:E`): S y E se cuantizan a la rejilla de frames
   (`round(t*fps)/fps`). E se recorta a la duración del input si es mayor.
   - Vídeo: expresión `setpts` condicional con `if(lt(T,S), PTS, if(lt(T,E),
     S/TB+(PTS-S/TB)/factor, ADD/TB+PTS-E/TB))` donde `ADD = S + D/F`.
   - Audio: `atrim` en 3 tramos + `atempo` en el medio + `concat`.
   - Fórmula duración: `S + D/F + max(dur-E, 0)`.

5. `minterpolate` (opcional): interpola frames sintéticos `mi_mode=mci`.
   MUY lento (~10x). Solo útil cuando `factor < 1` y `fps > fuente`.

6. Verificación del módulo:
   `python -m pytest tests/test_slowmo.py -q --import-mode=importlib -p no:hydra_pytest`.

## Pitfalls

- **atempo stage range [0.5, 100]**: `factor=0.25` necesita 2 stages de
  `0.5` cada uno (0.5 × 0.5 = 0.25). `factor=0.125` → 3 stages. Usar
  `atempo_chain()` que calcula N mínimo automáticamente.
- **trim resets PTS a 0**: después de `trim`, PTS empieza en 0 en el
  timebase del input. Los offsets de `setpts` deben usar valores en la
  unidad correcta (ticks, no segundos). TB para vídeo = `1/out_fps`,
  para audio = `1/48000`.
- **concat necesita formato idéntico/fps**: todos los streams de entrada
  al `concat` deben tener el mismo formato y timebase. Si se usa
  `setpts` para cambiar timestamps, el fps efectivo cambia y concat
  produce frames duplicados/faltantes. Para vídeo, usar `if(lt(T,...))`
  en vez de trim+concat.
- **minterpolate muy lento**: ~10x más lento que realtime. Solo usar con
  `--interpolate minterpolate` cuando se necesita slow motion suave para
  demo/producto. Sin minterpolate, el slow motion repite frames (menor
  calidad pero instantáneo).
- **Cuantización de frame-grid**: S y E se snapean a `round(t*fps)/fps`.
  Usar tolerancia de ±1 frame en las expectativas de duración.
- **`-r` para fps**: sin `-r`, `setpts` stretching causa que ffmpeg
  reporte un fps menor al original. `-r {fps}` fuerza el frame rate
  duplicando frames cuando es necesario.

## Verification

1. Suite del módulo: 27 passed (`tests/test_slowmo.py --import-mode=importlib -p no:hydra_pytest`).
2. E2E clip completo: 4s testsrc2@30fps → factor 0.5 → ~8s, fps 30;
   factor 0.25 → ~16s.
3. E2E segmento: 4s input, `--at 1:3` factor 0.5 → ~6s (1s + 2s×2 + 1s).
4. CLI: `--dry-run` imprime VOXERA PLAN con factor/duración/math;
   `--help` en español.
5. Sin audio: funciona (vídeo only, `-an`).
6. atempo_chain: 0.5 → 1 stage; 0.25 → 2 stages; 0.125 → 3 stages;
   2.0 → 1 stage; todos los stages ≥ 0.5.
