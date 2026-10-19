'use strict';

/* ---------- constants ---------- */
const PILLARS = {
  P1: 'Learning from sparse and evolving evidence',
  P2: 'Representing and generalizing preferences',
  P3: 'When to infer, ask, act, or defer',
  P4: 'Evaluating user-specific interaction',
};
const CELLS = {
  outcome_population: { name: 'General preference optimization', row: 'Outcome', col: 'Population' },
  outcome_individual: { name: 'Personalized preferences and rewards', row: 'Outcome', col: 'Individual' },
  procedure_population: { name: 'Shared interaction policies', row: 'Procedure', col: 'Population' },
  procedure_individual: { name: 'User-specific interaction policies', row: 'Procedure', col: 'Individual' },
};
const LEVELS = [
  { key: 'yes', label: 'Yes' },
  { key: 'partial', label: 'Partial' },
  { key: 'no', label: 'No' },
  { key: 'not established', label: 'Not established' },
];
const STATUS_FIELDS = [
  { key: 'per_user', label: "Learns from an individual's evidence" },
  { key: 'across_sessions', label: 'Adapts across sessions' },
  { key: 'transfer', label: 'Reports a transfer evaluation' },
];
const STAGES = [
  { label: 'All papers in the map', test: () => true },
  { label: "Learns from an individual's evidence", test: p => isOn(p.per_user) },
  { label: '… and adapts interaction decisions', test: p => isOn(p.per_user) && p.decisions.length > 0 },
  { label: '… and adapts across sessions', test: p => STAGES[2].test(p) && isOn(p.across_sessions) },
  { label: '… and reports a transfer evaluation', test: p => STAGES[3].test(p) && isOn(p.transfer) },
];
const T1_COLS = [
  ['user_evidence', 'User-specific evidence'],
  ['interaction_decisions', 'Interaction decisions'],
  ['longitudinal', 'Longitudinal'],
  ['cross_task_transfer', 'Cross-task transfer'],
  ['individual_evaluation', 'Individual evaluation'],
];
const EARLY = 2016; // years before this are grouped in the year chart

let PAPERS = [];
let META = {};
const state = { q: '', category: '', pillar: '', cell: '', decision: '', stage: 0, year: '', cited: false, status: null, sort: 'year' };

/* ---------- helpers ---------- */
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const isOn = f => f.level === 'yes' || f.level === 'partial';
const levelKey = l => (l === 'n/a' ? 'no' : l);
const levelLabel = l => (LEVELS.find(x => x.key === levelKey(l)) || { label: l }).label;
const svgNS = 'http://www.w3.org/2000/svg';
const readable = s => String(s ?? '').replace(/\b(outcome|procedure)_(population|individual|averaged)\b/g, (m, a, b) => `${a} · ${b === 'averaged' ? 'population' : b}`);
const yearKey = y => (y && y < EARLY ? 'pre' : String(y ?? ''));

function seqStep(value, max) {
  if (!value) return 0;
  return Math.max(1, Math.min(7, Math.ceil((value / max) * 7)));
}

/* ---------- tooltip ---------- */
const tip = () => $('tooltip');
function showTip(evt, html) {
  const t = tip();
  t.innerHTML = html;
  t.hidden = false;
  const pad = 12;
  const r = t.getBoundingClientRect();
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + r.width > window.innerWidth - 8) x = evt.clientX - r.width - pad;
  if (y + r.height > window.innerHeight - 8) y = evt.clientY - r.height - pad;
  t.style.left = `${x}px`;
  t.style.top = `${y}px`;
}
function hideTip() { tip().hidden = true; }
function withTip(node, html) {
  node.addEventListener('pointermove', e => showTip(e, html));
  node.addEventListener('pointerleave', hideTip);
  node.addEventListener('focus', () => {
    const b = node.getBoundingClientRect();
    showTip({ clientX: b.left + b.width / 2, clientY: b.top }, html);
  });
  node.addEventListener('blur', hideTip);
}

