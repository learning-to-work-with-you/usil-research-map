'use strict';

/* ---------- constants ---------- */
let PILLARS = {}; // from data/schema.json
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
  { key: 'not established', label: 'Not stated' },
];
// The four USIL ingredients, each counted on its own (no order implied).
const INGREDIENTS = [
  { key: 'person', label: "Learns from one person's evidence", short: 'One person', desc: 'Approvals, corrections, answers, or behavior from the individual user.', test: p => isOn(p.per_user) },
  { key: 'decisions', label: 'Adapts interaction decisions', short: 'Decisions', desc: 'When to ask, act, confirm, defer, or explain, not only what to produce.', test: p => p.decisions.length > 0 },
  { key: 'sessions', label: 'Adapts across sessions', short: 'Sessions', desc: 'What is learned persists and updates over time.', test: p => isOn(p.across_sessions) },
  { key: 'transfer', label: 'Tests transfer to new tasks', short: 'Transfer', desc: 'Checks whether what was learned carries to new kinds of tasks.', test: p => isOn(p.transfer) },
];
const covered = p => INGREDIENTS.filter(g => g.test(p)).length;
const EARLY = 2016; // years before this are grouped in the year chart

let PAPERS = [];
let META = {};
let SCHEMA = {};
const state = { q: '', category: '', pillar: '', cell: '', decision: '', ingr: '', cover: '', year: '', sort: 'year', ptype: '', users: '', pp: false };

/* ---------- helpers ---------- */
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const isOn = f => f.level === 'yes' || f.level === 'partial';
const levelLabel = l => (LEVELS.find(x => x.key === l) || { label: l }).label;
const svgNS = 'http://www.w3.org/2000/svg';
const readable = s => String(s ?? '').replace(/\b(outcome|procedure)_(population|individual|averaged)\b/g, (m, a, b) => `${a} · ${b === 'averaged' ? 'population' : b}`);
const yearKey = y => (y && y < EARLY ? 'pre' : String(y ?? ''));

/* ---------- data: data/papers.csv + data/schema.json ---------- */
function parseCSV(text) {
  const rows = [];
  let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field); field = '';
      if (row.length > 1 || row[0] !== '') rows.push(row);
      row = [];
    } else field += c;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  const [head, ...body] = rows;
  return body.map(r => Object.fromEntries(head.map((h, i) => [h.replace(/^\uFEFF/, ''), (r[i] ?? '').trim()])));
}

const column = name => SCHEMA.columns.find(c => c.name === name) || {};
// Display label for a schema value, e.g. lab('evaluation_users', 'real') -> 'Real people'
const lab = (name, v) => ((column(name).values || {})[v]) || v;
const list = v => (v ? v.split(';').map(x => x.trim()).filter(Boolean) : []);
const LEVEL_OF = v => (['yes', 'partial', 'no'].includes(v) ? v : 'not established');
const STUDY_COLS = ['paper_type', 'settings', 'user_signals', 'user_representation', 'preference_change', 'personalization_unit',
  'evaluation_users', 'evaluation_scale', 'per_person_results', 'interaction_cost_metrics', 'decision_factors', 'resources'];

function toPaper(r) {
  const decs = list(r.interaction_decisions);
  const known = decs.length > 0 && !decs.includes('not-stated');
  const decisions = known ? decs.filter(d => d !== 'none').map(d => lab('interaction_decisions', d)) : [];
  const level = c => ({ level: LEVEL_OF(r[c]) });
  const p = {
    id: r.key, title: r.title, authors: r.authors, year: /^\d{4}$/.test(r.year) ? Number(r.year) : null,
    venue: r.venue, url: r.url, category: r.category, pillars: list(r.pillars), summary: r.summary,
    summary_source: r.annotation_source === 'pipeline-fulltext' ? 'full text' : 'catalog',
    what_is_learned: r.what_is_learned, user_evidence: r.user_evidence,
    per_user: level('per_user'), across_sessions: level('across_sessions'), transfer: level('evaluates_transfer'),
    decisions, decisions_known: known,
    relation: r.usil_relation, open_question: r.open_question, notes: r.notes,
    provenance: { source: r.annotation_source, text_mode: r.annotation_source === 'pipeline-fulltext' ? 'full-text' : '', quote_verification_rate: r.quotes_verified || null, annotated_on: r.annotated_on },
    study: {}, provisional: r.annotation_source === 'pending',
  };
  STUDY_COLS.forEach(c => {
    const v = column(c).list ? list(r[c]).filter(x => x !== 'none') : r[c];
    if (v && v.length) p.study[c] = v;
  });
  // 2x2: whose evidence (individual if yes/partial) x what adapts (procedure if any decision, outcome if none)
  const who = { yes: 'individual', partial: 'individual', no: 'population' }[r.per_user];
  const what = !known ? null : decs.includes('none') ? 'outcome' : 'procedure';
  p.cell = who && what ? `${what}_${who}` : null;
  return p;
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

/* ---------- shared bits ---------- */
// Papers added in this version but not yet read in full are listed in Browse, not counted in charts.
const charted = () => PAPERS.filter(p => !p.provisional);
const shortName = p => {
  const t = p.title.split(/:\s|\?\s/)[0];
  return t.length > 44 ? `${t.slice(0, 42).trimEnd()}…` : t;
};
const period = y => (!y || y < 2023 ? 'p1' : y < 2025 ? 'p2' : 'p3');
const PERIODS = [['p1', 'Before 2023'], ['p2', '2023–2024'], ['p3', '2025–2026']];
const keyAct = (node, fn) => {
  node.addEventListener('click', fn);
  node.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); } });
};
const paperChip = p => `<button type="button" class="pchip" data-id="${esc(p.id)}">${esc(shortName(p))}<span>${p.year ?? ''}</span></button>`;
function wirePaperButtons(root) {
  root.querySelectorAll('button[data-id]').forEach(b => {
    b.addEventListener('click', e => { e.stopPropagation(); openPaper(b.dataset.id); });
    const p = PAPERS.find(x => x.id === b.dataset.id);
    if (p && b.classList.contains('dot')) withTip(b, `<strong>${esc(p.title)}</strong><br>${p.year ?? ''} · ${esc(p.category)}`);
  });
}

