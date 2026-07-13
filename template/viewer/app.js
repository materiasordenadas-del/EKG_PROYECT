'use strict';

const LEAD_GRID = [
  ['I', 'aVR', 'V1', 'V4'],
  ['II', 'aVL', 'V2', 'V5'],
  ['III', 'aVF', 'V3', 'V6'],
];
const LONG_LEAD = 'II';
const PAPER_MM_PX = 8;
const PAPER_SPEED_MM_PER_SEC = 25;
const STATIC_SHORT_SEC = 2.5;
const STATIC_LONG_SEC = 10;
const ANIM_SHORT_SEC = 2.5;
const ANIM_LONG_SEC = 10;

const state = {
  catalog: [], signal: null, metadata: null, educational: null, resolutionHz: 100,
  diagnosisVisible: false, displayMode: 'animated', surfaceMode: 'paper', originalHeartRate: null, targetHeartRate: null,
  isPlaying: true, displayTimeSec: 0, rafId: 0, lastFrameTs: 0,
};

const $ = id => document.getElementById(id);

function localDataKey(url) {
  return url.replace(/^(\.\.\/)+/, '').replace(/^\.\//, '');
}

async function loadJson(url) {
  const localData = window.ECG_BANK_DATA;
  const key = localDataKey(url);
  if (localData && Object.prototype.hasOwnProperty.call(localData, key)) return localData[key];
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${url}`);
  return response.json();
}

function setStatus(message, isError = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error', isError);
}

function cycle(value, max) {
  if (max <= 0) return 0;
  value %= max;
  return value < 0 ? value + max : value;
}

function shortWindowSec() {
  return ANIM_SHORT_SEC;
}

function longWindowSec() {
  return ANIM_LONG_SEC;
}

function updateTimeReadout() {
  $('timeReadout').textContent = `t = ${state.displayTimeSec.toFixed(2).replace('.', ',')} s`;
}

function percentile(values, fraction) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.round((sorted.length - 1) * fraction)))] || 0;
}

function estimateOriginalHeartRate(signal) {
  const data = signal?.leads?.II;
  const fs = Number(signal?.sampleRateHz);
  if (!Array.isArray(data) || data.length < fs * 3 || !Number.isFinite(fs) || fs <= 0) return 60;

  const baseline = percentile(data, 0.5);
  const amplitudes = data.map(value => Math.abs(Number(value) - baseline));
  const p90 = percentile(amplitudes, 0.9);
  const threshold = p90 + (percentile(amplitudes, 0.995) - p90) * 0.3;
  const refractorySamples = Math.round(fs * 0.25);
  const peaks = [];
  for (let index = 1; index < amplitudes.length - 1; index++) {
    if (amplitudes[index] < threshold || amplitudes[index] < amplitudes[index - 1] || amplitudes[index] < amplitudes[index + 1]) continue;
    const previous = peaks[peaks.length - 1];
    if (previous !== undefined && index - previous < refractorySamples) {
      if (amplitudes[index] > amplitudes[previous]) peaks[peaks.length - 1] = index;
    } else peaks.push(index);
  }
  const intervals = [];
  for (let index = 1; index < peaks.length; index++) {
    const seconds = (peaks[index] - peaks[index - 1]) / fs;
    if (seconds >= 0.3 && seconds <= 2.5) intervals.push(seconds);
  }
  const interval = percentile(intervals, 0.5);
  const rate = interval ? Math.round(60 / interval) : 60;
  return Math.min(300, Math.max(20, rate));
}

function updateHeartRateControls() {
  const original = state.originalHeartRate || 60;
  const target = state.targetHeartRate || original;
  $('originalHeartRate').textContent = `${original} lpm`;
  $('targetHeartRateInput').value = String(target);
}

function heartRateScale() {
  const original = state.originalHeartRate || 60;
  const target = state.targetHeartRate || original;
  return target / original;
}

function traceColor() {
  return state.surfaceMode === 'monitor' ? '#39ff88' : '#101820';
}

function updateModeControls() {
  const animated = state.displayMode === 'animated';
  document.querySelectorAll('.anim-only').forEach(el => el.classList.toggle('hidden', !animated));
  if (!animated) stopPlayback();
  else if (state.isPlaying) startPlayback();
  updatePlayPauseButton();
}

function updatePlayPauseButton() {
  $('playPauseButton').textContent = state.isPlaying ? 'Pausar' : 'Reproducir';
}

function startPlayback() {
  if (state.displayMode !== 'animated' || !state.signal || state.rafId) return;
  state.isPlaying = true;
  state.lastFrameTs = 0;
  updatePlayPauseButton();
  state.rafId = requestAnimationFrame(tick);
}

function stopPlayback() {
  if (state.rafId) cancelAnimationFrame(state.rafId);
  state.rafId = 0;
  state.lastFrameTs = 0;
}

function tick(timestamp) {
  state.rafId = 0;
  if (state.displayMode !== 'animated' || !state.signal || !state.isPlaying) return;
  if (!state.lastFrameTs) state.lastFrameTs = timestamp;
  const deltaSec = (timestamp - state.lastFrameTs) / 1000;
  state.lastFrameTs = timestamp;
  state.displayTimeSec += deltaSec;
  updateTimeReadout();
  draw();
  state.rafId = requestAnimationFrame(tick);
}

async function init() {
  try {
    window.ECGTopographyOverlay?.init();
    state.catalog = await loadJson('../catalog/rhythms_catalog.json');
    if (!Array.isArray(state.catalog) || !state.catalog.length) throw new Error('El catálogo está vacío.');

    for (const item of state.catalog) {
      const option = document.createElement('option');
      option.value = item.id;
      option.textContent = item.title;
      $('rhythmSelect').appendChild(option);
    }

    $('rhythmSelect').addEventListener('change', () => loadRhythm($('rhythmSelect').value));
    $('gainSelect').addEventListener('change', draw);
    $('resolutionSelect').addEventListener('change', () => { state.resolutionHz = Number($('resolutionSelect').value); loadRhythm($('rhythmSelect').value); });
    $('displayModeSelect').addEventListener('change', () => {
      state.displayMode = $('displayModeSelect').value;
      updateModeControls();
      draw();
    });
    $('surfaceModeSelect').addEventListener('change', () => {
      state.surfaceMode = $('surfaceModeSelect').value;
      document.body.classList.toggle('monitor-surface', state.surfaceMode === 'monitor');
      draw();
    });
    $('targetHeartRateInput').addEventListener('change', () => {
      const value = Number($('targetHeartRateInput').value);
      const original = state.originalHeartRate || 60;
      state.targetHeartRate = Number.isFinite(value) ? Math.min(300, Math.max(20, Math.round(value))) : original;
      updateHeartRateControls();
    });
    $('resetHeartRateButton').addEventListener('click', () => {
      state.targetHeartRate = state.originalHeartRate || 60;
      updateHeartRateControls();
    });
    $('playPauseButton').addEventListener('click', () => {
      state.isPlaying = !state.isPlaying;
      updatePlayPauseButton();
      state.isPlaying ? startPlayback() : stopPlayback();
    });
    $('restartButton').addEventListener('click', () => {
      state.displayTimeSec = 0;
      updateTimeReadout();
      draw();
      if (state.displayMode === 'animated' && state.isPlaying) startPlayback();
    });
    $('diagnosisButton').addEventListener('click', () => {
      state.diagnosisVisible = !state.diagnosisVisible;
      $('diagnosisButton').textContent = state.diagnosisVisible ? 'Ocultar diagnóstico' : 'Mostrar diagnóstico';
      updateEducational();
    });
    window.addEventListener('resize', debounce(draw, 120));

    updateModeControls();
    await loadRhythm(state.catalog[0].id);
  } catch (error) {
    setStatus(`No se pudo abrir el banco: ${error.message}`, true);
  }
}

async function loadRhythm(id) {
  const item = state.catalog.find(x => x.id === id);
  if (!item) return;
  setStatus(`Cargando ${item.title}…`);

  try {
    const base = `../rhythms/${id}`;
    const [signal, metadata, educational] = await Promise.all([
      loadJson(`${base}/signal_${state.resolutionHz}hz.json`),
      loadJson(`${base}/metadata.json`),
      loadJson(`${base}/educational.json`).catch(() => ({ rhythmId: id, findings: [], questions: [] })),
    ]);

    state.signal = signal;
    state.metadata = metadata;
    state.educational = educational;
    const originalRateSignal = state.resolutionHz === 500 ? signal : await loadJson(`${base}/signal_500hz.json`);
    state.originalHeartRate = estimateOriginalHeartRate(originalRateSignal);
    state.targetHeartRate = state.originalHeartRate;
    updateHeartRateControls();
    state.displayTimeSec = 0;
    state.diagnosisVisible = false;
    $('diagnosisButton').textContent = 'Mostrar diagnóstico';
    $('subtitle').textContent = `${signal.source?.dataset ?? 'ECG'} · ${signal.sampleRateHz} Hz · ${signal.durationSeconds} s · amplitud en ${signal.units}`;

    updateRecordInfo();
    updateEducational();
    updateTimeReadout();
    draw();
    if (state.displayMode === 'animated' && state.isPlaying) startPlayback();
    setStatus('Registro cargado. DII y DII largo terminan en el mismo instante y mantienen la misma escala temporal.');
  } catch (error) {
    setStatus(`No se pudo cargar ${item.title}: ${error.message}`, true);
  }
}

function updateRecordInfo() {
  const m = state.metadata || {};
  const patient = m.patient || {};
  const acquisition = m.acquisition || {};
  const report = m.report || {};
  const validation = m.validation || {};
  const quality = m.quality || {};
  const comparison = m.samplingValidation || {};

  const section = (title, rows, body = '') => `
    <section class="record-section">
      <h3>${escapeHtml(title)}</h3>
      ${rows.length ? `<dl>${rows.map(([k,v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(formatMeta(v))}</dd>`).join('')}</dl>` : ''}
      ${body}
    </section>`;

  const codeDetails = Array.isArray(report.scpCodeDetails) ? report.scpCodeDetails : [];
  const codeBody = codeDetails.length ? `<div class="code-grid">${codeDetails.map(item => `
    <div class="code-card"><strong>${escapeHtml(item.code)}</strong><span>${escapeHtml(formatMeta(item.description))}</span><small>Puntuación: ${escapeHtml(formatMeta(item.probability))}</small></div>`).join('')}</div>` : '<p>No hay códigos SCP.</p>';

  const leadResults = comparison.leads || {};
  const comparisonBody = `<div class="validation-box ${comparison.allPrecordialsPreserved ? 'ok' : 'warn'}">
    <strong>${escapeHtml(formatMeta(comparison.conclusion))}</strong>
    <table class="meta-table"><thead><tr><th>Derivación</th><th>Correlación</th><th>Diferencia pico-pico</th><th>Conservada</th></tr></thead><tbody>
    ${Object.entries(leadResults).map(([lead, value]) => `<tr><td>${escapeHtml(lead)}</td><td>${escapeHtml(formatMeta(value.correlation100vs500))}</td><td>${escapeHtml(formatMeta(value.peakToPeakDifferencePercent))}%</td><td>${value.morphologyPreserved ? 'Sí' : 'No'}</td></tr>`).join('')}
    </tbody></table></div>`;

  $('recordSections').innerHTML = [
    section('Paciente', [['ID del paciente', patient.patientId], ['Edad', patient.age], ['Sexo', patient.sex], ['Altura', patient.height], ['Peso', patient.weight]]),
    section('Adquisición', [['Fecha del registro', acquisition.recordingDate], ['Dispositivo', acquisition.device], ['Centro', acquisition.site], ['Personal de adquisición', acquisition.nurse], ['ID del ECG', m.ecgId]]),
    section('Informe', [['Informe original', report.original], ['Informe autogenerado inicial', report.initialAutogenerated], ['Eje cardíaco', report.heartAxis], ['Estadio de infarto 1', report.infarctionStadium1], ['Estadio de infarto 2', report.infarctionStadium2], ['Registro puro', report.isPure ? 'Sí' : 'No'], ['Códigos concomitantes', Array.isArray(report.concomitantCodes) ? report.concomitantCodes.join(', ') : report.concomitantCodes]], codeBody),
    section('Validación', [['Validado por humano', validation.validatedByHuman ? 'Sí' : 'No'], ['Segunda opinión', validation.secondOpinion ? 'Sí' : 'No'], ['Validador', validation.validatedBy], ['Grupo de partición', validation.stratFold], ['Estado', validation.selectionReview]]),
    section('Calidad técnica', [['Deriva de línea de base', quality.baselineDrift], ['Ruido estático', quality.staticNoise], ['Ruido en ráfagas', quality.burstNoise], ['Problemas de electrodos', quality.electrodeProblems], ['Latidos extras', quality.extraBeats], ['Marcapasos', quality.pacemaker]]),
    section('Comparación 100 vs 500 Hz — V2 a V5', [], comparisonBody),
  ].join('');
}

