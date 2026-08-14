"""Unit + e2e de video stabilize (anti-temblor de mano): OpenCV + ffmpeg.

- Álgebra de similitudes: round-trip descomponer/montar, inversa exacta,
  parametrización por centro (el centro se mueve exactamente (tx, ty)).
- Trayectoria: acumulación (C_t = C_{t-1}·M_t^-1), suavizado gaussiano
  (lo lineal se conserva en el interior, el jitter sinusoidal se mata).
- Correcciones + zoom adaptativo: reducción del temblor visible > 90 %,
  zoom exacto z = min/(min-2e) y capa, crop black sin zoom.
- Estimación: traslación y rotación sintéticas exactas, sin textura -> None.
- e2e sintéticos (ffmpeg): vídeo con temblor conocido -> el temblor medido
  con phase correlation cae >= 50 %; vídeo estático -> copia directa
  bit-exacta; audio y duración preservados; plan --dry-run; CLI wiring.
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from voxera import video_stabilize as vs
from voxera.errors import EnhancementError

FFMPEG = shutil.which("ffmpeg") or (
    Path("C:/ffmpeg/bin/ffmpeg.exe").exists() and "C:/ffmpeg/bin/ffmpeg.exe"
)
pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg required")

W, H, FPS, DUR = 240, 320, 30, 3.0


# ---------------------------------------------------------------- helpers

def make_scene(seed: int = 0) -> np.ndarray:
    """Escena estática con textura rica (blobs aleatorios) para el tracking."""
    rng = np.random.default_rng(seed)
    bg = np.full((H, W, 3), 90, dtype=np.uint8)
    img = bg.copy()
    for _ in range(60):
        x, y = rng.integers(0, W - 20), rng.integers(0, H - 20)
        w, h = rng.integers(8, 40), rng.integers(8, 40)
        color = rng.integers(40, 255, size=3)
        img[y : y + h, x : x + w] = color
    return img


def shake_trajectory(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Temblor determinista (sinusoides lentas + rápidas), amplitudes ~16/12 px."""
    import cv2

    t = np.arange(n)
    sx = 12 * np.sin(2 * np.pi * t / 60) + 4 * np.sin(2 * np.pi * t / 9 + 0.7)
    sy = 9 * np.sin(2 * np.pi * t / 47 + 2) + 3 * np.sin(2 * np.pi * t / 11)
    return sx, sy


def make_video(tmp_path, name="in.mp4", shake=True, seed=0, with_audio=True):
    """Sintético: escena estática + temblor de cámara conocido (o estático)."""
    import cv2

    scene = make_scene(seed)
    total = int(round(DUR * FPS))
    sx, sy = shake_trajectory(total) if shake else (np.zeros(total), np.zeros(total))
    frames = []
    for i in range(total):
        M = np.array([[1.0, 0.0, sx[i]], [0.0, 1.0, sy[i]]])
        frames.append(
            cv2.warpAffine(scene, M, (W, H),
                           flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        )
    raw = b"".join(f.tobytes() for f in frames)
    out = tmp_path / name
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=3"]
    cmd += ["-shortest"] if with_audio else ["-t", "3"]
    cmd += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "96k"]
    cmd.append(str(out))
    subprocess.run(cmd, input=raw, check=True, capture_output=True)
    return out, total


def decode_frames(video, scale=0.5, crop_frac=0.75):
    """Decodifica gris a media resolución, recortado al centro (75%).

    El recorte central evita que los bordes (negros con --crop black, o
    replicados con el zoom) confundan la phase correlation: el contenido
    visible nunca se sale de la zona central (margen > temblor máx).
    """
    import cv2

    proc = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(video), "-an",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    )
    n = len(proc.stdout) // (W * H * 3)
    arr = np.frombuffer(proc.stdout, dtype=np.uint8).reshape(n, H, W, 3)
    gray = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in arr]
    if scale < 1.0:
        small = (int(W * scale), int(H * scale))
        gray = [cv2.resize(g, small, interpolation=cv2.INTER_AREA) for g in gray]
    if crop_frac < 1.0:
        hh, ww = gray[0].shape
        y0, y1 = int(hh * (1 - crop_frac) / 2), int(hh * (1 + crop_frac) / 2)
        x0, x1 = int(ww * (1 - crop_frac) / 2), int(ww * (1 + crop_frac) / 2)
        gray = [g[y0:y1, x0:x1] for g in gray]
    return gray


