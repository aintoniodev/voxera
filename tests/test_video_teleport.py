"""Unit tests de video teleport v2: teletransportación real (toma única).

- Schedule de fases por frame (white_a/empty/appear/white_b/after, vanish).
- Primitivas: erase (plate), paste desplazado con feather, paste blanco.
- Plate de fondo: nanmedian consciente de persona (sujeto móvil → sin agujero;
  sujeto estático → agujero rellenado con el fondo).
- Validación de opciones y plan --dry-run.
- e2e sintético: cámara fija + cuadrado móvil = "sujeto" → fases verificadas
  por frame en la salida decodificada (shift y vanish).

Los tests corren sin torch/LaMa (fallback diff-borde + relleno EDT/Telea).
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


@pytest.fixture(autouse=True)
def _synthetic_fallback(monkeypatch):
    """Fuerza diff-borde y sin LaMa: el cuadrado sintético no es 'person'
    para DeepLabV3 y así los tests son idénticos con o sin torch/LaMa."""
    monkeypatch.setattr(vt, "_HAS_TORCH", False)
    monkeypatch.setattr(vt, "_lama_available", lambda: False)


def make_frames(static=False):
    total = int(round(DUR * FPS))
    bg = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
    frames = []
    for i in range(total):
        fr = bg.copy()
        y = 100 if static else 40 + 2 * i
        fr[y : y + 60, 60:120] = PERSON_VAL
        frames.append(fr)
    return frames


def make_source(tmp_path, name="in.mp4", static=False):
    frames = make_frames(static)
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
    return out, len(frames)


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


class TestParseShift:
    def test_default_when_none(self):
        assert vt.parse_shift(None) == (-25.0, 0.0)

    def test_custom(self):
        assert vt.parse_shift("25, -15") == (25.0, -15.0)
        assert vt.parse_shift("0,0") == (0.0, 0.0)

    def test_bad_format(self):
        with pytest.raises(ValueError):
            vt.parse_shift("25")
        with pytest.raises(ValueError):
            vt.parse_shift("a,b")

    def test_out_of_range(self):
        with pytest.raises(ValueError):
            vt.parse_shift("95,0")
        with pytest.raises(ValueError):
            vt.parse_shift("0,-91")


class TestSchedule:
    def test_shift_mode_phases(self):
        sched = vt.teleport_schedule(f0=10, total=40, pattern="2-2-2")
        assert [sched.get(i, "normal") for i in range(10)] == ["normal"] * 10
        assert sched[10] == sched[11] == "white_a"
        assert sched[12] == "empty"        # hueco: primero esfumado
        assert sched[13] == "appear"       # luego ya en B
        assert sched[14] == sched[15] == "white_b"
        assert all(sched[i] == "after" for i in range(16, 40))

    def test_odd_gap(self):
        # g=3: 1 empty + 2 appear
        sched = vt.teleport_schedule(f0=5, total=20, pattern="2-3-2")
        assert sched[7] == "empty"
        assert sched[8] == sched[9] == "appear"
        assert sched[10] == sched[11] == "white_b"
        assert sched[12] == "after"

    def test_vanish_mode(self):
        sched = vt.teleport_schedule(f0=10, total=40, pattern="2-2-2", vanish=True)
        assert sched[10] == sched[11] == "white_a"
        # tras el blanco inicial: TODO vacío hasta el final
        assert all(sched[i] == "empty" for i in range(12, 40))

    def test_truncated_near_end(self):
        sched = vt.teleport_schedule(f0=38, total=40, pattern="2-2-2")
        assert set(sched.values()) <= {"white_a", "empty", "appear", "white_b", "after"}

    def test_f0_clamped(self):
        sched = vt.teleport_schedule(f0=0, total=10)
        assert 1 in sched and 0 not in sched


class TestComposite:
    def test_white_opaque_inside_mask(self):
        fr = np.zeros((H, W, 3), dtype=np.uint8)
        m = np.zeros((H, W), dtype=bool)
        m[100:160, 50:130] = True
        out = vt.composite_silhouette(fr, m)
        assert (out[m] == 255).all()
        assert (out[~m] == 0).all()  # fuera de la máscara: bit-exacto


class TestErasePaste:
    def test_erase_replaces_with_plate(self):
        fr = np.zeros((H, W, 3), dtype=np.uint8)
        fr[100:160, 50:130] = PERSON_VAL
        plate = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        m = np.zeros((H, W), dtype=bool)
        m[100:160, 50:130] = True
        out = vt.erase_person(fr, m, plate)
        assert (out[m] == BG_VAL).all()
        assert (out[~m] == 0).all()  # fuera: intacto

    def test_paste_person_moves_interior(self):
        src = np.zeros((H, W, 3), dtype=np.uint8)
        src[100:160, 50:130] = PERSON_VAL
        m = np.zeros((H, W), dtype=bool)
        m[100:160, 50:130] = True
        out = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        out = vt.paste_person(out, src, m, dy=10, dx=20)
        # interior profundo del destino: píxeles exactos de la persona
        assert (out[125:150, 85:120] == PERSON_VAL).all()
        # zona lejana intacta
        assert (out[:50, :40] == BG_VAL).all()

    def test_paste_negative_shift(self):
        src = np.zeros((H, W, 3), dtype=np.uint8)
        src[100:160, 50:130] = PERSON_VAL
        m = np.zeros((H, W), dtype=bool)
        m[100:160, 50:130] = True
        out = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        out = vt.paste_person(out, src, m, dy=0, dx=-40)
        assert (out[115:150, 30:60] == PERSON_VAL).all()

    def test_paste_white(self):
        out = np.zeros((H, W, 3), dtype=np.uint8)
        m = np.zeros((H, W), dtype=bool)
        m[100:160, 50:130] = True
        out = vt.paste_white(out, m, dy=0, dx=30)
        assert out[110:150, 90:150].mean() > 250

    def test_shift_slices_out_of_frame(self):
        m = np.zeros((H, W), dtype=bool)
        m[100:160, 50:130] = True
        assert vt._shift_slices((H, W), m, dy=0, dx=-500) is None

    def test_shift_slices_empty_mask(self):
        # persona no detectada: no debe explotar (ys.min() sobre vacío)
        m = np.zeros((H, W), dtype=bool)
        assert vt._shift_slices((H, W), m, dy=5, dx=5) is None
        out = np.zeros((H, W, 3), dtype=np.uint8)
        vt.paste_person(out, out.copy(), m, 5, 5)  # no-op sin error
        vt.paste_white(out, m, 5, 5)


class TestPersonMask:
    def test_fallback_finds_subject_on_uniform_bg(self):
        # sin torch (tests en .venv-ims): fallback diff-borde
        fr = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        fr[100:160, 50:130] = PERSON_VAL
        m = vt.person_mask(fr, dilate=0)
        assert m[100:160, 50:130].mean() > 0.95
        assert m[:80, :40].mean() < 0.05


class TestPlate:
    def test_moving_subject_no_hole(self, tmp_path):
        # sujeto móvil: la nanmedian consciente recupera TODO el fondo
        src, _ = make_source(tmp_path)
        plate, engine = vt.build_plate(src, samples=16)
        assert plate.shape == (H, W, 3)
        assert np.abs(plate.astype(int) - BG_VAL).mean() < 3
        assert engine in {"nanmedian", "lama", "telea", "edt"}

    def test_static_subject_hole_filled(self, tmp_path):
        # sujeto estático: agujero persistente rellenado con el fondo uniforme
        src, _ = make_source(tmp_path, static=True)
        plate, engine = vt.build_plate(src, samples=8)
        assert np.abs(plate.astype(int) - BG_VAL).mean() < 3


class TestValidate:
    def test_ok(self):
        vt.TeleportOptions(time=1.0).validate()
        vt.TeleportOptions(time=1.0, vanish=True).validate()
        vt.TeleportOptions(time=1.0, shift="30,-10").validate()

    def test_bad_pattern(self):
        with pytest.raises(EnhancementError):
            vt.TeleportOptions(time=1.0, pattern="2-x").validate()

    def test_bad_time(self):
        with pytest.raises(EnhancementError):
            vt.TeleportOptions(time=-1).validate()

    def test_bad_shift(self):
        with pytest.raises(EnhancementError):
            vt.TeleportOptions(time=1.0, shift="nope").validate()
        with pytest.raises(EnhancementError):
            vt.TeleportOptions(time=1.0, shift="99,0").validate()

    def test_bad_plate_samples(self):
        with pytest.raises(EnhancementError):
            vt.TeleportOptions(time=1.0, plate_samples=1).validate()


class TestPlan:
    def test_plan_mentions_shift(self, tmp_path):
        src = make_source(tmp_path)[0]
        plan = vt.build_plan(src, vt.TeleportOptions(time=1.0, shift="25,0"))
        assert "VOXERA PLAN" in plan and "teleport" in plan
        assert "2-2-2" in plan and "reaparece" in plan

    def test_plan_mentions_vanish(self, tmp_path):
        src = make_source(tmp_path)[0]
        plan = vt.build_plan(src, vt.TeleportOptions(time=1.0, vanish=True))
        assert "desaparece" in plan and "plate" in plan


# --------------------------------------------------------------------- e2e

class TestEndToEnd:
    def test_shift_teleport_in_output(self, tmp_path):
        src, total = make_source(tmp_path)
        out = tmp_path / "teleport.mp4"
        vt.teleport_video(src, out, vt.TeleportOptions(time=1.5, shift="-25,0"))
        frames = decode_all(out)
        srcf = decode_all(src)
        assert len(frames) == len(srcf) == total

        f0 = int(round(1.5 * FPS))  # 45
        dx = int(round(-0.25 * W))  # -45

        def sq_y(i):
            return 40 + 2 * i

        # white_a: el cuadrado en A se vuelve blanco
        for i in (f0, f0 + 1):
            y = sq_y(i)
            assert frames[i][y + 10 : y + 50, 70:110].mean() > 250, i
        # empty: fondo en todo el frame (persona esfumada)
        assert np.abs(frames[f0 + 2].astype(int) - BG_VAL).mean() < 3, f0 + 2
        # appear: cuadrado ya en B (x+dx), A vacío
        y = sq_y(f0 + 3)
        assert frames[f0 + 3][y + 10 : y + 50, 60 + dx + 10 : 60 + dx + 50].mean() > 200
        assert np.abs(frames[f0 + 3][:, 70:110].astype(int) - BG_VAL).mean() < 3
        # white_b: blanco en B
        for i in (f0 + 4, f0 + 5):
            y = sq_y(i)
            assert frames[i][y + 10 : y + 50, 60 + dx + 10 : 60 + dx + 50].mean() > 250, i
        # after: cuadrado vivo en B, A vacío
        for i in (f0 + 6, f0 + 20, total - 1):
            y = sq_y(i)
            assert frames[i][y + 10 : y + 50, 60 + dx + 10 : 60 + dx + 50].mean() > 200, i
            assert np.abs(frames[i][:, 70:110].astype(int) - BG_VAL).mean() < 3, i
        # antes del parpadeo: bit-exacto
        for i in (0, 10, f0 - 1):
            assert np.abs(frames[i].astype(int) - srcf[i].astype(int)).mean() < 2, i

    def test_vanish_in_output(self, tmp_path):
        src, total = make_source(tmp_path)
        out = tmp_path / "vanish.mp4"
        vt.teleport_video(src, out, vt.TeleportOptions(time=1.0, vanish=True))
        frames = decode_all(out)
        f0 = int(round(1.0 * FPS))  # 30
        # white_a: blanco
        y = 40 + 2 * f0
        assert frames[f0][y + 10 : y + 50, 70:110].mean() > 250
        # desde el hueco hasta el final: TODO fondo
        for i in (f0 + 2, f0 + 10, total - 1):
            assert np.abs(frames[i].astype(int) - BG_VAL).mean() < 3, i
        # antes: intacto
        assert np.abs(frames[0].astype(int) - decode_all(src)[0].astype(int)).mean() < 2

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