function formatMeta(value) {
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'No indicado';
  if (typeof value === 'object' && value !== null) return JSON.stringify(value);
  if (value === null || value === undefined || value === '' || String(value).toLowerCase() === 'nan') return 'No indicado';
  return String(value);
}

function normalizeMeta(value) {
  if (value === null || value === undefined || value === '' || String(value).toLowerCase() === 'nan') return 'No indicado';
  return String(value);
}

function updateEducational() {
  const e = state.educational || {};
  const diagnosis = state.diagnosisVisible ? (state.signal?.title ?? '') : 'Diagnóstico oculto';
  const findings = Array.isArray(e.findings) && e.findings.length
    ? `<ul class="finding-list">${e.findings.map(f => `<li>${escapeHtml(f.label || String(f))}</li>`).join('')}</ul>`
    : '<p>Todavía no hay hallazgos educativos cargados.</p>';
  $('educationalContent').innerHTML = `<div class="diagnosis">${escapeHtml(diagnosis)}</div>${findings}`;
}

function draw() {
  const signal = state.signal;
  if (!signal) return;

  const canvas = $('ecgCanvas');
  const marginX = 36, marginTop = 34, marginBottom = 26;
  const paperWidth = STATIC_LONG_SEC * PAPER_SPEED_MM_PER_SEC * PAPER_MM_PX;
  const cssWidth = paperWidth + marginX * 2;
  const cssHeight = 760;
  const dpr = window.devicePixelRatio || 1;

  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;

  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const width = cssWidth - marginX * 2;
  const height = cssHeight - marginTop - marginBottom;
  drawGrid(ctx, marginX, marginTop, width, height);

  const topHeight = height * 0.72;
  const rowHeight = topHeight / 3;
  const colWidth = width / 4;
  const longTop = marginTop + topHeight + 16;
  const longHeight = height - topHeight - 16;
  const gain = Number($('gainSelect').value);
  const fs = Number(signal.sampleRateHz);

  if (state.displayMode === 'static') {
    drawStatic(ctx, signal, fs, marginX, marginTop, colWidth, rowHeight, width, longTop, longHeight, gain);
  } else {
    drawAnimated(ctx, signal, fs, marginX, marginTop, colWidth, rowHeight, width, longTop, longHeight, gain);
  }

  if (state.surfaceMode === 'paper') drawCalibration(ctx, marginX + 4, marginTop + 3, gain);
  window.ECGTopographyOverlay?.syncGeometry();
  window.ECGTopographyOverlay?.renderFrames();
}