def measure_shake_px(frames) -> float:
    """Mediana del desplazamiento global entre frames (phase correlation)."""
    import cv2

    deltas = []
    for a, b in zip(frames[:-1], frames[1:]):
        (dx, dy), _resp = cv2.phaseCorrelate(
            a.astype(np.float32), b.astype(np.float32)
        )
        deltas.append(float(np.hypot(dx, dy)))
    return float(np.median(deltas))


# ---------------------------------------------------------------- álgebra

class TestSimilarityAlgebra:
    def test_decompose_assemble_roundtrip(self):
        rng = np.random.default_rng(0)
        for _ in range(20):
            M = vs.assemble_similarity(
                rng.uniform(-50, 50), rng.uniform(-50, 50),
                rng.uniform(-20, 20), rng.uniform(-20, 20),
                rng.uniform(-30, 30), rng.uniform(0.7, 1.4),
            )
            tx, ty, a, s = vs.decompose_similarity(M)
            th = np.radians(a)
            R = np.array([[s * np.cos(th), -s * np.sin(th)],
                          [s * np.sin(th), s * np.cos(th)]])
            c = np.array([50.0, 40.0])
            t_center = np.array([tx, ty]) + R @ c - c
            M2 = vs.assemble_similarity(50, 40, *t_center, a, s)
            assert np.allclose(M, M2, atol=1e-9)

    def test_center_moves_exactly(self):
        M = vs.assemble_similarity(160, 120, 5, -3, 10, 1.1)
        moved = M @ np.array([160.0, 120.0, 1.0])
        assert np.allclose(moved, [165, 117], atol=1e-9)

    def test_inverse_exact(self):
        rng = np.random.default_rng(1)
        for _ in range(10):
            M = vs.assemble_similarity(160, 120, *rng.uniform(-15, 15, 2),
                                       rng.uniform(-20, 20), rng.uniform(0.8, 1.2))
            Mh = np.vstack([M, [0, 0, 1]])
            inv = np.vstack([vs.inverse_similarity(M), [0, 0, 1]])
            assert np.allclose(Mh @ inv, np.eye(3), atol=1e-9)

    def test_degenerate_raises(self):
        with pytest.raises(EnhancementError):
            vs.inverse_similarity(np.zeros((2, 3)))


class TestPath:
    def test_accumulate_translations(self):
        rels = [vs.assemble_similarity(0, 0, d[0], d[1], 0, 1.0)
                for d in [(2, 0), (3, 1), (-1, 2)]]
        paths = vs.accumulate_path(rels)
        tx, ty, ang, sc = vs.path_params(paths, 160, 120)
        assert np.allclose(tx, [-2, -5, -4], atol=1e-9)
        assert np.allclose(ty, [0, -1, -3], atol=1e-9)
        assert np.allclose(ang, 0, atol=1e-9)
        assert np.allclose(sc, 1, atol=1e-9)

    def test_smooth_preserves_linear_interior(self):
        n = 200
        lin = np.arange(n) * 0.5
        stx, _, _, _ = vs.smooth_params(lin, np.zeros(n), np.zeros(n),
                                        np.ones(n), 15)
        interior = slice(45, -45)
        assert np.max(np.abs(stx[interior] - lin[interior])) < 0.05

    def test_smooth_kills_sine_jitter(self):
        n = 200
        t = np.arange(n)
        lin = t * 0.5
        jitter = 10 * np.sin(2 * np.pi * t / 6)
        stx, _, _, _ = vs.smooth_params(lin + jitter, np.zeros(n), np.zeros(n),
                                        np.ones(n), 15)
        interior = slice(45, -45)
        assert np.std(stx[interior] - lin[interior]) < 0.05

    def test_smoothing_zero_is_identity(self):
        rng = np.random.default_rng(2)
        tx = rng.normal(0, 5, 40)
        stx, _, _, _ = vs.smooth_params(tx, np.zeros(40), np.zeros(40),
                                        np.ones(40), 0)
        assert np.allclose(stx, tx)