function dataTable(rows, headers) {
  return `<details class="data-table"><summary>Show data</summary><table><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></details>`;
}

/* ---------- horizontal bar chart (SVG) ---------- */
function plotWidth(container) {
  return Math.max(280, Math.round(container.clientWidth || 520));
}

function hbars(container, items, { onClick, isActive, unit = 'papers', labelWidth } = {}) {
  const W = plotWidth(container);
  const stacked = W < 460;
  const rowH = stacked ? 40 : 30, barH = 16, gap = stacked ? 20 : (rowH - barH) / 2;
  const longest = Math.max(...items.map(i => i.label.length));
  const lw = stacked ? 0 : (labelWidth || Math.min(250, Math.max(90, longest * 6.6)));
  const valW = 40, plotW = W - lw - valW;
  const max = Math.max(1, ...items.map(i => i.value));
  const H = items.length * rowH;
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('role', 'group');
  items.forEach((it, i) => {
    const y = i * rowH;
    const w = it.value ? Math.max(3, (it.value / max) * plotW) : 0;
    const g = document.createElementNS(svgNS, 'g');
    g.setAttribute('class', `mark${isActive && isActive(it) ? ' on' : ''}`);
    if (onClick) {
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      g.setAttribute('aria-label', `${it.label}: ${it.value} ${unit}. Filter papers.`);
      g.addEventListener('click', () => onClick(it));
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(it); } });
    }
    const r = 4;
    const x0 = lw, yb = y + gap;
    const path = w > r
      ? `M${x0},${yb} H${x0 + w - r} Q${x0 + w},${yb} ${x0 + w},${yb + r} V${yb + barH - r} Q${x0 + w},${yb + barH} ${x0 + w - r},${yb + barH} H${x0} Z`
      : `M${x0},${yb} h${w} v${barH} h${-w} Z`;
    g.innerHTML = `<rect class="hit" x="0" y="${y}" width="${W}" height="${rowH}"></rect>
      ${stacked ? `<text class="lab" x="0" y="${y + 14}">${esc(it.label)}</text>` : `<text class="lab" x="${lw - 10}" y="${y + rowH / 2 + 4}" text-anchor="end">${esc(it.label)}</text>`}
      <path class="bar" d="${path}"></path>
      <text class="val" x="${x0 + w + 6}" y="${yb + barH / 2 + 4}">${it.value}</text>`;
    withTip(g, `<strong>${esc(it.label)}</strong><br>${it.value} ${unit}${it.note ? `<br>${esc(it.note)}` : ''}`);
    svg.appendChild(g);
  });
  container.innerHTML = '';
  container.appendChild(svg);
  container.insertAdjacentHTML('beforeend', dataTable(items.map(i => [i.label, i.value]), ['', unit]));
}