function getCurrentLeadLayout() {
  const canvas = $('ecgCanvas');
  const cssWidth = parseFloat(canvas?.style.width);
  const cssHeight = parseFloat(canvas?.style.height);
  if (!Number.isFinite(cssWidth) || !Number.isFinite(cssHeight)) return null;
  const marginX = 36, marginTop = 34, marginBottom = 26;
  const width = cssWidth - marginX * 2;
  const height = cssHeight - marginTop - marginBottom;
  const topHeight = height * 0.72;
  const rowHeight = topHeight / 3;
  const colWidth = width / 4;
  const longTop = marginTop + topHeight + 16;
  const longHeight = height - topHeight - 16;
  const rects = {};
  LEAD_GRID.forEach((rowLeads, row) => rowLeads.forEach((lead, col) => {
    rects[lead] = { x: marginX + col * colWidth, y: marginTop + row * rowHeight, width: colWidth, height: rowHeight };
  }));
  rects.II_LONG = { x: marginX, y: longTop, width, height: longHeight };
  return { cssWidth, cssHeight, rects };
}

function drawStatic(ctx, signal, fs, marginX, marginTop, colWidth, rowHeight, width, longTop, longHeight, gain) {
  const shortSec = STATIC_SHORT_SEC;
  const longSec = Math.min(STATIC_LONG_SEC, signal.durationSeconds);
  const scale = heartRateScale();

  for (let row = 0; row < 3; row++) {
    for (let col = 0; col < 4; col++) {
      const lead = LEAD_GRID[row][col];
      drawLeadSegment(ctx, signal.leads[lead], fs, col * shortSec, shortSec, scale,
        marginX + col * colWidth, marginTop + row * rowHeight, colWidth, rowHeight, gain, lead);
    }
  }

  drawLeadSegment(ctx, signal.leads[LONG_LEAD], fs, 0, longSec, scale,
    marginX, longTop, width, longHeight, gain, `${LONG_LEAD} largo`);
}

