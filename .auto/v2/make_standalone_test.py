#!/usr/bin/env python
"""Generate a self-contained AB test (5 difficult pairs) for offline listening.

Embeds the two conditions per pair (B=DF2, C=DF2+master, normalized -16 LUFS)
as base64 MP3 so the single HTML works without the server: open in any
browser, listen with A/B buttons, vote (blind, side order randomized per
listener), download one CSV with all votes.

Pick criteria (from oyente1's round-1 votes): clips where the master clearly
helped (susurro, pc5_conversacion, metros) + clips where DF2 won (chorros,
grito) — the discriminating set for the >=60% decision.

Output: .auto/human/voxera-test-AB-dificiles.html (~2-3 MB)
Usage: python .auto/v2/make_standalone_test.py
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
COND = ROOT / ".auto" / "human" / "conditions"

CLIPS = [
    "test_pc4_susurro",      # susurro: DF2 MOS 1 vs C MOS 3 (C gana fuerte)
    "test_pc5_conversacion", # conversacion baja: DF2 MOS 1 vs C MOS 3 (C gana fuerte)
    "test_metros",           # ruido de metro: C gano (MOS 3/3)
    "test_chorros",          # agua de fondo: B (DF2) gano (caso adverso)
    "test_pc2_grito",        # grito: B (DF2) gano (caso adverso)
]

FFMPEG = shutil.which("ffmpeg") or "C:/ffmpeg/bin/ffmpeg.exe"
TARGET = ROOT / ".auto" / "human" / "voxera-test-AB-dificiles.html"

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>voxera · Test A/B (5 pares)</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; background: #111; color: #ddd; margin: 0; padding: 16px; max-width: 640px; margin: 0 auto; }
  h1 { font-size: 18px; color: #7c5cff; }
  .card { background: #1a1a1e; border: 1px solid #2a2a30; border-radius: 12px; padding: 16px; margin: 12px 0; }
  .row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin: 8px 0; }
  button { background: #2a2a30; color: #eee; border: 1px solid #3a3a44; border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: 14px; }
  button.primary { background: #7c5cff; border-color: #7c5cff; color: #fff; }
  button.side { min-width: 84px; padding: 12px 16px; font-size: 16px; font-weight: 700; border-radius: 10px; }
  button.side.onA { background: #1d3a5f; border-color: #7ab8ff; color: #7ab8ff; }
  button.side.onB { background: #4a2f12; border-color: #ffb35c; color: #ffb35c; }
  input[type=text] { background: #222; color: #ddd; border: 1px solid #3a3a44; border-radius: 6px; padding: 6px; width: 100%; }
  canvas { width: 100%; height: 130px; background: #0c0c10; border-radius: 8px; display: block; }
  .tag { font-size: 12px; color: #999; }
  #seek { width: 100%; }
  .bar { height: 6px; background: #26262e; border-radius: 3px; overflow: hidden; }
  .bar > div { height: 100%; background: #7c5cff; }
</style>
</head>
<body>
<h1>voxera · Test A/B <span class="tag">5 pares · ~10 min · usa auriculares</span></h1>

<div class="card">
  <div class="tag">Escucha cada par con los botones A y B (puedes alternar las veces que quieras).
  Marca cuál prefieres y un MOS (1=pésimo … 5=excelente) para cada lado. No hay respuestas
  correctas: queremos TU preferencia.</div>
  <div class="row"><span class="tag" style="width:100%">Tu nombre:</span>
  <input type="text" id="listener" placeholder="p.ej. Laura"></div>
  <div class="row"><button id="blind">Modo ciego: OFF</button>
  <span class="tag">(ON = las etiquetas pasan a X/Y)</span></div>
</div>

<div id="pairs"></div>

<div class="card">
  <div class="row"><button id="download" class="primary">📥 Descargar mis votos (CSV)</button>
  <button id="reset">Reiniciar votos</button></div>
  <div class="tag" id="status">Votos registrados: 0/5</div>
  <div class="tag">Al terminar: descarga el CSV y envíalo de vuelta (junto al nombre).</div>
</div>

<script>
const PAIRS = __PAIRS__;

let ac = null, master = null, src = null, playing = false, playStart = 0, playPos = 0;
let side = "A", blind = false, current = null;
const votes = [];

// randomize pair order + side mapping per listener (blind methodology)
for (const p of PAIRS) {
  p.order = Math.random();
  p.swap = Math.random() < 0.5;
}
PAIRS.sort((a, b) => a.order - b.order);

function ensureGraph() {
  if (!ac) { ac = new (window.AudioContext || window.webkitAudioContext)();
    master = ac.createGain(); master.connect(ac.destination); }
}
async function loadBuffer(url, which) {
  ensureGraph();
  const r = await fetch(url);
  const buf = await ac.decodeAudioData(await r.arrayBuffer());
  current.bufs[which] = buf; current.durs[which] = buf.duration;
  draw();
}
async function loadPair(p) {
  current = p; p.bufs = {}; p.durs = {}; playPos = 0; stopPlay();
  await Promise.all([loadBuffer(p.aData, "A"), loadBuffer(p.bData, "B")]);
  renderPair(p);
}
function teardown() {
  if (src) { try { src.onended = null; src.stop(); } catch (e) {}
    try { src.disconnect(); } catch (e) {} src = null; }
}
function stopPlay() { playing = false; teardown(); }
function play() {
  const buf = current.bufs[side];
  if (!buf) return;
  ensureGraph(); ac.resume(); teardown();
  const s = ac.createBufferSource(); s.buffer = buf; s.connect(master);
  master.gain.value = 1;
  const off = Math.max(0, Math.min(playPos, buf.duration - 0.02));
  s.start(0, off); s.onended = () => { if (src === s) playing = false; };
  src = s; playStart = ac.currentTime - off; playing = true;
  requestAnimationFrame(tick);
}
function tick() {
  if (!playing) return;
  playPos = ac.currentTime - playStart;
  const dur = current.durs[side] || 0;
  if (playPos >= dur) { stopPlay(); playPos = 0; renderPair(current); return; }
  draw();
  requestAnimationFrame(tick);
}
function switchSide(s) {
  const was = playing; if (was) stopPlay();
  side = s;
  if (was && current.bufs[s]) play();
  renderPair(current);
}
function draw() {
  const p = current; if (!p) return;
  const cv = document.getElementById("cv" + p.id), ctx = cv.getContext("2d");
  ctx.clearRect(0, 0, cv.width, cv.height);
  const H = cv.height, W = cv.width;
  for (const [k, color] of [["A", "#7ab8ff"], ["B", "#ffb35c"]]) {
    const buf = p.bufs[k]; if (!buf) continue;
    const d = buf.getChannelData(0), cols = W, block = Math.max(1, Math.floor(d.length / cols));
    const y0 = k === "A" ? 0 : H / 2;
    ctx.fillStyle = (k === side ? color : color + "44");
    for (let x = 0; x < cols; x++) {
      let mn = 1, mx = -1;
      const st = x * block;
      for (let i = st; i < st + block; i += 8) { const v = d[i]; if (v < mn) mn = v; if (v > mx) mx = v; }
      ctx.fillRect(x, y0 + (H/2)*0.5 + mn*(H/2)*0.5, 1, Math.max(1, (mx-mn)*(H/2)*0.5));
    }
  }
  ctx.fillStyle = "#111"; ctx.fillRect(0, H/2 - 3, W, 6);
  if (playing && current.durs[side]) {
    ctx.fillStyle = "#fff";
    ctx.fillRect(W * (playPos / current.durs[side]) - 1, 0, 2, H);
  }
  const el = document.getElementById("seek" + p.id);
  if (el && current.durs[side]) el.value = Math.round((playPos / current.durs[side]) * 1000);
  const t = document.getElementById("time" + p.id);
  if (t) t.textContent = fmt(playPos) + " / " + fmt(current.durs[side] || 0);
}
function fmt(s) { s = Math.max(0, s); return Math.floor(s / 60) + ":" + (s % 60).toFixed(1).padStart(4, "0"); }

function lbl(k) { return blind ? (k === "A" ? "X" : "Y") : k; }

function renderPair(p) {
  const cv = document.getElementById("cv" + p.id);
  draw();
  document.getElementById("btnA" + p.id).className = "side " + (side === "A" ? "onA" : "");
  document.getElementById("btnB" + p.id).className = "side " + (side === "B" ? "onB" : "");
  document.getElementById("btnA" + p.id).textContent = lbl("A");
  document.getElementById("btnB" + p.id).textContent = lbl("B");
  document.getElementById("sel" + p.id).textContent = "escuchando: " + lbl(side);
  document.getElementById("mosAv" + p.id).textContent = document.getElementById("mosA" + p.id).value;
  document.getElementById("mosBv" + p.id).textContent = document.getElementById("mosB" + p.id).value;
}

function markPref(p, pref) {
  p.pref = pref;
  for (const k of ["A", "B", "tie"]) {
    const el = document.getElementById("pref" + p.id + k);
    if (el) el.style.outline = k === pref ? "2px solid #7c5cff" : "none";
  }
}

function buildUI() {
  const root = document.getElementById("pairs");
  root.innerHTML = PAIRS.map((p, i) => `
  <div class="card">
    <div class="row"><span class="tag">Par ${i + 1} / ${PAIRS.length} — clip: ${p.clip}</span>
    <span class="tag" id="sel${p.id}"></span></div>
    <div class="row" style="justify-content:center">
      <button class="side" id="btnA${p.id}">A</button>
      <button id="play${p.id}" class="primary">▶</button>
      <button id="stop${p.id}">■</button>
      <button class="side" id="btnB${p.id}">B</button>
    </div>
    <canvas id="cv${p.id}" width="1200" height="260"></canvas>
    <input type="range" id="seek${p.id}" min="0" max="1000" value="0">
    <div class="row" style="justify-content:space-between"><span class="tag" id="time${p.id}"></span></div>
    <div class="row" style="justify-content:center">
      <button id="pref${p.id}A" class="side onA">Prefiero A</button>
      <button id="pref${p.id}tie" class="side">Empate</button>
      <button id="pref${p.id}B" class="side onB">Prefiero B</button>
    </div>
    <div class="row">
      <span class="tag" style="width:100%">MOS ${lbl("A")} (1-5):</span>
      <input type="range" id="mosA${p.id}" min="1" max="5" step="1" value="3" style="flex:1">
      <span id="mosAv${p.id}">3</span>
      <span class="tag" style="width:100%">MOS ${lbl("B")} (1-5):</span>
      <input type="range" id="mosB${p.id}" min="1" max="5" step="1" value="3" style="flex:1">
      <span id="mosBv${p.id}">3</span>
    </div>
    <div class="tag">MOS: 1=pésimo · 2=malo · 3=aceptable · 4=bueno · 5=excelente</div>
    <div class="row"><span class="tag" style="width:100%">Comentario (opcional):</span>
    <input type="text" id="comment${p.id}" placeholder="p.ej. 'la B suena más natural'"></div>
  </div>`).join("");

  for (const p of PAIRS) {
    document.getElementById("play" + p.id).onclick = () => { current = p; playing ? stopPlay() : play(); };
    document.getElementById("stop" + p.id).onclick = () => { current = p; stopPlay(); playPos = 0; renderPair(p); };
    document.getElementById("btnA" + p.id).onclick = () => { current = p; switchSide("A"); };
    document.getElementById("btnB" + p.id).onclick = () => { current = p; switchSide("B"); };
    document.getElementById("seek" + p.id).oninput = e => {
      current = p; const dur = current.durs[side] || 0;
      playPos = (e.target.value / 1000) * dur;
      if (playing) play();
      draw();
    };
    document.getElementById("pref" + p.id + "A").onclick = () => markPref(p, "A");
    document.getElementById("pref" + p.id + "B").onclick = () => markPref(p, "B");
    document.getElementById("pref" + p.id + "tie").onclick = () => markPref(p, "tie");
    document.getElementById("mosA" + p.id).oninput = e =>
      document.getElementById("mosAv" + p.id).textContent = e.target.value;
    document.getElementById("mosB" + p.id).oninput = e =>
      document.getElementById("mosBv" + p.id).textContent = e.target.value;
  }
}

function collectVotes() {
  const listener = document.getElementById("listener").value.trim() || "anon";
  const out = [];
  for (const p of PAIRS) {
    const mosA = +document.getElementById("mosA" + p.id).value;
    const mosB = +document.getElementById("mosB" + p.id).value;
    const comment = document.getElementById("comment" + p.id).value.trim();
    out.push({
      listener, clip: p.clip, pair: p.pair,
      side_a_file: p.swap ? p.bFile : p.aFile,
      side_b_file: p.swap ? p.aFile : p.bFile,
      preferred: p.pref || "", blind, mos_a: mosA, mos_b: mosB, comment,
    });
  }
  return out;
}
function updateStatus() {
  const n = collectVotes().filter(v => v.preferred).length;
  document.getElementById("status").textContent = "Votos registrados: " + n + "/" + PAIRS.length;
  if (n === PAIRS.length) document.getElementById("status").textContent += " — ¡listo para descargar! 🎉";
}
document.getElementById("download").onclick = function () {
  const votes = collectVotes();
  if (votes.some(v => !v.preferred)) {
    if (!confirm("Hay pares sin preferencia marcada. ¿Descargar igualmente?")) return;
  }
  const header = "listener,clip,pair,side_a_file,side_b_file,preferred,blind,mos_a,mos_b,comment";
  const rows = votes.map(v => [v.listener, v.clip, v.pair, v.side_a_file, v.side_b_file,
    v.preferred, v.blind, v.mos_a, v.mos_b, v.comment]
    .map(x => '"' + String(x).replace(/"/g, '""') + '"').join(","));
  const blob = new Blob([header + "\\n" + rows.join("\\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "votos_" + (document.getElementById("listener").value.trim() || "anon") + ".csv";
  a.click();
  document.getElementById("status").textContent = "CSV descargado ✓ envíalo de vuelta";
};
document.getElementById("reset").onclick = () => {
  for (const p of PAIRS) { p.pref = null;
    document.getElementById("mosA" + p.id).value = 3;
    document.getElementById("mosB" + p.id).value = 3;
    document.getElementById("comment" + p.id).value = "";
  }
  updateStatus();
};
document.getElementById("blind").onclick = function () {
  blind = !blind;
  this.textContent = "Modo ciego: " + (blind ? "ON" : "OFF");
  for (const p of PAIRS) renderPair(p);
};

// wire vote status updates
document.addEventListener("click", e => {
  if (e.target.id && e.target.id.startsWith("pref")) updateStatus();
});

(async function init() {
  buildUI();
  // preload the rest in the background
  for (const p of PAIRS.slice(1)) {
    const r1 = await fetch(p.aData), r2 = await fetch(p.bData);
    const [b1, b2] = await Promise.all([r1.arrayBuffer(), r2.arrayBuffer()]);
    ensureGraph();
    p.bufs = { A: await ac.decodeAudioData(b1), B: await ac.decodeAudioData(b2) };
    p.durs = { A: p.bufs.A.duration, B: p.bufs.B.duration };
  }
  // auto-advance: after voting pair i, move to i+1
  loadPair(PAIRS[0]);
  const origMark = markPref;
  markPref = function (p, pref) {
    origMark(p, pref);
    updateStatus();
    const idx = PAIRS.indexOf(p);
    if (idx < PAIRS.length - 1) {
      setTimeout(() => { current = PAIRS[idx + 1]; side = "A"; playPos = 0; renderPair(current); }, 400);
    }
  };
})();
</script>
</body>
</html>
"""