class TestCorrectionZoom:
    def _traj(self, n=100):
        t = np.arange(n)
        dx = 10 * np.sin(2 * np.pi * t / 5)
        dy = 6 * np.sin(2 * np.pi * t / 7 + 1)
        return [vs.assemble_similarity(0, 0, dx[i], dy[i],
                                       0.6 * np.sin(2 * np.pi * i / 30), 1.0)
                for i in range(n)]

    def test_residual_much_smaller_than_input(self):
        rels = self._traj()
        paths = vs.accumulate_path(rels)
        tx, ty, a, s = vs.path_params(paths, 160, 120)
        stx, sty, sa, ss = vs.smooth_params(tx, ty, a, s, 15)
        in_m, in_s = vs.shake_stats(rels, 320, 240)
        out_m, out_s = vs.residual_stats(stx, sty, 1.0)
        assert in_m > 1.0
        assert out_s < 0.3 * in_s
        assert out_m < in_m

    def test_rotation_shake_also_reduced(self):
        rels = self._traj()
        paths = vs.accumulate_path(rels)
        tx, ty, a, s = vs.path_params(paths, 160, 120)
        stx, sty, sa, ss = vs.smooth_params(tx, ty, a, s, 15)
        in_m, in_s = vs.shake_stats(rels, 320, 240)
        out_m, out_s = vs.residual_stats(stx, sty, 1.2)
        assert out_s < 0.3 * in_s

    def test_compute_zoom_exact(self):
        I = np.eye(2, 3)
        T6 = vs.assemble_similarity(0, 0, 6, 0, 0, 1.0)
        warps = [I] * 3 + [T6] + [I] * 3
        z = vs.compute_zoom(warps, 320, 240, 2.0)
        assert abs(z - 240 / (240 - 12)) < 1e-9

    def test_compute_zoom_cap_and_zero(self):
        I = np.eye(2, 3)
        T6 = vs.assemble_similarity(0, 0, 6, 0, 0, 1.0)
        warps = [I] * 3 + [T6] + [I] * 3
        assert vs.compute_zoom(warps, 320, 240, 1.03) == pytest.approx(1.03)
        assert vs.compute_zoom([I] * 5, 320, 240, 2.0) == 1.0

    def test_crop_black_no_zoom(self):
        rels = self._traj()
        paths = vs.accumulate_path(rels)
        tx, ty, a, s = vs.path_params(paths, 160, 120)
        stx, sty, sa, ss = vs.smooth_params(tx, ty, a, s, 15)
        _, zoom = vs.correction_transforms(paths, stx, sty, sa, ss,
                                           320, 240, "black", 1.2)
        assert zoom == 1.0
        _, zoom_k = vs.correction_transforms(paths, stx, sty, sa, ss,
                                             320, 240, "keep", 1.2)
        assert zoom_k > 1.0

    def test_full_metrics_reduction(self):
        tr = vs.Trajectory()
        tr.rel = self._traj()
        info = {"w": 320, "h": 240, "fps": 30, "est_scale": 1.0,
                "max_shift": 16.0, "frames": len(tr.rel)}
        _, m = vs.stabilize_paths(tr, info, vs.StabilizeOptions(smoothing=15))
        assert m["reduction_pct"] > 90
        assert m["in_median"] > 1.0
        assert 1.0 <= m["zoom"] <= 1.2

    def test_warps_actually_cancel_shake(self):
        """Pixel-level: la posición del contenido en la salida sigue el marco
        suavizado, NO el temblor (regresión del bug D·C^-1 que lo duplicaba)."""
        n = 60
        t = np.arange(n)
        dx = 8 * np.sin(2 * np.pi * t / 10)
        dy = 5 * np.sin(2 * np.pi * t / 13)
        rels = [vs.assemble_similarity(0, 0, dx[i], dy[i], 0, 1.0)
                for i in range(n)]
        paths = vs.accumulate_path(rels)
        tx, ty, a, s = vs.path_params(paths, 160, 120)
        stx, sty, sa, ss = vs.smooth_params(tx, ty, a, s, 12)
        warps, _zoom = vs.correction_transforms(paths, stx, sty, sa, ss,
                                                320, 240, "keep", 1.2)
        p = np.array([160.0, 120.0, 1.0])
        scx, scy = np.cumsum(dx), np.cumsum(dy)  # posición del contenido en cada frame
        out_pos = np.array([
            (np.asarray(W) @ (p + np.array([scx[i], scy[i], 0.0])))[:2]
            for i, W in enumerate(warps)
        ])
        moves = np.hypot(np.diff(out_pos[:, 0]), np.diff(out_pos[:, 1]))
        # entrada: mediana del paso ≈ 2-4 px; salida: sigue al marco suavizado
        assert np.median(moves) < 0.5, f"el contenido aún tiembla: {np.median(moves):.2f} px"