/* ---------- papers per year, stacked by what they personalize ---------- */
const YEAR_PARTS = [
  { key: 'usil', label: "Learns interaction decisions from one person's evidence", test: p => p.cell === 'procedure_individual', fill: 'var(--seq-7)' },
  { key: 'placed', label: 'Other placed papers', test: p => p.cell && p.cell !== 'procedure_individual', fill: 'var(--seq-4)' },
  { key: 'other', label: 'Not placed', test: p => !p.cell, fill: 'var(--seq-2)' },
];
function yearChart(container) {
  const papers = charted();
  const buckets = new Map();
  papers.forEach(p => { if (p.year) { const k = yearKey(p.year); if (!buckets.has(k)) buckets.set(k, []); buckets.get(k).push(p); } });
  const years = [...buckets.keys()].filter(k => k !== 'pre').map(Number).sort((a, b) => a - b);
  const items = [];
  if (buckets.has('pre')) items.push({ key: 'pre', label: `Before ${EARLY}`, short: `<${EARLY}`, list: buckets.get('pre') });
  for (let y = Math.min(...years); y <= Math.max(...years); y++) items.push({ key: String(y), label: String(y), short: `'${String(y).slice(2)}`, list: buckets.get(String(y)) || [] });
  const W = plotWidth(container), H = 200, padL = 28, padB = 24, padT = 18;
  const plotW = W - padL, plotH = H - padB - padT;
  const max = Math.max(...items.map(i => i.list.length));
  const niceMax = Math.ceil(max / 10) * 10;
  const slot = plotW / items.length, barW = Math.min(34, slot - 6);
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  let grid = '';
  for (let v = 0; v <= niceMax; v += niceMax / 2) {
    const y = padT + plotH - (v / niceMax) * plotH;
    grid += `<line class="gridline" x1="${padL}" x2="${W}" y1="${y}" y2="${y}"></line><text class="axis" x="${padL - 6}" y="${y + 4}" text-anchor="end">${v}</text>`;
  }
  svg.innerHTML = grid;
  items.forEach((it, i) => {
    const n = it.list.length;
    const x = padL + i * slot + (slot - barW) / 2;
    const g = document.createElementNS(svgNS, 'g');
    g.setAttribute('class', `mark${state.year === it.key ? ' on' : ''}`);
    g.setAttribute('tabindex', '0');
    g.setAttribute('role', 'button');
    const parts = YEAR_PARTS.map(pt => ({ ...pt, n: it.list.filter(pt.test).length }));
    g.setAttribute('aria-label', `${it.label}: ${n} papers, ${parts[0].n} learn interaction decisions from one person. Filter papers.`);
    let y0 = padT + plotH, segs = '';
    parts.forEach(pt => {
      if (!pt.n) return;
      const h = (pt.n / niceMax) * plotH;
      segs += `<rect class="seg" x="${x}" y="${y0 - h}" width="${barW}" height="${Math.max(1, h - 1)}" rx="2" style="fill:${pt.fill}"></rect>`;
      y0 -= h;
    });
    g.innerHTML = `<rect class="hit" x="${padL + i * slot}" y="${padT}" width="${slot}" height="${plotH}"></rect>${segs}
      ${slot >= 26 || i % 2 === items.length % 2 ? `<text class="axis" x="${x + barW / 2}" y="${H - 6}" text-anchor="middle">${esc(it.short)}</text>` : ''}
      ${n >= max * 0.4 ? `<text class="val" x="${x + barW / 2}" y="${y0 - 5}" text-anchor="middle">${n}</text>` : ''}`;
    keyAct(g, () => setFilter({ year: state.year === it.key ? '' : it.key }));
    withTip(g, `<strong>${esc(it.label)}</strong><br>${n} paper${n === 1 ? '' : 's'}${parts.map(pt => `<br>${pt.n} · ${esc(pt.label)}`).join('')}`);
    svg.appendChild(g);
  });
  container.innerHTML = '';
  container.appendChild(svg);
  container.insertAdjacentHTML('beforeend', `<div class="status-legend">${YEAR_PARTS.map(pt => `<span class="lv" style="--c:${pt.fill}">${esc(pt.label)}</span>`).join('')}</div>`);
  container.insertAdjacentHTML('beforeend', dataTable(items.map(i => [i.label, i.list.length, ...YEAR_PARTS.map(pt => i.list.filter(pt.test).length)]), ['Year', 'Papers', ...YEAR_PARTS.map(pt => pt.label)]));
}