def encode_mp3(wav: Path) -> str:
    """Encode a wav to mono 160k mp3 and return base64."""
    import tempfile

    fd, tmp_name = tempfile.mkstemp(suffix=".mp3")  # .mp3 extension so ffmpeg detects the format
    import os

    os.close(fd)
    mp3 = Path(tmp_name)
    try:
        subprocess.run(
            [FFMPEG, "-y", "-v", "error", "-i", str(wav), "-ac", "1", "-b:a", "160k", str(mp3)],
            check=True, capture_output=True,
        )
        return base64.b64encode(mp3.read_bytes()).decode()
    finally:
        mp3.unlink(missing_ok=True)


def main() -> int:
    if not COND.is_dir():
        print(f"conditions dir missing: {COND} — run prepare_human.py first")
        return 1
    pairs = []
    for clip in CLIPS:
        b = COND / f"{clip}_B.wav"
        c = COND / f"{clip}_C.wav"
        if not (b.exists() and c.exists()):
            print(f"missing conditions for {clip}")
            return 1
        print(f"  {clip}: encoding B ({b.stat().st_size//1024}KB) + C ...")
        pairs.append({
            "id": f"p{len(pairs) + 1}",
            "clip": clip, "pair": "B vs C",
            "aData": "data:audio/mpeg;base64," + encode_mp3(b),
            "bData": "data:audio/mpeg;base64," + encode_mp3(c),
            "aFile": b.name, "bFile": c.name,
        })
    html = HTML.replace("__PAIRS__", json.dumps(pairs))
    TARGET.write_text(html, encoding="utf-8")
    size_mb = TARGET.stat().st_size / 1e6
    print(f"\n{len(pairs)} pares -> {TARGET} ({size_mb:.1f} MB)")
    print("Pásalo por WhatsApp/correo; se abre en Chrome/Edge (móvil o PC), sin servidor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
