# Skill: voxera-audio-tonal

> Mirror del skill del agente (canonical en el skill store local de pi,
> `~/.agents/skills/voxera-audio-tonal/SKILL.md`, fuera del repo).

## When to Use
Añadir MUSICALIDAD tonal a un vídeo con voxera (`voxera audio transition|riser|melody`), editar `src/voxera/audio_tonal.py`, o diagnosticar un elemento tonal que no empuja la emoción. Trigger: el pedido es "tell the people how to feel" — QUÉ debe sentir el oyente, no qué se mueve en pantalla: "haz que esta escena se sienta X", "quiero tensión antes del corte", "una melodía triste debajo", "transición de esperanza a melancolía", "música de fondo", "score emocional".

DECISIÓN (orden estricto):
1º Identificar la EMOCIÓN del momento narrativo — qué debe SENTIR el oyente en ese punto, no la acción visual.
2º Traducirla a un mood de la tabla MOODS. Cada mood YA decide modo, raíz, registro, timbre, detune, vibrato, contorno y densidad — no improvisar esos parámetros a mano:

| mood | modo | raíz (registro) | timbre | frase-emoción (qué le dice al oyente) |
|---|---|---|---|---|
| hope | lydian | C (oct 5) | triangle | asciende y abre: el #4 del lidio es el color de las promesas |
| tension | phrygian | E (oct 3) | saw | semitonos bajos y ritmo apretado: algo va a pasar |
| melancholy | minor | A (oct 4) | sine | desciende lento, sin prisa: lo que ya no vuelve |
| triumph | major | C (oct 4) | square | arpegio ascendente de tónica a octava: meta alcanzada |
| wonder | pentatonic_major | G (oct 5) | bell | campanas pentatónicas escasas: no hay notas malas, solo asombro |
| calm | dorian | D (oct 4) | sine | dorio (menor con 6ª mayor): serenidad con movimiento suave |
| mystery | harmonic_minor | A (oct 4) | sine | la 7ª mayor sobre acorde menor y el detune ancho: la puerta entreabierta |
| urgency | pentatonic_minor | E (oct 4) | saw | pentatónica menor densa y staccato: corre |

Guía narrativa→mood: revelación esperanzadora→hope; cuenta atrás/plano que se cierra→tension; despedida/nostalgia→melancholy; logro/triunfo→triumph; asombro/primera mirada→wonder; respiro/después de la tormenta→calm; enigma/pista falsa→mystery; persecución/CTA que corre→urgency.
3º Elegir la primitiva por la FORMA del pedido:
- transición de emoción A→B en un punto → `transition` (acorde A → acorde B con revozado de movimiento mínimo y glide logarítmico por voz, no un crossfade crudo)
- tensión creciente que RESUELVE en un corte/impacto → `riser` (--hit = timestamp del corte; la subida acaba EXACTO en el hit, la cola de release resuelve después)
- estado emocional sostenido bajo la voz → `melody` (pregunta + respuesta en la escala y contorno del mood; apoyo bajo voz con --duck 4-8)

NO usar este skill cuando el pedido es de otro dominio:
- SOLO movimiento/énfasis visual (zoom, punch-in, auto-emphasis) → skill voxera-grow-zoom
- filtrado narrativo de "otro espacio" (auriculares, teléfono, flashback) → skill voxera-audio-lowpass

## Procedure
1. Comandos (defaults reales del módulo):
   - `.venv-ims/Scripts/voxera audio transition IN -o OUT [--from calm] [--to hope] [--from-key NOTA] [--to-key NOTA] [--at 0] [--dur 3] [--gain -18] [--curve 62] [--easing smooth|out|in|linear] [--dry-run]`
   - `.venv-ims/Scripts/voxera audio riser IN -o OUT [--mood tension] [--key NOTA] [--hit T] [--dur 2] [--style notes|glide] [--gain -16] [--tail 0.3] [--dry-run]`
   - `.venv-ims/Scripts/voxera audio melody IN -o OUT [--mood wonder] [--key NOTA] [--start 0] [--bars 4] [--bpm B] [--seed 0] [--gain -20] [--duck 0-24] [--dry-run]`
   Rangos (validate): transition dur 0.5-30, at ≥ 0; riser dur 0.5-15, hit ≥ dur, tail 0-5; melody bars 1-64, bpm 30-300 (default: el del mood), duck 0-24; gain SIEMPRE [-60, 0] (positivos rechazados).