/* ---------- vertical bars by year ---------- */
function yearChart(container) {
  const counts = new Map();
  PAPERS.forEach(p => { if (p.year) { const k = yearKey(p.year); counts.set(k, (counts.get(k) || 0) + 1); } });
  const years = [...counts.keys()].filter(k => k !== 'pre').map(Number).sort((a, b) => a - b);
  const items = [];
  if (counts.has('pre')) items.push({ key: 'pre', label: `Before ${EARLY}`, short: `<${EARLY}`, value: counts.get('pre') });
  const lo = Math.min(...years), hi = Math.max(...years);
  for (let y = lo; y <= hi; y++) items.push({ key: String(y), label: String(y), short: `'${String(y).slice(2)}`, value: counts.get(String(y)) || 0 });
  const W = plotWidth(container), H = 190, padL = 28, padB = 24, padT = 16;
  const plotW = W - padL, plotH = H - padB - padT;
  const max = Math.max(...items.map(i => i.value));
  const niceMax = Math.ceil(max / 10) * 10;
  const slot = plotW / items.length, barW = Math.min(30, slot - 6);
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  let grid = '';
  for (let v = 0; v <= niceMax; v += niceMax / 2) {
    const y = padT + plotH - (v / niceMax) * plotH;
    grid += `<line class="gridline" x1="${padL}" x2="${W}" y1="${y}" y2="${y}"></line><text class="axis" x="${padL - 6}" y="${y + 4}" text-anchor="end">${v}</text>`;
  }
  svg.innerHTML = grid;
  items.forEach((it, i) => {
    const h = it.value ? Math.max(2, (it.value / niceMax) * plotH) : 0;
    const x = padL + i * slot + (slot - barW) / 2, yTop = padT + plotH - h;
    const r = Math.min(4, h / 2);
    const g = document.createElementNS(svgNS, 'g');
    g.setAttribute('class', `mark${state.year === it.key ? ' on' : ''}`);
    g.setAttribute('tabindex', '0');
    g.setAttribute('role', 'button');
    g.setAttribute('aria-label', `${it.label}: ${it.value} papers. Filter papers.`);
    const d = h ? `M${x},${padT + plotH} V${yTop + r} Q${x},${yTop} ${x + r},${yTop} H${x + barW - r} Q${x + barW},${yTop} ${x + barW},${yTop + r} V${padT + plotH} Z` : '';
    g.innerHTML = `<rect class="hit" x="${padL + i * slot}" y="${padT}" width="${slot}" height="${plotH}"></rect>
      ${d ? `<path class="bar" d="${d}"></path>` : ''}
      ${slot >= 26 || i % 2 === items.length % 2 ? `<text class="axis" x="${x + barW / 2}" y="${H - 6}" text-anchor="middle">${esc(it.short)}</text>` : ''}
      ${it.value >= max * 0.5 ? `<text class="val" x="${x + barW / 2}" y="${yTop - 5}" text-anchor="middle">${it.value}</text>` : ''}`;
    const act = () => setFilter({ year: state.year === it.key ? '' : it.key });
    g.addEventListener('click', act);
    g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); } });
    withTip(g, `<strong>${esc(it.label)}</strong><br>${it.value} paper${it.value === 1 ? '' : 's'}`);
    svg.appendChild(g);
  });
  container.innerHTML = '';
  container.appendChild(svg);
  container.insertAdjacentHTML('beforeend', dataTable(items.map(i => [i.label, i.value]), ['Year', 'Papers']));
}

/* ---------- 2x2 ---------- */
function cellChart(container) {
  const counts = Object.fromEntries(Object.keys(CELLS).map(k => [k, PAPERS.filter(p => p.cell === k).length]));
  const unclassified = PAPERS.filter(p => !p.cell).length;
  const max = Math.max(...Object.values(counts));
  const btn = k => {
    const n = counts[k], s = seqStep(n, max);
    return `<button type="button" class="cell s${s}${k === 'procedure_individual' ? ' usil' : ''}${state.cell === k ? ' on' : ''}" data-cell="${k}" style="background:var(--seq-${s})" aria-label="${esc(CELLS[k].name)}: ${n} papers. Filter papers."><strong>${n}</strong><span>${esc(CELLS[k].name)}</span></button>`;
  };
  container.innerHTML = `<div class="cells">
      <span></span><span class="ax"><b>Population</b>shared across users</span><span class="ax"><b>Individual</b>adapted to one user</span>
      <span class="ay"><b>Outcome</b>what is produced</span>${btn('outcome_population')}${btn('outcome_individual')}
      <span class="ay"><b>Procedure</b>how work is done</span>${btn('procedure_population')}${btn('procedure_individual')}
    </div>
    <p class="cells-note">Placed by two labels: whether a paper learns from an individual's evidence, and whether it affects interaction decisions. ${unclassified} papers lack one of these labels and are not placed. The quadrants are not mutually exclusive in practice.</p>
    ${dataTable(Object.keys(CELLS).map(k => [CELLS[k].row, CELLS[k].col, counts[k]]).concat([['Not placed', '', unclassified]]), ['Personalizes', 'For', 'Papers'])}`;
  container.querySelectorAll('button.cell').forEach(b => {
    b.addEventListener('click', () => setFilter({ cell: state.cell === b.dataset.cell ? '' : b.dataset.cell }));
    withTip(b, `<strong>${esc(CELLS[b.dataset.cell].row)} · ${esc(CELLS[b.dataset.cell].col)}</strong><br>${counts[b.dataset.cell]} papers`);
  });
}

