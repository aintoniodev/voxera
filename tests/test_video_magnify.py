"""Unit tests de video magnify (lente de aumento): solo ffmpeg + numpy.

- Opciones: validación de rangos y defaults.
- Máscaras PNG: disco con pluma (centro opaco -> borde 0) y aro de borde
  (pico de alpha en el radio, antialias ~1 px).
- Filtro: cadena split->crop->scale->alphamerge->overlay con lente estática.
- Plan --dry-run.
- E2E numérico: patrón de franjas verticales de periodo conocido; dentro de
  la lente el periodo aparente debe ser ~zoom x menor (la frecuencia se
  multiplica), fuera debe quedar intacto; aro presente en el radio.
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


def make_stripes_video(tmp_path, name="in.mp4", duration=1.0, period=16.0,
                       size=f"{W}x{H}", rate=30, sine=False):
    """Vídeo sintético: franjas verticales de periodo conocido + audio.

    Periodo en px = `period`. Con sine=True la onda es senoidal (128+100·sin):
    invariante ante el escalado lanczos — la medida de periodo por FFT es
    exacta. Con sine=False es onda cuadrada nítida (235/16).
    """
    import soundfile as sf
    import tests.synth as s

    w, h = (int(v) for v in size.split("x"))
    n = int(round(w / period))
    x = np.arange(w)
    if sine:
        row = np.clip(128 + 100 * np.sin(2 * np.pi * x * n / w), 0, 255)
        row = row.astype(np.uint8)
    else:
        row = np.where(((x * n / w) % 1.0) < 0.5, 235, 16).astype(np.uint8)
    frame = np.tile(row[None, :, None], (h, 1, 3))
    wav = tmp_path / "audio.wav"
    sf.write(str(wav), s.speech_like(duration), SR)
    raw = tmp_path / "in.yuv"
    n_frames = int(round(duration * rate))
    raw.write_bytes(frame.tobytes() * n_frames)
    out = tmp_path / name
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", size, "-r", str(rate), "-i", str(raw),
         "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "96k", "-shortest", str(out)],
        check=True, capture_output=True,
    )
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


def decode_png_rgba(path):
    """Decodifica un PNG RGBA a numpy HxWx4 (vía ffmpeg, sin cv2)."""
    proc = subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-i", str(path), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
        check=True, capture_output=True,
    )
    n = len(proc.stdout) // 4
    side = int(round(n ** 0.5))
    return np.frombuffer(proc.stdout, np.uint8).reshape(side, side, 4)


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


class TestOptions:
    def test_defaults(self):
        o = vm.MagnifyOptions()
        o.validate()
        assert o.center == (0.5, 0.38)
        assert o.size == pytest.approx(0.35)
        assert o.zoom == pytest.approx(3.0)
        assert o.feather == pytest.approx(0.05)
        assert o.ring_width == pytest.approx(0.025)

    @pytest.mark.parametrize("kw", [
        dict(center=(1.5, 0.5)),
        dict(center=(0.5, -0.1)),
        dict(size=0.0),
        dict(size=0.6),
        dict(zoom=1.0),
        dict(zoom=25),
        dict(feather=-0.1),
        dict(feather=0.6),
        dict(ring_width=-1),
        dict(ring_width=0.5),
        dict(crf=0),
        dict(start=5.0, end=5.0),
        dict(start=6.0, end=5.0),
    ])
    def test_invalid(self, kw):
        with pytest.raises(EnhancementError):
            vm.MagnifyOptions(**kw).validate()


class TestGeometry:
    def test_lens_inside_frame(self):
        g = vm.lens_geometry(W, H, vm.MagnifyOptions(center=(0.5, 0.5), size=0.35))
        r = g["radius"]
        assert g["cx"] == W / 2 and g["cy"] == H / 2
        assert r == int(round(0.35 * W))
        assert g["cx"] - r >= 0 and g["cx"] + r <= W
        assert g["cy"] - r >= 0 and g["cy"] + r <= H

    def test_center_clamped_to_frame(self):
        g = vm.lens_geometry(W, H, vm.MagnifyOptions(center=(0.0, 1.0), size=0.35))
        r = g["radius"]
        assert g["cx"] == r          # pegado al borde izq
        assert g["cy"] == H - r      # pegado al borde inferior
        assert g["crop"] % 2 == 0

    def test_zoom_effective(self):
        g = vm.lens_geometry(W, H, vm.MagnifyOptions(zoom=3.0, size=0.35))
        assert g["zoom_eff"] == pytest.approx(3.0, abs=0.2)
        g2 = vm.lens_geometry(W, H, vm.MagnifyOptions(zoom=10.0, size=0.35))
        assert g2["zoom_eff"] >= 9.0


class TestMasks:
    def test_png_signature_and_size(self, tmp_path):
        mask, ring = vm.build_lens_masks(56, 0.05, 0.025, tmp_path)
        for p, expect in ((mask, "lens_mask.png"), (ring, "lens_ring.png")):
            assert p.name == expect
            data = p.read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
        # ffmpeg sabe decodificarlas
        for p in (mask, ring):
            subprocess.run([FFMPEG, "-v", "error", "-i", str(p), "-frames:v", "1",
                            "-f", "null", "-"], check=True, capture_output=True)

    def test_mask_disc_alpha(self, tmp_path):
        # feather=0: borde duro — esquinas transparentes, centro y bordes opacos
        mask, _ = vm.build_lens_masks(50, 0.0, 0.025, tmp_path)
        a = decode_png_rgba(mask)[:, :, 3]
        assert a[50, 50] == 255
        assert a[0, 0] == 0 and a[0, 99] == 0 and a[99, 0] == 0 and a[99, 99] == 0
        assert a[50, 0] == 255 and a[0, 50] == 255  # el disco llena el canvas 2R
        # feather=0.2: rampa — media por anillos decrece con el radio
        mask, _ = vm.build_lens_masks(50, 0.2, 0.025, tmp_path)
        a = decode_png_rgba(mask)[:, :, 3]
        assert a[50, 50] == 255
        y, x = np.mgrid[0:100, 0:100]
        d = np.hypot(x - 50, y - 50)
        radii = [42, 46, 48, 49]  # dentro de la zona de rampa (fade 40..50)
        means = [a[(d >= r - 2) & (d <= r + 2)].mean() for r in radii]
        assert all(m1 > m2 for m1, m2 in zip(means, means[1:]))

    def test_ring_alpha_peak_at_radius(self, tmp_path):
        _, ring = vm.build_lens_masks(50, 0.05, 0.05, tmp_path)
        a = decode_png_rgba(ring)[:, :, 3]
        y, x = np.mgrid[0:100, 0:100]
        d = np.hypot(x - 50, y - 50)
        band = a[(d >= 48) & (d <= 52)].mean()
        assert band > 150          # aro visible en el radio
        assert a[(d < 40)].mean() < 10   # nada dentro
        assert a[(d > 62)].mean() < 10   # nada fuera
        # color blanco en la zona del aro
        rgb = decode_png_rgba(ring)[:, :, :3]
        assert rgb[(d >= 49) & (d <= 51)].mean() > 200


class TestFilter:
    def test_chain(self):
        vf = vm.build_magnify_filter(W, H, vm.MagnifyOptions(), duration=2.0)
        assert "split=2" in vf
        assert "crop=" in vf and "scale=" in vf
        assert "alphamerge" in vf
        assert vf.count("overlay=") == 2
        assert vf.endswith("format=yuv420p[vout]")
        assert "[0:v]" in vf and "[1:v]" in vf and "[2:v]" in vf

    def test_lens_static_position(self):
        o = vm.MagnifyOptions(center=(0.25, 0.3), size=0.2)
        g = vm.lens_geometry(W, H, o)
        vf = vm.build_magnify_filter(W, H, o, duration=1.0)
        assert f"crop={g['crop']}:{g['crop']}:" in vf
        x0, y0 = g["cx"] - g["radius"], g["cy"] - g["radius"]
        assert f"overlay=x={vm._fmt(x0)}:y={vm._fmt(y0)}" in vf


class TestPlan:
    def test_plan_contract(self, tmp_path):
        plan = vm.build_plan(make_stripes_video(tmp_path), vm.MagnifyOptions())
        assert plan.startswith("VOXERA PLAN (video magnify)")
        for token in ("entrada", "lente", "zoom=", "encoder", "filtro"):
            assert token in plan

    def test_plan_bad_opts_raises(self, tmp_path):
        with pytest.raises(EnhancementError):
            vm.build_plan(make_stripes_video(tmp_path), vm.MagnifyOptions(zoom=1.0))


class TestEndToEnd:
    def test_magnify_e2e(self, tmp_path):
        """Senoidal de 8 px: dentro de la lente el periodo aparente debe ser
        8*zoom_eff (la lente muestra la zona 2x más grande -> franjas 2x más
        anchas; lanczos es lineal, la senoide solo cambia de escala), fuera
        8 px, aro presente en el radio, resto del frame intacto.
        zoom=2 -> periodo interior ~16 px: ~8 ciclos en la ventana (FFT limpio)."""
        inp = make_stripes_video(tmp_path, duration=1.0, period=8.0, sine=True)
        out = tmp_path / "out.mp4"
        opts = vm.MagnifyOptions(center=(0.5, 0.4), size=0.35, zoom=2.0,
                                 feather=0.02, ring_width=0.025)
        result = vm.magnify_video(inp, out, opts)
        assert result == out

        g = vm.lens_geometry(W, H, opts)
        r, cx, cy = int(g["radius"]), int(g["cx"]), int(g["cy"])
        orig = decode_frame(inp)
        rend = decode_frame(out)
        expected_in = 8.0 * g["zoom_eff"]

        # 1) dentro de la lente: x en disco 0.6r, y dentro del band del crop
        #    (el patch ampliado solo cubre crop/2 de alto en el centro)
        d_in = dominant_period(rend, cx - int(0.6 * r), cx + int(0.6 * r),
                               cy - int(0.45 * r), cy + int(0.45 * r))
        assert abs(d_in - expected_in) < 1.0, (
            f"periodo dentro {d_in:.2f}px (esperado ~{expected_in:.2f})")

        # 2) fuera de la lente: periodo intacto 8 px (ventana ancha a la izq)
        d_out = dominant_period(rend, 8, cx - r - 16, cy - 40, cy + 40)
        assert 7 <= d_out <= 9.5, f"periodo fuera {d_out:.2f}px (esperado 8)"

        # 3) resto del frame casi idéntico al original (diff mínima)
        y, x = np.mgrid[0:H, 0:W]
        inside = (x - cx) ** 2 + (y - cy) ** 2 <= (r * 1.1) ** 2
        outside = ~inside
        diff = np.abs(orig[outside].astype(np.int16) - rend[outside].astype(np.int16))
        assert diff.mean() < 3.0, f"diff fuera de la lente {diff.mean():.2f}"

        # 4) aro presente: brillo máximo del perfil radial en ~r
        yy, xx = np.mgrid[0:H, 0:W]
        d = np.hypot(xx - cx, yy - cy)
        prof = []
        for rad in range(int(r * 0.7), int(r * 1.25), 4):
            band = (d >= rad - 2) & (d <= rad + 2)
            prof.append((rad, float(rend[band].mean(axis=0)[0])))
        peak_r, peak_v = max(prof, key=lambda p: p[1])
        base_v = rend[yy, xx][d <= r * 0.5].mean(axis=0)[0]
        assert abs(peak_r - r) <= 6, f"aro en r={peak_r} (esperado ~{r})"
        assert peak_v > base_v + 8, f"aro no visible: {peak_v:.1f} vs {base_v:.1f}"

    def test_magnify_segment(self, tmp_path):
        inp = make_stripes_video(tmp_path, duration=2.0)
        out = tmp_path / "out.mp4"
        opts = vm.MagnifyOptions(start=0.5, end=1.5)
        vm.magnify_video(inp, out, opts)
        import voxera.video_enhance as ve
        probe = ve.probe_video(out)
        assert abs(probe["duration_s"] - 1.0) <= 0.25

    def test_no_ring_keeps_lens(self, tmp_path):
        inp = make_stripes_video(tmp_path, duration=1.0)
        out = tmp_path / "out.mp4"
        vm.magnify_video(inp, out, vm.MagnifyOptions(ring_width=0.0, zoom=2.0))
        import voxera.video_enhance as ve
        probe = ve.probe_video(out)
        assert probe["width"] == W and probe["height"] == H
