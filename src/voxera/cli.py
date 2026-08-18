"""The voxera command-line interface (Track 0 + Track 1).

Thin adapter over the core: parse args, dispatch, map failures to exit codes.

Exit codes (docs/SPECS-fase2.md):
    0  OK
    1  processing error (EnhancementError)
    2  usage error / unknown backend
    20 VOXERA_NO_SPEECH (VAD speech ratio < 5%)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from voxera import __version__
from voxera.analyze import analyze
from voxera.determinism import dump_report
from voxera.dsp import DEFAULT_PRESET, preset_names
from voxera.enhance import EnhancementError, UnknownBackendError, enhance
from voxera.errors import NO_SPEECH_EXIT_CODE, NoSpeechError
from voxera.master import master_file
from voxera.restore import restore_file
from voxera.score import score_file
from voxera.silence import LEVELS, silence_file
from voxera import video as video_mod
from voxera import video_enhance
from voxera import video_zoom
from voxera import video_teleport
from voxera import video_magnify
from voxera import video_silence
from voxera import video_stabilize
from voxera import captions
from voxera import audio_lowpass
from voxera import audio_tonal
from voxera import autopilot as autopilot_mod

_DEFAULT_LLM_CMD = autopilot_mod._DEFAULT_LLM_CMD
from voxera import video_slowmo

PROG = "voxera"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="device policy (default: auto — CUDA if available)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print the system block (backend, model, device, torch, RTF)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Voice/podcast post-production powered by pluggable neural backends.",
    )
    parser.add_argument("--version", action="version", version=f"voxera {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # --- enhance -----------------------------------------------------------
    enhance_parser = subparsers.add_parser(
        "enhance",
        help="enhance an audio file (NN backend + optional master pipeline)",
        description="Load an audio file, run one pluggable backend's enhancement, "
        "and write the improved file. With --preset the full master pipeline "
        "always runs after the backend; without it, backend-only (back-compat).",
    )
    enhance_parser.add_argument("input", help="source audio file (WAV)")
    enhance_parser.add_argument(
        "-o", "--output", required=True, help="output path for the enhanced audio"
    )
    enhance_parser.add_argument(
        "--backend",
        default="deepfilternet",
        help="enhancement backend (default: deepfilternet); the core validates the name",
    )
    enhance_parser.add_argument(
        "--model",
        default=None,
        help="backend model override (default: backend's own default)",
    )
    enhance_parser.add_argument(
        "--attn-limit-db",
        type=float,
        default=None,
        help="dpdfnet attenuation limit in dB (default: 24)",
    )
    enhance_parser.add_argument(
        "--pf",
        action="store_true",
        default=None,
        help="deepfilternet post-filter (default: off — the measured Pareto winner)",
    )
    enhance_parser.add_argument(
        "--preset",
        nargs="?",
        const=DEFAULT_PRESET,
        default=None,
        help="voice preset — ALWAYS runs the full master pipeline after the NN "
        f"(default preset: {DEFAULT_PRESET})",
    )
    enhance_parser.add_argument(
        "--dsp-only",
        action="store_true",
        help="pipeline without any neural network (master puro)",
    )
    enhance_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and exit 0 without writing OUT or loading the NN",
    )
    enhance_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="inference seed (determinism on CPU)",
    )
    enhance_parser.add_argument(
        "--audio-bitrate",
        default="192k",
        help="AAC bitrate for video output (default: 192k)",
    )
    _add_common(enhance_parser)

    # --- master ------------------------------------------------------------
    master_parser = subparsers.add_parser(
        "master",
        help="voice mastering ONLY: DSP pipeline, no neural network",
        description="Run the frozen voice-mastering pipeline (DC removal, "
        "high-pass, vocal EQ, de-esser, compressor, limiter, loudness) "
        "without any neural network. Byte-equivalent deterministic.",
    )
    master_parser.add_argument("input", help="source audio file (WAV)")
    master_parser.add_argument(
        "-o", "--output", required=True, help="output path for the mastered audio"
    )
    master_parser.add_argument(
        "--preset",
        default=DEFAULT_PRESET,
        choices=preset_names(),
        help=f"voice preset (default: {DEFAULT_PRESET})",
    )
    master_parser.add_argument(
        "--lufs",
        type=float,
        default=None,
        help="override the preset loudness target (LUFS-I)",
    )
    master_parser.add_argument(
        "--dehum",
        action="store_true",
        help="notch the dominant mains hum (50/100/150 Hz) detected in the input",
    )
    master_parser.add_argument(
        "--no-eq", action="store_true", help="disable vocal EQ and de-esser"
    )
    master_parser.add_argument(
        "--no-comp", action="store_true", help="disable the compressor"
    )
    master_parser.add_argument(
        "--no-limit", action="store_true", help="disable the limiter"
    )
    master_parser.add_argument(
        "--no-loudnorm", action="store_true", help="disable loudness normalization"
    )
    master_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and exit 0 without writing OUT",
    )
    master_parser.add_argument(
        "--audio-bitrate",
        default="192k",
        help="AAC bitrate for video output (default: 192k)",
    )
    _add_common(master_parser)

    # --- analyze -----------------------------------------------------------
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="analyze an audio file (analysis ONLY, never modifies audio)",
        description="Report loudness, VAD, SNR, spectral bands, hum, RT60, "
        "DC offset, plosives, breaths, mouth clicks and a heuristic noise "
        "type — every estimate with confidence.",
    )
    analyze_parser.add_argument("input", help="source audio file (WAV)")
    analyze_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="write the JSON report to this path (in addition to stdout)",
    )
    analyze_parser.add_argument(
        "--format",
        choices=("tty", "json"),
        default="tty",
        help="report format (default: tty human summary)",
    )
    _add_common(analyze_parser)

    # --- score --------------------------------------------------------------
    score_parser = subparsers.add_parser(
        "score",
        help="voice score (CVS 0-100) — evaluation ONLY, never modifies audio",
        description="Product Voice Score: Noise/Clarity/Loudness/Room/Dynamics "
        "weighted into a CVS 0-100 + verdict. With --ref also reports "
        "Voice Preservation % (resemblyzer speaker cosine).",
    )
    score_parser.add_argument("input", help="source audio file (WAV)")
    score_parser.add_argument(
        "--ref",
        default=None,
        help="reference audio (e.g. the original) for Voice Preservation %",
    )
    score_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="write the JSON report to this path (in addition to stdout)",
    )
    score_parser.add_argument(
        "--format",
        choices=("tty", "json"),
        default="tty",
        help="report format (default: tty human summary)",
    )
    _add_common(score_parser)

    # --- silence ------------------------------------------------------------
    silence_parser = subparsers.add_parser(
        "silence",
        help="editing ONLY: trim silences, handle breaths and mouth clicks",
        description="Trim over-long gaps between speech (never cutting breaths), "
        "optionally attenuate/remove breaths and attenuate mouth clicks.",
    )
    silence_parser.add_argument("input", help="source audio file (WAV)")
    silence_parser.add_argument(
        "-o", "--output", required=True, help="output path for the cleaned audio"
    )
    silence_parser.add_argument(
        "--level",
        choices=tuple(LEVELS),  # imported below
        default="medium",
        help="trim aggressiveness (default: medium)",
    )
    silence_parser.add_argument(
        "--breaths",
        choices=("preserve", "attenuate", "remove"),
        default="preserve",
        help="breath handling (default: preserve — never remove by default)",
    )
    silence_parser.add_argument(
        "--declick",
        action="store_true",
        help="attenuate mouth-click transients by 6 dB",
    )
    _add_common(silence_parser)

    # --- restore ------------------------------------------------------------
    restore_parser = subparsers.add_parser(
        "restore",
        help="restoration heuristics: declip, deplosive, dehum (+ optional preset)",
        description="Declip (flat-top reconstruction), de-plosive (LF burst "
        "reduction at onsets), de-hum (notch) — then optionally the master "
        "pipeline with a preset.",
    )
    restore_parser.add_argument("input", help="source audio file (WAV)")
    restore_parser.add_argument(
        "-o", "--output", required=True, help="output path for the restored audio"
    )
    restore_parser.add_argument(
        "--declip", action="store_true", help="reconstruct hard-clipped flat-tops"
    )
    restore_parser.add_argument(
        "--deplosive", action="store_true", help="reduce LF plosive bursts at onsets"
    )
    restore_parser.add_argument(
        "--dehum",
        type=int,
        default=None,
        help="notch the mains hum at this frequency (50/100/150)",
    )
    restore_parser.add_argument(
        "--preset",
        default=None,
        choices=preset_names(),
        help="optional master preset to run after restoration",
    )
    restore_parser.add_argument(
        "--lufs", type=float, default=None, help="override the preset LUFS target"
    )
    _add_common(restore_parser)

    # --- inspect ------------------------------------------------------------
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="analyze + recommendation (pretty wrapper of analyze)",
        description="Run analyze and print a recommendation based on the metrics "
        "(dehum, declick, restore, enhance presets).",
    )
    inspect_parser.add_argument("input", help="source audio file (WAV)")
    _add_common(inspect_parser)

    # --- video --------------------------------------------------------------
    video_parser = subparsers.add_parser(
        "video",
        help="neural video enhancement (vertical 9:16, requiere GPU CUDA)",
        description="Enhance vertical videos: Real-ESRGAN (CUDA) + remux de audio. "
        "Un solo default (realesr-animevideov3, ganador AB); --model x4plus es el "
        "escape 'natural' (~10x más lento). Sin menú de presets.",
    )
    vsub = video_parser.add_subparsers(dest="video_command", required=True, metavar="COMMAND")

    vinfo = vsub.add_parser("info", help="probe de un vídeo (ffprobe, JSON)")
    vinfo.add_argument("input", help="archivo de vídeo")

    venh = vsub.add_parser(
        "enhance",
        help="mejorar un vídeo (frames -> NN -> 1080x1920 -> remux audio)",
    )
    venh.add_argument("input", help="vídeo de entrada (vertical 9:16)")
    venh.add_argument("-o", "--output", required=True, help="salida .mp4")
    venh.add_argument(
        "--model",
        choices=video_enhance.VIDEO_MODELS,
        default=video_enhance.DEFAULT_VIDEO_MODEL,
        help=f"modelo (default: {video_enhance.DEFAULT_VIDEO_MODEL} — ganador AB)",
    )
    venh.add_argument(
        "--fps", type=int, default=30,
        help="fps de salida (default 30; 60 duplica el tiempo de cómputo)",
    )
    venh.add_argument("--width", type=int, default=1080, help="ancho de salida (default 1080)")
    venh.add_argument("--height", type=int, default=1920, help="alto de salida (default 1920)")
    venh.add_argument(
        "--tile", type=int, default=512,
        help="tile size (default 512; menor = menos VRAM)",
    )
    venh.add_argument("--no-half", action="store_true", help="fp32 (más VRAM, más lento)")
    venh.add_argument(
        "--crf", type=int, default=18,
        help="x264 CRF (default 18; más alto = fichero más pequeño)",
    )
    venh.add_argument("--audio-bitrate", default="192k", help="AAC bitrate (default 192k)")
    venh.add_argument(
        "--master-audio", nargs="?", const=DEFAULT_PRESET, default=None,
        metavar="PRESET",
        help="masterizar el audio con el preset de voxera antes del remux (default: creator)",
    )
    venh.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan y salir sin escribir nada (no carga NN)",
    )
    venh.add_argument(
        "--keep-frames", action="store_true",
        help="conservar los frames temporales (debug)",
    )

    vcmp = vsub.add_parser(
        "compare",
        help="montar un vídeo A/B lado a lado (herramienta de evaluación)",
    )
    vcmp.add_argument("a", help="primera versión (p.ej. mejorada)")
    vcmp.add_argument("b", help="segunda versión (p.ej. mejorada)")
    vcmp.add_argument("-o", "--output", required=True, help="salida .mp4 lado a lado")
    vcmp.add_argument(
        "--source", default=None,
        help="3er panel opcional (p.ej. el original)",
    )
    vcmp.add_argument(
        "--seg", nargs=2, type=float, default=None, metavar=("START", "END"),
        help="segmento a comparar en segundos (se aplica a todos los inputs)",
    )
    vcmp.add_argument("--fps", type=int, default=30, help="fps de salida (default 30)")

    vzoom = vsub.add_parser(
        "zoom",
        help="zoom 'Grow': push-in con curva de easing + punto de anclaje "
        "(100%% ffmpeg, sin Premiere)",
        description="Zoom no lineal como el del tutorial de @serri.mp4: en vez de "
        "zoom lineal, una curva de easing anclada a un punto (p. ej. la cara). "
        "Sin GPU: solo ffmpeg. Curva 60-65 = el rango del tutorial.",
    )
    vzoom.add_argument("input", help="vídeo de entrada")
    vzoom.add_argument("-o", "--output", required=True, help="salida .mp4")
    vzoom.add_argument(
        "--pct", type=float, default=video_zoom.DEFAULT_PCT,
        help=f"%% de zoom (default {video_zoom.DEFAULT_PCT:g} — la demo del tutorial es +40%% en 4s; 12%% en 55s es invisible)",
    )
    vzoom.add_argument(
        "--dir", dest="direction", choices=video_zoom.ZOOM_DIRECTIONS,
        default=video_zoom.DEFAULT_DIRECTION,
        help="grow (ampliar, default) | shrink (reducir, ventana negra) | pulse (ampliar y reducir)",
    )
    vzoom.add_argument(
        "--hold", type=float, default=video_zoom.DEFAULT_HOLD,
        help="fracción de la duración en el pico, solo pulse (default 0)",
    )
    vzoom.add_argument(
        "--auto-emphasis", action="store_true",
        help="criterio automático: detecta los picos de energía de la voz y "
        "aplica un pulso (ampliar y reducir) en cada momento (pulse_dur="
        f"{video_zoom.ZoomOptions().pulse_dur:g}s, max {video_zoom.ZoomOptions().max_pulses})",
    )
    vzoom.add_argument(
        "--pulse-dur", type=float, default=video_zoom.ZoomOptions().pulse_dur,
        help="duración de cada pulso en segundos (default 3)",
    )
    vzoom.add_argument(
        "--max-pulses", type=int, default=video_zoom.ZoomOptions().max_pulses,
        help="máximo número de pulsos con --auto-emphasis (default 4)",
    )
    vzoom.add_argument(
        "--anchor", default="0.5,0.5", metavar="X,Y",
        help="punto de anclaje normalizado 0-1 (default 0.5,0.5; talking-head ~0.5,0.33)",
    )
    vzoom.add_argument(
        "--curve", type=float, default=video_zoom.DEFAULT_CURVE,
        help=f"curva de easing 0-100 (default {video_zoom.DEFAULT_CURVE:g} — el 60-65 del tutorial; 0 = lineal)",
    )
    vzoom.add_argument(
        "--easing", choices=video_zoom.ZOOM_EASINGS, default="smooth",
        help="smooth (default, S-curva) | out (arranca rápido) | in (acelera) | linear",
    )
    vzoom.add_argument(
        "--start", type=float, default=None,
        help="inicio del segmento en segundos (default: principio)",
    )
    vzoom.add_argument(
        "--end", type=float, default=None,
        help="fin del segmento en segundos (default: fin del vídeo)",
    )
    vzoom.add_argument(
        "--crf", type=int, default=18,
        help="x264 CRF (default 18; más alto = fichero más pequeño)",
    )
    vzoom.add_argument(
        "--audio-bitrate", default="192k", help="AAC bitrate (default 192k)",
    )
    vzoom.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan y salir sin escribir nada",
    )

    vtel = vsub.add_parser(
        "teleport",
        help="teletransportación real: parpadeo blanco + la persona desaparece de A y reaparece en B",
        description="Teletransportación sobre toma única con cámara fija: parpadeo de "
        "silueta blanca 2-2-2 (tutorial @serri.mp4) y, bajo el parpadeo, la persona "
        "se BORRA de su posición (fondo reconstruido: mediana consciente de persona "
        "+ inpainting LaMa) y REAPARECE desplazada (recorte vivo por segmentación, "
        "pegado frame a frame). Con --vanish desaparece sin reaparecer.",
    )
    vtel.add_argument("input", help="vídeo de entrada")
    vtel.add_argument("-o", "--output", required=True, help="salida .mp4")
    vtel.add_argument(
        "--time", type=float, required=True,
        help="instante del teletransporte en segundos (primer frame blanco)",
    )
    vtel.add_argument(
        "--shift", default=None, metavar="DX,DY",
        help=f"destino B como 'dx,dy' en %% del ancho/alto (default "
             f"{video_teleport.DEFAULT_SHIFT} = reaparece a la izquierda); "
             "p.ej. '25,0' derecha, '0,-15' arriba",
    )
    vtel.add_argument(
        "--vanish", action="store_true",
        help="la persona desaparece y NO reaparece (se ve el fondo el resto del vídeo)",
    )
    vtel.add_argument(
        "--plate-samples", type=int, default=video_teleport.DEFAULT_PLATE_SAMPLES,
        help=f"frames muestreados para reconstruir el fondo (default {video_teleport.DEFAULT_PLATE_SAMPLES})",
    )
    vtel.add_argument(
        "--pattern", default=video_teleport.DEFAULT_PATTERN,
        help=f"patrón de parpadeo 'W-G-W' en frames (default {video_teleport.DEFAULT_PATTERN} "
        f"— los 2-2-2 del tutorial: 2 blanco, hueco, 2 blanco)",
    )
    vtel.add_argument(
        "--dilate", type=int, default=video_teleport.DEFAULT_DILATE,
        help=f"px de dilatación de la silueta (default {video_teleport.DEFAULT_DILATE}; "
        "más = cubre mejor al sujeto, menos = silueta más fiel)",
    )
    vtel.add_argument(
        "--crf", type=int, default=18,
        help="x264 CRF (default 18; más alto = fichero más pequeño)",
    )
    vtel.add_argument(
        "--audio-bitrate", default="192k", help="AAC bitrate (default 192k)",
    )
    vtel.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan y salir sin escribir nada",
    )


    vmag = vsub.add_parser(
        "magnify",
        help="lente de aumento circular: amplía la zona elegida (tutorial Premiere 26.3)",
        description="Efecto 'Magnify' de Adobe Premiere Pro 26.3 (tutorial de "
        "@billycreative_): una lente circular que amplía la zona que hay "
        "debajo, como una lupa al enseñar un paper. Medido en el tutorial: "
        "lente estática, radio ~0.35 del ancho, borde nítido. Sin GPU: "
        "ffmpeg + dos PNG generados con numpy.",
    )
    vmag.add_argument("input", help="vídeo de entrada")
    vmag.add_argument("-o", "--output", required=True, help="salida .mp4")
    vmag.add_argument(
        "--center", default="0.5,0.38", metavar="X,Y",
        help="centro de la lente normalizado 0-1 (default 0.5,0.38 — mitad superior, "
        "zona de contenido; en el tutorial ~0.36,0.29)",
    )
    vmag.add_argument(
        "--size", type=float, default=video_magnify.DEFAULT_SIZE,
        help=f"radio de la lente como fracción de min(w,h) (default "
        f"{video_magnify.DEFAULT_SIZE:g} — medido en el tutorial: ~0.35 del ancho)",
    )
    vmag.add_argument(
        "--zoom", type=float, default=video_magnify.DEFAULT_ZOOM,
        help=f"ampliación de la lente en veces (default {video_magnify.DEFAULT_ZOOM:g}x; "
        f"el 'Magnify' de Premiere usa %%, 200 = 3x en esta convención)",
    )
    vmag.add_argument(
        "--feather", type=float, default=video_magnify.DEFAULT_FEATHER,
        help=f"suavizado del borde como fracción del radio (default "
        f"{video_magnify.DEFAULT_FEATHER:g}; 0 = borde duro)",
    )
    vmag.add_argument(
        "--ring-width", type=float, default=video_magnify.DEFAULT_RING_WIDTH,
        help=f"grosor del aro de borde como fracción del radio (default "
        f"{video_magnify.DEFAULT_RING_WIDTH:g}; 0 = sin aro)",
    )
    vmag.add_argument(
        "--motion", choices=video_magnify.MOTIONS,
        default=video_magnify.DEFAULT_MOTION,
        help="auto (default): los movimientos se disparan con los picos de voz, "
        "barrido automático si no hay voz | scan: barrido en celdas | "
        "voice: solo con voz | static: lente quieta",
    )
    vmag.add_argument(
        "--grid", default="2x2", metavar="COLSxROWS",
        help="celdas del barrido en orden de lectura (default 2x2; máx 6 celdas)",
    )
    vmag.add_argument(
        "--hold", type=float, default=video_magnify.DEFAULT_HOLD,
        help=f"pausa en cada celda del barrido en s (default "
        f"{video_magnify.DEFAULT_HOLD:g})",
    )
    vmag.add_argument(
        "--move-dur", type=float, default=video_magnify.DEFAULT_MOVE_DUR,
        help=f"duración de cada transición entre celdas en s (default "
        f"{video_magnify.DEFAULT_MOVE_DUR:g}, curva S)",
    )
    vmag.add_argument(
        "--min-gap", type=float, default=video_magnify.DEFAULT_MIN_GAP,
        help=f"separación mínima entre momentos de voz en s (default "
        f"{video_magnify.DEFAULT_MIN_GAP:g})",
    )
    vmag.add_argument(
        "--sharpen", type=float, default=video_magnify.DEFAULT_SHARPEN,
        help=f"unsharp leve tras el upscale (default "
        f"{video_magnify.DEFAULT_SHARPEN:g}; 0 = sin — la lente queda más suave)",
    )
    vmag.add_argument(
        "--start", type=float, default=None,
        help="inicio del segmento en segundos (default: principio)",
    )
    vmag.add_argument(
        "--end", type=float, default=None,
        help="fin del segmento en segundos (default: fin del vídeo)",
    )
    vmag.add_argument(
        "--crf", type=int, default=18,
        help="x264 CRF (default 18; más alto = fichero más pequeño)",
    )
    vmag.add_argument(
        "--audio-bitrate", default="192k", help="AAC bitrate (default 192k)",
    )
    vmag.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan y salir sin escribir nada",
    )

    vcuts = vsub.add_parser(
        "cutsilence",
        help="edición automática: elimina los silencios del vídeo (jump-cuts "
        "estilo TikTok), audio y vídeo a la vez con sync exacto",
        description="Detecta los silencios entre frases con el mismo VAD de "
        "'voxera silence' y los recorta del vídeo Y del audio en un solo paso "
        "de ffmpeg (select/aselect + setpts, cortes cuantizados a la rejilla "
        "de frames -> sync A/V frame-accurate). 100%% ffmpeg — sin Premiere, "
        "sin edición manual.",
    )
    vcuts.add_argument("input", help="vídeo de entrada")
    vcuts.add_argument("-o", "--output", required=True, help="salida .mp4")
    vcuts.add_argument(
        "--level", choices=tuple(video_silence.TRIGGERS), default="medium",
        help="agresividad: gaps > light 1.5s | medium 0.8s | aggressive 0.4s "
        "(default medium)",
    )
    vcuts.add_argument(
        "--keep", type=float, default=video_silence.DEFAULT_KEEP,
        help=f"segundos de silencio conservados en cada corte (default "
        f"{video_silence.DEFAULT_KEEP:g}; 0 = cortes a cero, sonido encadenado)",
    )
    vcuts.add_argument(
        "--crf", type=int, default=18,
        help="x264 CRF (default 18; más alto = fichero más pequeño)",
    )
    vcuts.add_argument(
        "--audio-bitrate", default="192k", help="AAC bitrate (default 192k)",
    )
    vcuts.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan y salir sin escribir nada",
    )

    vstab = vsub.add_parser(
        "stabilize",
        help="estabilización de vídeo: quita el temblor de mano (anti-shake, "
        "como el Warp Stabilizer en Smooth Motion)",
        description="Elimina el temblor de cámara de vídeos handheld: features "
        "Shi-Tomasi + Lucas-Kanade + RANSAC estiman el movimiento frame a frame, "
        "la trayectoria acumulada se suaviza con un gaussiano (--smoothing) y cada "
        "frame se corrige con un warp; el recorte se cubre con un zoom adaptativo "
        "mínimo (--crop keep) o dejando bordes negros (--crop black). 100%% "
        "OpenCV + ffmpeg, sin GPU, sin Premiere. Ya estable -> copia directa.",
    )
    vstab.add_argument("input", help="vídeo de entrada (handheld/tembloroso)")
    vstab.add_argument("-o", "--output", required=True, help="salida .mp4")
    vstab.add_argument(
        "--smoothing", type=float, default=video_stabilize.DEFAULT_SMOOTHING,
        help=f"sigma del gaussiano sobre la trayectoria en frames (default "
        f"{video_stabilize.DEFAULT_SMOOTHING:g} ≈ 0.5 s a 30 fps; más = más "
        f"pegado pero más lag en paneos; 0 = sin suavizado)",
    )
    vstab.add_argument(
        "--max-shift", type=float, default=None,
        help=f"máx. movimiento por frame en px (default: auto = 5%% de min(w,h) "
        f"— los paneos rápidos/cortes se congelan, no se estabilizan)",
    )
    vstab.add_argument(
        "--max-angle", type=float, default=video_stabilize.DEFAULT_MAX_ANGLE,
        help=f"máx. rotación por frame en grados (default "
        f"{video_stabilize.DEFAULT_MAX_ANGLE:g}; 0 = sin límite)",
    )
    vstab.add_argument(
        "--crop", choices=("keep", "black"), default="keep",
        help="keep (default): zoom adaptativo mínimo que cubre los bordes "
        "(capado a --max-zoom) | black: bordes negros a la vista (inspección)",
    )
    vstab.add_argument(
        "--max-zoom", type=float, default=video_stabilize.DEFAULT_MAX_ZOOM,
        help=f"capa del zoom adaptativo en veces (default "
        f"{video_stabilize.DEFAULT_MAX_ZOOM:g}; más = aguanta más temblor "
        f"recortando más)",
    )
    vstab.add_argument(
        "--crf", type=int, default=18,
        help="x264 CRF (default 18; más alto = fichero más pequeño)",
    )
    vstab.add_argument(
        "--audio-bitrate", default="192k", help="AAC bitrate (default 192k)",
    )
    vstab.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan (con la métrica de temblor) y salir sin escribir nada",
    )

    vslow = vsub.add_parser(
        "slowmo",
        help="slow motion (y fast motion): ralentiza o acelera vídeo con setpts + atempo",
        description=("Slow motion (factor < 1) o fast motion (factor > 1) sobre "
        "todo el clip o un segmento dado (--at S:E), en un solo paso de "
        "ffmpeg. setpts re-escala vídeo, atempo preserva el pitch del audio. "
        "Opcionalmente minterpolate para interpolar frames (MUY lento)."),
    )
    vslow.add_argument("input", help="vídeo de entrada")
    vslow.add_argument("-o", "--output", required=True, help="salida .mp4")
    vslow.add_argument(
        "--factor", type=float, default=video_slowmo.DEFAULT_FACTOR,
        help=f"multiplicador de velocidad (default {video_slowmo.DEFAULT_FACTOR} = "
        f"2x más lento; 0.25 = 4x más lento; 2.0 = 2x más rápido; "
        f"rango {video_slowmo.FACTOR_MIN}–{video_slowmo.FACTOR_MAX})",
    )
    vslow.add_argument(
        "--at", default=None, metavar="S:E",
        help="segmento a ralentizar en segundos (S:E, p.ej. 1:3); "
        "el resto del clip queda a 1x",
    )
    vslow.add_argument(
        "--interpolate", choices=video_slowmo.INTERPOLATE_OPTIONS,
        default=video_slowmo.DEFAULT_INTERPOLATE,
        help="none (default) | minterpolate (interpola frames, MUY lento)",
    )
    vslow.add_argument(
        "--fps", type=int, default=video_slowmo.DEFAULT_INTERPOLATE_FPS,
        help=f"fps de interpolación minterpolate (default {video_slowmo.DEFAULT_INTERPOLATE_FPS})",
    )
    vslow.add_argument(
        "--crf", type=int, default=18,
        help="x264 CRF (default 18; más alto = fichero más pequeño)",
    )
    vslow.add_argument(
        "--audio-bitrate", default="192k", help="AAC bitrate (default 192k)",
    )
    vslow.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan y salir sin escribir nada",
    )

    vcap = vsub.add_parser(
        "captions",
        help="subtítulos/karaoke con ASR word-level (faster-whisper)",
        description="Genera subtítulos en vídeo: transcripción word-level con "
        "faster-whisper,打包 en cues, ASS karaoke o estático, y burn-in con "
        "ffmpeg libass en un solo paso. Estilo karaoke con {\\k} por palabra "
        "o estático con fade.",
    )
    vcap.add_argument("input", help="vídeo de entrada")
    vcap.add_argument("-o", "--output", required=True, help="salida .mp4")
    vcap.add_argument(
        "--model", default=captions.DEFAULT_MODEL,
        help=f"modelo Whisper (default: {captions.DEFAULT_MODEL})",
    )
    vcap.add_argument(
        "--lang", default=None,
        help="idioma (default: auto); p. ej. 'es', 'en'",
    )
    vcap.add_argument(
        "--style", choices=captions.STYLES, default="karaoke",
        help="karaoke (default, \\k por palabra) | static (fade in/out)",
    )
    vcap.add_argument(
        "--text-style", choices=captions.TEXT_STYLES, default="classic",
        help="classic (default, tal cual) | playful (minúsculas, sin puntuación)",
    )
    vcap.add_argument(
        "--font-size", type=int, default=captions.DEFAULT_FONT_SIZE,
        help=f"tamaño de fuente (default {captions.DEFAULT_FONT_SIZE})",
    )
    vcap.add_argument(
        "--outline", type=int, default=captions.DEFAULT_OUTLINE,
        help=f"grosor del borde (default {captions.DEFAULT_OUTLINE})",
    )
    vcap.add_argument(
        "--max-lines", type=int, default=captions.DEFAULT_MAX_LINES,
        help=f"máximo de líneas por cue (default {captions.DEFAULT_MAX_LINES})",
    )
    vcap.add_argument(
        "--chars-per-sec", type=float, default=captions.DEFAULT_CHARS_PER_SEC,
        help=f"velocidad de lectura (default {captions.DEFAULT_CHARS_PER_SEC})",
    )
    vcap.add_argument(
        "--highlight", default="",
        help="palabras a resaltar en naranja (separadas por coma)",
    )
    vcap.add_argument(
        "--words-json", default=None, metavar="PATH",
        help="JSON con palabras pre-transcritas (formato {\"words\": [...]})",
    )
    vcap.add_argument(
        "--ass-only", default=None, metavar="PATH",
        help="escribe el ASS aquí y NO hace burn-in",
    )
    vcap.add_argument(
        "--crf", type=int, default=18,
        help="x264 CRF (default 18; más alto = fichero más pequeño)",
    )
    vcap.add_argument(
        "--audio-bitrate", default="192k", help="AAC bitrate (default 192k)",
    )
    vcap.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan y salir sin escribir nada",
    )

    # --- audio --------------------------------------------------------------
    audio_parser = subparsers.add_parser(
        "audio",
        help="efectos de audio (100%% numpy/scipy, sin Premiere)",
        description="Efectos de audio replicados de tutoriales: el 'Pase Bajo' "
        "de @serri.mp4 (low-pass 800 Hz con transición suave en los cortes).",
    )
    asub = audio_parser.add_subparsers(dest="audio_command", required=True, metavar="COMMAND")

    alow = asub.add_parser(
        "lowpass",
        help="efecto 'Pase Bajo': low-pass con transición suave (tutorial @serri.mp4)",
        description="Replicación del efecto 'Pase Bajo' de Adobe Premiere (tutorial "
        "de @serri.mp4): filtra las frecuencias agudas (cutoff 800 Hz por defecto) "
        "con una rampa suave en los cortes para que el cambio no sea brusco. "
        "Sin Premiere: numpy/scipy.",
    )
    alow.add_argument("input", help="audio de entrada (.wav, .mp3, .m4a, .flac…)")
    alow.add_argument("-o", "--output", required=True, help="salida .wav (48 kHz 24-bit)")
    alow.add_argument(
        "--cutoff", type=float, default=audio_lowpass.DEFAULT_CUTOFF,
        help=f"frecuencia de corte Hz (default {audio_lowpass.DEFAULT_CUTOFF:g} — "
        f"'ajustaremos el valor a 800 hercios' del tutorial)",
    )
    alow.add_argument(
        "--transition", type=float, default=audio_lowpass.DEFAULT_TRANSITION,
        help=f"duración de la rampa en cada borde en s (default "
        f"{audio_lowpass.DEFAULT_TRANSITION:g} — la 'transición predeterminada' "
        f"de Premiere; 0 = cambio brusco)",
    )
    alow.add_argument(
        "--curve", type=float, default=audio_lowpass.DEFAULT_CURVE,
        help=f"curva de easing 0-100 (default {audio_lowpass.DEFAULT_CURVE:g} — "
        f"el 60-65 del creador; 0 = lineal)",
    )
    alow.add_argument(
        "--easing", choices=audio_lowpass.LP_EASINGS, default="smooth",
        help="smooth (default, S-curva) | out (arranca rápido) | in (acelera) | linear",
    )
    alow.add_argument(
        "--order", type=int, choices=audio_lowpass.LP_ORDERS,
        default=audio_lowpass.DEFAULT_ORDER,
        help=f"orden del filtro (default {audio_lowpass.DEFAULT_ORDER} — ~12 dB/oct "
        f"medido en el tutorial): 1 = 6 dB/oct, 2 = 12 dB/oct, 4 = 24 dB/oct",
    )
    alow.add_argument(
        "--resonance", type=float, default=None,
        help="Q del LPF 0.5-2.0 (default: Butterworth Q=0.707 — sin pico, el "
        "comportamiento original); Q>0.707 => pico en el cutoff, carácter "
        "'de caja'/'orejas tapadas'. Solo con order 2 o 4.",
    )
    alow.add_argument(
        "--occlusion", type=float, default=audio_lowpass.DEFAULT_OCCLUSION,
        help=f"refuerzo de graves en dB 0-12 (default {audio_lowpass.DEFAULT_OCCLUSION:g} "
        f"= off): el 'efecto de oclusión' de taparse las orejas — la conducción "
        f"ósea refuerza ~100-500 Hz; un LPF solo corta agudos",
    )
    alow.add_argument(
        "--shelf", type=float, default=audio_lowpass.DEFAULT_SHELF,
        help=f"frecuencia central del shelf de oclusión en Hz (default "
        f"{audio_lowpass.DEFAULT_SHELF:g})",
    )
    alow.add_argument(
        "--start", type=float, default=None,
        help="inicio de la región filtrada en s (default: principio del clip)",
    )
    alow.add_argument(
        "--end", type=float, default=None,
        help="fin de la región filtrada en s (default: fin del clip); con --start "
        "y --end = el caso del tutorial: rampa de entrada, mantener, rampa de salida",
    )
    alow.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan y salir sin escribir nada",
    )

    atr = asub.add_parser(
        "transition",
        help="transición tonal entre emociones: acorde A → acorde B con "
        "voice-leading de movimiento mínimo",
        description="Cambio de emoción armónica: sintetiza un pad que va del "
        "acorde del mood origen al del mood destino con glide logarítmico "
        "voz a voz (movimiento mínimo, no un crossfade crudo) y lo mezcla "
        "sobre el audio existente. La tabla de moods (hope, tension, "
        "melancholy…) es 'tell the people how to feel': cada mood es una "
        "instrucción de cómo debe sentir el oyente la escena. 100 % "
        "numpy/scipy, sin Premiere.",
    )
    atr.add_argument("input", help="audio de entrada (.wav, .mp3, .m4a, .flac…)")
    atr.add_argument("-o", "--output", required=True, help="salida .wav (48 kHz 24-bit)")
    atr.add_argument(
        "--from", dest="from_mood", choices=audio_tonal.MOOD_NAMES,
        default=audio_tonal.TransitionOptions().from_mood,
        help=f"emoción de origen (default {audio_tonal.TransitionOptions().from_mood} — "
        f"de dónde parte la escena)",
    )
    atr.add_argument(
        "--to", dest="to_mood", choices=audio_tonal.MOOD_NAMES,
        default=audio_tonal.TransitionOptions().to_mood,
        help=f"emoción de destino (default {audio_tonal.TransitionOptions().to_mood} — "
        f"el sentir al que llega el corte)",
    )
    atr.add_argument(
        "--from-key", dest="from_key", choices=audio_tonal.NOTE_NAMES, default=None,
        help="tónica del acorde origen (sostenidos; default: la raíz del mood)",
    )
    atr.add_argument(
        "--to-key", dest="to_key", choices=audio_tonal.NOTE_NAMES, default=None,
        help="tónica del acorde destino (sostenidos; default: la raíz del mood)",
    )
    atr.add_argument(
        "--at", type=float, default=audio_tonal.TransitionOptions().at,
        help=f"inicio de la transición en s (default {audio_tonal.TransitionOptions().at:g} — "
        f"el instante en que la escena cambia de emoción)",
    )
    atr.add_argument(
        "--dur", type=float, default=audio_tonal.TransitionOptions().dur,
        help=f"duración de la transición en s (default {audio_tonal.TransitionOptions().dur:g}; "
        f"cuánto tarda el oyente en llegar al nuevo sentir)",
    )
    atr.add_argument(
        "--gain", type=float, default=audio_tonal.TransitionOptions().gain_db,
        help="ganancia del elemento en dB (negativa; default -18 — apoyo, no protagonista)",
    )
    atr.add_argument(
        "--curve", type=float, default=audio_tonal.DEFAULT_CURVE,
        help=f"curva de easing 0-100 del glide (default {audio_tonal.DEFAULT_CURVE:g} — "
        f"misma convención que lowpass/video zoom; 0 = lineal)",
    )
    atr.add_argument(
        "--easing", choices=audio_tonal.TONAL_EASINGS, default="smooth",
        help="smooth (default, S-curva) | out (arranca rápido) | in (acelera) | linear",
    )
    atr.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan (acordes, movimiento en semitonos) y salir sin escribir nada",
    )

    ari = asub.add_parser(
        "riser",
        help="riser tonal que termina exactamente en el corte/drop",
        description="Tensión ascendente que TERMINA en el hit (el corte o drop "
        "del vídeo): notas de la escala del mood que aceleran (o un glide de "
        "2 octavas) con crescendo (ease)² y una cola de release que resuelve "
        "después del impacto. Con --hit el riser acaba justo ahí; sin él, al "
        "final del archivo. 100 % numpy/scipy, sin Premiere.",
    )
    ari.add_argument("input", help="audio de entrada (.wav, .mp3, .m4a, .flac…)")
    ari.add_argument("-o", "--output", required=True, help="salida .wav (48 kHz 24-bit)")
    ari.add_argument(
        "--mood", choices=audio_tonal.MOOD_NAMES,
        default=audio_tonal.RiserOptions().mood,
        help=f"emoción del riser (default {audio_tonal.RiserOptions().mood} — "
        f"la tensión que empuja hacia el corte)",
    )
    ari.add_argument(
        "--key", choices=audio_tonal.NOTE_NAMES, default=None,
        help="tónica (sostenidos; default: la raíz del mood)",
    )
    ari.add_argument(
        "--hit", type=float, default=None,
        help="instante del corte/drop en s — el riser TERMINA aquí "
        "(default: fin del archivo)",
    )
    ari.add_argument(
        "--dur", type=float, default=audio_tonal.RiserOptions().dur,
        help=f"duración de la subida en s (default {audio_tonal.RiserOptions().dur:g}; "
        f"la rampa de expectativa antes del hit)",
    )
    ari.add_argument(
        "--style", choices=("notes", "glide"), default=audio_tonal.RiserOptions().style,
        help="notes (default, grados que aceleran) | glide (barrido de 2 octavas "
        "con vibrato creciente)",
    )
    ari.add_argument(
        "--gain", type=float, default=audio_tonal.RiserOptions().gain_db,
        help=f"ganancia del elemento en dB (negativa; default "
        f"{audio_tonal.RiserOptions().gain_db:g} — apoyo, no protagonista)",
    )
    ari.add_argument(
        "--tail", type=float, default=audio_tonal.RiserOptions().tail,
        help="release en s que resuelve después del hit",
    )
    ari.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan (subida, hit, tail) y salir sin escribir nada",
    )

    ame = asub.add_parser(
        "melody",
        help="melodía generada en tonalidad bajo la voz (determinista por seed)",
        description="Melodía generada en la escala del mood, pregunta + "
        "respuesta (la primera frase queda en el aire, la segunda resuelve "
        "en la tónica), rejilla en corcheas y contorno melódico del mood. "
        "Determinista: mismo seed → misma melodía. Con --duck baja el audio "
        "existente bajo la melodía. 100 % numpy/scipy, sin Premiere.",
    )
    ame.add_argument("input", help="audio de entrada (.wav, .mp3, .m4a, .flac…)")
    ame.add_argument("-o", "--output", required=True, help="salida .wav (48 kHz 24-bit)")
    ame.add_argument(
        "--mood", choices=audio_tonal.MOOD_NAMES,
        default=audio_tonal.MelodyOptions().mood,
        help=f"emoción de la melodía (default {audio_tonal.MelodyOptions().mood} — "
        f"el color que acompaña a la voz)",
    )
    ame.add_argument(
        "--key", choices=audio_tonal.NOTE_NAMES, default=None,
        help="tónica (sostenidos; default: la raíz del mood)",
    )
    ame.add_argument(
        "--start", type=float, default=audio_tonal.MelodyOptions().start,
        help=f"inicio de la melodía en s (default {audio_tonal.MelodyOptions().start:g})",
    )
    ame.add_argument(
        "--bars", type=int, default=audio_tonal.MelodyOptions().bars,
        help=f"número de compases (default {audio_tonal.MelodyOptions().bars} — "
        f"2 frases: pregunta + respuesta)",
    )
    ame.add_argument(
        "--bpm", type=float, default=None,
        help="tempo (default: el bpm del mood; 30-300)",
    )
    ame.add_argument(
        "--seed", type=int, default=audio_tonal.MelodyOptions().seed,
        help=f"semilla del generador (default {audio_tonal.MelodyOptions().seed} — "
        f"misma seed, misma melodía)",
    )
    ame.add_argument(
        "--gain", type=float, default=audio_tonal.MelodyOptions().gain_db,
        help=f"ganancia del elemento en dB (negativa; default "
        f"{audio_tonal.MelodyOptions().gain_db:g} — bajo la voz, nunca encima)",
    )
    ame.add_argument(
        "--duck", type=float, default=audio_tonal.MelodyOptions().duck_db,
        help="ducking del audio existente bajo la melodía en dB (default 0 = off; "
        "4-8 recomendado bajo voz)",
    )
    ame.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el plan (notas, rango MIDI, duck) y salir sin escribir nada",
    )

    # --- autopilot --------------------------------------------------------
    ap_parser = subparsers.add_parser(
        "autopilot",
        help="raw→short: plan de edición + ejecución + A/B harness",
        description="Orquesta el pipeline completo de edición: un planner "
        "(rule determinista o LLM) genera un edit-spec JSON, el executor "
        "compone las APIs de voxera, y el harness A/B produce ambas "
        "variantes con checklist de publicación.",
    )
    ap_sub = ap_parser.add_subparsers(
        dest="autopilot_command", required=True, metavar="COMMAND",
    )

    # autopilot run
    apr = ap_sub.add_parser(
        "run",
        help="ejecutar autopilot: planificar + ejecutar → short optimizado",
        description="Genera un edit-spec (rule o llm), ejecuta el pipeline "
        "cutsilence→zoom→effects→captions, y escribe el manifest QA.",
    )
    apr.add_argument("input", help="vídeo de entrada (raw MP4)")
    apr.add_argument(
        "-o", "--output", required=True, help="salida .mp4"
    )
    apr.add_argument(
        "--planner", choices=("rule", "llm"), default="rule",
        help="planificador: rule (determinista, default) o llm",
    )
    apr.add_argument(
        "--words-json", default=None, metavar="PATH",
        help='JSON con palabras pre-transcritas (formato {"words": [...]})',
    )
    apr.add_argument(
        "--llm-cmd", default=None, metavar="CMD",
        help=f"comando LLM para planner=llm (default: {_DEFAULT_LLM_CMD})",
    )
    apr.add_argument(
        "--max-dur", type=float, default=45.0,
        help="duración máxima del short en segundos (default 45)",
    )
    apr.add_argument(
        "--level", choices=("light", "medium", "aggressive"),
        default="medium",
        help="agresividad de cutsilence (default medium)",
    )
    apr.add_argument(
        "--aspect", choices=("9:16", "keep"), default="9:16",
        help="aspecto de salida (default 9:16)",
    )
    apr.add_argument(
        "--crf", type=int, default=18,
        help="x264 CRF (default 18)",
    )
    apr.add_argument(
        "--model", default="base",
        help="modelo Whisper para transcripción (default base)",
    )
    apr.add_argument(
        "--dry-run", action="store_true",
        help="imprimir el manifest sin ejecutar nada",
    )

    # autopilot ab
    apab = ap_sub.add_parser(
        "ab",
        help="A/B harness: ejecuta rule + llm y genera checklist",
        description="Ejecuta ambas variantes (rule y llm) sobre el mismo "
        "input, genera {prefix}.ab_manifest.json con checklist de "
        "publicación y comparación.",
    )
    apab.add_argument("input", help="vídeo de entrada (raw MP4)")
    apab.add_argument(
        "-o", "--prefix", required=True,
        help="prefijo de salida (genera {prefix}.rule.mp4 y {prefix}.llm.mp4)",
    )
    apab.add_argument(
        "--planner-a", choices=("rule", "llm"), default="rule",
        help="primer planificador (default rule)",
    )
    apab.add_argument(
        "--planner-b", choices=("rule", "llm"), default="llm",
        help="segundo planificador (default llm)",
    )
    apab.add_argument(
        "--llm-cmd", default=None, metavar="CMD",
        help=f"comando LLM para planners que lo necesiten (default: {_DEFAULT_LLM_CMD})",
    )
    apab.add_argument(
        "--max-dur", type=float, default=45.0,
        help="duración máxima del short en segundos (default 45)",
    )
    apab.add_argument(
        "--level", choices=("light", "medium", "aggressive"),
        default="medium",
        help="agresividad de cutsilence (default medium)",
    )
    apab.add_argument(
        "--aspect", choices=("9:16", "keep"), default="9:16",
        help="aspecto de salida (default 9:16)",
    )
    apab.add_argument(
        "--crf", type=int, default=18,
        help="x264 CRF (default 18)",
    )
    apab.add_argument(
        "--model", default="base",
        help="modelo Whisper para transcripción (default base)",
    )
    apab.add_argument(
        "--words-json", default=None, metavar="PATH",
        help='JSON con palabras pre-transcritas (formato {"words": [...]})',
    )

    return parser


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _fmt(value, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _analyze_tty(report: dict) -> str:
    inp = report["input"]
    ch = {1: "mono", 2: "stereo"}.get(inp["channels"], f"{inp['channels']}ch")
    loud = report["loudness"]
    voice = report["voice"]
    spec = report["spectral"]
    hum = spec["hum_db"]
    room = report["room"]
    art = report["artifacts"]
    nt = art["noise_type"]
    hum_str = f" {hum['dominant']} ({_fmt(hum['h50'] if hum.get('h50') is not None else hum.get('h100'))})" if hum.get("dominant") else ""
    snr = voice["snr_db"]
    snr_str = f"SNR {_fmt(snr['value'])} dB (conf {snr['confidence']:.2f})" if snr["value"] is not None else "SNR n/a"
    rt = f"RT60 {_fmt(room['rt60_s'], 2)} s (conf {room['confidence']:.2f}) · {room['reverb']}" if room["rt60_s"] is not None else "RT60 n/a"
    return "\n".join(
        [
            "",
            f"Input:      {inp['format']} · {inp['sample_rate']} Hz · {ch} · {inp['duration_s']:.2f} s",
            f"Loudness:   LUFS-I {_fmt(loud['integrated_lufs'])} · LUFS-S {_fmt(loud['short_term_lufs'])}"
            f" · LRA {_fmt(loud['lra'])} · TP {_fmt(loud['true_peak_db'])} dBTP · RMS {_fmt(loud['rms_db'])} dB",
            f"Voice:      speech {report['voice']['speech_ratio'] * 100:.0f}% · {snr_str}",
            f"Spectral:   rumble {_fmt(spec['rumble_db'])} · hum{hum_str} · mud {_fmt(spec['mud_db'])}"
            f" · boxiness {_fmt(spec['boxiness_db'])} · presence {_fmt(spec['presence_db'])} · air {_fmt(spec['air_db'])}",
            f"Room:       {rt}",
            f"Artifacts:  DC {_fmt(art['dc_offset_db'])} dBFS · plosives {art['plosives']['candidates']}"
            f" ({art['plosives']['confidence']:.2f}) · breaths {art['breaths']['count']}"
            f" · clicks {art['mouth_click_candidates']['count']} ({art['mouth_click_candidates']['confidence']:.2f})",
            f"Noise type: {nt['type']} (conf {nt['confidence']:.2f})"
            + (" · stationary" if nt["stationary"] else "")
            + (" · tonal" if nt["tonal"] else "")
            + (" · broadband" if nt["broadband"] else ""),
        ]
    )


def _print_verbose(result: dict) -> None:
    device = result.get("device", "cpu")
    print(f"Backend:  {result.get('backend') or '—'}")
    print(f"Model:    {result.get('model') or '—'}")
    print(f"Device:   {device}")
    try:
        import torch

        print(f"Torch:    {'CUDA ' + torch.version.cuda if torch.cuda.is_available() else 'CPU'}")
    except Exception:  # noqa: BLE001
        print("Torch:    n/a")
    for key in ("rtf_model", "rtf_pipeline", "rtf_e2e", "rtf_master"):
        if result.get(key) is not None:
            print(f"RTF:      {result[key]:.3f} ({key.removeprefix('rtf_')})", file=sys.stderr)


def _print_stages(result: dict) -> None:
    for stage in result.get("stages", []):
        print(f"  ✓ {stage}")


def _score_tty(report: dict, ref: str | None) -> str:
    score = report["score"]
    dims = score["dimensions"]
    lines = [
        "",
        f"Voice Score: {score['cvs']:.0f}/100 — \"{score['verdict']}\"",
    ]
    for key, label in (
        ("noise", "Noise"),
        ("clarity", "Clarity"),
        ("loudness", "Loudness"),
        ("room", "Room"),
        ("dynamics", "Dynamics"),
    ):
        d = dims[key]
        lines.append(f"  {label:<10} {d['value']:>5.0f}/100  ({d['detail']})")
    if "voice_preservation_pct" in report:
        lines.append(f"Voice preservation: {report['voice_preservation_pct']:.1f}% (vs {ref})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _video_output_check(out: Path) -> None:
    if out.suffix.lower() not in video_mod.VIDEO_EXTENSIONS:
        raise EnhancementError(
            f"video input requires a video output path (e.g. .mp4), got: {out}"
        )


def _enhance_video(args) -> int:
    """Video path: extract audio -> pipeline -> mux (video bit-identical)."""
    out = Path(args.output)
    tmp_in = video_mod.temp_wav()
    tmp_out = video_mod.temp_wav()
    try:
        _video_output_check(out)
        video_mod.extract_audio(args.input, tmp_in)
        result = enhance(
            tmp_in,
            tmp_out,
            backend=args.backend,
            model=args.model,
            attn_limit_db=args.attn_limit_db,
            pf=args.pf,
            preset=args.preset,
            dsp_only=args.dsp_only,
            device=args.device,
            seed=args.seed,
        )
        if isinstance(result, dict) and result.get("plan"):
            print(result["plan"])
            return 0
        video_mod.mux(args.input, tmp_out, out, bitrate=args.audio_bitrate)
        drift = video_mod.check_drift(args.input, out)
    finally:
        tmp_in.unlink(missing_ok=True)
        tmp_out.unlink(missing_ok=True)
    print(f"✓ {out} · drift {drift * 1000:.0f} ms · AAC {args.audio_bitrate}")
    return 0


def _master_video(args) -> int:
    out = Path(args.output)
    tmp_in = video_mod.temp_wav()
    tmp_out = video_mod.temp_wav()
    try:
        _video_output_check(out)
        video_mod.extract_audio(args.input, tmp_in)
        result = master_file(
            tmp_in,
            tmp_out,
            preset_name=args.preset,
            lufs=args.lufs,
            dehum_hz=None,
            no_eq=args.no_eq,
            no_comp=args.no_comp,
            no_limit=args.no_limit,
            no_loudnorm=args.no_loudnorm,
            device=args.device,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            print(result["plan"])
            return 0
        video_mod.mux(args.input, tmp_out, out, bitrate=args.audio_bitrate)
        drift = video_mod.check_drift(args.input, out)
    finally:
        tmp_in.unlink(missing_ok=True)
        tmp_out.unlink(missing_ok=True)
    print(f"✓ {out} · drift {drift * 1000:.0f} ms · AAC {args.audio_bitrate}")
    return 0


def _cmd_enhance(args) -> int:
    if video_mod.is_video_path(args.input):
        if args.preset is None and not args.dsp_only:
            print(
                f"{PROG}: error: video input requires --preset or --dsp-only "
                "(the master pipeline is mandatory for video)",
                file=sys.stderr,
            )
            return 2
        try:
            return _enhance_video(args)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
    try:
        result = enhance(
            Path(args.input),
            Path(args.output),
            backend=args.backend,
            model=args.model,
            attn_limit_db=args.attn_limit_db,
            pf=args.pf,
            preset=args.preset,
            dsp_only=args.dsp_only,
            dry_run=args.dry_run,
            device=args.device,
            seed=args.seed,
        )
    except UnknownBackendError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 2
    except NoSpeechError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return NO_SPEECH_EXIT_CODE
    except EnhancementError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1

    if isinstance(result, dict):
        if args.dry_run:
            print(result["plan"])
        else:
            if args.verbose:
                _print_verbose(result)
            print(f"✓ {result['output']}")
            if args.verbose:
                _print_stages(result)
            else:
                print(f"  stages: {', '.join(result['stages'])}")
    else:
        print(result)
    return 0


def _cmd_master(args) -> int:
    if video_mod.is_video_path(args.input):
        try:
            return _master_video(args)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
    dehum_hz = None
    if args.dehum and not args.dry_run:
        try:
            hum = analyze(args.input, device=args.device)["spectral"]["hum_db"]
        except EnhancementError:
            hum = {}
        dominant = hum.get("dominant")
        dehum_hz = {"50 Hz": 50, "100 Hz": 100, "150 Hz": 150}.get(dominant or "", None)
        if dehum_hz is None and not args.verbose:
            print("note: no dominant hum detected; --dehum no-op", file=sys.stderr)
    try:
        result = master_file(
            Path(args.input),
            Path(args.output),
            preset_name=args.preset,
            lufs=args.lufs,
            dehum_hz=dehum_hz,
            no_eq=args.no_eq,
            no_comp=args.no_comp,
            no_limit=args.no_limit,
            no_loudnorm=args.no_loudnorm,
            device=args.device,
            dry_run=args.dry_run,
        )
    except NoSpeechError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return NO_SPEECH_EXIT_CODE
    except EnhancementError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(result["plan"])
    else:
        if args.verbose:
            _print_verbose(result)
            _print_stages(result)
        else:
            print(f"✓ {result['output']} · LUFS {_fmt(result['lufs_out'])}"
                  f" · TP {_fmt(result['true_peak_out'])} dBTP"
                  f" · {result['duration_s']:.2f} s")
    return 0


def _cmd_analyze(args) -> int:
    try:
        report = analyze(args.input, device=args.device)
    except EnhancementError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1
    text = dump_report(report)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    if args.format == "json" or args.output:
        print(text, end="")
    else:
        print(_analyze_tty(report))
    if args.verbose:
        sys_block = report["system"]
        print(
            f"system: voxera {sys_block['voxera_version']} · pipeline "
            f"{sys_block['pipeline_version']} · {sys_block['device']} · "
            f"{sys_block['processing_time_s']:.3f} s",
            file=sys.stderr,
        )
    return 0


def _cmd_score(args) -> int:
    try:
        report = score_file(args.input, ref_path=args.ref, device=args.device)
    except EnhancementError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1
    text = dump_report(report)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    if args.format == "json" or args.output:
        print(text, end="")
    else:
        print(_score_tty(report, args.ref))
    return 0


def _cmd_silence(args) -> int:
    try:
        result = silence_file(
            Path(args.input),
            Path(args.output),
            level=args.level,
            breaths=args.breaths,
            declick=args.declick,
            device=args.device,
        )
    except NoSpeechError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return NO_SPEECH_EXIT_CODE
    except EnhancementError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1
    if args.verbose:
        _print_verbose(result)
    print(
        f"✓ {result['output']} · original {result['duration_in_s'] / 60:.0f}:{result['duration_in_s'] % 60:04.1f}"
        f" → cleaned {result['duration_out_s'] / 60:.0f}:{result['duration_out_s'] % 60:04.1f}"
        f" · speech {result['speech_ratio_in'] * 100:.0f}% → {result['speech_ratio_out'] * 100:.0f}%"
    )
    return 0


def _cmd_restore(args) -> int:
    try:
        result = restore_file(
            Path(args.input),
            Path(args.output),
            do_declip=args.declip,
            do_deplosive=args.deplosive,
            dehum_hz=args.dehum,
            preset=args.preset,
            lufs=args.lufs,
            device=args.device,
        )
    except NoSpeechError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return NO_SPEECH_EXIT_CODE
    except EnhancementError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1
    if args.verbose:
        _print_verbose(result)
    print(
        f"✓ {result['output']} · stages: {', '.join(result['stages'])}"
        f" · clipping {result['clipping_ratio_in'] * 100:.2f}% → {result['clipping_ratio_out'] * 100:.2f}%"
    )
    return 0


def _cmd_inspect(args) -> int:
    try:
        report = analyze(args.input, device=args.device)
    except EnhancementError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1
    print(_analyze_tty(report))
    print("\nRecommendation:")
    art = report["artifacts"]
    spec = report["spectral"]
    room = report["room"]
    voice = report["voice"]
    snr = voice["snr_db"]["value"]
    if art["mouth_click_candidates"]["count"] >= 5:
        print("  · mouth clicks detected → voxera silence --declick")
    if art["breaths"]["count"] >= 3:
        print("  · breaths detected (preserved by default) → voxera silence --breaths attenuate")
    if art["plosives"]["candidates"] >= 2:
        print("  · plosives detected → voxera restore --deplosive")
    if report["loudness"]["clipping_ratio"] > 0.001:
        print("  · clipping detected → voxera restore --declip")
    hum = spec["hum_db"]
    hum_key = {"50 Hz": "h50", "100 Hz": "h100", "150 Hz": "h150"}.get(hum.get("dominant") or "")
    if hum_key and (hum.get(hum_key) or -99) > -45:
        print(f"  · mains hum {hum['dominant']} → voxera master --dehum / restore --dehum")
    if room["reverb"] in ("medium", "high"):
        print("  · reverb present → restoration track (dereverb) postergado")
    if snr is not None and snr < 15:
        print("  · noisy input → voxera enhance --preset creator")
    if snr is not None and snr >= 15:
        print("  · decent signal → voxera master --preset youtube")
    nt = art["noise_type"]
    if nt["stationary"] and nt["type"] in ("fan", "ac", "hiss", "hum"):
        print("  · ruido estacionario (" + nt["type"] + ") → voxera enhance --preset bad-room (o DF2 solo)")
    return 0


def _cmd_video(args) -> int:
    if args.video_command == "info":
        try:
            info = video_enhance.probe_video(args.input)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    if args.video_command == "enhance":
        opts = video_enhance.VideoOptions(
            model=args.model,
            fps=args.fps,
            width=args.width,
            height=args.height,
            tile=args.tile,
            half=not args.no_half,
            crf=args.crf,
            audio_bitrate=args.audio_bitrate,
            master_audio=args.master_audio is not None,
            master_preset=args.master_audio or DEFAULT_PRESET,
            keep_frames=args.keep_frames,
        )
        try:
            if args.dry_run:
                print(video_enhance.build_plan(args.input, opts))
                return 0
            out = video_enhance.enhance_video(args.input, args.output, opts)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    if args.video_command == "teleport":
        opts = video_teleport.TeleportOptions(
            time=args.time,
            pattern=args.pattern,
            shift=args.shift,
            vanish=args.vanish,
            dilate=args.dilate,
            plate_samples=args.plate_samples,
            crf=args.crf,
            audio_bitrate=args.audio_bitrate,
        )
        try:
            if args.dry_run:
                print(video_teleport.build_plan(args.input, opts))
                return 0
            out = video_teleport.teleport_video(args.input, args.output, opts)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0
        try:
            out = video_enhance.compare_videos(
                args.a, args.b, args.output,
                source=args.source,
                seg=tuple(args.seg) if args.seg else None,
                fps=args.fps,
            )
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    if args.video_command == "zoom":
        ax, ay = (float(v) for v in args.anchor.split(","))
        opts = video_zoom.ZoomOptions(
            pct=args.pct,
            anchor=(ax, ay),
            curve=args.curve,
            easing=args.easing,
            direction=args.direction,
            hold=args.hold,
            auto_emphasis=args.auto_emphasis,
            pulse_dur=args.pulse_dur,
            max_pulses=args.max_pulses,
            start=args.start,
            end=args.end,
            crf=args.crf,
            audio_bitrate=args.audio_bitrate,
        )
        try:
            if args.dry_run:
                print(video_zoom.build_plan(args.input, opts))
                return 0
            out = video_zoom.zoom_video(args.input, args.output, opts)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    if args.video_command == "magnify":
        cx_, cy_ = (float(v) for v in args.center.split(","))
        cols, rows = (int(v) for v in args.grid.lower().split("x"))
        opts = video_magnify.MagnifyOptions(
            center=(cx_, cy_),
            size=args.size,
            zoom=args.zoom,
            feather=args.feather,
            ring_width=args.ring_width,
            motion=args.motion,
            grid=(cols, rows),
            hold=args.hold,
            move_dur=args.move_dur,
            min_gap=args.min_gap,
            sharpen=args.sharpen,
            start=args.start,
            end=args.end,
            crf=args.crf,
            audio_bitrate=args.audio_bitrate,
        )
        try:
            if args.dry_run:
                print(video_magnify.build_plan(args.input, opts))
                return 0
            out = video_magnify.magnify_video(args.input, args.output, opts)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    if args.video_command == "cutsilence":
        opts = video_silence.CutSilenceOptions(
            level=args.level,
            keep=args.keep,
            crf=args.crf,
            audio_bitrate=args.audio_bitrate,
        )
        try:
            if args.dry_run:
                print(video_silence.build_plan(args.input, opts))
                return 0
            out = video_silence.cutsilence_video(args.input, args.output, opts)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    if args.video_command == "stabilize":
        opts = video_stabilize.StabilizeOptions(
            smoothing=args.smoothing,
            max_shift=args.max_shift,
            max_angle=args.max_angle,
            crop=args.crop,
            max_zoom=args.max_zoom,
            crf=args.crf,
            audio_bitrate=args.audio_bitrate,
        )
        try:
            if args.dry_run:
                print(video_stabilize.build_plan(args.input, opts))
                return 0
            out = video_stabilize.stabilize_video(args.input, args.output, opts)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    if args.video_command == "slowmo":
        # Parse --at S:E
        seg_start, seg_end = None, None
        if args.at:
            try:
                seg_start, seg_end = (float(v) for v in args.at.split(":"))
            except (ValueError, TypeError):
                print(
                    f"{PROG}: error: --at debe tener formato S:E (p.ej. 1:3), "
                    f"got {args.at!r}",
                    file=sys.stderr,
                )
                return 2
        try:
            if args.dry_run:
                print(video_slowmo.build_plan(
                    args.input,
                    factor=args.factor,
                    start=seg_start,
                    end=seg_end,
                    interpolate=args.interpolate,
                    fps=args.fps,
                    crf=args.crf,
                    audio_bitrate=args.audio_bitrate,
                ))
                return 0
            out = video_slowmo.slowmo_video(
                args.input, args.output,
                factor=args.factor,
                start=seg_start,
                end=seg_end,
                interpolate=args.interpolate,
                fps=args.fps,
                crf=args.crf,
                audio_bitrate=args.audio_bitrate,
            )
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    if args.video_command == "captions":
        hl = tuple(h.strip() for h in args.highlight.split(',') if h.strip()) if args.highlight else ()
        try:
            if args.dry_run:
                print(captions.build_plan(
                    args.input,
                    model=args.model,
                    lang=args.lang,
                    style=args.style,
                    text_style=args.text_style,
                    font_size=args.font_size,
                    outline=args.outline,
                    max_lines=args.max_lines,
                    chars_per_sec=args.chars_per_sec,
                    highlight=hl,
                    words_json=args.words_json,
                    ass_only=args.ass_only,
                    crf=args.crf,
                    audio_bitrate=args.audio_bitrate,
                ))
                return 0
            out = captions.captions_video(
                args.input, args.output,
                words_json=args.words_json,
                model=args.model,
                lang=args.lang,
                style=args.style,
                text_style=args.text_style,
                font_size=args.font_size,
                outline=args.outline,
                max_lines=args.max_lines,
                chars_per_sec=args.chars_per_sec,
                highlight=hl,
                ass_only=args.ass_only,
                crf=args.crf,
                audio_bitrate=args.audio_bitrate,
            )
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    return 2


def _cmd_audio(args) -> int:
    if args.audio_command == "lowpass":
        opts = audio_lowpass.LowPassOptions(
            cutoff=args.cutoff,
            transition=args.transition,
            curve=args.curve,
            easing=args.easing,
            order=args.order,
            resonance=args.resonance,
            occlusion=args.occlusion,
            shelf=args.shelf,
            start=args.start,
            end=args.end,
        )
        try:
            if args.dry_run:
                print(audio_lowpass.build_plan(args.input, opts))
                return 0
            out = audio_lowpass.lowpass_file(args.input, args.output, opts)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    if args.audio_command == "transition":
        opts = audio_tonal.TransitionOptions(
            from_mood=args.from_mood,
            to_mood=args.to_mood,
            from_key=args.from_key,
            to_key=args.to_key,
            at=args.at,
            dur=args.dur,
            gain_db=args.gain,
            curve=args.curve,
            easing=args.easing,
        )
        try:
            if args.dry_run:
                print(audio_tonal.build_transition_plan(args.input, opts))
                return 0
            out = audio_tonal.transition_file(args.input, args.output, opts)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    if args.audio_command == "riser":
        opts = audio_tonal.RiserOptions(
            mood=args.mood,
            key=args.key,
            hit=args.hit,
            dur=args.dur,
            style=args.style,
            gain_db=args.gain,
            tail=args.tail,
        )
        try:
            if args.dry_run:
                print(audio_tonal.build_riser_plan(args.input, opts))
                return 0
            out = audio_tonal.riser_file(args.input, args.output, opts)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    if args.audio_command == "melody":
        opts = audio_tonal.MelodyOptions(
            mood=args.mood,
            key=args.key,
            start=args.start,
            bars=args.bars,
            bpm=args.bpm,
            seed=args.seed,
            gain_db=args.gain,
            duck_db=args.duck,
        )
        try:
            if args.dry_run:
                print(audio_tonal.build_melody_plan(args.input, opts))
                return 0
            out = audio_tonal.melody_file(args.input, args.output, opts)
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(f"✓ {out}")
        return 0

    return 2


def _cmd_autopilot(args) -> int:
    if args.autopilot_command == "run":
        try:
            manifest = autopilot_mod.run_autopilot(
                args.input, args.output,
                planner=args.planner,
                words_json=args.words_json,
                llm_cmd=args.llm_cmd,
                max_dur=args.max_dur,
                level=args.level,
                aspect=args.aspect,
                crf=args.crf,
                model=args.model,
                dry_run=args.dry_run,
            )
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(json.dumps(manifest, indent=2, ensure_ascii=False))
        else:
            qa = manifest.get("qa", {})
            dur_out = qa.get("dur_out", 0)
            print(f"✓ {args.output} · {dur_out:.2f}s")
        return 0

    if args.autopilot_command == "ab":
        try:
            ab_manifest = autopilot_mod.run_ab(
                args.input, args.prefix,
                planner_a=args.planner_a,
                planner_b=args.planner_b,
                llm_cmd=args.llm_cmd,
                max_dur=args.max_dur,
                level=args.level,
                aspect=args.aspect,
                crf=args.crf,
                model=args.model,
                words_json=args.words_json,
            )
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        for label in ("rule", "llm"):
            v = ab_manifest.get("variants", {}).get(label, {})
            if v.get("error"):
                print(f"  ✗ {label}: {v['error']}")
            elif v.get("output"):
                qa = v.get("qa", {})
                print(f"  ✓ {v['output']} · {qa.get('dur_out', 0):.2f}s")
        print(f"  manifest: {args.prefix}.ab_manifest.json")
        return 0

    return 2


def main(argv: list[str] | None = None) -> int:
    # Windows console/pipes default to cp1252 and crash on '✓' etc.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - exotic streams
            pass
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "enhance":
        return _cmd_enhance(args)
    if args.command == "master":
        return _cmd_master(args)
    if args.command == "analyze":
        return _cmd_analyze(args)
    if args.command == "score":
        return _cmd_score(args)
    if args.command == "silence":
        return _cmd_silence(args)
    if args.command == "restore":
        return _cmd_restore(args)
    if args.command == "inspect":
        return _cmd_inspect(args)
    if args.command == "video":
        return _cmd_video(args)
    if args.command == "audio":
        return _cmd_audio(args)
    if args.command == "autopilot":
        return _cmd_autopilot(args)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