/* ---------- stacked status bars ---------- */
function statusChart(container) {
  const W = plotWidth(container), stacked = W < 460;
  const lw = stacked ? 0 : 210, rowH = stacked ? 44 : 34, barH = 18, plotW = W - lw;
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${STATUS_FIELDS.length * rowH}`);
  const rows = [];
  STATUS_FIELDS.forEach((f, i) => {
    const y = stacked ? i * rowH + 20 : i * rowH + (rowH - barH) / 2;
    const counts = LEVELS.map(l => PAPERS.filter(p => levelKey(p[f.key].level) === l.key).length);
    rows.push([f.label, ...counts]);
    const total = counts.reduce((a, b) => a + b, 0);
    svg.insertAdjacentHTML('beforeend', stacked ? `<text x="0" y="${y - 6}">${esc(f.label)}</text>` : `<text x="${lw - 10}" y="${y + barH / 2 + 4}" text-anchor="end">${esc(f.label)}</text>`);
    let x = lw;
    LEVELS.forEach((l, j) => {
      const w = (counts[j] / total) * plotW;
      if (!w) return;
      const g = document.createElementNS(svgNS, 'g');
      const on = state.status && state.status.field === f.key && state.status.level === l.key;
      g.setAttribute('class', `mark${on ? ' on' : ''}`);
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      g.setAttribute('aria-label', `${f.label}, ${l.label}: ${counts[j]} papers. Filter papers.`);
      const fill = `var(--lv-${l.key === 'not established' ? 'ne' : l.key})`;
      g.innerHTML = `<rect x="${x + 1}" y="${y}" width="${Math.max(1, w - 2)}" height="${barH}" rx="2" style="fill:${fill};cursor:pointer;${on ? 'stroke:var(--accent);stroke-width:2' : ''}"></rect>`;
      const act = () => setFilter({ status: on ? null : { field: f.key, level: l.key } });
      g.addEventListener('click', act);
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); } });
      withTip(g, `<strong>${esc(f.label)}</strong><br>${esc(l.label)}: ${counts[j]} of ${total} (${Math.round((counts[j] / total) * 100)}%)`);
      svg.appendChild(g);
      x += w;
    });
  });
  container.innerHTML = '';
  container.appendChild(svg);
  container.insertAdjacentHTML('beforeend', `<div class="status-legend">${LEVELS.map(l => `<span class="lv lv-${l.key === 'not established' ? 'ne' : l.key}">${l.label}</span>`).join('')}</div>`);
  container.insertAdjacentHTML('beforeend', dataTable(rows, ['', ...LEVELS.map(l => l.label)]));
}

/* ---------- category x pillar matrix ---------- */
function matrixChart(container) {
  const cats = META.categories.filter(c => PAPERS.some(p => p.category === c));
  const pills = Object.keys(PILLARS);
  const n = (c, k) => PAPERS.filter(p => p.category === c && p.pillars.includes(k)).length;
  const max = Math.max(...cats.flatMap(c => pills.map(k => n(c, k))));
  container.innerHTML = `<div class="matrix-scroll"><table class="matrix"><thead><tr><th>Research area</th>${pills.map(k => `<th title="${esc(PILLARS[k])}">${k}</th>`).join('')}</tr></thead><tbody>${cats.map(c => `<tr><td>${esc(c)}</td>${pills.map(k => {
    const v = n(c, k), s = seqStep(v, max);
    const on = state.category === c && state.pillar === k;
    return v ? `<td><button type="button" class="s${s}${on ? ' on' : ''}" style="background:var(--seq-${s})" data-c="${esc(c)}" data-k="${k}" aria-label="${esc(c)}, ${k}: ${v} papers. Filter papers.">${v}</button></td>` : '<td class="zero">–</td>';
  }).join('')}</tr>`).join('')}</tbody></table></div>`;
  container.querySelectorAll('button').forEach(b => {
    b.addEventListener('click', () => {
      const on = state.category === b.dataset.c && state.pillar === b.dataset.k;
      setFilter(on ? { category: '', pillar: '' } : { category: b.dataset.c, pillar: b.dataset.k });
    });
    withTip(b, `<strong>${esc(b.dataset.c)}</strong><br>${b.dataset.k}: ${esc(PILLARS[b.dataset.k])}<br>${b.textContent} papers`);
  });
}

/* ---------- charts ---------- */
function drawCharts() {
  const plot = id => document.querySelector(`#${id} .plot`);
  hbars(plot('chart-funnel'), STAGES.map((s, i) => ({ key: i, label: s.label, value: PAPERS.filter(s.test).length })), {
    onClick: it => setFilter({ stage: state.stage === it.key ? 0 : it.key }),
    isActive: it => it.key !== 0 && state.stage === it.key,
    labelWidth: 230,
  });
  cellChart(plot('chart-cells'));
  yearChart(plot('chart-years'));
  const decCounts = {};
  PAPERS.forEach(p => p.decisions.forEach(d => { decCounts[d] = (decCounts[d] || 0) + 1; }));
  const decItems = Object.entries(decCounts).filter(([k]) => k !== 'Other').sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ key: k, label: k, value: v }));
  hbars(plot('chart-decisions'), decItems, {
    onClick: it => setFilter({ decision: state.decision === it.key ? '' : it.key }),
    isActive: it => state.decision === it.key,
  });
  statusChart(plot('chart-status'));
  hbars(plot('chart-categories'), META.categories.map(c => ({ key: c, label: c, value: PAPERS.filter(p => p.category === c).length })), {
    onClick: it => setFilter({ category: state.category === it.key && !state.pillar ? '' : it.key, pillar: '' }),
    isActive: it => state.category === it.key,
  });
  matrixChart(plot('chart-matrix'));
}