2. `--key`: default = la raíz del mood (hope→C, tension→E, ...); en transition son `--from-key`/`--to-key` (una por acorde). Solo sobreescribir para casar con música ya existente en el clip (deducir/pedir la tónica; sostenidos — "C#", no "Db"). El registro (octava) lo aporta siempre el mood: no es configurable.
3. Flujo recomendado: `--dry-run` PRIMERO. VOXERA PLAN muestra — transition: acordes A→B con nombres de nota y movimiento mínimo en semitonos; riser: subida (grados o glide), hit y tail; melody: nº de notas, rango MIDI, bpm/seed y duck (renderiza para contar notas: rápido y determinista). Luego escuchar, ajustar gain (-16 a -24 como apoyo bajo voz), repetir.
4. Colocación (reglas duras; `_check_placement` rechaza lo que no cabe):
   - transition: `--at` en el CORTE de escena (región [at, at+dur]; el cambio armónico empuja el corte).
   - riser: TERMINA en `--hit` — subida [hit-dur, hit], cola [hit, hit+tail]; exige hit ≥ dur y hit+tail ≤ duración del archivo. Sin --hit: el elemento acaba al EOF (hit = duración − tail).
   - melody: desde `--start` con `--bars` múltiplo de la frase (par ≥ 2: pregunta + respuesta); región = start + bars·4·(60/bpm) s.
5. Determinismo: transition y riser no usan azar (misma entrada → misma salida); melody usa RNG sembrado — mismo --seed, misma melodía. Versionar el seed en el proyecto (anotarlo junto al comando para reproducir el render exacto).
6. Receta sobre el audio de un VÍDEO (montaje completo, verificado 2026-08-17): extraer (`ffmpeg -i 02c -vn -ar 48000 -ac 2 -c:a pcm_s16le src.wav`), encadenar los elementos (cada `-o` es el `IN` del siguiente; los elementos no deben solaparse), reconstruir el estéreo según el pitfall del mono, y remuxar SIN tocar el vídeo: `ffmpeg -i 02c -i final.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 320k`. Las anclas salen de words.json (pivote, secciones, CTA), no de tiempos estimados.

## Pitfalls
- Gains positivos los rechaza validate ([-60, 0]), pero los cercanos a 0 (-6, -3) entierran la voz: apoyo bajo voz SIEMPRE negativo, -16..-24 dB.
- saw/square son osciladores naïvos filtrados a 7 kHz (butter2 anti-alias): NO quitar el lowpass — sin él hay aliasing audible.
- detune > 12 cents = batido audible: es CHORUS (dos osc a ±cents), no una afinación rota; mystery usa 14 A PROPÓSITO (la puerta entreabierta).
- El riser DEBE caber en el archivo: hit ≥ dur y hit+tail ≤ duración — si no, EnhancementError (reduce --dur/--tail).
- Melodía fuera de escala imposible por construcción (solo se eligen índices de scale_midi): confía pero verifica con las notas del plan; primera nota = tónica y última nota = tónica (forzadas), la pregunta termina en 4º o 2º grado.
- duck > 10 dB suena a bombeo (rampas de 0.3 s en ambos bordes): apoyo sutil 4-8 dB.
- Fixtures PCM_16 (sf.write sin subtype): comparar contra la entrada LEÍDA, no contra el array original (~1e-5 de cuantización).
- Fuera de la región mezclada la salida es BIT-EXACTA al input (mix_element copia el seco; clip a [-1, 1] solo dentro) — los tests lo exigen.
- bell (wonder) suelta notas que se solapan por el release largo (cada nota suena dur+release): DESEADO — resonancias campaniles, no un bug.
- El CLI SIEMPRE escribe wav 48 kHz MONO (downmix interno) aunque la entrada sea estéreo: para conservar el estéreo del original, reconstruye `stereo = src + (out_mono − mean(src, axis=1))` en ambos canales (el diff ya lleva elemento + duck) con clip a [-1, 1]; fuera de las regiones queda bit-exacto (verificado a 0 LSB24).
- El lector rechaza 96 kHz (solo 16/22.05/44.1/48 kHz): extrae el audio del vídeo con `-ar 48000`; ojo con intermedios de vídeo cuyo loudnorm sale a 96 kHz.
- Al re-renderizar el vídeo (p. ej. subir calidad) los tiempos se mueven: recomputa TODAS las anclas (transition/riser/melody) desde el words.json nuevo, anclando a PALABRAS (busca el ancla en el JSON), no a segundos fijos; luego re-verifica la mezcla.