function drawAnimated(ctx, signal, fs, marginX, marginTop, colWidth, rowHeight, width, longTop, longHeight, gain) {
  const shortSec = shortWindowSec();
  const longSec = longWindowSec();
  const displayEndSec = state.displayTimeSec;
  const scale = heartRateScale();

  for (let row = 0; row < 3; row++) {
    for (let col = 0; col < 4; col++) {
      const lead = LEAD_GRID[row][col];
      const x = marginX + col * colWidth;
      const y = marginTop + row * rowHeight;
      drawCircularWindow(ctx, signal.leads[lead], fs, displayEndSec - shortSec, shortSec, scale,
        x, y, colWidth, rowHeight, gain, lead);
      drawCursorBar(ctx, x + colWidth - 3, y, rowHeight);
    }
  }

  drawCircularWindow(ctx, signal.leads[LONG_LEAD], fs, displayEndSec - longSec, longSec, scale,
    marginX, longTop, width, longHeight, gain, `${LONG_LEAD} largo`);
  drawCursorBar(ctx, marginX + width - 3, longTop, longHeight);
}

function sampleAt(data, timeSec, sampleRate) {
  const sourceDuration = data.length / sampleRate;
  const sourceTime = cycle(timeSec, sourceDuration);
  const position = sourceTime * sampleRate;
  const index0 = Math.floor(position) % data.length;
  const index1 = (index0 + 1) % data.length;
  const fraction = position - Math.floor(position);
  return Number(data[index0]) * (1 - fraction) + Number(data[index1]) * fraction;
}

