"""Unit tests de video magnify (lente de aumento móvil): ffmpeg + numpy.

- Opciones: validación de rangos y defaults (incluye motion/grid/hold).
- Geometría: ventana par >= disco, crop par, zoom efectivo.
- Máscaras PNG (gris): disco con pluma (centro 255 -> borde 0) y aro.
- Plan de movimiento: static/scan/voice/auto, timing y clamps.
- Filtro: pipeline TODO YUV (sin rgba) con maskedmerge, crop animado.
- E2E numérico: senoide (periodo interior = 8*zoom_eff, fuera = 8),
  calidad (amplitud conservada), movimiento scan (la lente llega a las
  celdas), movimiento voice (disparado por picos de energía), timing con
  --start (el offset de 't' tras -ss), aro, sin-aro, segmento.
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from voxera import video_magnify as vm
from voxera.errors import EnhancementError

FFMPEG = shutil.which("ffmpeg") or (
    Path("C:/ffmpeg/bin/ffmpeg.exe").exists() and "C:/ffmpeg/bin/ffmpeg.exe"
)
pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg required")

SR = 16000
W, H = 320, 568


def make_video(tmp_path, name="in.mp4", duration=1.0, period=8.0,
               size=f"{W}x{H}", rate=30, sine=True, audio="speech"):
    """Vídeo sintético: senoide vertical de periodo conocido + audio.

    - sine=True: 128+100·sin (invariante ante lanczos; FFT exacto).
    - audio="speech": voz sintética (tests.synth); "bursts": dos ráfagas
      de tono separadas (para motion=voice); None: sin audio.
    """
    import soundfile as sf
    import tests.synth as s

    w, h = (int(v) for v in size.split("x"))
    n = int(round(w / period))
    x = np.arange(w)
    if sine:
        row = np.clip(128 + 100 * np.sin(2 * np.pi * x * n / w), 0, 255)
    else:
        row = np.where(((x * n / w) % 1.0) < 0.5, 235, 16)
    row = row.astype(np.uint8)
    frame = np.tile(row[None, :, None], (h, 1, 3))
    wav = tmp_path / "audio.wav"
    if audio == "bursts":
        t = np.arange(int(duration * SR)) / SR
        sig = np.zeros_like(t)
        burst = 0.6 * np.sin(2 * np.pi * 440 * t)
        sig[(t >= 0.5) & (t < 0.9)] = burst[(t >= 0.5) & (t < 0.9)]
        sig[(t >= 1.6) & (t < 2.0)] = burst[(t >= 1.6) & (t < 2.0)]
        sf.write(str(wav), sig.astype(np.float32), SR)
    elif audio == "speech":
        sf.write(str(wav), s.speech_like(duration), SR)
    raw = tmp_path / "in.yuv"
    n_frames = int(round(duration * rate))
    raw.write_bytes(frame.tobytes() * n_frames)
    out = tmp_path / name
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", size, "-r", str(rate), "-i", str(raw)]
    if audio:
        cmd += ["-i", str(wav), "-c:a", "aac", "-b:a", "96k"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest" if audio else "-an",
            str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def decode_frame(path, idx=0):
    """Decodifica un frame del vídeo a RGB (numpy HxWx3 uint8)."""
    proc = subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-i", str(path), "-vf",
         f"select=eq(n\\,{idx})", "-vframes", "1", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
    )
    return np.frombuffer(proc.stdout, np.uint8).reshape(H, W, 3)


def decode_png_gray(path):
    """Decodifica un PNG gris a numpy HxW (vía ffmpeg, sin cv2)."""
    proc = subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-i", str(path), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True, capture_output=True,
    )
    side = int(round((len(proc.stdout)) ** 0.5))
    return np.frombuffer(proc.stdout, np.uint8).reshape(side, side)


def dominant_period(img, x0, x1, y0, y1):
    """Periodo horizontal dominante (px) de una región, por FFT de fila media."""
    region = img[y0:y1, x0:x1].mean(axis=2).astype(np.float32)
    row = region[region.shape[0] // 2]
    row = row - row.mean()
    spec = np.abs(np.fft.rfft(row))
    freqs = np.fft.rfftfreq(len(row))
    spec[0] = 0
    k = int(np.argmax(spec))
    if spec[k] <= 0:
        return float("inf")
    return 1.0 / freqs[k] if freqs[k] > 0 else float("inf")


def sine_amplitude(img, x0, x1, y0, y1):
    """Amplitud del pico FFT (px de luma) en una región."""
    region = img[y0:y1, x0:x1].mean(axis=2).astype(np.float32)
    row = region[region.shape[0] // 2]
    row = row - row.mean()
    spec = np.abs(np.fft.rfft(row))
    return 2.0 * float(spec.max()) / len(row)


def expected_ring_center(cx, cy, win, w, h):
    """Centro real del aro: el centro pedido se redondea a la rejilla par de
    la ventana (clamp + 2*floor) igual que el motor."""
    wx = min(max(2 * int((cx - win / 2) // 2), 0), w - win)
    wy = min(max(2 * int((cy - win / 2) // 2), 0), h - win)
    return (wx + win / 2, wy + win / 2)


def find_lens_center(rend, gx, gy, r, search=14):
    """Centro de la lente por score de anillo: de los candidatos en una
    ventana, el que maximiza la fracción de píxeles blancos (>252) sobre el
    círculo de radio r. Robusto al overshoot del unsharp dentro de la lente
    (el aro es la ÚNICA estructura blanca sobre el círculo exacto)."""
    gray = rend[:, :, 0]
    gx, gy = int(gx), int(gy)
    th = np.linspace(0, 2 * np.pi, 128, endpoint=False)
    radii = [r - 2, r, r + 2]
    best = (None, -1.0)
    for cx in range(max(0, gx - search), gx + search + 1, 2):
        for cy in range(max(0, gy - search), gy + search + 1, 2):
            score = 0.0
            n = 0
            for rr in radii:
                xs = np.round(cx + rr * np.cos(th)).astype(int)
                ys = np.round(cy + rr * np.sin(th)).astype(int)
                ok = (xs >= 0) & (xs < gray.shape[1]) & (ys >= 0) & (ys < gray.shape[0])
                if ok.any():
                    score += np.count_nonzero(gray[ys[ok], xs[ok]] > 252)
                    n += int(ok.sum())
            score = score / max(n, 1)
            if score > best[1]:
                best = ((cx, cy), score)
    # refinamiento fino (paso 1 px) alrededor del mejor candidato
    bx, by = best[0]
    best2 = best
    for cx in range(bx - 3, bx + 4):
        for cy in range(by - 3, by + 4):
            if (cx, cy) == (bx, by):
                continue
            score = 0.0
            n = 0
            for rr in radii:
                xs = np.round(cx + rr * np.cos(th)).astype(int)
                ys = np.round(cy + rr * np.sin(th)).astype(int)
                ok = (xs >= 0) & (xs < gray.shape[1]) & (ys >= 0) & (ys < gray.shape[0])
                if ok.any():
                    score += np.count_nonzero(gray[ys[ok], xs[ok]] > 252)
                    n += int(ok.sum())
            score = score / max(n, 1)
            if score > best2[1]:
                best2 = ((cx, cy), score)
    return best2[0]


class TestOptions:
    def test_defaults(self):
        o = vm.MagnifyOptions()
        o.validate()
        assert o.center == (0.5, 0.38)
        assert o.size == pytest.approx(0.35)
        assert o.zoom == pytest.approx(3.0)
        assert o.motion == "auto"
        assert o.grid == (2, 2)
        assert o.hold == pytest.approx(2.5)
        assert o.sharpen == pytest.approx(0.5)

    @pytest.mark.parametrize("kw", [
        dict(center=(1.5, 0.5)),
        dict(size=0.0),
        dict(size=0.6),
        dict(zoom=1.0),
        dict(zoom=25),
        dict(feather=-0.1),
        dict(ring_width=-1),
        dict(motion="teleport"),
        dict(grid=(0, 2)),
        dict(grid=(4, 2)),
        dict(grid=(3, 3)),
        dict(hold=0.1),
        dict(move_dur=0.1),
        dict(min_gap=0.1),
        dict(sharpen=-1),
        dict(crf=0),
        dict(start=6.0, end=5.0),
    ])
    def test_invalid(self, kw):
        with pytest.raises(EnhancementError):
            vm.MagnifyOptions(**kw).validate()


class TestGeometry:
    def test_window_even_and_big_enough(self):
        g = vm.lens_geometry(W, H, vm.MagnifyOptions(size=0.35, feather=0.05))
        assert g["win"] % 2 == 0
        assert g["win"] >= 2 * g["radius"]
        assert g["crop"] % 2 == 0
        assert g["radius"] == int(round(0.35 * W))

    def test_window_fits_frame(self):
        with pytest.raises(EnhancementError):
            vm.lens_geometry(64, 64, vm.MagnifyOptions(size=0.5))


class TestMasks:
    def test_png_signature_and_ffmpeg_decodes(self, tmp_path):
        disc, ring = vm.build_lens_masks(56, 0.05, 0.025, 128, tmp_path)
        for p in (disc, ring):
            data = p.read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
            subprocess.run([FFMPEG, "-v", "error", "-i", str(p), "-frames:v", "1",
                            "-f", "null", "-"], check=True, capture_output=True)

    def test_disc_gray_ramp(self, tmp_path):
        disc, _ = vm.build_lens_masks(50, 0.2, 0.025, 120, tmp_path)
        a = decode_png_gray(disc)
        assert a[60, 60] == 255
        assert a[0, 0] == 0 and a[119, 0] == 0
        y, x = np.mgrid[0:120, 0:120]
        d = np.hypot(x - 59.5, y - 59.5)
        radii = [42, 46, 48, 49]  # dentro de la zona de rampa (fade 40..50)
        means = [a[(d >= r - 2) & (d <= r + 2)].mean() for r in radii]
        assert all(m1 > m2 for m1, m2 in zip(means, means[1:]))

    def test_ring_gray_at_radius(self, tmp_path):
        _, ring = vm.build_lens_masks(50, 0.05, 0.05, 120, tmp_path)
        a = decode_png_gray(ring)
        y, x = np.mgrid[0:120, 0:120]
        d = np.hypot(x - 59.5, y - 59.5)
        assert a[(d >= 48) & (d <= 52)].mean() > 150
        assert a[(d < 40)].mean() < 10
        assert a[(d > 62)].mean() < 10


class TestWaypoints:
    def test_static(self):
        plan = vm.waypoint_plan(vm.MagnifyOptions(motion="static", center=(0.9, 0.9)),
                                W, H, 5.0)
        assert len(plan) == 1
        _, _, (cx, cy) = plan[0]
        assert cx == W - vm.lens_geometry(W, H, vm.MagnifyOptions())["radius"]

    def test_scan_timing(self):
        o = vm.MagnifyOptions(motion="scan", grid=(2, 1), hold=1.0, move_dur=0.5)
        plan = vm.waypoint_plan(o, W, H, 10.0)
        assert len(plan) == 2
        t0, d0, target = plan[1]
        assert t0 == 0.0 and d0 == 0.5
        r = vm.lens_geometry(W, H, o)["radius"]
        assert target == (W - r, H / 2)  # celda derecha
        assert plan[0][2] == (r, H / 2)  # parte de la celda izquierda

    def test_scan_row_major_order(self):
        o = vm.MagnifyOptions(motion="scan", grid=(2, 2), hold=0.5, move_dur=0.5)
        plan = vm.waypoint_plan(o, W, H, 10.0)
        targets = [t[2] for t in plan]
        r = vm.lens_geometry(W, H, o)["radius"]
        # orden de lectura: sup-izq, sup-der, inf-izq, inf-der (0.25/0.75)
        expect = [(r, 142), (W - r, 142), (r, 426), (W - r, 426)]
        assert [tuple(round(v) for v in p) for p in targets] == \
               [tuple(round(v) for v in p) for p in expect]
        # tiempos: move 0..0.5, hold 0.5..1.0, move 1.0..1.5, ...
        assert plan[2][0] == pytest.approx(1.0)

    def test_voice_timing(self):
        o = vm.MagnifyOptions(motion="voice", grid=(2, 1), move_dur=0.8)
        plan = vm.waypoint_plan(o, W, H, 5.0, moments=[1.0])
        assert plan[1][0] == pytest.approx(1.0)
        assert plan[1][1] == pytest.approx(0.8)

    def test_voice_more_moments_than_cells(self):
        o = vm.MagnifyOptions(motion="voice", grid=(2, 1), move_dur=0.5)
        plan = vm.waypoint_plan(o, W, H, 5.0, moments=[0.5, 1.5, 2.5])
        assert len(plan) == 2  # 2 celdas -> 1 transición (+ punto de partida)

    def test_auto_uses_voice_or_scan(self):
        o = vm.MagnifyOptions(motion="auto", grid=(2, 1), move_dur=0.5, hold=0.5)
        p_voice = vm.waypoint_plan(o, W, H, 5.0, moments=[1.0])
        assert p_voice[1][0] == pytest.approx(1.0)
        p_scan = vm.waypoint_plan(o, W, H, 5.0, moments=None)
        assert p_scan[1][0] == pytest.approx(0.0)

    def test_moment_clamped_to_duration(self):
        o = vm.MagnifyOptions(motion="voice", grid=(2, 1), move_dur=0.5)
        plan = vm.waypoint_plan(o, W, H, 2.0, moments=[50.0])
        assert plan[1][0] == pytest.approx(1.5)  # dur - move_dur


class TestFilter:
    def test_chain_is_all_yuv(self):
        vf = vm.build_magnify_filter(W, H, vm.MagnifyOptions(motion="static"),
                                     duration=2.0)
        assert "format=rgba" not in vf       # calidad: sin conversión RGB
        assert vf.count("maskedmerge") == 2  # disco + aro en YUV
        assert "crop=" in vf and "scale=" in vf
        assert "flags=lanczos" in vf
        assert vf.count("overlay=") == 2
        assert "unsharp=5:5:0.5" in vf
        assert "[0:v]" in vf and "[1:v]" in vf and "[2:v]" in vf
        assert vf.endswith("format=yuv420p[vout]")

    def test_no_sharpen_when_zero(self):
        vf = vm.build_magnify_filter(W, H, vm.MagnifyOptions(sharpen=0.0),
                                     duration=1.0)
        assert "unsharp" not in vf

    def test_motion_expr_has_easing_and_even_rounding(self):
        o = vm.MagnifyOptions(motion="scan", grid=(2, 1), move_dur=0.5, hold=0.5)
        vf = vm.build_magnify_filter(W, H, o, duration=2.0)
        assert "pow(" in vf                      # curva S
        assert "2*floor" in vf                   # redondeo par (croma)
        assert "min(max(" in vf                  # clamp al frame
        assert "maskedmerge" in vf

    def test_segment_offset_in_expr(self):
        vf = vm.build_magnify_filter(W, H, vm.MagnifyOptions(motion="scan",
                                                             start=3.0),
                                     duration=2.0)
        assert "(t-3.000000)" in vf              # tras -ss 't' queda offseteado


class TestPlan:
    def test_plan_contract(self, tmp_path):
        plan = vm.build_plan(make_video(tmp_path), vm.MagnifyOptions())
        assert plan.startswith("VOXERA PLAN (video magnify)")
        for token in ("entrada", "lente", "motion", "encoder", "filtro"):
            assert token in plan

    def test_plan_bad_opts_raises(self, tmp_path):
        with pytest.raises(EnhancementError):
            vm.build_plan(make_video(tmp_path), vm.MagnifyOptions(zoom=1.0))


class TestEndToEnd:
    def test_static_e2e(self, tmp_path):
        """Senoide de 8 px: dentro de la lente periodo = 8*zoom_eff (las
        franjas se ven zoom veces más anchas), fuera 8 px, aro en el radio,
        fuera de la lente casi intacto."""
        inp = make_video(tmp_path, duration=1.0, period=8.0)
        out = tmp_path / "out.mp4"
        opts = vm.MagnifyOptions(motion="static", center=(0.5, 0.4), size=0.35,
                                 zoom=2.0, feather=0.02, ring_width=0.025)
        assert vm.magnify_video(inp, out, opts) == out
        g = vm.lens_geometry(W, H, opts)
        r = g["radius"]
        cx = int(round(2 * (min(max(0.5 * W, r), W - r) - g["win"] / 2) / 2)) + g["win"] // 2
        cy = int(round(2 * (min(max(0.4 * H, r), H - r) - g["win"] / 2) / 2)) + g["win"] // 2
        orig = decode_frame(inp)
        rend = decode_frame(out)

        d_in = dominant_period(rend, cx - int(0.6 * r), cx + int(0.6 * r),
                               cy - int(0.45 * r), cy + int(0.45 * r))
        assert abs(d_in - 8.0 * g["zoom_eff"]) < 1.0, f"dentro {d_in:.2f}px"
        d_out = dominant_period(rend, 8, cx - r - 16, cy - 40, cy + 40)
        assert 7 <= d_out <= 9.5, f"fuera {d_out:.2f}px"

        y, x = np.mgrid[0:H, 0:W]
        outside = (x - cx) ** 2 + (y - cy) ** 2 > (r * 1.15) ** 2
        diff = np.abs(orig[outside].astype(np.int16) - rend[outside].astype(np.int16))
        assert diff.mean() < 3.0, f"diff fuera {diff.mean():.2f}"

        # aro presente: pico del perfil radial en ~r
        d = np.hypot(x - cx, y - cy)
        prof = [(rad, float(rend[(d >= rad - 2) & (d <= rad + 2)].mean(axis=0)[0]))
                for rad in range(int(r * 0.8), int(r * 1.2), 4)]
        peak_r, peak_v = max(prof, key=lambda p: p[1])
        assert abs(peak_r - r) <= 8, f"aro en r={peak_r} (esperado ~{r})"
        base_v = rend[d <= r * 0.5].mean(axis=0)[0]
        assert peak_v > base_v + 8

    def test_quality_amplitude_preserved(self, tmp_path):
        """Calidad: la amplitud de la senoide dentro de la lente se conserva
        (>= 90% de la fuente). Un upscale suave (p. ej. bilinear) la hunde;
        lanczos + unsharp la mantienen."""
        inp = make_video(tmp_path, duration=1.0, period=8.0)
        out = tmp_path / "out.mp4"
        opts = vm.MagnifyOptions(motion="static", center=(0.5, 0.4), size=0.35,
                                 zoom=2.0, feather=0.02, ring_width=0.025)
        vm.magnify_video(inp, out, opts)
        g = vm.lens_geometry(W, H, opts)
        r = g["radius"]
        cx = int(round(2 * (min(max(0.5 * W, r), W - r) - g["win"] / 2) / 2)) + g["win"] // 2
        cy = int(round(2 * (min(max(0.4 * H, r), H - r) - g["win"] / 2) / 2)) + g["win"] // 2
        orig = decode_frame(inp)
        rend = decode_frame(out)
        a_in = sine_amplitude(rend, cx - int(0.45 * r), cx + int(0.45 * r),
                              cy - int(0.4 * r), cy + int(0.4 * r))
        a_src = sine_amplitude(orig, 8, 8 + 2 * int(0.45 * r), 100, 200)
        assert a_in / a_src >= 0.9, f"amplitud {a_in:.1f} vs fuente {a_src:.1f}"

    def test_motion_scan_e2e(self, tmp_path):
        """scan 2x1: frame 0 con la lente en la celda izquierda, tras el
        movimiento en la derecha (centro del aro detectado por píxeles
        blancos)."""
        inp = make_video(tmp_path, duration=2.0, period=8.0)
        out = tmp_path / "out.mp4"
        opts = vm.MagnifyOptions(motion="scan", grid=(2, 1), size=0.35,
                                 zoom=2.0, hold=0.6, move_dur=0.6)
        vm.magnify_video(inp, out, opts)
        g = vm.lens_geometry(W, H, opts)
        r = g["radius"]
        win = g["win"]
        ex0, ey0 = expected_ring_center(r, H / 2, win, W, H)
        ex1, ey1 = expected_ring_center(W - r, H / 2, win, W, H)
        c0 = find_lens_center(decode_frame(out, 0), r, H / 2, r)
        assert c0 is not None and abs(c0[0] - ex0) <= 6, f"frame0 en {c0}"
        c1 = find_lens_center(decode_frame(out, 55), W - r, H / 2, r)
        assert c1 is not None and abs(c1[0] - ex1) <= 6, f"frame55 en {c1}"

    def test_motion_voice_e2e(self, tmp_path):
        """voice: dos ráfagas de tono -> la transición arranca en el momento
        detectado; antes la lente está en la celda 1, después en la 2."""
        inp = make_video(tmp_path, duration=3.0, period=8.0, audio="bursts")
        out = tmp_path / "out.mp4"
        opts = vm.MagnifyOptions(motion="voice", grid=(2, 1), size=0.35,
                                 zoom=2.0, move_dur=0.8, min_gap=1.0)
        vm.magnify_video(inp, out, opts)
        g = vm.lens_geometry(W, H, opts)
        r = g["radius"]
        win = g["win"]
        p0 = (r, H / 2)
        p1 = (W - r, H / 2)
        ex0, ey0 = expected_ring_center(r, H / 2, win, W, H)
        ex1, ey1 = expected_ring_center(W - r, H / 2, win, W, H)
        c_early = find_lens_center(decode_frame(out, 6), *p0, r)   # t=0.2
        assert c_early is not None and abs(c_early[0] - ex0) <= 6, \
            f"antes de la voz en {c_early}"
        c_late = find_lens_center(decode_frame(out, 80), *p1, r)   # t=2.7
        assert c_late is not None and abs(c_late[0] - ex1) <= 6, \
            f"después de la voz en {c_late}"

    def test_segment_timing_with_offset(self, tmp_path):
        """--start: el primer frame del segmento debe tener la lente en la
        celda inicial (verifica el offset de 't' tras -ss)."""
        inp = make_video(tmp_path, duration=3.0, period=8.0)
        out = tmp_path / "out.mp4"
        opts = vm.MagnifyOptions(motion="scan", grid=(2, 1), size=0.35,
                                 zoom=2.0, hold=0.6, move_dur=0.6,
                                 start=1.0, end=2.5)
        vm.magnify_video(inp, out, opts)
        g = vm.lens_geometry(W, H, opts)
        r = g["radius"]
        win = g["win"]
        ex0, _ = expected_ring_center(r, H / 2, win, W, H)
        c0 = find_lens_center(decode_frame(out, 0), r, H / 2, r)
        assert c0 is not None and abs(c0[0] - ex0) <= 6, f"frame0 con --start en {c0}"

    def test_no_ring_keeps_lens(self, tmp_path):
        inp = make_video(tmp_path, duration=1.0)
        out = tmp_path / "out.mp4"
        vm.magnify_video(inp, out, vm.MagnifyOptions(ring_width=0.0, zoom=2.0))
        import voxera.video_enhance as ve
        probe = ve.probe_video(out)
        assert probe["width"] == W and probe["height"] == H

    def test_magnify_segment(self, tmp_path):
        inp = make_video(tmp_path, duration=2.0)
        out = tmp_path / "out.mp4"
        vm.magnify_video(inp, out, vm.MagnifyOptions(start=0.5, end=1.5))
        import voxera.video_enhance as ve
        probe = ve.probe_video(out)
        assert abs(probe["duration_s"] - 1.0) <= 0.25