/* ---------- Table 1 ---------- */
function drawTable1() {
  const byId = Object.fromEntries(PAPERS.map(p => [p.id, p]));
  const rows = META.table1_order.map(k => byId[k]).filter(Boolean);
  let group = '';
  const body = rows.map(p => {
    const t = p.table1;
    const head = t.group !== group ? `<tr class="grp"><td colspan="${T1_COLS.length + 2}">${esc(t.group)}</td></tr>` : '';
    group = t.group;
    const cells = T1_COLS.map(([k, label]) => {
      const lv = t[k], cls = lv === 'not established' ? 'ne' : lv;
      return `<td class="r"><span class="rate rate-${cls}" role="img" aria-label="${esc(label)}: ${esc(levelLabel(lv))}" title="${esc(levelLabel(lv))}"></span></td>`;
    }).join('');
    return `${head}<tr><td><button type="button" class="linkish" data-id="${esc(p.id)}">${esc(t.name)}</button> <span class="muted">${p.year ?? ''}</span>${t.note ? `<br><span class="src">${esc(t.note)}</span>` : ''}</td><td>${esc(t.learns)}</td>${cells}</tr>`;
  }).join('');
  $('table1').innerHTML = `<thead><tr><th>Work</th><th>What is learned or evaluated</th>${T1_COLS.map(([, l]) => `<th class="r">${esc(l)}</th>`).join('')}</tr></thead><tbody>${body}</tbody>`;
  $('table1').querySelectorAll('button[data-id]').forEach(b => b.addEventListener('click', () => openPaper(b.dataset.id)));
}