/* ---------- 2x2 with one dot per paper ---------- */
let throughYear = null; // slider position; null = all years
function cellChart(container) {
  const papers = charted();
  const years = papers.map(p => p.year).filter(Boolean);
  const lo = Math.max(EARLY, Math.min(...years)), hi = Math.max(...years);
  const upTo = throughYear ?? hi;
  const shown = p => !p.year || p.year <= upTo || (upTo === lo && p.year < lo);
  const byCell = Object.fromEntries(Object.keys(CELLS).map(k => [k, papers.filter(p => p.cell === k).sort((a, b) => (a.year || 0) - (b.year || 0))]));
  const unplaced = papers.filter(p => !p.cell).length;
  const cell = k => {
    const list = byCell[k], n = list.filter(shown).length;
    return `<div class="qcell${k === 'procedure_individual' ? ' usil' : ''}${state.cell === k ? ' on' : ''}">
      <button type="button" class="qhead" data-cell="${k}" aria-label="${esc(CELLS[k].name)}: ${n} papers. Filter papers.">
        <strong>${n}</strong><span>${esc(CELLS[k].name)}${k === 'procedure_individual' ? ' <em>USIL</em>' : ''}</span>
      </button>
      <div class="dots">${list.map(p => `<button type="button" class="dot ${period(p.year)}${shown(p) ? '' : ' later'}" data-id="${esc(p.id)}" aria-label="${esc(p.title)}, ${p.year ?? ''}"></button>`).join('')}</div>
    </div>`;
  };
  container.innerHTML = `<div class="quad">
      <span></span><span class="ax"><b>Population</b>shared across users</span><span class="ax"><b>Individual</b>adapted to one person</span>
      <span class="ay"><b>Outcome</b>what is produced</span>${cell('outcome_population')}${cell('outcome_individual')}
      <span class="ay"><b>Procedure</b>how work is done</span>${cell('procedure_population')}${cell('procedure_individual')}
    </div>
    <div class="quad-foot">
      <label class="slider"><span>Papers through <b id="through">${upTo === hi ? hi : upTo}</b></span>
        <input type="range" id="year-slider" min="${lo}" max="${hi}" step="1" value="${upTo}" aria-label="Show papers published through this year"></label>
      <div class="status-legend">${PERIODS.map(([k, l]) => `<span class="lv lv-dot ${k}">${l}</span>`).join('')}</div>
    </div>
    <p class="cells-note">Placed by two labels: whether a paper learns from one person's evidence, and whether it affects interaction decisions. ${unplaced} papers lack one of these labels and are not placed.</p>
    ${dataTable(Object.keys(CELLS).map(k => [CELLS[k].row, CELLS[k].col, byCell[k].length]).concat([['Not placed', '', unplaced]]), ['Personalizes', 'For', 'Papers'])}`;
  container.querySelectorAll('button.qhead').forEach(b => {
    b.addEventListener('click', () => setFilter({ cell: state.cell === b.dataset.cell ? '' : b.dataset.cell }));
  });
  wirePaperButtons(container);
  $('year-slider').addEventListener('input', e => {
    throughYear = Number(e.target.value);
    const pos = e.target.value;
    cellChart(container);
    const s = $('year-slider'); s.value = pos; s.focus();
  });
}

