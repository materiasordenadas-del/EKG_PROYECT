'use strict';

(function createTopographyOverlay(global) {
  const PALETTE = ['#1565c0', '#c62828', '#2e7d32', '#7b1fa2', '#ef6c00', '#00695c'];
  const state = { mode: 'simple', activationCounter: 0, activeSelections: new Map() };
  const $ = id => document.getElementById(id);

  function data() { return global.ECG_TOPOGRAPHY_EDUCATION; }
  function modeData() { return data().modeDefinitions[state.mode]; }
  function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c])); }
  function roleStyle(role) { return data().uiSemantics.roleStyles[role] || data().uiSemantics.roleStyles.primary; }

  function makeChip(item, sourceType) {
    const active = state.activeSelections.has(item.id);
    return `<button type="button" class="education-chip ${active ? 'is-active' : ''}" data-topography-id="${escapeHtml(item.id)}" data-source-type="${sourceType}" aria-pressed="${active}" title="${escapeHtml(item.label)}">${escapeHtml(item.shortLabel || item.label)}</button>`;
  }

  function renderControls() {
    const current = modeData();
    $('topographyTerritoryBar').innerHTML = current.topographicTerritories.slice().sort((a, b) => a.order - b.order).map(item => makeChip(item, 'topography')).join('');
    $('coronaryCorrelationBar').innerHTML = current.coronaryCorrelations.slice().sort((a, b) => a.order - b.order).map(item => makeChip(item, 'coronary')).join('');
    document.querySelectorAll('[data-education-mode]').forEach(button => {
      const active = button.dataset.educationMode === state.mode;
      button.setAttribute('aria-pressed', String(active));
      button.classList.toggle('is-active', active);
    });
    document.querySelectorAll('[data-topography-id]').forEach(button => button.addEventListener('click', () => toggle(button.dataset.topographyId, button.dataset.sourceType)));
    renderDetails();
    renderFrames();
  }

  function findItem(id) {
    return [...modeData().topographicTerritories, ...modeData().coronaryCorrelations].find(item => item.id === id);
  }

  function toggle(id, sourceType) {
    if (state.activeSelections.has(id)) state.activeSelections.delete(id);
    else {
      const item = findItem(id);
      if (!item) return;
      state.activationCounter += 1;
      state.activeSelections.set(id, { id, sourceType, label: item.label, color: PALETTE[(state.activationCounter - 1) % PALETTE.length], activationOrder: state.activationCounter, leadGroups: item.leadGroups, item });
    }
    renderControls();
  }

  function reset() {
    state.activeSelections.clear();
    state.activationCounter = 0;
    renderControls();
  }

  function renderDetails() {
    const selections = [...state.activeSelections.values()].sort((a, b) => a.activationOrder - b.activationOrder);
    const coronary = selections.filter(selection => selection.sourceType === 'coronary');
    $('topographyLegend').innerHTML = selections.length ? selections.map(selection => {
      const styles = [...new Set(selection.leadGroups.filter(group => group.role !== 'additionalUnavailable').map(group => roleStyle(group.role).frameStyle))].join(', ');
      return `<span class="topography-legend-item"><i style="--legend-color:${selection.color}"></i>${escapeHtml(selection.label)} — ${escapeHtml(styles || 'etiqueta')}</span>`;
    }).join('') : '<span>Seleccione uno o más territorios o arterias para ver sus derivaciones.</span>';
    $('coronaryDetails').innerHTML = coronary.map(selection => {
      const item = selection.item;
      const groups = item.leadGroups.filter(group => group.role !== 'additionalUnavailable').map(group => `<li><strong>${escapeHtml(roleStyle(group.role).label)}:</strong> ${escapeHtml(group.leads.join(', '))}</li>`).join('');
      const extra = item.leadGroups.filter(group => group.role === 'additionalUnavailable').flatMap(group => group.leads);
      return `<article class="coronary-card"><h3>${escapeHtml(item.label)}</h3><p>${escapeHtml(item.summary || item.interpretation || item.oneLine || '')}</p><p><strong>Territorios habituales:</strong> ${escapeHtml((item.territories || []).join(', '))}</p><ul>${groups}</ul>${extra.length ? `<p><strong>Derivaciones adicionales:</strong> ${escapeHtml(extra.join(', '))}. No disponibles en este ECG de 12 derivaciones.</p>` : ''}<p class="clinical-caution"><strong>Límite:</strong> ${escapeHtml(item.caution || '')}</p></article>`;
    }).join('');
    const unavailable = [...new Set(selections.flatMap(selection => selection.leadGroups.filter(group => group.role === 'additionalUnavailable').flatMap(group => group.leads)))];
    $('additionalLeadNotice').innerHTML = unavailable.length ? `<strong>Derivaciones adicionales recomendadas:</strong> ${escapeHtml(unavailable.join(', '))}. No disponibles en este registro de 12 derivaciones.${unavailable.includes('V4R') ? ' V4R es la derivación clave.' : ''}` : '';
  }

  function syncGeometry() {
    const overlay = $('ecgLeadOverlay');
    const canvas = $('ecgCanvas');
    if (!overlay || !canvas) return;
    overlay.style.width = canvas.style.width;
    overlay.style.height = canvas.style.height;
  }

  function renderFrames() {
    const overlay = $('ecgLeadOverlay');
    if (!overlay || typeof global.getCurrentLeadLayout !== 'function') return;
    overlay.innerHTML = '';
    const layout = global.getCurrentLeadLayout();
    if (!layout) return;
    const byLead = new Map();
    [...state.activeSelections.values()].sort((a, b) => a.activationOrder - b.activationOrder).forEach(selection => {
      selection.leadGroups.forEach(group => {
        if (group.role === 'additionalUnavailable') return;
        const leads = [...group.leads];
        if (data().uiSemantics.includeLongLeadDuplicateWhenLeadIIIsSelected && leads.includes('II')) leads.push('II_LONG');
        leads.forEach(lead => {
          if (!layout.rects[lead]) return;
          if (!byLead.has(lead)) byLead.set(lead, []);
          byLead.get(lead).push({ selection, role: group.role });
        });
      });
    });
    byLead.forEach((frames, lead) => frames.forEach((frame, ringIndex) => {
      const base = layout.rects[lead];
      const expansion = ringIndex * 5;
      const element = document.createElement('div');
      element.className = `ecg-lead-frame frame-${roleStyle(frame.role).frameStyle}`;
      element.style.cssText = `left:${base.x + 3 - expansion}px;top:${base.y + 3 - expansion}px;width:${base.width - 6 + expansion * 2}px;height:${base.height - 6 + expansion * 2}px;border-color:${frame.selection.color}`;
      overlay.appendChild(element);
    }));
  }

  function init() {
    if (!data() || !$('topographyTerritoryBar')) return;
    document.querySelectorAll('[data-education-mode]').forEach(button => button.addEventListener('click', () => { state.mode = button.dataset.educationMode; reset(); }));
    $('resetTopographySelections').addEventListener('click', reset);
    renderControls();
  }

  global.ECGTopographyOverlay = { init, syncGeometry, renderFrames, state };
})(window);
