"""Unit tests de video levitate: efecto levitación (frame hold + flotar).

- Offsets: subida con curva de easing y balanceo senoidal (puro, testable).
- Sombra blanda: se encoge/aclara con el progreso; no-op sin máscara.
- Validación de opciones y plan --dry-run.
- e2e sintético: cámara fija + cuadrado móvil = "sujeto" → antes del frame
  hold bit-exacto; tras él, el cuadrado congelado aparece ELEVADO y su
  posición original queda como fondo.

Los tests corren sin torch/LaMa (fallback diff-borde + nanmedian), igual que
test_video_teleport.py.
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from voxera import cli
from voxera import video_levitate as vl
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
    """Fuerza diff-borde y sin LaMa (el cuadrado no es 'person' para DeepLabV3)."""
    monkeypatch.setattr(vt, "_HAS_TORCH", False)
    monkeypatch.setattr(vt, "_lama_available", lambda: False)


def make_source(tmp_path, name="in.mp4"):
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
    proc = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(video), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    )
    n = len(proc.stdout) // (W * H * 3)
    return np.frombuffer(proc.stdout, dtype=np.uint8).reshape(n, H, W, 3)


# ---------------------------------------------------------------- pure units


class TestOffset:
    def test_before_and_at_is_zero(self):
        assert vl.levitation_offset(0.0, 1.0, 48, 1.0, 0) == 0.0
        assert vl.levitation_offset(1.0, 1.0, 48, 1.0, 0) == 0.0
        assert vl.levitation_offset(0.5, 1.0, 48, 1.0, 0) == 0.0

    def test_full_lift_at_end_of_rise(self):
        # linear (curve 0) → en t=at+dur el progreso es 1 y dy = -lift
        assert vl.levitation_offset(2.0, 1.0, 48, 1.0, 0, curve=0) == pytest.approx(-48.0)

    def test_rise_is_upward_and_monotonic(self):
        offs = [vl.levitation_offset(t, 1.0, 48, 1.0, 0, curve=62) for t in (1.1, 1.5, 1.9, 2.0)]
        assert all(o < 0 for o in offs)
        # cada vez más arriba: decreciente (más negativo) frame a frame
        assert all(a >= b for a, b in zip(offs, offs[1:]))
        assert offs[-1] == pytest.approx(-48.0)

    def test_bob_oscillates_around_lift(self):
        offs = [vl.levitation_offset(1.0 + 1.0 + k * 0.1, 1.0, 48, 1.0, 5.0, curve=0)
                for k in range(24)]
        assert min(offs) <= -48.0 - 4.0      # pico arriba
        assert max(offs) >= -48.0 + 4.0      # pico abajo
        assert all(o < 0 for o in offs)      # nunca vuelve al suelo

    def test_progress(self):
        assert vl.lift_progress(1.0, 1.0, 1.0) == 0.0
        assert vl.lift_progress(1.5, 1.0, 1.0) == pytest.approx(0.5)
        assert vl.lift_progress(3.0, 1.0, 1.0) == 1.0

    def test_static_disables_periodic_bob(self):
        assert vl.levitation_offset(3.0, 1.0, 48, 1.0, 8, curve=0,
                                     motion="static") == pytest.approx(-48.0)

    def test_transform_reaches_position_rotation_and_scale(self):
        dy, dx, rot, scale = vl.levitation_transform(
            2.0, 1.0, 48.0, 1.0, 0.0,
            move_x_px=18.0, move_y_px=6.0,
            rotate_deg=12.0, scale_pct=20.0,
            motion="static", curve=0,
        )
        assert (dy, dx, rot, scale) == pytest.approx((-42.0, 18.0, 12.0, 1.2))

    def test_drift_adds_lateral_motion_after_rise(self):
        _, dx, _, _ = vl.levitation_transform(
            2.4, 1.0, 48.0, 1.0, 0.0,
            move_x_px=10.0, motion="drift", sway_px=5.0,
            sway_period=1.6, curve=0,
        )
        assert dx == pytest.approx(15.0, abs=0.05)


class TestKeyframes:
    def test_parse_and_interpolate_full_path(self):
        keyframes = vl.parse_keyframes(
            "1:8,-12,10,12;0:0,0;0.5:10,-5,6,4"
        )
        assert [point.progress for point in keyframes] == [0.0, 0.5, 1.0]
        assert vl.interpolate_keyframes(0.5, keyframes) == pytest.approx(
            (10.0, -5.0, 6.0, 4.0)
        )
        assert vl.interpolate_keyframes(1.5, keyframes) == pytest.approx(
            (8.0, -12.0, 10.0, 12.0)
        )

    def test_keyframes_transform_uses_percentages_and_replaces_legacy_path(self):
        keyframes = vl.parse_keyframes("0:0,0;0.5:10,-5,6,4;1:8,-12,10,12")
        result = vl.levitation_transform(
            1.5, 1.0, 120.0, 1.0, 0.0,
            move_x_px=80.0, move_y_px=80.0, rotate_deg=90.0, scale_pct=50.0,
            motion="static", curve=0, keyframes=keyframes,
            frame_width=200, frame_height=400,
        )
        assert result == pytest.approx((-20.0, 20.0, 6.0, 1.04))

    def test_keyframes_require_identity_at_zero(self):
        with pytest.raises(ValueError, match="empezar en progreso 0"):
            vl.parse_keyframes("0.2:0,0;1:4,-8")
        with pytest.raises(ValueError, match="pose original"):
            vl.parse_keyframes("0:1,0;1:4,-8")
        with pytest.raises(ValueError, match="repetir"):
            vl.parse_keyframes("0:0,0;0.5:1,1;0.5:2,2")


class TestShadow:
    def _mask(self):
        m = np.zeros((H, W), dtype=bool)
        m[100:160, 50:130] = True
        return m

    def test_darkens_below_subject(self):
        fr = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        out = vl.render_shadow(fr, self._mask(), lift_norm=0.0, strength=0.5)
        # bajo los pies (y > 160) debe oscurecer; arriba lejos no
        assert out[170:180, 70:110].mean() < BG_VAL
        assert out[:60, 70:110].mean() == BG_VAL

    def test_lift_fades_shadow(self):
        fr = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        ground = vl.render_shadow(fr, self._mask(), lift_norm=0.0, strength=0.5)
        floated = vl.render_shadow(fr, self._mask(), lift_norm=1.0, strength=0.5)
        # flotando la sombra es más tenue (más cercana al fondo) que en el suelo
        assert floated[170:180, 70:110].mean() > ground[170:180, 70:110].mean()

    def test_empty_mask_noop(self):
        fr = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        out = vl.render_shadow(fr, np.zeros((H, W), dtype=bool), 0.0, 0.5)
        assert np.array_equal(out, fr)


class TestObjectMask:
    def test_detects_arbitrary_colored_object_against_plate(self):
        background = np.full((H, W, 3), BG_VAL, dtype=np.uint8)
        frame = background.copy()
        frame[90:150, 45:125] = PERSON_VAL
        mask = vt.object_mask(frame, background)
        assert mask[110:140, 60:110].mean() > 0.98
        assert not mask[:40].any()


class TestValidate:
    def test_ok(self):
        vl.LevitateOptions(at=1.0).validate()
        vl.LevitateOptions(at=1.0, lift=0, bob=0, shadow=True, subject="object").validate()

    def test_bad_at(self):
        with pytest.raises(EnhancementError):
            vl.LevitateOptions(at=-1).validate()

    def test_bad_lift(self):
        with pytest.raises(EnhancementError):
            vl.LevitateOptions(at=1.0, lift=70).validate()

    def test_bad_easing(self):
        with pytest.raises(EnhancementError):
            vl.LevitateOptions(at=1.0, easing="bounce").validate()

    def test_bad_motion(self):
        with pytest.raises(EnhancementError):
            vl.LevitateOptions(at=1.0, motion="teleport").validate()

    def test_bad_transform(self):
        with pytest.raises(EnhancementError):
            vl.LevitateOptions(at=1.0, rotate=181).validate()
        with pytest.raises(EnhancementError):
            vl.LevitateOptions(at=1.0, scale=-76).validate()

    def test_bad_move_string(self):
        with pytest.raises(ValueError):
            vl.parse_move("1,2,3")
        with pytest.raises(ValueError):
            vl.parse_move("101,0")

    def test_bad_keyframes(self):
        with pytest.raises(EnhancementError, match="keyframes inválidos"):
            vl.LevitateOptions(at=1.0, keyframes="0:2,0;1:4,-8").validate()

    def test_bad_subject(self):
        with pytest.raises(EnhancementError):
            vl.LevitateOptions(at=1.0, subject="alien").validate()

    def test_missing_mask(self):
        with pytest.raises(EnhancementError):
            vl.LevitateOptions(at=1.0, mask="nope.png").validate()

    def test_missing_plate(self):
        with pytest.raises(EnhancementError):
            vl.LevitateOptions(at=1.0, plate="nope.mp4").validate()


class TestPlan:
    def test_plan_mentions_effect(self, tmp_path):
        src = make_source(tmp_path)[0]
        plan = vl.build_plan(src, vl.LevitateOptions(at=1.0))
        assert "VOXERA PLAN" in plan and "levitate" in plan
        assert "congelar" in plan and "elevar" in plan

    def test_plan_mentions_shadow_and_plate(self, tmp_path):
        src = make_source(tmp_path)[0]
        plan = vl.build_plan(src, vl.LevitateOptions(at=1.0, shadow=True))
        assert "sombra" in plan and "plate" in plan

    def test_plan_mentions_arbitrary_subject(self, tmp_path):
        src = make_source(tmp_path)[0]
        plan = vl.build_plan(src, vl.LevitateOptions(at=1.0, subject="object"))
        assert "objeto arbitrario" in plan and "sujeto  : object" in plan

    def test_plan_mentions_full_motion(self, tmp_path):
        src = make_source(tmp_path)[0]
        plan = vl.build_plan(src, vl.LevitateOptions(
            at=1.0, motion="drift", move_x=10, move_y=-3,
            rotate=8, scale=12, sway=2.5,
        ))
        assert "movimiento" in plan
        assert "move +10.0%,-3.0%" in plan
        assert "rotate +8.0" in plan and "scale +12.0%" in plan

    def test_plan_mentions_keyframes(self, tmp_path):
        src = make_source(tmp_path)[0]
        plan = vl.build_plan(src, vl.LevitateOptions(
            at=1.0,
            keyframes=vl.parse_keyframes("0:0,0;0.5:4,-6,3,5;1:8,-12,6,10"),
        ))
        assert "3 keyframes" in plan
        assert "reemplaza lift/move/rotate/scale" in plan
        assert "0:+0.0,+0.0" in plan


class TestCLI:
    def test_parser_accepts_keyframe_path(self):
        args = cli.build_parser().parse_args([
            "video", "levitate", "in.mp4", "-o", "out.mp4", "--at", "1.0",
            "--keyframes", "0:0,0;0.5:4,-8,3,5;1:8,-15,6,10",
        ])
        points = vl.parse_keyframes(args.keyframes)
        assert len(points) == 3
        assert args.keyframes.startswith("0:0,0")


# --------------------------------------------------------------------- e2e


class TestEndToEnd:
    def test_arbitrary_object_lifts_and_background_shows(self, tmp_path):
        src, total = make_source(tmp_path)
        out = tmp_path / "levitate_object.mp4"
        vl.levitate_video(
            src, out,
            vl.LevitateOptions(at=1.0, lift=15.0, dur=1.0, bob=0.0, subject="object"),
        )
        frames = decode_all(out)
        srcf = decode_all(src)
        assert len(frames) == len(srcf) == total

        f0 = int(round(1.0 * FPS))   # 30
        y0 = 40 + 2 * f0             # 100
        lift_px = int(round(0.15 * H))  # 48

        # antes del frame hold: bit-exacto (passthrough)
        for i in (0, 10, f0 - 1):
            assert np.abs(frames[i].astype(int) - srcf[i].astype(int)).mean() < 2, i

        # en el frame hold: el cuadrado sigue en su sitio (dy ≈ 0)
        assert frames[f0][y0 + 10 : y0 + 50, 70:110].mean() > 200

        # tras la subida (frame 75, t=2.5s): el cuadrado congelado está arriba
        new_top = y0 - lift_px         # 52
        assert frames[75][new_top + 5 : new_top + 30, 70:110].mean() > 200
        # su posición original queda como fondo (plate)
        assert frames[75][y0 + 15 : y0 + 40, 70:110].mean() < BG_VAL + 6

    def test_shadow_and_bob_do_not_break_output(self, tmp_path):
        src, total = make_source(tmp_path)
        out = tmp_path / "levitate_shadow.mp4"
        vl.levitate_video(
            src, out,
            vl.LevitateOptions(at=1.0, lift=15.0, dur=1.0, bob=2.0, shadow=True),
        )
        frames = decode_all(out)
        assert len(frames) == total
        # el sujeto sigue elevado al final (presencia arriba, hueco abajo)
        f0 = int(round(1.0 * FPS))
        y0 = 40 + 2 * f0
        assert frames[-1][y0 - 48 + 5 : y0 - 48 + 30, 70:110].mean() > 200

    def test_audio_remuxed(self, tmp_path):
        src, _ = make_source(tmp_path)
        out = tmp_path / "audio.mp4"
        vl.levitate_video(src, out, vl.LevitateOptions(at=1.0))
        import voxera.video_enhance as ve
        assert ve.probe_video(out)["has_audio"]

    def test_full_motion_transform_renders(self, tmp_path):
        src, total = make_source(tmp_path)
        out = tmp_path / "levitate_motion.mp4"
        vl.levitate_video(
            src, out,
            vl.LevitateOptions(
                at=1.0, lift=12.0, dur=1.0, bob=0.0,
                motion="drift", move_x=12.0, move_y=-2.0,
                rotate=12.0, scale=15.0, sway=2.0,
            ),
        )
        frames = decode_all(out)
        assert len(frames) == total
        # La trayectoria no altera el passthrough anterior al frame hold.
        source = decode_all(src)
        assert np.abs(frames[29].astype(int) - source[29].astype(int)).mean() < 2
        # El recorte transformado sigue teniendo píxeles del sujeto después de subir.
        assert frames[75].max() >= PERSON_VAL - 12

    def test_keyframes_render_a_multi_point_path(self, tmp_path):
        src, total = make_source(tmp_path)
        out = tmp_path / "levitate_keyframes.mp4"
        vl.levitate_video(
            src, out,
            vl.LevitateOptions(
                at=1.0, lift=40.0, dur=1.0, bob=0.0, motion="static",
                curve=0,
                keyframes=vl.parse_keyframes("0:0,0;0.5:4,-6;1:10,-12"),
            ),
        )
        frames = decode_all(out)
        assert len(frames) == total
        # El keyframe final es x=10% W, y=-12% H; lift=40% se ignora.
        y0 = 40 + 2 * int(round(1.0 * FPS))
        final_y = y0 - int(round(0.12 * H))
        final_x = 60 + int(round(0.10 * W))
        assert frames[75][final_y + 4 : final_y + 48, final_x + 4 : final_x + 56].mean() > 190

    def test_out_of_bounds_at_raises(self, tmp_path):
        src, _ = make_source(tmp_path)
        with pytest.raises(EnhancementError):
            vl.levitate_video(src, tmp_path / "x.mp4", vl.LevitateOptions(at=10.0))