function drawCircularWindow(ctx, data, fs, displayStartSec, windowSec, scale, x, y, width, height, gain, label) {
  if (!Array.isArray(data) || !data.length || windowSec <= 0) return;

  const centerY = y + height / 2;
  const pxPerMv = PAPER_MM_PX * gain;
  const sampleCount = Math.max(2, Math.round(windowSec * fs * scale));

  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, width, height);
  ctx.clip();
  drawBaseline(ctx, x, y, width, height);

  ctx.strokeStyle = traceColor();
  ctx.lineWidth = 1.35;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();

  for (let i = 0; i < sampleCount; i++) {
    const ratio = i / (sampleCount - 1);
    const displayTime = displayStartSec + ratio * windowSec;
    const sourceTime = displayTime * scale;
    const px = x + ratio * width;
    const py = centerY - sampleAt(data, sourceTime, fs) * pxPerMv;
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  }

  ctx.stroke();
  drawLeadLabel(ctx, label, x, y);
  ctx.restore();
}

function drawLeadSegment(ctx, data, fs, displayStartSec, durationSec, scale, x, y, width, height, gain, label) {
  if (!Array.isArray(data) || !data.length || durationSec <= 0) return;

  const pointCount = Math.max(2, Math.round(durationSec * fs * scale));
  const centerY = y + height / 2;
  const pxPerMv = PAPER_MM_PX * gain;

  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, width, height);
  ctx.clip();
  drawBaseline(ctx, x, y, width, height);

  if (pointCount >= 2) {
    ctx.strokeStyle = traceColor();
    ctx.lineWidth = 1.35;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    for (let i = 0; i < pointCount; i++) {
      const ratio = i / (pointCount - 1);
      const displayTime = displayStartSec + ratio * durationSec;
      const sourceTime = displayTime * scale;
      const px = x + ratio * width;
      const py = centerY - sampleAt(data, sourceTime, fs) * pxPerMv;
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    }
    ctx.stroke();
  }

  drawLeadLabel(ctx, label, x, y);
  ctx.restore();
}

