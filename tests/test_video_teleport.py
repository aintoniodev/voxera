"""Unit tests de video teleport (teletransportación): numpy/scipy, sin GPU, sin Premiere.

- Patrón de parpadeo y plan de fases por frame (2-2-2 del tutorial).
- Máscara de sujeto por diff contra fondo + morfología (sintético exacto).
- Silueta blanca opaca (composite) y desaparición (inpaint) — bit-exactos.
- Validación de opciones y plan --dry-run.
- Dos e2e sintéticos (cámara fija + blob móvil = "sujeto"): modo parpadeo y
  modo --remove, verificando frames por fase en la salida decodificada.
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from voxera import video_teleport as vt
from voxera.errors import EnhancementError

FFMPEG = shutil.which("ffmpeg") or (
    Path("C:/ffmpeg/bin/ffmpeg.exe").exists() and "C:/ffmpeg/bin/ffmpeg.exe"
)
pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg required")

W, H, FPS, DUR = 180, 320, 30, 3.0
BG_VAL, PERSON_VAL = 100, 230


def make_source(tmp_path, name="in.mp4", remove_video=False):
    """Sintético: fondo gris constante + cuadrado blanco móvil ("sujeto").

    El cuadrado baja 2px/frame desde y=40 (mismo patrón de encoder que el
    módulo: libx264 crf 18 yuv420p, así las zonas intactas son comparables).
    """
    total = int(round(DUR * FPS))
    rng = np.random.default_rng(0)
    bg = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
    frames = []
    for i in range(total):
        fr = bg.copy()
        y = 40 + 2 * i
        fr[y : y + 60, 60:120] = PERSON_VAL
        frames.append(fr)
    raw = b"".join(f.tobytes() for f in frames)
    out = tmp_path / name
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest",
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "96k", str(out)],
        input=raw, check=True, capture_output=True,
    )
    return out, total


def decode_frames(video, t0=None, t1=None):
    """Decodifica rgb24 (mismo camino que el módulo). Devuelve lista np.ndarray."""
    cmd = [FFMPEG, "-v", "error", "-i", str(video), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    if t0 is not None:
        cmd[3:3] = ["-ss", f"{t0:.6f}", "-t", f"{t1 - t0:.6f}"]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    n = len(proc.stdout) // (W * H * 3)
    return [np.frombuffer(proc.stdout, dtype=np.uint8).reshape(n, H, W, 3)[i]
            for i in range(n)]


# ---------------------------------------------------------------- pure units

class TestParsePattern:
    def test_default_tutorial(self):
        assert vt.parse_pattern("2-2-2") == (2, 2, 2)

    def test_other(self):
        assert vt.parse_pattern(" 4 - 1 - 3 ") == (4, 1, 3)

    def test_bad_shape(self):
        with pytest.raises(ValueError):
            vt.parse_pattern("2-2")
        with pytest.raises(ValueError):
            vt.parse_pattern("2-x-2")

    def test_bad_range(self):
        with pytest.raises(ValueError):
            vt.parse_pattern("0-2-2")
        with pytest.raises(ValueError):
            vt.parse_pattern("2-2-999")


class TestSchedule:
    def test_tutorial_phases(self):
        sched = vt.flicker_schedule(f0=10, total=40, pattern="2-2-2", hold_frames=0, remove=False)
        assert [sched.get(i, "normal") for i in range(10)] == ["normal"] * 10
        assert sched[10] == sched[11] == "white"
        assert sched[12] == sched[13] == "gap"
        assert sched[14] == sched[15] == "white"
        assert [sched.get(i, "normal") for i in range(16, 40)] == ["normal"] * 24

    def test_remove_adds_hold_and_gone(self):
        sched = vt.flicker_schedule(f0=10, total=60, hold_frames=4, remove=True)
        assert sched[16] == sched[17] == sched[18] == sched[19] == "hold"
        assert sched[20] == "gone"

    def test_truncated_near_end(self):
        # f0=55 en un vídeo de 60 frames: hold 61..66 se recorta a 60; nunca gone
        sched = vt.flicker_schedule(f0=55, total=60, hold_frames=6, remove=True)
        assert set(sched.values()) <= {"white", "gap", "hold"}
        assert 60 not in sched or sched.get(60, None) != "gone"

    def test_f0_clamped_to_valid(self):
        sched = vt.flicker_schedule(f0=0, total=10)
        assert 1 in sched


class TestMaskPipeline:
    def _scene(self):
        bg = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        fr = bg.copy()
        fr[100:160, 50:130] = PERSON_VAL
        return bg, fr

    def test_median_background(self):
        bg, fr = self._scene()
        frames = [bg.copy() for _ in range(3)]
        frames[1][200:210, 10:20] = PERSON_VAL  # sujeto en otro sitio en 1 de 3
        m = vt.median_background(frames)
        assert m[200:210, 10:20].max() < BG_VAL + 3

    def test_robust_median_keeps_clean_reference_outside_subject(self):
        # la mediana es solo referencia de máscara: fuera del sujeto queda
        # limpia aunque 1 de 3 muestras tenga al sujeto en otro sitio
        bg, fr = self._scene()
        frames = [bg.copy() for _ in range(3)]
        frames[1][200:210, 10:20] = PERSON_VAL
        m = vt.median_background(frames)
        assert m[200:210, 10:20].max() < BG_VAL + 3

    def test_subject_mask_finds_blob(self):
        bg, fr = self._scene()
        m = vt.subject_mask(fr, bg)
        assert m[100:160, 50:130].mean() > 0.95
        assert m[:90, :40].mean() < 0.01

    def test_mask_empty_when_no_subject(self):
        bg, _ = self._scene()
        m = vt.subject_mask(bg, bg)
        assert not m.any()

    def test_composite_white_opaque(self):
        bg, fr = self._scene()
        m = vt.subject_mask(fr, bg)
        out = vt.composite_silhouette(fr, m)
        assert (out[m] == 255).all()
        assert (out[~m] == fr[~m]).all()  # fuera de la máscara: bit-exacto

    def test_inpaint_restores_background(self):
        bg, fr = self._scene()
        m = vt.subject_mask(fr, bg)
        out = vt.inpaint_bg(fr, m, bg)
        assert (out == bg).all()  # relleno desde el fondo (mediana) -> fondo uniforme

    def test_inpaint_skips_subject_edge_band(self):
        # ropa oscura no detectada (diff < umbral) alrededor del sujeto: el
        # relleno se toma del fondo (mediana), NUNCA del borde de la ropa.
        bg, _ = self._scene()
        fr2 = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        fr2[100:160, 50:130] = PERSON_VAL                    # sujeto (detectado)
        fr2[86:174, 36:144] = BG_VAL + 15                    # banda 14px, diff 15 < 18 (NO detectada)
        fr2[100:160, 50:130] = PERSON_VAL                    # el sujeto pisa a la banda
        m = vt.subject_mask(fr2, bg)
        assert m[120, 90] and not m[92, 60]                  # control: sujeto sí, banda no
        out = vt.inpaint_bg(fr2, m, bg)
        # el interior del sujeto se rellena con el fondo REAL (100), no con la banda (115)
        assert abs(int(out[110:150, 60:120].mean()) - BG_VAL) < 2

    def test_inpaint_noop_without_mask(self):
        bg, fr = self._scene()
        out = vt.inpaint_bg(fr, np.zeros_like(bg, dtype=bool), bg)
        assert (out == fr).all()


class TestValidate:
    def test_ok(self):
        vt.TeleportOptions(time=1.0).validate()

    def test_bad_pattern_raises(self):
        with pytest.raises(EnhancementError):
            vt.TeleportOptions(time=1.0, pattern="2-x").validate()

    def test_bad_time(self):
        with pytest.raises(EnhancementError):
            vt.TeleportOptions(time=-1).validate()

    def test_bad_threshold(self):
        with pytest.raises(EnhancementError):
            vt.TeleportOptions(time=1.0, threshold=0).validate()


class TestPlan:
    def test_plan_mentions_effect(self, tmp_path):
        src = make_source(tmp_path)[0]
        plan = vt.build_plan(src, vt.TeleportOptions(time=1.0, remove=True))
        assert "VOXERA PLAN" in plan and "teleport" in plan
        assert "2-2-2" in plan and "parpadeo" in plan
        assert "sujeto eliminado" in plan


# --------------------------------------------------------------------- e2e

class TestEndToEnd:
    def test_ghost_mode_flicker_only(self, tmp_path):
        src, total = make_source(tmp_path)
        out = tmp_path / "ghost.mp4"
        vt.teleport_video(src, out, vt.TeleportOptions(time=1.5))
        frames = decode_frames(out)
        srcf = decode_frames(src)
        assert len(frames) == len(srcf) == total

        f0 = int(round(1.5 * FPS))
        # frames blancos: interior del sujeto blanco (silueta lo cubre; el borde
        # depende del dilate escalado, por eso se mide el interior)
        for i in (f0, f0 + 1, f0 + 4, f0 + 5):
            y = 40 + 2 * i
            sq = (slice(y + 4, y + 56), slice(64, 116))
            assert frames[i][sq].mean() > 250, i
        # hueco: igual que la fuente
        for i in (f0 + 2, f0 + 3):
            assert np.abs(frames[i].astype(int) - srcf[i].astype(int)).mean() < 2, i
        # fuera de la ventana: igual que la fuente
        for i in (0, 10, f0 + 20, total - 1):
            assert np.abs(frames[i].astype(int) - srcf[i].astype(int)).mean() < 2, i

    def test_remove_mode_full_teleport(self, tmp_path):
        src, total = make_source(tmp_path)
        out = tmp_path / "remove.mp4"
        vt.teleport_video(src, out, vt.TeleportOptions(time=1.5, remove=True, hold=0.2))
        frames = decode_frames(out)
        srcf = decode_frames(src)
        assert len(frames) == total

        f0 = int(round(1.5 * FPS))
        hold_end = f0 + 2 * 2 + 2 + int(round(0.2 * FPS))
        # frames blancos: silueta blanca opaca (máscara del frame actual, como la
        # roto de cada corte del tutorial — sigue al sujeto en ese instante)
        for i in (f0, f0 + 1, f0 + 4, f0 + 5):
            y = 40 + 2 * i
            sq = (slice(y + 4, y + 56), slice(64, 116))
            assert frames[i][sq].mean() > 250, (i, frames[i][sq].mean())
        # tras el parpadeo: el sujeto YA NO ESTÁ (fondo restaurado)
        for i in (hold_end + 1, total - 1):
            y = 40 + 2 * i
            sq = (slice(y, y + 60), slice(60, 120))
            assert abs(float(frames[i][sq].mean()) - BG_VAL) < 3, (i, frames[i][sq].mean())
        # hold: silueta congelada blanca en la posición del último frame blanco
        y = 40 + 2 * (f0 + 5)
        sq = (slice(y + 4, y + 56), slice(64, 116))
        assert frames[f0 + 6][sq].mean() > 250

    def test_audio_remuxed(self, tmp_path):
        src, _ = make_source(tmp_path)
        out = tmp_path / "audio.mp4"
        vt.teleport_video(src, out, vt.TeleportOptions(time=1.0))
        import voxera.video_enhance as ve
        assert ve.probe_video(out)["has_audio"]

    def test_out_of_bounds_time_raises(self, tmp_path):
        src, _ = make_source(tmp_path)
        with pytest.raises(EnhancementError):
            vt.teleport_video(src, tmp_path / "x.mp4", vt.TeleportOptions(time=10.0))