## Verification
1. tests: `.venv-ims/Scripts/python.exe -m pytest tests/test_audio_tonal.py -q` (56 tests: teoría note_to_midi/scale/triad/voice-leading, tabla MOODS, opciones + validación, renders de las 3 primitivas, mix bit-exacto, plans, e2e).
2. Verificación numérica manual (siempre que se toque el render o la mezcla):
   - transition: rFFT en una ventana inicial y una final del elemento → picos en midi_to_freq de las notas de cada triada (A al inicio, B revozada al final).
   - riser: RMS de ventanas cuartiles del elemento monótono CRECIENTE hasta el hit; longitud = (dur+tail)·sr con el crescendo acabando exactamente en int(dur·sr); tras el hit decae exponencial (τ = tail/3).
   - melody: todas las notas (midi) ∈ scale_midi(root, mode, 2) y la última = tónica (del plan o de la lista de notas de render_melody).
   - mix: np.array_equal(out, dry) fuera de [i0, i0+n_elem).
4. Demos reales (voz estéreo 12.5 s, `media/audio/tonal/`, verificados 2026-08-17): `demo_transition.wav` (hope→melancholy 2-6 s: pico FFT inicial C5=523 Hz del acorde C lidio, final A3=220 Hz = bajo pivote de la tónica de Am, las 5 alturas del acorde B presentes; archivo a 0.5 LSB24 fuera de región, corr(diff, elemento·g)=1.000 dentro); `demo_riser.wav` (tension, hit t=10: cuartiles RMS 1e-5→0.014→0.090→0.140 monótonos, pre-hit > tail); `demo_melody.wav` (wonder, 3 compases, seed 7, duck 6 dB: 6 notas todas en G pent. mayor, frase respuesta termina en tónica G6, dry atenuado −6.00 dB medido en ventana con voz).
   - OJO archivo vs elemento: sobre audio REAL con voz, el pico FFT de la MEZCLA lo domina la voz (elemento a −16..−20 dB) — verificar acordes/crescendo sobre el ELEMENTO puro (render_*) y el archivo vía diff contra `audioio.load_audio(IN).samples` (downmix interno mono 48k; el input puede ser estéreo) con tolerancia 1 LSB24 y correlación del diff.
5. Demo render + escucha: aplicar la primitiva a un clip real y OÍRLA — el plan es necesario pero no suficiente (la emoción se valida con el oído).

## Reference Implementation (código núcleo)

La teoría (escala → triada → revozado de movimiento mínimo) es lo que separa esto de un crossfade crudo; `render_transition` muestra cómo se consume; `mix_element` fija la convención de región bit-exacta (misma que lowpass). Condensado a lo esencial del módulo real (`src/voxera/audio_tonal.py`; `ease` viene de `audio_lowpass`):

