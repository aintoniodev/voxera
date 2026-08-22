"""Unit tests de video zoom (Grow): solo ffmpeg, sin GPU, sin Premiere.

- Curva de easing: monotónica, bounded, curve=0 => lineal.
- Filtro: cadena scale->crop->scale con ancla y expresión por frame.
- Validación de opciones y plan --dry-run.
- Un e2e: testsrc + voz sintética -> zoom -> verificar streams y duración.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

import tests.synth as s
from voxera import video_zoom as vz
from voxera.errors import EnhancementError

FFMPEG = shutil.which("ffmpeg") or (
    Path("C:/ffmpeg/bin/ffmpeg.exe").exists() and "C:/ffmpeg/bin/ffmpeg.exe"
)
pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg required")

SR = 16000


def make_video(tmp_path, name="in.mp4", duration=2.0, size="320x568", rate=30):
    """testsrc + voz sintética (mismo patrón que test_video_enhance.py)."""
    wav = tmp_path / "audio.wav"
    import soundfile as sf

    sf.write(str(wav), s.speech_like(duration), SR)
    out = tmp_path / name
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "lavfi",
         "-i", f"testsrc=duration={duration}:size={size}:rate={rate}",
         "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "96k", "-shortest", str(out)],
        check=True, capture_output=True,
    )
    return out


class TestEase:
    def test_bounds_and_monotonic(self):
        for easing in vz.ZOOM_EASINGS:
            prev = -1.0
            for i in range(101):
                v = vz.ease(i / 100, 62, easing)
                assert 0.0 <= v <= 1.0, (easing, i, v)
                assert v >= prev - 1e-9, (easing, i, v, prev)
                prev = v

    def test_curve_zero_is_linear(self):
        for easing in ("smooth", "out", "in"):
            for p in (0.0, 0.25, 0.5, 0.75, 1.0):
                assert vz.ease(p, 0, easing) == pytest.approx(p, abs=1e-9)

    def test_endpoints(self):
        for easing in vz.ZOOM_EASINGS:
            assert vz.ease(0.0, 62, easing) == 0.0
            assert vz.ease(1.0, 62, easing) == 1.0

    def test_linear_passthrough(self):
        assert vz.ease(0.3, 99, "linear") == 0.3

    def test_default_matches_tutorial_range(self):
        # con curva 62, a mitad de camino el zoom va ~50% del total (S suave)
        v = vz.ease(0.5, vz.DEFAULT_CURVE, "smooth")
        assert 0.48 <= v <= 0.52


class TestOptions:
    def test_bad_pct(self):
        with pytest.raises(EnhancementError):
            vz.ZoomOptions(pct=0).validate()

    def test_shrink_pct_100(self):
        with pytest.raises(EnhancementError):
            vz.ZoomOptions(direction="shrink", pct=100).validate()

    def test_bad_curve(self):
        with pytest.raises(EnhancementError):
            vz.ZoomOptions(curve=101).validate()

    def test_bad_easing(self):
        with pytest.raises(EnhancementError):
            vz.ZoomOptions(easing="nope").validate()

    def test_bad_direction(self):
        with pytest.raises(EnhancementError):
            vz.ZoomOptions(direction="nope").validate()

    def test_bad_hold(self):
        with pytest.raises(EnhancementError):
            vz.ZoomOptions(direction="pulse", hold=1.5).validate()

    def test_bad_anchor(self):
        with pytest.raises(EnhancementError):
            vz.ZoomOptions(anchor=(1.5, 0.5)).validate()

    def test_bad_seg(self):
        with pytest.raises(EnhancementError):
            vz.ZoomOptions(start=5, end=2).validate()

    def test_bad_ss(self):
        with pytest.raises(EnhancementError):
            vz.ZoomOptions(ss=3).validate()

    def test_defaults(self):
        o = vz.ZoomOptions()
        assert o.pct == vz.DEFAULT_PCT == 40.0
        assert o.curve == vz.DEFAULT_CURVE == 62.0
        assert o.anchor == (0.5, 0.5)
        assert o.direction == "grow"


class TestZCurve:
    def test_grow_endpoints(self):
        o = vz.ZoomOptions(pct=40)
        assert vz.z_at(0.0, 4.0, o) == pytest.approx(1.0)
        assert vz.z_at(4.0, 4.0, o) == pytest.approx(1.4, abs=1e-6)
        # en el último frame (30fps) el zoom está prácticamente en el pico
        assert vz.z_at(4.0 - 1 / 30, 4.0, o) == pytest.approx(1.4, abs=1e-3)

    def test_grow_monotonic(self):
        o = vz.ZoomOptions(pct=40)
        prev = -1
        for i in range(41):
            z = vz.z_at(i / 10, 4.0, o)
            assert z >= prev - 1e-9
            prev = z

    def test_shrink_endpoints(self):
        o = vz.ZoomOptions(pct=23, direction="shrink")
        assert vz.z_at(0.0, 2.0, o) == pytest.approx(1.0)
        assert vz.z_at(2.0, 2.0, o) == pytest.approx(0.77, abs=1e-6)

    def test_pulse_shape(self):
        o = vz.ZoomOptions(pct=40, direction="pulse", hold=0.2)
        # in 40% -> pico en t=1.6 (40%% de 4s) -> hold 0.8s -> out hasta 4s
        assert vz.z_at(0.0, 4.0, o) == pytest.approx(1.0)
        assert vz.z_at(1.6, 4.0, o) == pytest.approx(1.4, abs=1e-6)
        assert vz.z_at(2.4, 4.0, o) == pytest.approx(1.4, abs=1e-6)
        assert vz.z_at(4.0, 4.0, o) == pytest.approx(1.0, abs=1e-6)
        # continuidad en el pico y en el valle
        assert vz.z_at(1.599, 4.0, o) < 1.4
        assert vz.z_at(2.401, 4.0, o) < 1.4

    def test_pulse_no_hold(self):
        o = vz.ZoomOptions(pct=30, direction="pulse")
        assert vz.z_at(2.0, 4.0, o) == pytest.approx(1.3, abs=1e-6)
        assert vz.z_at(4.0, 4.0, o) == pytest.approx(1.0, abs=1e-6)

    def test_matches_tutorial_measurement(self):
        # La demo del tutorial: +40% en ~4s con curva 62 smooth.
        o = vz.ZoomOptions(pct=40, curve=62)
        measured = [(0.2, 1.002), (1.0, 1.041), (2.0, 1.228), (3.0, 1.375), (4.0, 1.401)]
        for t, m in measured:
            assert abs(vz.z_at(t, 4.0, o) - m) < 0.08, (t, vz.z_at(t, 4.0, o), m)


class TestFilter:
    def test_filter_chain(self):
        vf = vz.build_zoom_filter(1080, 1920, 55.5, vz.ZoomOptions())
        # fps= primero: normaliza VFR -> CFR para que los timestamps del
        # zoompan cuadren con la duración real del input
        assert vf.startswith("fps=30,scale=2160:3840:flags=lanczos,zoompan=")
        assert "zoompan=z='" in vf and "d=1:fps=30:s=2160x3840" in vf
        assert vf.endswith("scale=1080:1920:flags=lanczos,setsar=1,format=yuv420p")
        assert "(iw-iw/zoom)*0.500000" in vf  # ancla centrada

    def test_anchor_off_center(self):
        vf = vz.build_zoom_filter(1080, 1920, 10, vz.ZoomOptions(anchor=(0.5, 0.33)))
        assert "(ih-ih/zoom)*0.330000" in vf

    def test_curve_zero_linear_expr(self):
        vf = vz.build_zoom_filter(320, 568, 2, vz.ZoomOptions(curve=0))
        assert "pow" not in vf

    def test_shrink_chain_has_pad(self):
        vf = vz.build_zoom_filter(320, 568, 2, vz.ZoomOptions(pct=20, direction="shrink"))
        assert "pad=" in vf
        assert "color=black" in vf
        assert "zoompan=" in vf

    def test_pulse_chain_has_both_phases(self):
        vf = vz.build_zoom_filter(320, 568, 4, vz.ZoomOptions(pct=30, direction="pulse", hold=0.2))
        # rampa de subida (in) y rampa reversa (out) sin resta entre bloques
        assert "time-0.000000)/1.600000" in vf
        assert "2.400000+1.600000+time*(-1.000000)" in vf
        assert "*(" in vf  # pulso = E_in * E_rev

    def test_segment_duration(self):
        probe = {"duration_s": 10.0}
        assert vz._segment_duration(probe, vz.ZoomOptions()) == 10.0
        assert vz._segment_duration(probe, vz.ZoomOptions(start=2, end=5)) == 3.0
        assert vz._segment_duration(probe, vz.ZoomOptions(start=9.99)) == pytest.approx(0.01)


class TestPlan:
    def test_plan_contract(self, tmp_path):
        plan = vz.build_plan(make_video(tmp_path), vz.ZoomOptions())
        assert "VOXERA PLAN (video zoom)" in plan
        assert "ampliar +40.0%" in plan
        assert "curva=62" in plan
        assert "easing=smooth" in plan
        assert "zoompan=" in plan

    def test_plan_pulse_label(self, tmp_path):
        plan = vz.build_plan(make_video(tmp_path), vz.ZoomOptions(pct=30, direction="pulse", hold=0.2))
        assert "pulso +30.0% (hold 20%)" in plan

    def test_plan_bad_opts_raises(self, tmp_path):
        with pytest.raises(EnhancementError):
            vz.build_plan(make_video(tmp_path), vz.ZoomOptions(pct=-1))


class TestEndToEnd:
    def test_zoom_e2e(self, tmp_path):
        inp = make_video(tmp_path)
        out = tmp_path / "zoomed.mp4"
        opts = vz.ZoomOptions(pct=15, anchor=(0.5, 0.4), curve=62)
        result = vz.zoom_video(inp, out, opts)
        assert result == out
        probe = __import__("voxera.video_enhance", fromlist=["probe_video"]).probe_video(out)
        assert probe["width"] == 320
        assert probe["height"] == 568
        assert probe["has_audio"] is True
        assert abs(probe["duration_s"] - 2.0) < 0.25

    def test_auto_emphasis_e2e(self, tmp_path):
        # audio con dos ráfagas claras -> dos pulsos en t≈0.8 y t≈1.6
        import soundfile as sf
        import numpy as np

        wav = tmp_path / "bursts.wav"
        sr = 16000
        x = np.zeros(sr * 3, dtype="float32")
        for t0 in (0.7, 1.5):
            i0 = int(t0 * sr)
            x[i0 : i0 + sr // 2] = 0.9 * np.sin(
                2 * np.pi * 220 * np.arange(sr // 2) / sr
            )
        sf.write(str(wav), x, sr)
        inp = tmp_path / "in.mp4"
        subprocess.run(
            [FFMPEG, "-y", "-v", "error", "-f", "lavfi",
             "-i", "testsrc=duration=3:size=320x568:rate=30",
             "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "96k", "-shortest", str(inp)],
            check=True, capture_output=True,
        )
        opts = vz.ZoomOptions(auto_emphasis=True, max_pulses=2)
        out = tmp_path / "emph.mp4"
        vz.zoom_video(inp, out, opts)
        probe = __import__("voxera.video_enhance", fromlist=["probe_video"]).probe_video(out)
        assert abs(probe["duration_s"] - 3.0) < 0.25
        assert probe["has_audio"] is True

    def test_find_emphasis_moments(self, tmp_path):
        import soundfile as sf
        import numpy as np

        wav = tmp_path / "bursts.wav"
        sr = 16000
        x = np.zeros(sr * 4, dtype="float32")
        for t0 in (0.7, 1.6, 2.5):
            i0 = int(t0 * sr)
            x[i0 : i0 + sr // 2] = 0.9 * np.sin(2 * np.pi * 220 * np.arange(sr // 2) / sr)
        sf.write(str(wav), x, sr)
        inp = tmp_path / "in.mp4"
        subprocess.run(
            [FFMPEG, "-y", "-v", "error", "-f", "lavfi",
             "-i", "testsrc=duration=4:size=320x568:rate=30",
             "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "96k", "-shortest", str(inp)],
            check=True, capture_output=True,
        )
        moments = vz.find_emphasis_moments(inp, vz.ZoomOptions(max_pulses=3), min_gap=0.5)
        assert len(moments) == 3
        for t, m in zip((0.7, 1.6, 2.5), moments):
            assert abs(t - m) < 0.3, (t, m)

    def test_multi_pulse_filter(self):
        vf = vz.build_zoom_filter(
            320, 568, 8.0,
            vz.ZoomOptions(pct=30, auto_emphasis=True, pulse_dur=2.0),
            moments=[1.5, 5.0],
        )
        # sin max() ni restas entre bloques (ver _clamp01)
        assert "max(" not in vf
        assert "abs(" in vf  # clamp 0-1
        assert "time-0.500000" in vf  # t0 del primer pulso = 1.5 - in_ (in_=1.0)
        assert ")+(" in vf  # unión por suma (pulsos no solapados)

    def test_shrink_e2e(self, tmp_path):
        inp = make_video(tmp_path)
        out = tmp_path / "shrunk.mp4"
        vz.zoom_video(inp, out, vz.ZoomOptions(pct=20, direction="shrink"))
        probe = __import__("voxera.video_enhance", fromlist=["probe_video"]).probe_video(out)
        assert probe["width"] == 320 and probe["height"] == 568
        assert probe["has_audio"] is True

    def test_pulse_e2e(self, tmp_path):
        inp = make_video(tmp_path, duration=4.0)
        out = tmp_path / "pulse.mp4"
        vz.zoom_video(inp, out, vz.ZoomOptions(pct=30, direction="pulse", hold=0.2))
        probe = __import__("voxera.video_enhance", fromlist=["probe_video"]).probe_video(out)
        assert abs(probe["duration_s"] - 4.0) < 0.25

    def test_zoom_segment(self, tmp_path):
        inp = make_video(tmp_path, duration=3.0)
        out = tmp_path / "seg.mp4"
        vz.zoom_video(inp, out, vz.ZoomOptions(start=0.5, end=2.0))
        probe = __import__("voxera.video_enhance", fromlist=["probe_video"]).probe_video(out)
        assert abs(probe["duration_s"] - 1.5) < 0.3

    def test_missing_input(self, tmp_path):
        with pytest.raises(EnhancementError):
            vz.zoom_video(tmp_path / "nope.mp4", tmp_path / "o.mp4", vz.ZoomOptions())