/* ---------- coverage: the four ingredients, each counted on its own ---------- */
function coverageChart(container) {
  const papers = charted(), total = papers.length;
  const rows = INGREDIENTS.map(g => ({ ...g, n: papers.filter(g.test).length })).sort((a, b) => b.n - a.n);
  const dist = [0, 1, 2, 3, 4].map(k => papers.filter(p => covered(p) === k).length);
  const maxd = Math.max(...dist, 1);
  const all = papers.filter(p => covered(p) === 4).sort((a, b) => (b.year || 0) - (a.year || 0));
  container.innerHTML = `
    <p class="cov-head">Each ingredient on its own</p>
    <div class="cov-rows">${rows.map(r => `
      <button type="button" class="cov-row${state.ingr === r.key ? ' on' : ''}" data-ingr="${r.key}" aria-label="${esc(r.label)}: ${r.n} of ${total} papers. Filter papers.">
        <span class="cov-text"><b>${esc(r.label)}</b><small>${esc(r.desc)}</small></span>
        <span class="cov-track" aria-hidden="true"><span style="width:${(r.n / total) * 100}%"></span></span>
        <span class="cov-n"><b>${r.n}</b><small>${Math.round((r.n / total) * 100)}%</small></span>
      </button>`).join('')}</div>
    <p class="cov-head">How many ingredients each paper covers</p>
    <div class="cov-dist">${dist.map((n, k) => `
      <button type="button" class="cov-col${String(state.cover) === String(k) ? ' on' : ''}${k === 4 ? ' all' : ''}" data-cover="${k}" aria-label="${n} papers cover ${k} of 4 ingredients. Filter papers.">
        <span class="cov-colbar"><span style="height:${(n / maxd) * 100}%"></span></span>
        <b>${n}</b><small>${k === 4 ? 'all 4' : k}</small>
      </button>`).join('')}</div>
    <div class="stage-papers cov-all"><span class="stage-papers-label">All four together: ${all.length} paper${all.length === 1 ? '' : 's'}</span>${all.map(paperChip).join('')}</div>
    <div class="funnel-goal"><span class="stage-n">★</span><span><b>USIL asks for all four together,</b> plus an evaluation for each person. <a href="https://learntoworkwithyou.org/position-paper/">Read the position paper →</a></span></div>
    ${dataTable(rows.map(r => [r.label, r.n, `${Math.round((r.n / total) * 100)}%`]), ['Ingredient', 'Papers', `Share of ${total}`])}
    ${dataTable(dist.map((n, k) => [k === 4 ? 'All 4' : k, n]), ['Ingredients covered', 'Papers'])}`;
  container.querySelectorAll('.cov-row').forEach(b => b.addEventListener('click', () => setFilter({ ingr: state.ingr === b.dataset.ingr ? '' : b.dataset.ingr })));
  container.querySelectorAll('.cov-col').forEach(b => b.addEventListener('click', () => setFilter({ cover: String(state.cover) === b.dataset.cover ? '' : b.dataset.cover })));
  wirePaperButtons(container);
}

/* ---------- the four challenges ---------- */
// What full-text reading adds to each challenge card: one breakdown per challenge.
const STUDY_VIEW = {
  P1: { label: 'Learns from', col: 'user_signals', of: p => p.study.user_signals || [] },
  P2: { label: 'Represents the user as', col: 'user_representation', of: p => (p.study.user_representation && p.study.user_representation !== 'none' ? [p.study.user_representation] : []) },
  P3: { label: 'Decides based on', col: 'decision_factors', of: p => p.study.decision_factors || [] },
  P4: { label: 'Evaluated with', col: 'evaluation_users', of: p => (p.study.evaluation_users ? [p.study.evaluation_users] : []) },
};
const CHALLENGES = {
  P1: { n: '01', name: 'Understanding', title: 'Learning from sparse, evolving evidence', q: "How can an agent infer a person's interaction preferences from sparse, ambiguous, and evolving evidence?" },
  P2: { n: '02', name: 'Modeling', title: 'Representing and generalizing preferences', q: 'How should an agent represent what it learns about a person, and which preferences generalize across tasks?' },
  P3: { n: '03', name: 'Interacting', title: 'Learning when to ask, explain, act, or defer', q: 'How should an agent choose how to interact with each person, given stakes, uncertainty, and authorization?' },
  P4: { n: '04', name: 'Measuring', title: 'Evaluating for each person', q: 'How can we measure whether an agent learns to work better with a particular person?' },
};
function challengeCards(container) {
  const papers = charted();
  container.innerHTML = Object.entries(CHALLENGES).map(([k, c]) => {
    const list = papers.filter(p => p.pillars.includes(k));
    const fresh = PAPERS.filter(p => p.provisional && p.pillars.includes(k)).length;
    const areas = Object.entries(list.reduce((m, p) => ({ ...m, [p.category]: (m[p.category] || 0) + 1 }), {})).sort((a, b) => b[1] - a[1]).slice(0, 3);
    const key = list.slice().sort((a, b) => covered(b) - covered(a) || (b.year || 0) - (a.year || 0)).slice(0, 3);
    const bar = (n, label) => `<div class="cstep"><span>${label}</span><div class="ctrack"><div style="width:${list.length ? (n / list.length) * 100 : 0}%"></div></div><b>${n}</b></div>`;
    return `<article class="challenge${state.pillar === k ? ' on' : ''}">
      <p class="c-id">${c.n} / ${c.name.toUpperCase()}</p>
      <h3>${esc(c.title)}</h3>
      <p class="c-q">${esc(c.q)}</p>
      <p class="c-count"><b>${list.length}</b> papers${fresh ? ` <span class="badge badge-new">+${fresh} not yet annotated</span>` : ''}</p>
      <div class="csteps">${INGREDIENTS.map(g => bar(list.filter(g.test).length, g.label)).join('')}</div>
      <p class="c-label">Most active areas</p>
      <div class="c-areas">${areas.map(([a, n]) => `<button type="button" class="tag tag-btn" data-area="${esc(a)}">${esc(a)} <b>${n}</b></button>`).join('')}</div>
      ${studyBreakdown(k, list)}
      <p class="c-label">Cover the most ingredients</p>
      <div class="c-papers">${key.map(paperChip).join('')}</div>
      <button type="button" class="c-all" data-pillar="${k}">See all ${list.length + fresh} papers →</button>
    </article>`;
  }).join('');
  container.querySelectorAll('.c-all').forEach(b => b.addEventListener('click', () => setFilter({ pillar: b.dataset.pillar, category: '' })));
  container.querySelectorAll('.tag-btn').forEach(b => b.addEventListener('click', () => {
    const k = b.closest('.challenge').querySelector('.c-all').dataset.pillar;
    setFilter({ pillar: k, category: b.dataset.area });
  }));
  wirePaperButtons(container);
}

