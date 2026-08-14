"""Unit tests de video teleport (teletransportación): parpadeo de silueta blanca.

- Patrón de parpadeo y plan de fases por frame (2-2-2 del tutorial).
- Silueta blanca opaca (composite) — bit-exacta fuera de la máscara.
- Segmentación de persona (torch) o fallback diff-borde (tests sintéticos).
- Validación de opciones y plan --dry-run.
- e2e sintético: cámara fija + blob móvil = "sujeto" -> parpadeo verificado
  por fase en la salida decodificada.
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


def make_source(tmp_path, name="in.mp4"):
    """Sintético: fondo gris constante + cuadrado blanco móvil ("sujeto")."""
    total = int(round(DUR * FPS))
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


def decode_all(video):
    """Decodifica rgb24 completo (frame-exacto por construcción)."""
    proc = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(video), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    )
    n = len(proc.stdout) // (W * H * 3)
    return np.frombuffer(proc.stdout, dtype=np.uint8).reshape(n, H, W, 3)


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
        sched = vt.flicker_schedule(f0=10, total=40, pattern="2-2-2")
        assert [sched.get(i, "normal") for i in range(10)] == ["normal"] * 10
        assert sched[10] == sched[11] == "white"
        assert sched[12] == sched[13] == "gap"
        assert sched[14] == sched[15] == "white"
        assert [sched.get(i, "normal") for i in range(16, 40)] == ["normal"] * 24

    def test_truncated_near_end(self):
        sched = vt.flicker_schedule(f0=38, total=40, pattern="2-2-2")
        assert set(sched.values()) <= {"white", "gap", "normal"}

    def test_f0_clamped(self):
        sched = vt.flicker_schedule(f0=0, total=10)
        assert 1 in sched


class TestComposite:
    def test_white_opaque_inside_mask(self):
        fr = np.zeros((H, W, 3), dtype=np.uint8)
        m = np.zeros((H, W), dtype=bool)
        m[100:160, 50:130] = True
        out = vt.composite_silhouette(fr, m)
        assert (out[m] == 255).all()
        assert (out[~m] == 0).all()  # fuera de la máscara: bit-exacto


class TestPersonMask:
    def test_fallback_finds_subject_on_uniform_bg(self):
        # sin torch (tests en .venv-ims): fallback diff-borde
        fr = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        fr[100:160, 50:130] = PERSON_VAL
        m = vt.person_mask(fr, dilate=0)
        assert m[100:160, 50:130].mean() > 0.95
        assert m[:80, :40].mean() < 0.05


class TestValidate:
    def test_ok(self):
        vt.TeleportOptions(time=1.0).validate()

    def test_bad_pattern(self):
        with pytest.raises(EnhancementError):
            vt.TeleportOptions(time=1.0, pattern="2-x").validate()

    def test_bad_time(self):
        with pytest.raises(EnhancementError):
            vt.TeleportOptions(time=-1).validate()


class TestPlan:
    def test_plan_mentions_effect(self, tmp_path):
        src = make_source(tmp_path)[0]
        plan = vt.build_plan(src, vt.TeleportOptions(time=1.0))
        assert "VOXERA PLAN" in plan and "teleport" in plan
        assert "2-2-2" in plan and "parpadeo" in plan


# --------------------------------------------------------------------- e2e

class TestEndToEnd:
    def test_flicker_pattern_in_output(self, tmp_path):
        src, total = make_source(tmp_path)
        out = tmp_path / "teleport.mp4"
        vt.teleport_video(src, out, vt.TeleportOptions(time=1.5))
        frames = decode_all(out)
        srcf = decode_all(src)
        assert len(frames) == len(srcf) == total

        f0 = int(round(1.5 * FPS))
        # frames blancos: interior del sujeto blanco (silueta)
        for i in (f0, f0 + 1, f0 + 4, f0 + 5):
            y = 40 + 2 * i
            sq = (slice(y + 4, y + 56), slice(64, 116))
            assert frames[i][sq].mean() > 250, i
        # hueco: igual que la fuente
        for i in (f0 + 2, f0 + 3):
            assert np.abs(frames[i].astype(int) - srcf[i].astype(int)).mean() < 2, i
        # fuera de la ventana: igual que la fuente (bit-exacto)
        for i in (0, 10, f0 + 20, total - 1):
            assert np.abs(frames[i].astype(int) - srcf[i].astype(int)).mean() < 2, i

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