class TestStats:
    def test_shake_stats_translation(self):
        rels = [vs.assemble_similarity(0, 0, 2, 0, 0, 1.0)] * 5
        med, std = vs.shake_stats(rels, 320, 240)
        assert med == pytest.approx(2.0)
        assert std == pytest.approx(0.0)

    def test_residual_stats_constant(self):
        n = 50
        stx = np.ones(n) * 3.0
        med, std = vs.residual_stats(stx, np.zeros(n), 1.0)
        assert med == pytest.approx(0.0)
        assert std == pytest.approx(0.0)

    def test_residual_stats_scales_with_zoom(self):
        n = 50
        stx = np.arange(n, dtype=float)
        m1, _ = vs.residual_stats(stx, np.zeros(n), 1.0)
        m2, _ = vs.residual_stats(stx, np.zeros(n), 2.0)
        assert m2 == pytest.approx(2 * m1)


class TestOptions:
    def test_defaults_valid(self):
        vs.StabilizeOptions().validate()

    @pytest.mark.parametrize("kwargs", [
        dict(smoothing=-1), dict(smoothing=121),
        dict(max_shift=0), dict(max_shift=1001),
        dict(max_angle=46), dict(max_angle=-1),
        dict(crop="x"), dict(max_zoom=0.5), dict(max_zoom=2.5),
        dict(crf=0), dict(crf=52),
    ])
    def test_invalid_raises(self, kwargs):
        with pytest.raises(EnhancementError):
            vs.StabilizeOptions(**kwargs).validate()

    def test_max_shift_none_ok(self):
        vs.StabilizeOptions(max_shift=None).validate()


class TestEstimateMotion:
    def test_translation(self):
        rng = np.random.default_rng(0)
        img = (rng.random((240, 320)) * 255).astype(np.uint8)
        img2 = np.zeros_like(img)
        img2[3:, 5:] = img[:-3, :-5]  # desplazada (+5, +3)
        M, pts = vs.estimate_motion(img, img2, None)
        tx, ty, a, _ = vs.decompose_similarity(M)
        assert abs(tx - 5) < 0.5 and abs(ty - 3) < 0.5 and abs(a) < 0.1
        assert pts is not None and len(pts) >= 2

    def test_rotation(self):
        import cv2

        rng = np.random.default_rng(1)
        img = (rng.random((240, 320)) * 255).astype(np.uint8)
        ang = np.radians(2.0)
        M = np.array([[np.cos(ang), -np.sin(ang), 0],
                      [np.sin(ang), np.cos(ang), 0]])
        img2 = cv2.warpAffine(img, M, (320, 240))
        Mh, _ = vs.estimate_motion(img, img2, None)
        _, _, a, _ = vs.decompose_similarity(Mh)
        assert abs(a - 2.0) < 0.1

    def test_uniform_frames_none(self):
        u = np.full((240, 320), 128, np.uint8)
        M, _ = vs.estimate_motion(u, u, None)
        assert M is None

    def test_reuses_previous_points(self):
        rng = np.random.default_rng(2)
        img = (rng.random((240, 320)) * 255).astype(np.uint8)
        img2 = np.zeros_like(img)
        img2[2:, 4:] = img[:-2, :-4]
        M1, pts = vs.estimate_motion(img, img2, None)
        M2, pts2 = vs.estimate_motion(img2, img, pts)  # ahora a la inversa
        tx2, ty2, _, _ = vs.decompose_similarity(M2)
        assert abs(tx2 + 4) < 0.5 and abs(ty2 + 2) < 0.5


# ---------------------------------------------------------------- e2e