function studyBreakdown(k, list) {
  const v = STUDY_VIEW[k];
  const read = list.filter(p => p.study && Object.keys(p.study).length);
  if (!read.length) return '';
  const counts = {};
  read.forEach(p => v.of(p).forEach(x => { counts[x] = (counts[x] || 0) + 1; }));
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 4);
  if (!top.length) return '';
  const max = top[0][1];
  return `<p class="c-label">${esc(v.label)} <span class="c-of">of ${read.length} read in full</span></p>
    <div class="csteps">${top.map(([x, n]) => `<div class="cstep"><span>${esc(lab(v.col, x))}</span><div class="ctrack"><div style="width:${(n / max) * 100}%;background:var(--orange)"></div></div><b>${n}</b></div>`).join('')}</div>`;
}

/* ---------- who the users are in evaluations ---------- */
const USERS = [
  { key: 'real', label: 'Real people', fill: 'var(--seq-7)' },
  { key: 'both', label: 'Real and simulated', fill: 'var(--seq-5)' },
  { key: 'simulated', label: 'Simulated users only', fill: 'var(--orange)' },
  { key: 'none', label: 'No user evaluation', fill: 'var(--seq-2)' },
];
function usersChart(container) {
  const read = charted().filter(p => p.study && p.study.evaluation_users);
  if (!read.length) { container.innerHTML = '<p class="cells-note">Appears once papers are read in full.</p>'; return; }
  const rows = USERS.map(u => ({ ...u, n: read.filter(p => p.study.evaluation_users === u.key).length }));
  const max = Math.max(...rows.map(r => r.n), 1);
  container.innerHTML = `<div class="sbars">${rows.map(r => `
    <button type="button" class="sbar${state.users === r.key ? ' on' : ''}" data-u="${esc(r.key)}" aria-label="${esc(r.label)}: ${r.n} papers. Filter papers.">
      <span class="sbar-label">${esc(r.label)} <small>${r.n} papers</small></span>
      <span class="sbar-track" style="width:${(r.n / max) * 100}%"><span style="flex:1;background:${r.fill}"></span></span>
    </button>`).join('')}</div>
    <p class="cells-note">Of ${read.length} papers read in full.</p>
    ${dataTable(rows.map(r => [r.label, r.n]), ['Evaluated with', 'Papers'])}`;
  container.querySelectorAll('.sbar').forEach(b => b.addEventListener('click', () => setFilter({ users: state.users === b.dataset.u ? '' : b.dataset.u })));
}

/* ---------- results reported for each person ---------- */
function perPersonChart(container) {
  const withUsers = charted().filter(p => p.study && p.study.evaluation_users && p.study.evaluation_users !== 'none');
  const per = withUsers.filter(p => p.study.per_person_results === 'yes').sort((a, b) => (b.year || 0) - (a.year || 0));
  if (!withUsers.length) { container.innerHTML = '<p class="cells-note">Appears once papers are read in full.</p>'; return; }
  container.innerHTML = `<button type="button" class="pp-big${state.pp ? ' on' : ''}" aria-label="${per.length} of ${withUsers.length} papers report results for each person. Filter papers.">
      <b>${per.length}</b><span>of ${withUsers.length} papers that evaluate with users report results <strong>for each person</strong>; the rest report averages.</span>
    </button>
    <div class="pp-track" aria-hidden="true"><span style="width:${Math.max(1, (per.length / withUsers.length) * 100)}%"></span></div>
    <div class="c-papers pp-papers">${per.map(paperChip).join('')}</div>
    <p class="cells-note">Per-person results: each user is judged against their own preferences or costs. This is what USIL's fourth challenge asks for.</p>`;
  container.querySelector('.pp-big').addEventListener('click', () => setFilter({ pp: !state.pp }));
  wirePaperButtons(container);
}