/* ---------- filtering ---------- */
function filtered() {
  const q = state.q.trim().toLowerCase();
  const stage = STAGES[state.stage];
  return PAPERS.filter(p =>
    (!state.category || p.category === state.category) &&
    (!state.pillar || p.pillars.includes(state.pillar)) &&
    (!state.cell || p.cell === state.cell) &&
    (!state.decision || p.decisions.includes(state.decision)) &&
    (!state.year || yearKey(p.year) === state.year) &&
    (!state.cited || p.cited) &&
    (!state.status || levelKey(p[state.status.field].level) === state.status.level) &&
    stage.test(p) &&
    (!q || [p.title, p.authors, p.venue, p.summary, p.relation, p.category].join(' ').toLowerCase().includes(q))
  );
}

function chips() {
  const list = [];
  if (state.q) list.push(['q', `Search: "${state.q}"`, { q: '' }]);
  if (state.category) list.push(['category', state.category, { category: '' }]);
  if (state.pillar) list.push(['pillar', `${state.pillar}: ${PILLARS[state.pillar]}`, { pillar: '' }]);
  if (state.cell) list.push(['cell', `${CELLS[state.cell].row} · ${CELLS[state.cell].col}`, { cell: '' }]);
  if (state.decision) list.push(['decision', `Decision: ${state.decision}`, { decision: '' }]);
  if (state.stage) list.push(['stage', STAGES[state.stage].label.replace('… and ', 'Also ').replace(/^./, c => c.toUpperCase()), { stage: 0 }]);
  if (state.year) list.push(['year', state.year === 'pre' ? `Before ${EARLY}` : state.year, { year: '' }]);
  if (state.status) {
    const f = STATUS_FIELDS.find(x => x.key === state.status.field);
    list.push(['status', `${f.label}: ${levelLabel(state.status.level)}`, { status: null }]);
  }
  if (state.cited) list.push(['cited', 'Cited in the position paper', { cited: false }]);
  $('chips').innerHTML = list.map(([k, label], i) => `<button type="button" class="chip" data-i="${i}" aria-label="Remove filter ${esc(label)}">${esc(label)}</button>`).join('');
  $('chips').querySelectorAll('.chip').forEach(b => b.addEventListener('click', () => setFilter(list[Number(b.dataset.i)][2])));
}

function sortPapers(list) {
  const cmp = {
    year: (a, b) => (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title),
    title: (a, b) => a.title.localeCompare(b.title),
    area: (a, b) => META.categories.indexOf(a.category) - META.categories.indexOf(b.category) || (b.year || 0) - (a.year || 0),
  }[state.sort];
  return list.slice().sort(cmp);
}

function renderResults() {
  const list = sortPapers(filtered());
  $('result-count').textContent = `${list.length} of ${PAPERS.length} papers`;
  $('results').innerHTML = list.length ? list.map(p => `
    <article class="paper">
      <div class="meta"><span>${p.year ?? ''}</span><span>${esc(p.venue)}</span>${p.cited ? '<span class="badge badge-cited">Cited</span>' : ''}${p.provenance.table1_verified ? '<span class="badge badge-t1">Table 1</span>' : p.summary_source === 'full text' ? '<span class="badge badge-full">Full text</span>' : ''}</div>
      <h3><button type="button" data-id="${esc(p.id)}">${esc(p.title)}</button></h3>
      <p class="authors">${esc(p.authors)}</p>
      <p class="summary">${esc(p.summary)}</p>
      <div class="tags">
        <span class="tag">${esc(p.category)}</span>
        ${p.cell ? `<span class="tag tag-cell">${esc(CELLS[p.cell].row)} · ${esc(CELLS[p.cell].col)}</span>` : ''}
        ${p.pillars.map(k => `<span class="tag" title="${esc(PILLARS[k])}">${k}</span>`).join('')}
      </div>
    </article>`).join('') : '<div class="empty">No papers match these filters. Remove a filter above or clear them all.</div>';
  $('results').querySelectorAll('button[data-id]').forEach(b => b.addEventListener('click', () => openPaper(b.dataset.id)));
}

