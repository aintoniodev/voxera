/* ga-demo.js — reusable mini evolutionary simulator.
   A rugged 1-D fitness landscape with three search modes:
     random search · hill climbing · genetic algorithm
   Usage:
     <div id="demo"></div>
     <script src="../assets/ga-demo.js"></script>
     <script>GADemo.mount(document.getElementById('demo'));</script>
   Vanilla JS, no dependencies.
*/
(function (global) {
  'use strict';

  var N = 220;                 // landscape width (number of samples)
  var GAUSS = 0.04;            // mutation sigma as fraction of N

  function landscape(x) {
    var v = 0.5
      + 0.25 * Math.sin(x / 9)
      + 0.18 * Math.sin(x / 4.3 + 1.7)
      + 0.12 * Math.sin(x / 1.9 + 0.4);
    return Math.max(0, Math.min(1, v));
  }

  // precompute
  var heights = [];
  var globalBestX = 0, globalBestF = -1;
  for (var i = 0; i < N; i++) {
    heights.push(landscape(i));
    if (heights[i] > globalBestF) { globalBestF = heights[i]; globalBestX = i; }
  }

  function gauss() {
    // Box-Muller
    var u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  function clamp(x) { return Math.max(0, Math.min(N - 1, x)); }

  function mount(container) {
    var state = {
      mode: 'ga',
      pop: [],
      bestEver: null,        // {x, f}
      gen: 0,
      history: [],           // best-so-far per generation
      running: false,
      timer: null,
      speed: 60,
      popSize: 20,
      mutRate: 0.08,
      crossRate: 0.7,
      current: null          // for hill climbing: current position
    };

    // ---- DOM ----
    container.innerHTML =
      '<div class="demo">' +
      '  <div class="demo-controls no-print">' +
      '    <div class="demo-modes">' +
      '      <button class="btn mode" data-mode="random">Random</button>' +
      '      <button class="btn mode" data-mode="hc">Hill climb</button>' +
      '      <button class="btn mode active" data-mode="ga">Genetic alg.</button>' +
      '    </div>' +
      '    <div class="demo-sliders">' +
      '      <label>Population <input type="range" id="d-pop" min="1" max="40" value="20"></label>' +
      '      <label>Mutation <input type="range" id="d-mut" min="0" max="1" step="0.01" value="0.08"></label>' +
      '      <label>Crossover <input type="range" id="d-cross" min="0" max="1" step="0.05" value="0.7"></label>' +
      '      <label>Speed <input type="range" id="d-speed" min="10" max="300" step="10" value="60"></label>' +
      '    </div>' +
      '    <div class="demo-actions">' +
      '      <button class="btn" id="d-run">Run</button>' +
      '      <button class="btn" id="d-step">Step</button>' +
      '      <button class="btn" id="d-reset">Reset</button>' +
      '    </div>' +
      '  </div>' +
      '  <div class="demo-canvases">' +
      '    <canvas class="demo-land" height="230" width="700"></canvas>' +
      '    <canvas class="demo-curve" height="90" width="700"></canvas>' +
      '  </div>' +
      '  <div class="demo-status"></div>' +
      '</div>';

    var land = container.querySelector('.demo-land');
    var curve = container.querySelector('.demo-curve');
    var statusEl = container.querySelector('.demo-status');
    var lctx = land.getContext('2d');
    var cctx = curve.getContext('2d');

    var popInput = container.querySelector('#d-pop');
    var mutInput = container.querySelector('#d-mut');
    var crossInput = container.querySelector('#d-cross');
    var speedInput = container.querySelector('#d-speed');

    function readInputs() {
      state.popSize = parseInt(popInput.value, 10);
      state.mutRate = parseFloat(mutInput.value);
      state.crossRate = parseFloat(crossInput.value);
      state.speed = parseInt(speedInput.value, 10);
    }

    // ---- core algorithms ----
    function randomIndividual() { return { x: Math.random() * N }; }
    function fitness(ind) { return landscape(ind.x); }

    function initPop() {
      state.pop = [];
      for (var k = 0; k < state.popSize; k++) state.pop.push(randomIndividual());
      state.current = randomIndividual();
      state.bestEver = null;
      state.gen = 0;
      state.history = [];
      evaluateAll();
    }

    function evaluateAll() {
      state.pop.forEach(function (ind) {
        ind.f = fitness(ind);
        trackBest(ind);
      });
      if (state.mode === 'hc') trackBest(state.current);
      if (state.mode === 'random') trackBest(state.bestEver);
    }

    function trackBest(ind) {
      if (!ind) return;
      if (!state.bestEver || ind.f > state.bestEver.f) {
        state.bestEver = { x: ind.x, f: ind.f };
      }
    }

    function tournament(k) {
      var best = state.pop[Math.floor(Math.random() * state.pop.length)];
      for (var j = 1; j < k; j++) {
        var c = state.pop[Math.floor(Math.random() * state.pop.length)];
        if (c.f > best.f) best = c;
      }
      return best;
    }

    function mutate(x) {
      return clamp(x + GAUSS * N * state.mutRate * 10 * gauss());
    }

    function gaGeneration() {
      state.pop.forEach(function (ind) { ind.f = fitness(ind); });
      // elitism: carry over top 2
      var sorted = state.pop.slice().sort(function (a, b) { return b.f - a.f; });
      var next = [{ x: sorted[0].x }, { x: sorted[1].x }];
      while (next.length < state.popSize) {
        var a = tournament(3);
        var b = tournament(3);
        var child;
        if (Math.random() < state.crossRate) {
          // blend crossover
          child = (a.x + b.x) / 2 + GAUSS * N * 0.5 * gauss();
        } else {
          child = a.x;
        }
        child = mutate(child);
        next.push({ x: clamp(child) });
      }
      state.pop = next;
    }

    function hcStep() {
      var trial = { x: clamp(state.current.x + GAUSS * N * gauss()) };
      if (fitness(trial) > fitness(state.current)) state.current = trial;
      trackBest(state.current);
    }

    function randomStep() {
      trackBest(randomIndividual());
    }

    function step() {
      if (state.mode === 'ga') gaGeneration();
      else if (state.mode === 'hc') hcStep();
      else randomStep();
      state.gen++;
      // record best-so-far
      var bf = state.bestEver ? state.bestEver.f : 0;
      state.history.push(bf);
      if (state.history.length > 500) state.history.shift();
      draw();
    }

    // ---- rendering ----
    function draw() {
      drawLand();
      drawCurve();
      var best = state.bestEver ? state.bestEver.f.toFixed(3) : '—';
      var modeName = { random: 'random search', hc: 'hill climbing', ga: 'genetic algorithm' }[state.mode];
      statusEl.textContent = state.mode.toUpperCase() +
        ' · generation ' + state.gen +
        ' · best f = ' + best +
        (state.bestEver ? ' at x ≈ ' + state.bestEver.x.toFixed(0) + ' of ' + N : '') +
        '  (' + modeName + ')';
    }

    function drawLand() {
      var w = land.width, h = land.height;
      var pad = 10;
      lctx.clearRect(0, 0, w, h);

      function px(x) { return pad + (x / (N - 1)) * (w - 2 * pad); }
      function py(f) { return h - pad - f * (h - 2 * pad); }

      // landscape area
      lctx.beginPath();
      lctx.moveTo(px(0), h - pad);
      for (var i = 0; i < N; i++) lctx.lineTo(px(i), py(heights[i]));
      lctx.lineTo(px(N - 1), h - pad);
      lctx.closePath();
      lctx.fillStyle = '#eef0e4';
      lctx.fill();
      lctx.strokeStyle = '#9aa58a';
      lctx.lineWidth = 1;
      lctx.stroke();

      // global optimum marker
      lctx.fillStyle = '#0f6b63';
      lctx.beginPath();
      lctx.moveTo(px(globalBestX), py(globalBestF) - 8);
      lctx.lineTo(px(globalBestX) - 4, py(globalBestF) - 2);
      lctx.lineTo(px(globalBestX) + 4, py(globalBestF) - 2);
      lctx.closePath();
      lctx.fill();

      // individuals
      var drawn = [];
      if (state.mode === 'ga' || state.mode === 'random') drawn = state.pop;
      if (state.mode === 'hc' && state.current) drawn = [state.current];

      drawn.forEach(function (ind) {
        var isBest = state.bestEver && ind.x === state.bestEver.x;
        lctx.fillStyle = isBest ? '#7f0019' : 'rgba(127,0,25,0.55)';
        lctx.beginPath();
        lctx.arc(px(ind.x), py(landscape(ind.x)), isBest ? 5 : 3.5, 0, Math.PI * 2);
        lctx.fill();
      });

      // best-so-far line
      if (state.bestEver) {
        lctx.strokeStyle = '#7f0019';
        lctx.lineWidth = 1.5;
        lctx.setLineDash([4, 3]);
        lctx.beginPath();
        lctx.moveTo(pad, py(state.bestEver.f));
        lctx.lineTo(w - pad, py(state.bestEver.f));
        lctx.stroke();
        lctx.setLineDash([]);
      }
    }

    function drawCurve() {
      var w = curve.width, h = curve.height;
      cctx.clearRect(0, 0, w, h);
      if (state.history.length < 2) return;
      cctx.strokeStyle = '#0f6b63';
      cctx.lineWidth = 2;
      cctx.beginPath();
      for (var i = 0; i < state.history.length; i++) {
        var x = (i / (state.history.length - 1)) * w;
        var y = h - 4 - state.history[i] * (h - 8);
        if (i === 0) cctx.moveTo(x, y); else cctx.lineTo(x, y);
      }
      cctx.stroke();
      // goal line
      cctx.strokeStyle = 'rgba(26,107,50,0.4)';
      cctx.setLineDash([3, 3]);
      cctx.beginPath();
      cctx.moveTo(0, h - 4 - globalBestF * (h - 8));
      cctx.lineTo(w, h - 4 - globalBestF * (h - 8));
      cctx.stroke();
      cctx.setLineDash([]);
    }

    // ---- controls ----
    function setMode(mode) {
      state.mode = mode;
      container.querySelectorAll('.mode').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-mode') === mode);
      });
      reset();
    }

    function reset() {
      stop();
      initPop();
      draw();
    }

    function run() {
      readInputs();
      if (state.running) { stop(); return; }
      state.running = true;
      container.querySelector('#d-run').textContent = 'Pause';
      state.timer = setInterval(function () {
        readInputs();
        step();
      }, state.speed);
    }

    function stop() {
      state.running = false;
      clearInterval(state.timer);
      var btn = container.querySelector('#d-run');
      if (btn) btn.textContent = 'Run';
    }

    container.querySelectorAll('.mode').forEach(function (b) {
      b.addEventListener('click', function () { setMode(b.getAttribute('data-mode')); });
    });
    container.querySelector('#d-run').addEventListener('click', run);
    container.querySelector('#d-step').addEventListener('click', function () { readInputs(); step(); });
    container.querySelector('#d-reset').addEventListener('click', reset);
    [popInput, mutInput, crossInput, speedInput].forEach(function (el) {
      el.addEventListener('input', readInputs);
    });

    // CSS for the demo (scoped so it works without the lesson stylesheet too)
    var style = document.createElement('style');
    style.textContent =
      '.demo .demo-controls { display:flex; flex-wrap:wrap; gap:0.6rem 1.2rem; align-items:center; margin-bottom:0.6rem; }' +
      '.demo .demo-modes { display:flex; gap:0.3rem; }' +
      '.demo .demo-sliders { display:flex; flex-wrap:wrap; gap:0.3rem 1rem; font-family:Georgia,serif; font-size:0.85rem; }' +
      '.demo .demo-sliders label { display:flex; align-items:center; gap:0.4rem; }' +
      '.demo .demo-canvases canvas { display:block; width:100%; height:auto; border:1px solid #d8d8cc; border-radius:5px; background:#fff; }' +
      '.demo .demo-curve { margin-top:0.5rem; }' +
      '.demo .demo-status { margin-top:0.5rem; font-family:"SF Mono",Consolas,monospace; font-size:0.78rem; color:#6a6a5e; }';
    container.appendChild(style);

    setMode('ga');
  }

  global.GADemo = { mount: mount };
})(window);