function drawBaseline(ctx, x, y, width, height) {
  if (state.surfaceMode === 'monitor') return;
  const centerY = y + height / 2;
  ctx.strokeStyle = 'rgba(16,24,32,.22)';
  ctx.lineWidth = 0.7;
  ctx.beginPath();
  ctx.moveTo(x, centerY);
  ctx.lineTo(x + width, centerY);
  ctx.stroke();
}

function drawGrid(ctx, x, y, width, height) {
  if (state.surfaceMode === 'monitor') {
    ctx.fillStyle = '#030706';
    ctx.fillRect(x, y, width, height);
    return;
  }
  const small = PAPER_MM_PX;
  ctx.save();
  ctx.fillStyle = '#fffdfd';
  ctx.fillRect(x, y, width, height);
  ctx.lineWidth = 0.45;
  ctx.strokeStyle = 'rgba(225,95,95,.24)';
  ctx.beginPath();
  for (let xx = x; xx <= x + width + .1; xx += small) { ctx.moveTo(xx, y); ctx.lineTo(xx, y + height); }
  for (let yy = y; yy <= y + height + .1; yy += small) { ctx.moveTo(x, yy); ctx.lineTo(x + width, yy); }
  ctx.stroke();
  ctx.lineWidth = 0.8;
  ctx.strokeStyle = 'rgba(205,60,60,.38)';
  ctx.beginPath();
  for (let xx = x; xx <= x + width + .1; xx += small * 5) { ctx.moveTo(xx, y); ctx.lineTo(xx, y + height); }
  for (let yy = y; yy <= y + height + .1; yy += small * 5) { ctx.moveTo(x, yy); ctx.lineTo(x + width, yy); }
  ctx.stroke();
  ctx.restore();
}

function drawLeadLabel(ctx, label, x, y) {
  ctx.save();
  ctx.fillStyle = state.surfaceMode === 'monitor' ? '#7dffad' : '#111820';
  ctx.font = '700 13px system-ui, sans-serif';
  ctx.fillText(label, x + 8, y + 18);
  ctx.restore();
}

function drawCursorBar(ctx, x, y, height) {
  ctx.save();
  ctx.strokeStyle = state.surfaceMode === 'monitor' ? '#39ff88' : '#157347';
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(x, y + 2);
  ctx.lineTo(x, y + height - 2);
  ctx.stroke();
  ctx.restore();
}

function drawCalibration(ctx, x, y, gain) {
  const mm = PAPER_MM_PX;
  const height = gain * mm;
  const width = 5 * mm;
  const base = y + 105;
  ctx.save();
  ctx.strokeStyle = '#101820';
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.moveTo(x, base);
  ctx.lineTo(x + mm, base);
  ctx.lineTo(x + mm, base - height);
  ctx.lineTo(x + mm + width, base - height);
  ctx.lineTo(x + mm + width, base);
  ctx.lineTo(x + mm * 2 + width, base);
  ctx.stroke();
  ctx.restore();
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

init();