function syncControls() {
  $('f-q').value = state.q;
  $('f-category').value = state.category;
  $('f-pillar').value = state.pillar;
  $('f-cell').value = state.cell;
  $('f-decision').value = state.decision;
  $('f-sort').value = state.sort;
  $('f-cited').checked = state.cited;
}

function setFilter(patch, { scroll = true } = {}) {
  Object.assign(state, patch);
  syncControls();
  drawCharts();
  chips();
  renderResults();
  hideTip();
  if (scroll && !('q' in patch) && !('sort' in patch)) {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    $('browse').scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }
}

/* ---------- detail dialog ---------- */
function openPaper(id) {
  const p = PAPERS.find(x => x.id === id);
  if (!p) return;
  const row = (k, v) => (v ? `<dt>${esc(k)}</dt><dd>${v}</dd>` : '');
  const lvl = f => `${esc(levelLabel(f.level))}${f.detail && f.detail.toLowerCase() !== f.level ? ` <span class="src">(${esc(f.detail)})</span>` : ''}`;
  const t = p.table1;
  const prov = p.provenance;
  const provText = prov.table1_verified
    ? 'Ratings checked by hand against the full text for the position paper (Table 1). Other fields are from the catalog.'
    : prov.text_mode === 'full-text' || prov.text_mode === 'full-text-html'
      ? `Summary and analysis drafted by a language model from the full text, with quotes checked against the paper${prov.quote_verification_rate != null && prov.quote_verification_rate !== '' ? ` (${Math.round(Number(prov.quote_verification_rate) * 100)}% of quotes found)` : ''}. Not yet reviewed by hand${prov.needs_review ? '; flagged for review' : ''}.`
      : 'Catalog entry from the abstract and metadata; not yet checked against the full text.';
  $('detail-body').innerHTML = `
    <h2 id="detail-title">${esc(p.title)}</h2>
    <p class="meta">${esc(p.authors)} · ${p.year ?? ''} · ${esc(p.venue)}</p>
    <div class="tags">${p.cited ? '<span class="badge badge-cited">Cited in the position paper</span>' : ''}<span class="tag">${esc(p.category)}</span>${p.pillars.map(k => `<span class="tag">${k} · ${esc(PILLARS[k])}</span>`).join('')}</div>
    <h3>Summary</h3>
    <p>${esc(readable(p.summary))}</p>
    <p class="src">${p.summary_source === 'full text' ? 'From the full text.' : 'From the catalog.'}</p>
    <h3>How it maps to USIL</h3>
    <dl class="kv">
      ${row('What is learned', esc(p.what_is_learned))}
      ${row("Learns from an individual's evidence", lvl(p.per_user))}
      ${row('Adapts across sessions', lvl(p.across_sessions))}
      ${row('Transfer evaluation', lvl(p.transfer))}
      ${row('Interaction decisions', p.decisions_known ? (p.decisions.length ? esc(p.decisions.join(', ')) : 'None') + (p.decisions_raw ? ` <span class="src">(${esc(p.decisions_raw)})</span>` : '') : 'Not yet coded')}
      ${row('Personalizes', p.cell ? `${esc(CELLS[p.cell].row)} · ${esc(CELLS[p.cell].col)}` : 'Not placed')}
      ${row('User evidence', esc(p.user_evidence))}
    </dl>
    ${t ? `<h3>Table 1 ratings</h3><dl class="kv">${T1_COLS.map(([k, l]) => row(l, esc(levelLabel(t[k])))).join('')}${t.note ? row('Note', esc(t.note)) : ''}</dl>` : ''}
    ${p.closest_overlap ? `<h3>Overlap with USIL</h3><p>${esc(readable(p.closest_overlap))}</p>` : p.relation ? `<h3>Relation to USIL</h3><p>${esc(readable(p.relation))}</p>` : ''}
    ${p.remaining_question ? `<h3>Open question for USIL</h3><p>${esc(readable(p.remaining_question))}</p>` : ''}
    ${p.cite_role ? `<h3>Role in the position paper</h3><p>${esc(p.cite_role)}${p.cite_section ? ` <span class="src">(${esc(p.cite_section)})</span>` : ''}</p>` : ''}
    <h3>Provenance</h3>
    <p class="src">${esc(provText)} Key: <code>${esc(p.id)}</code></p>
    ${p.url ? `<p><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">Open the paper</a></p>` : ''}`;
  const d = $('detail');
  if (typeof d.showModal === 'function') d.showModal(); else d.setAttribute('open', '');
  d.scrollTop = 0;
}