/* ---------- decisions, split by whose evidence ---------- */
const WHO = [
  { key: 'ind', label: "From one person's evidence", test: p => isOn(p.per_user), fill: 'var(--seq-7)' },
  { key: 'pop', label: 'Shared across users', test: p => ['no', 'n/a'].includes(p.per_user.level), fill: 'var(--seq-4)' },
  { key: 'ne', label: 'Not stated', test: p => p.per_user.level === 'not established', fill: 'var(--lv-ne)' },
];
function decisionChart(container) {
  const papers = charted();
  const names = [...new Set(papers.flatMap(p => p.decisions))].filter(d => d !== 'Other');
  const rows = names.map(d => {
    const list = papers.filter(p => p.decisions.includes(d));
    return { d, n: list.length, parts: WHO.map(w => list.filter(w.test).length) };
  }).sort((a, b) => b.n - a.n);
  const max = Math.max(...rows.map(r => r.n));
  container.innerHTML = `<div class="sbars">${rows.map(r => `
    <button type="button" class="sbar${state.decision === r.d ? ' on' : ''}" data-d="${esc(r.d)}" aria-label="${esc(r.d)}: ${r.n} papers, ${r.parts[0]} from one person's evidence. Filter papers.">
      <span class="sbar-label">${esc(r.d)} <small>${r.parts[0]} of ${r.n} per person</small></span>
      <span class="sbar-track" style="width:${(r.n / max) * 100}%">${r.parts.map((n, i) => n ? `<span style="flex:${n};background:${WHO[i].fill}"></span>` : '').join('')}</span>
    </button>`).join('')}</div>
    <div class="status-legend">${WHO.map(w => `<span class="lv" style="--c:${w.fill}">${esc(w.label)}</span>`).join('')}</div>
    ${dataTable(rows.map(r => [r.d, r.n, ...r.parts]), ['Decision', 'Papers', ...WHO.map(w => w.label)])}`;
  container.querySelectorAll('.sbar').forEach(b => {
    b.addEventListener('click', () => setFilter({ decision: state.decision === b.dataset.d ? '' : b.dataset.d }));
    const r = rows.find(x => x.d === b.dataset.d);
    withTip(b, `<strong>${esc(r.d)}</strong><br>${r.n} papers${WHO.map((w, i) => `<br>${r.parts[i]} · ${esc(w.label)}`).join('')}`);
  });
}

/* ---------- charts ---------- */
function drawCharts() {
  const plot = id => document.querySelector(`#${id} .plot`);
  cellChart(plot('chart-cells'));
  yearChart(plot('chart-years'));
  coverageChart(plot('chart-coverage'));
  challengeCards($('chart-challenges'));
  decisionChart(plot('chart-decisions'));
  usersChart(plot('chart-users'));
  perPersonChart(plot('chart-perperson'));
  const papers = charted();
  hbars(plot('chart-categories'), META.categories.map(c => ({ key: c, label: c, value: papers.filter(p => p.category === c).length })), {
    onClick: it => setFilter({ category: state.category === it.key && !state.pillar ? '' : it.key, pillar: '' }),
    isActive: it => state.category === it.key,
  });
}

