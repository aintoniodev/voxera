"""Unit tests de video cutsilence: edición automática de silencios (jump-cuts).

- Detección: tramos conservados (voz + gaps recortados a --keep).
- Cuantización a la rejilla de frames (sync A/V) y fusión de tramos.
- Filtros select/aselect: misma expresión en audio y vídeo, extremo superior
  exclusivo (sin frame extra por corte).
- Un e2e: testsrc + voz con silencios largos -> cortes -> duración esperada,
  conteo de frames exacto y sync A/V (< 0.1 s).
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import tests.synth as s
from voxera import video as video_mod
from voxera import video_enhance as ve
from voxera import video_silence as vs
from voxera.cli import main
from voxera.errors import EnhancementError

FFMPEG = shutil.which("ffmpeg") or (
    Path("C:/ffmpeg/bin/ffmpeg.exe").exists() and "C:/ffmpeg/bin/ffmpeg.exe"
)
pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg required")

SR = 48000
FPS = 30


def make_video(tmp_path, name="in.mp4", size="320x568", rate=FPS, audio=None):
    """testsrc + audio dado (mismo patrón que test_video_zoom.py).

    Fixture por defecto: s.long_gaps() = voz 1s + gap 2s + voz 1s +
    gap 1.2s + voz 1s (~5.2 s) — el caso de uso "jump-cuts".
    """
    if audio is None:
        audio = s.long_gaps()
    duration = len(audio) / SR
    wav = tmp_path / "audio.wav"
    sf.write(str(wav), audio, SR)
    out = tmp_path / name
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "lavfi",
         "-i", f"testsrc=duration={duration:.3f}:size={size}:rate={rate}",
         "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "96k", "-shortest", str(out)],
        check=True, capture_output=True,
    )
    return out


def audio_duration(path: Path) -> float:
    proc = subprocess.run(
        [video_mod._tool("ffprobe"), "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    return float(proc.stdout.strip() or 0.0)


def video_frames(path: Path) -> int:
    proc = subprocess.run(
        [video_mod._tool("ffprobe"), "-v", "error", "-select_streams", "v:0",
         "-count_frames", "-show_entries", "stream=nb_read_frames",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    return int(proc.stdout.strip())


class TestParts:
    """Detección de tramos a conservar sobre s.long_gaps() (6.2 s totales).

    Geometría esperada (margen de respiración 0.2 s del VAD):
      voz1 [0, ~1.2] · gap1 [1.2, 2.8] = 1.6 s · voz2 [2.8, 4.2] ·
      gap2 [4.2, 5.0] = 0.8 s · voz3 [5.0, 6.2]
    """

    def test_light_trims_only_long_gap(self):
        parts = vs.detect_keep_parts(s.long_gaps(), "light", 0.15)  # trigger 1.5
        assert len(parts) == 2
        a0, b0 = parts[0]
        assert a0 == pytest.approx(0.0, abs=0.05)
        assert b0 == pytest.approx(1.35, abs=0.1)  # voz1 + margen + keep
        a1, b1 = parts[1]
        assert a1 == pytest.approx(2.8, abs=0.1)  # margen antes de voz2
        assert b1 == pytest.approx(6.2, abs=0.1)  # hasta el final

    def test_aggressive_trims_both_gaps(self):
        parts = vs.detect_keep_parts(s.long_gaps(), "aggressive", 0.15)  # trigger 0.4
        assert len(parts) == 3
        assert parts[0][1] == pytest.approx(1.35, abs=0.1)
        assert parts[1][0] == pytest.approx(2.8, abs=0.1)
        assert parts[1][1] == pytest.approx(4.35, abs=0.1)  # voz2 + margen + keep
        assert parts[2][1] == pytest.approx(6.2, abs=0.1)

    def test_keep_zero_cuts_gap_entirely(self):
        parts = vs.detect_keep_parts(s.long_gaps(), "aggressive", 0.0)
        assert len(parts) == 3
        assert parts[0][1] == pytest.approx(1.2, abs=0.1)  # sin padding
        assert parts[1][1] == pytest.approx(4.2, abs=0.1)
        total = sum(b - a for a, b in parts)
        # voz1 (1.0 + márgenes) + voz2 (1.4) + voz3 (1.2)
        assert total == pytest.approx(3.8, abs=0.3)

    def test_medium_structure(self):
        parts = vs.detect_keep_parts(s.long_gaps(), "medium", 0.15)
        # gap1 (1.6 s) seguro > trigger; gap2 (0.8 s) justo en el borde -> no
        # fijamos la forma exacta, solo que corta y conserva voz entera
        total = sum(b - a for a, b in parts)
        assert total < 4.9
        assert parts[0][0] == pytest.approx(0.0, abs=0.05)

    def test_no_silence_keeps_everything(self):
        parts = vs.detect_keep_parts(s.speech_like(2.0, gap_frac=0.0), "aggressive", 0.0)
        total = sum(b - a for a, b in parts)
        assert total == pytest.approx(2.0, abs=0.2)


class TestQuantize:
    def test_snaps_to_frame_grid(self):
        out = vs.quantize_frames([(0.123, 2.345)], 30.0)
        assert out == [(round(0.123 * 30) / 30, round(2.345 * 30) / 30)]
        qa, qb = out[0]
        assert qa == pytest.approx(4 / 30)
        assert qb == pytest.approx(70 / 30)

    def test_merges_adjacent_after_snap(self):
        assert vs.quantize_frames([(0.5, 1.0), (1.0, 1.5)], 30.0) == [(0.5, 1.5)]

    def test_drops_subframe(self):
        # un tramo de 10 ms cuantizado a 30 fps colapsa a 0 frames
        assert vs.quantize_frames([(0.0, 0.01)], 30.0) == []
        # en cambio 10 ms pueden subir a 1 frame completo (redondeo)
        assert vs.quantize_frames([(0.01, 0.02)], 30.0) == [(0.0, 1 / 30)]

    def test_bad_fps(self):
        with pytest.raises(EnhancementError):
            vs.quantize_frames([(0.0, 1.0)], 0.0)


class TestFilters:
    def test_single_part_exclusive_end(self):
        vf, af = vs.build_cut_filters([(1.0, 2.0)], 30.0)
        assert "gte(t,1.000000)*lt(t,2.000000)" in vf
        assert "select='" in vf
        assert "setpts=N/30.000000/TB" in vf
        assert "aresample=48000" in af
        assert "aselect='gte(t,1.000000)*lt(t,2.000000)'" in af
        assert "asetpts=N/48000/TB" in af

    def test_multipart_sum(self):
        vf, af = vs.build_cut_filters([(1.0, 2.0), (3.0, 4.0)], 30.0)
        expr = "gte(t,1.000000)*lt(t,2.000000)+gte(t,3.000000)*lt(t,4.000000)"
        assert expr in vf
        assert expr in af  # la MISMA expresión en audio y vídeo

    def test_no_parts_raises(self):
        with pytest.raises(EnhancementError):
            vs.build_cut_filters([], 30.0)


class TestOptions:
    def test_bad_level(self):
        with pytest.raises(EnhancementError):
            vs.CutSilenceOptions(level="max").validate()

    def test_keep_negative(self):
        with pytest.raises(EnhancementError):
            vs.CutSilenceOptions(keep=-0.1).validate()

    def test_keep_too_large(self):
        with pytest.raises(EnhancementError):
            vs.CutSilenceOptions(keep=5.0).validate()

    def test_bad_crf(self):
        with pytest.raises(EnhancementError):
            vs.CutSilenceOptions(crf=0).validate()

    def test_defaults(self):
        opts = vs.CutSilenceOptions()
        assert opts.level == "medium"
        assert opts.keep == pytest.approx(0.15)
        opts.validate()  # no raise


class TestPlan:
    def test_dry_run_reports_cuts(self, tmp_path):
        inp = make_video(tmp_path)
        plan = vs.build_plan(inp, vs.CutSilenceOptions(level="light"))
        assert "VOXERA PLAN (video cutsilence)" in plan
        assert "tramos" in plan
        assert "→" in plan
        assert "filtro" in plan

    def test_dry_run_no_audio_raises(self, tmp_path):
        no_audio = tmp_path / "mute.mp4"
        subprocess.run(
            [FFMPEG, "-y", "-v", "error", "-f", "lavfi",
             "-i", "testsrc=duration=2:size=160x284:rate=30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(no_audio)],
            check=True, capture_output=True,
        )
        with pytest.raises(EnhancementError):
            vs.build_plan(no_audio, vs.CutSilenceOptions())


class TestNoSpeech:
    def test_silent_audio_raises(self, tmp_path):
        inp = make_video(tmp_path, audio=s.silence(3.0))
        with pytest.raises(EnhancementError):
            vs.cutsilence_video(inp, tmp_path / "out.mp4", vs.CutSilenceOptions())


class TestE2E:
    def test_removes_silence_frame_exact(self, tmp_path):
        inp = make_video(tmp_path)
        opts = vs.CutSilenceOptions(level="light")  # determinista: solo gap1
        out = vs.cutsilence_video(inp, tmp_path / "out.mp4", opts)
        assert out.exists()

        x = s.long_gaps()
        parts = vs.detect_keep_parts(x, "light", opts.keep)
        quant = vs.quantize_frames(parts, FPS)
        expected = sum(b - a for a, b in quant)

        oprobe = ve.probe_video(out)
        assert abs(oprobe["duration_s"] - expected) < 0.3
        assert oprobe["duration_s"] < 5.0  # cortó ~1.6 s de los 6.2 s
        assert abs(oprobe["fps"] - FPS) < 0.5
        # cortes frame-accurate: el número de frames es exactamente el esperado
        assert abs(video_frames(out) - round(expected * FPS)) <= 1
        # sync A/V: stream de audio y vídeo duran lo mismo
        assert abs(audio_duration(out) - oprobe["duration_s"]) < 0.1

    def test_keep_zero_full_cut(self, tmp_path):
        inp = make_video(tmp_path)
        opts = vs.CutSilenceOptions(level="aggressive", keep=0.0)
        out = vs.cutsilence_video(inp, tmp_path / "out.mp4", opts)
        expected = sum(
            b - a
            for a, b in vs.quantize_frames(
                vs.detect_keep_parts(s.long_gaps(), "aggressive", 0.0), FPS
            )
        )
        oprobe = ve.probe_video(out)
        assert abs(oprobe["duration_s"] - expected) < 0.3
        assert oprobe["duration_s"] < 4.2

    def test_silence_below_trigger_passthrough(self, tmp_path):
        # sin gaps > trigger: copia directa (misma duración)
        inp = make_video(tmp_path, audio=s.speech_like(3.0, gap_frac=0.0))
        out = vs.cutsilence_video(inp, tmp_path / "out.mp4", vs.CutSilenceOptions(level="light"))
        oprobe = ve.probe_video(out)
        assert abs(oprobe["duration_s"] - 3.0) < 0.3


class TestCli:
    def test_dry_run_exits_0(self, tmp_path, capsys):
        inp = make_video(tmp_path)
        rc = main(["video", "cutsilence", str(inp), "-o",
                   str(tmp_path / "out.mp4"), "--dry-run"])
        assert rc == 0
        assert "VOXERA PLAN" in capsys.readouterr().out

    def test_full_run_exits_0(self, tmp_path, capsys):
        inp = make_video(tmp_path)
        out = tmp_path / "out.mp4"
        rc = main(["video", "cutsilence", str(inp), "-o", str(out), "--level", "light"])
        assert rc == 0
        assert "✓" in capsys.readouterr().out
        assert out.exists()

    def test_missing_output_exits_2(self, tmp_path):
        inp = make_video(tmp_path)
        import sys as _sys

        with pytest.raises(SystemExit) as exc:
            main(["video", "cutsilence", str(inp)])
        assert exc.value.code == 2