/* ---------- init ---------- */
async function init() {
  try {
    const res = await fetch('data/papers.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    PAPERS = data.papers;
    META = data.meta;
  } catch (err) {
    $('results').innerHTML = `<div class="empty">The paper data could not load (${esc(err.message)}). Open this page through a web server, such as GitHub Pages or <code>python -m http.server</code>, not as a local file.</div>`;
    return;
  }
  const years = PAPERS.map(p => p.year).filter(Boolean);
  const full = PAPERS.filter(p => p.summary_source === 'full text' || p.provenance.table1_verified).length;
  $('facts').innerHTML = [
    [PAPERS.length, 'papers'],
    [`${Math.min(...years)}–${Math.max(...years)}`, 'publication years'],
    [PAPERS.filter(p => p.cited).length, 'cited in the position paper'],
    [full, 'annotated from full text'],
  ].map(([v, l]) => `<div><dt>${esc(l)}</dt><dd>${esc(v)}</dd></div>`).join('');
  $('snapshot').textContent = `${META.snapshot}, ${PAPERS.length} papers`;

  META.categories.forEach(c => $('f-category').add(new Option(c, c)));
  Object.entries(PILLARS).forEach(([k, v]) => $('f-pillar').add(new Option(`${k}: ${v}`, k)));
  Object.entries(CELLS).forEach(([k, v]) => $('f-cell').add(new Option(`${v.row} · ${v.col}`, k)));
  [...new Set(PAPERS.flatMap(p => p.decisions))].filter(d => d !== 'Other').sort().forEach(d => $('f-decision').add(new Option(d, d)));

  $('f-q').addEventListener('input', e => setFilter({ q: e.target.value }, { scroll: false }));
  [['f-category', 'category'], ['f-pillar', 'pillar'], ['f-cell', 'cell'], ['f-decision', 'decision'], ['f-sort', 'sort']]
    .forEach(([id, key]) => $(id).addEventListener('change', e => setFilter({ [key]: e.target.value }, { scroll: false })));
  $('f-cited').addEventListener('change', e => setFilter({ cited: e.target.checked }, { scroll: false }));
  $('f-reset').addEventListener('click', () => setFilter({ q: '', category: '', pillar: '', cell: '', decision: '', stage: 0, year: '', cited: false, status: null }, { scroll: false }));
  $('filters').addEventListener('submit', e => e.preventDefault());
  $('detail-close').addEventListener('click', () => $('detail').close());
  $('detail').addEventListener('click', e => { if (e.target === $('detail')) $('detail').close(); });

  drawTable1();
  setFilter({}, { scroll: false });
  let lastW = window.innerWidth, timer;
  window.addEventListener('resize', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { if (window.innerWidth !== lastW) { lastW = window.innerWidth; drawCharts(); } }, 150);
  });
}

init();