/* ---------- filtering ---------- */
function filtered() {
  const q = state.q.trim().toLowerCase();
  const ingr = INGREDIENTS.find(g => g.key === state.ingr);
  return PAPERS.filter(p =>
    (!state.category || p.category === state.category) &&
    (!state.pillar || p.pillars.includes(state.pillar)) &&
    (!state.cell || p.cell === state.cell) &&
    (!state.decision || p.decisions.includes(state.decision)) &&
    (!state.ptype || p.study.paper_type === state.ptype) &&
    (!state.users || p.study.evaluation_users === state.users) &&
    (!state.pp || p.study.per_person_results === 'yes') &&
    (!state.year || yearKey(p.year) === state.year) &&
    (!ingr || ingr.test(p)) &&
    (state.cover === '' || covered(p) === Number(state.cover)) &&
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
  if (state.ptype) list.push(['ptype', `Type: ${lab('paper_type', state.ptype)}`, { ptype: '' }]);
  if (state.pp) list.push(['pp', 'Reports results for each person', { pp: false }]);
  if (state.users) list.push(['users', `Evaluated with: ${lab('evaluation_users', state.users)}`, { users: '' }]);
  if (state.ingr) list.push(['ingr', INGREDIENTS.find(g => g.key === state.ingr).label, { ingr: '' }]);
  if (state.cover !== '') list.push(['cover', state.cover === '4' ? 'Covers all four ingredients' : `Covers ${state.cover} of 4 ingredients`, { cover: '' }]);
  if (state.year) list.push(['year', state.year === 'pre' ? `Before ${EARLY}` : state.year, { year: '' }]);
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
    <article class="paper${p.provisional ? ' provisional' : ''}">
      <div class="meta"><span>${p.year ?? ''}</span><span>${esc(p.venue)}</span>${p.provisional ? '<span class="badge badge-new">Not yet annotated</span>' : ''}${p.summary_source === 'full text' ? '<span class="badge badge-full">Full text</span>' : p.provenance.source === 'manual' ? '<span class="badge badge-hand">By hand</span>' : ''}</div>
      <h3><button type="button" data-id="${esc(p.id)}">${esc(p.title)}</button></h3>
      <p class="authors">${esc(p.authors)}</p>
      <p class="summary">${esc(p.summary)}</p>
      <div class="tags">
        <span class="tag">${esc(p.category)}</span>
        ${p.cell ? `<span class="tag tag-cell">${esc(CELLS[p.cell].row)} · ${esc(CELLS[p.cell].col)}</span>` : ''}
        ${p.pillars.map(k => `<span class="tag" title="${esc(PILLARS[k])}">${k}</span>`).join('')}
        ${p.study.evaluation_users ? `<span class="tag tag-users">${esc(lab('evaluation_users', p.study.evaluation_users))}</span>` : ''}
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
  $('f-ptype').value = state.ptype;
  $('f-users').value = state.users;
  $('f-sort').value = state.sort;
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
function studyBlock(st) {
  if (!st || !Object.keys(st).length) return '';
  const row = (k, c) => {
    const v = st[c];
    return v && (!Array.isArray(v) || v.length) ? `<dt>${esc(k)}</dt><dd>${esc((Array.isArray(v) ? v : [v]).map(x => lab(c, x)).join(', '))}</dd>` : '';
  };
  const links = (st.resources || []).filter(u => /^https?:\/\//.test(u));
  return `<h3>Study design</h3><dl class="kv">
    ${row('Type', 'paper_type')}${row('Setting', 'settings')}${row('Learns from', 'user_signals')}
    ${row('Represents the user as', 'user_representation')}${row('Personalizes per', 'personalization_unit')}
    ${row('Preference change', 'preference_change')}
    ${st.evaluation_users ? `<dt>Evaluated with</dt><dd>${esc(lab('evaluation_users', st.evaluation_users))}${st.evaluation_scale ? ` (${esc(st.evaluation_scale)})` : ''}</dd>` : ''}
    ${row('Results per person', 'per_person_results')}${row('Measures user burden', 'interaction_cost_metrics')}
    ${row('Decision factors', 'decision_factors')}
    ${links.length ? `<dt>Code and data</dt><dd>${links.map(u => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(u.replace(/^https?:\/\//, '').slice(0, 48))}</a>`).join('<br>')}</dd>` : ''}
  </dl><p class="src">From the full text by a language model, with quotes checked against the paper.</p>`;
}

function openPaper(id) {
  const p = PAPERS.find(x => x.id === id);
  if (!p) return;
  const row = (k, v) => (v ? `<dt>${esc(k)}</dt><dd>${v}</dd>` : '');
  const lvl = f => esc(levelLabel(f.level));
  const prov = p.provenance;
  const provText = p.provisional
    ? 'Listed on the map but not yet annotated: the labels below are filled in once the paper is read.'
    : prov.text_mode === 'full-text' || prov.text_mode === 'full-text-html'
      ? `Summary and analysis drafted by a language model from the full text, with quotes checked against the paper${prov.quote_verification_rate != null && prov.quote_verification_rate !== '' ? ` (${Math.round(Number(prov.quote_verification_rate) * 100)}% of quotes found)` : ''}. Not yet reviewed by hand.`
      : prov.source === 'pipeline-abstract'
        ? 'Labels drafted by a language model from the abstract only; not yet checked against the full text.'
        : 'Labels added by hand by the map\'s contributors.';
  $('detail-body').innerHTML = `
    <h2 id="detail-title">${esc(p.title)}</h2>
    <p class="meta">${esc(p.authors)} · ${p.year ?? ''} · ${esc(p.venue)}</p>
    <div class="tags"><span class="tag">${esc(p.category)}</span>${p.pillars.map(k => `<span class="tag">${k} · ${esc(PILLARS[k])}</span>`).join('')}</div>
    <h3>Summary</h3>
    <p>${esc(readable(p.summary))}</p>
    <p class="src">${p.summary_source === 'full text' ? 'From the full text.' : 'From the catalog.'}</p>
    <h3>How it maps to USIL</h3>
    <dl class="kv">
      ${row('What is learned', esc(p.what_is_learned))}
      ${row("Learns from an individual's evidence", lvl(p.per_user))}
      ${row('Adapts across sessions', lvl(p.across_sessions))}
      ${row('Transfer evaluation', lvl(p.transfer))}
      ${row('Interaction decisions', p.decisions_known ? (p.decisions.length ? esc(p.decisions.join(', ')) : 'None') : 'Not stated')}
      ${row('Personalizes', p.cell ? `${esc(CELLS[p.cell].row)} · ${esc(CELLS[p.cell].col)}` : 'Not placed')}
      ${row('User evidence', esc(p.user_evidence))}
      ${row('Notes', esc(p.notes))}
    </dl>
    ${studyBlock(p.study)}
    ${p.relation ? `<h3>Relation to USIL</h3><p>${esc(readable(p.relation))}</p>` : ''}
    ${p.open_question ? `<h3>Open question for USIL</h3><p>${esc(readable(p.open_question))}</p>` : ''}
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
    const [csvRes, schemaRes] = await Promise.all([fetch('data/papers.csv', { cache: 'no-cache' }), fetch('data/schema.json', { cache: 'no-cache' })]);
    if (!csvRes.ok || !schemaRes.ok) throw new Error(`HTTP ${csvRes.ok ? schemaRes.status : csvRes.status}`);
    SCHEMA = await schemaRes.json();
    PILLARS = SCHEMA.pillars;
    META = { snapshot: SCHEMA.meta.version, updated: SCHEMA.meta.updated, categories: SCHEMA.categories };
    PAPERS = parseCSV(await csvRes.text()).filter(r => r.key).map(toPaper)
      .sort((a, b) => (META.categories.indexOf(a.category) + 1 || 99) - (META.categories.indexOf(b.category) + 1 || 99) || (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title));
  } catch (err) {
    $('results').innerHTML = `<div class="empty">The paper data could not load (${esc(err.message)}). Open this page through a web server, such as GitHub Pages or <code>python -m http.server</code>, not as a local file.</div>`;
    return;
  }
  const years = PAPERS.map(p => p.year).filter(Boolean);
  const fresh = PAPERS.filter(p => p.provisional).length;
  $('how-pending').hidden = !fresh;
  // Visitor-facing counts only; how labels were made is explained in the notice below.
  $('facts').innerHTML = [
    [PAPERS.length, 'papers'],
    [fresh, 'not yet annotated'],
    [`${Math.min(...years)}–${Math.max(...years)}`, 'publication years'],
    [Object.keys(PILLARS).length, 'research challenges'],
  ].filter(([v]) => v).map(([v, l]) => `<div><dt>${esc(l)}</dt><dd>${esc(v)}</dd></div>`).join('');
  $('version').textContent = `Version ${META.snapshot} · updated ${META.updated}`;
  $('living-now').innerHTML = fresh
    ? `<b>Now:</b> ${fresh} papers are listed but not yet annotated, mostly because no full text is available yet. They are in Browse and join the charts once labeled. <a href="https://github.com/learning-to-work-with-you/usil-research-map#contributing" target="_blank" rel="noopener">Help annotate one ↗</a>`
    : '';
  $('chart-scope').textContent = `Charts count the ${PAPERS.length - fresh} annotated papers. Click a quadrant to filter, or a dot to open a paper.`;
  $('snapshot').textContent = `${META.snapshot} (${META.updated}), ${PAPERS.length} papers`;

  META.categories.forEach(c => $('f-category').add(new Option(c, c)));
  Object.entries(PILLARS).forEach(([k, v]) => $('f-pillar').add(new Option(`${k}: ${v}`, k)));
  Object.entries(CELLS).forEach(([k, v]) => $('f-cell').add(new Option(`${v.row} · ${v.col}`, k)));
  [...new Set(PAPERS.flatMap(p => p.decisions))].filter(d => d !== 'Other').sort().forEach(d => $('f-decision').add(new Option(d, d)));
  Object.keys(column('paper_type').values).forEach(d => { if (PAPERS.some(p => p.study.paper_type === d)) $('f-ptype').add(new Option(lab('paper_type', d), d)); });
  USERS.forEach(u => { if (PAPERS.some(p => p.study.evaluation_users === u.key)) $('f-users').add(new Option(u.label, u.key)); });

  $('f-q').addEventListener('input', e => setFilter({ q: e.target.value }, { scroll: false }));
  [['f-category', 'category'], ['f-pillar', 'pillar'], ['f-cell', 'cell'], ['f-decision', 'decision'], ['f-ptype', 'ptype'], ['f-users', 'users'], ['f-sort', 'sort']]
    .forEach(([id, key]) => $(id).addEventListener('change', e => setFilter({ [key]: e.target.value }, { scroll: false })));
  $('f-reset').addEventListener('click', () => setFilter({ q: '', category: '', pillar: '', cell: '', decision: '', ingr: '', cover: '', year: '', ptype: '', users: '', pp: false }, { scroll: false }));
  $('filters').addEventListener('submit', e => e.preventDefault());
  $('detail-close').addEventListener('click', () => $('detail').close());
  $('detail').addEventListener('click', e => { if (e.target === $('detail')) $('detail').close(); });

  setFilter({}, { scroll: false });
  let lastW = window.innerWidth, timer;
  window.addEventListener('resize', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { if (window.innerWidth !== lastW) { lastW = window.innerWidth; drawCharts(); } }, 150);
  });
}

init();