class TestStabilizeE2E:
    def test_reduces_shake_measured_independently(self, tmp_path):
        """El temblor medido con phase correlation (ajeno al módulo) cae >= 50 %."""
        import cv2

        inp, _ = make_video(tmp_path)
        out = tmp_path / "out.mp4"
        vs.stabilize_video(inp, out, vs.StabilizeOptions(smoothing=15))
        in_shake = measure_shake_px(decode_frames(inp))
        out_shake = measure_shake_px(decode_frames(out))
        assert in_shake > 1.0, f"el sintético debería temblar, got {in_shake:.2f}"
        assert out_shake < 0.5 * in_shake, f"{out_shake:.2f} vs {in_shake:.2f}"
        assert out_shake < 0.8

    def test_duration_fps_frames_audio_preserved(self, tmp_path):
        inp, total = make_video(tmp_path)
        out = tmp_path / "out.mp4"
        vs.stabilize_video(inp, out, vs.StabilizeOptions())
        probe = __import__("voxera.video_enhance", fromlist=["probe_video"]).probe_video
        pin, pout = probe(inp), probe(out)
        assert abs(pout["duration_s"] - pin["duration_s"]) < 0.15
        assert abs(pout["fps"] - pin["fps"]) < 0.5
        assert pout["has_audio"] == pin["has_audio"] and pout["has_audio"]
        frames = len(decode_frames(out))
        assert abs(frames - total) <= 1

    def test_static_copies_directly(self, tmp_path):
        inp, _ = make_video(tmp_path, name="static.mp4", shake=False)
        out = tmp_path / "static-out.mp4"
        vs.stabilize_video(inp, out, vs.StabilizeOptions())
        assert inp.read_bytes() == out.read_bytes()

    def test_crop_black_works(self, tmp_path):
        inp, _ = make_video(tmp_path, name="black.mp4")
        out = tmp_path / "black-out.mp4"
        vs.stabilize_video(inp, out, vs.StabilizeOptions(crop="black"))
        assert out.exists()
        in_shake = measure_shake_px(decode_frames(inp))
        out_shake = measure_shake_px(decode_frames(out))
        assert out_shake < 0.7 * in_shake

    def test_without_audio(self, tmp_path):
        inp, _ = make_video(tmp_path, name="noaudio.mp4", with_audio=False)
        out = tmp_path / "noaudio-out.mp4"
        vs.stabilize_video(inp, out, vs.StabilizeOptions())
        probe = __import__("voxera.video_enhance", fromlist=["probe_video"]).probe_video
        assert not probe(out)["has_audio"]

    def test_plan(self, tmp_path):
        inp, _ = make_video(tmp_path, name="plan.mp4")
        plan = vs.build_plan(inp, vs.StabilizeOptions(smoothing=15))
        assert "VOXERA PLAN (video stabilize)" in plan
        assert "temblor" in plan
        assert "zoom" in plan

    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(EnhancementError):
            vs.stabilize_video(tmp_path / "nope.mp4", tmp_path / "o.mp4",
                               vs.StabilizeOptions())

    def test_cli_wiring(self):
        from voxera.cli import build_parser

        args = build_parser().parse_args(
            ["video", "stabilize", "in.mp4", "-o", "out.mp4",
             "--smoothing", "10", "--crop", "black", "--max-zoom", "1.1"])
        assert args.video_command == "stabilize"
        assert args.smoothing == 10.0
        assert args.crop == "black"
        assert args.max_zoom == 1.1
        assert args.max_shift is None

    @pytest.mark.skipif(
        not Path("media/demo-video.mp4").exists(), reason="demo no presente")
    def test_real_demo_runs(self, tmp_path):
        """E2E real: media/demo-video.mp4 (render Remotion, cámara fija)."""
        inp = Path("media/demo-video.mp4")
        out = tmp_path / "demo-out.mp4"
        vs.stabilize_video(inp, out, vs.StabilizeOptions(smoothing=15))
        probe = __import__("voxera.video_enhance", fromlist=["probe_video"]).probe_video
        pin, pout = probe(inp), probe(out)
        assert abs(pout["duration_s"] - pin["duration_s"]) < 0.15
        assert pout["has_audio"] == pin["has_audio"]