```python
import numpy as np

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
SCALES = {
    "major": (0, 2, 4, 5, 7, 9, 11), "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10), "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11), "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11), "pentatonic_major": (0, 2, 4, 7, 9),
    "pentatonic_minor": (0, 3, 5, 7, 10),
}
def note_to_midi(name: str, octave: int = 4) -> int:
    """Nota (sostenidos) + octava → MIDI (C4=60, A4=69)."""
    return NOTE_NAMES.index(name) + 12 * (octave + 1)
def midi_to_freq(midi: float) -> float:
    """MIDI → Hz (A4 = 440 Hz, temperamento igual)."""
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)
def scale_midi(root_midi: int, mode: str, n_octaves: int = 2) -> np.ndarray:
    """Grados del modo ascendentes + tónica superior (len = n_oct·len(iv)+1)."""
    out = [root_midi + 12 * o + iv for o in range(n_octaves) for iv in SCALES[mode]]
    out.append(root_midi + 12 * n_octaves)
    return np.asarray(out, dtype=int)
def triad_midi(root_midi: int, mode: str) -> tuple[int, int, int]:
    """Triada 1-3-5 = índices 0, 2, 4 de scale_midi (pentatónicas: idem)."""
    n = scale_midi(root_midi, mode, 1)
    return int(n[0]), int(n[2]), int(n[4])
def best_voice_leading(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, ...]:
    """Revozado de b con movimiento mínimo respecto a a: rotaciones de b y
    octavas ±12 por nota; minimiza Σ|a_i-b_i| (empate → menor salto máximo).
    LA diferencia entre un crossfade crudo y una transición musical."""
    best, best_key = tuple(b), None
    for rot in range(len(b)):
        rotated = b[rot:] + b[:rot]
        voiced, total = [], 0
        for b_i, a_i in zip(rotated, a):
            o = min((-12, 0, 12), key=lambda o: abs(b_i + o - a_i))
            voiced.append(b_i + o); total += abs(b_i + o - a_i)
        key = (total, max(abs(v - a_i) for v, a_i in zip(voiced, a)))
        if best_key is None or key < best_key:
            best_key, best = key, tuple(voiced)
    return best

def render_transition(sr: int, opts) -> np.ndarray:
    """Pad A→B (solo el elemento): glide LOGARÍTMICO por voz (movimiento
    melódico, NO crossfade), blend triangle+sine con detune/vibrato del mood
    destino, bajo pivote (tónica de B una octava abajo) en la 2ª mitad."""
    mood_a, mood_b = MOODS[opts.from_mood], MOODS[opts.to_mood]
    root_a = note_to_midi(opts.from_key or mood_a.root, mood_a.octave)
    root_b = note_to_midi(opts.to_key or mood_b.root, mood_b.octave)
    chord_a = triad_midi(root_a, mood_a.mode)
    b_voiced = best_voice_leading(chord_a, triad_midi(root_b, mood_b.mode))
    n = int(round(opts.dur * sr))
    t = np.arange(n, dtype=np.float64) / sr
    p = np.asarray(ease(t / opts.dur, opts.curve, opts.easing))  # curva S
    out = np.zeros(n, dtype=np.float64)
    for a_i, b_i, amp in zip(chord_a, b_voiced, (1.0, 0.8, 0.6)):  # la raíz manda
        fa, fb = midi_to_freq(float(a_i)), midi_to_freq(float(b_i))
        f = fa * (fb / fa) ** p  # glide logarítmico por voz
        f = f * (1.0 + mood_b.vibrato_depth * np.sin(2 * np.pi * mood_b.vibrato_hz * t))
        ratio = 2.0 ** (mood_b.detune_cents / 1200.0)  # detune chorus ±cents
        x = 0.25 * (_osc("triangle", f * ratio, sr, t) + _osc("triangle", f / ratio, sr, t)
                    + _osc("sine", f * ratio, sr, t) + _osc("sine", f / ratio, sr, t))
        out += amp * x
    bass = _osc("sine", midi_to_freq(root_b - 12), sr, t)  # bajo pivote
    mask = np.asarray(ease(np.clip((p - 0.5) * 2.0, 0.0, 1.0), 62.0, "smooth"))
    out += 0.5 * bass * mask
    out = out * _adsr(n, sr, 0.05, 0.15)  # max(attack/release de ambos moods)
    return _normalize(out)  # pico 0.5

def mix_element(samples: np.ndarray, sr: int, element: np.ndarray, at: float,
                gain_db: float, duck_db: float = 0.0, fade: float = 0.3) -> np.ndarray:
    """Mezcla el elemento sobre el seco en `at` s. Fuera de [i0, i0+n_elem):
    BIT-EXACTA al input (clip a [-1, 1] SOLO dentro). duck>0 baja el seco
    bajo el elemento con rampas S de `fade` s en ambos bordes."""
    dry = np.asarray(samples, dtype=np.float32).reshape(-1)
    elem = np.asarray(element, dtype=np.float32).reshape(-1)
    out = dry.copy()  # fuera de la región: bit-exacto
    i0 = int(round(at * sr))
    if i0 >= len(dry) or elem.size == 0:
        return out
    i1 = min(i0 + elem.size, len(dry))
    region = dry[i0:i1].astype(np.float64)
    if duck_db > 0.0:
        n_r = i1 - i0
        t_r = np.arange(n_r, dtype=np.float64) / sr
        depth = 10.0 ** (-duck_db / 20.0)
        shape = np.asarray(ease(np.clip(t_r / fade, 0.0, 1.0), 62.0, "smooth")) * np.asarray(
            ease(np.clip(((n_r / sr) - t_r) / fade, 0.0, 1.0), 62.0, "smooth"))
        region = region * (1.0 - (1.0 - depth) * shape)
    g = 10.0 ** (gain_db / 20.0)
    out[i0:i1] = np.clip(region + elem[: i1 - i0].astype(np.float64) * g,
                         -1.0, 1.0).astype(np.float32)
    return out
```

Omitido (ver `src/voxera/audio_tonal.py`): la síntesis privada (`_osc`/`_bell`/`_adsr`/`_voice`/`_normalize`, anti-alias 7 kHz de saw/square, parciales inarmónicos de la campana), la tabla MOODS completa como código (arriba, como tabla), `render_riser` (grados con duraciones geométricas r=0.72 apilados en acorde, o glide de 2 octavas exponencial; crescendo (ease)² hasta el hit + cola exponencial τ=tail/3), `render_melody` (rejilla de corcheas ponderada por density, pregunta/respuesta, rng sembrado) y los `build_*_plan`/`*_file`.
