/* VS corp CCTV Retail Analytics panel — hash-routed SPA. Every screen loads live data from the /api backend. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const app = $('#app');
const store = { get: k => { try { return localStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch {} }, del: k => { try { localStorage.removeItem(k); } catch {} } };

/* ---------- API + formatting ---------- */
async function api(path, { method = 'GET', body, form } = {}) {
  const init = { method };
  if (body) { init.headers = { 'Content-Type': 'application/json' }; init.body = JSON.stringify(body); }
  if (form) init.body = form;
  const res = await fetch('/api' + path, init);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed (' + res.status + ')');
  return data;
}
const qs = o => { const p = new URLSearchParams(); Object.entries(o).forEach(([k, v]) => { if (v !== '' && v != null) p.set(k, v); }); const s = p.toString(); return s ? '?' + s : ''; };
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const ymd = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const daysAgo = n => { const d = new Date(); d.setDate(d.getDate() - n); return ymd(d); };
const shortDay = iso => iso.slice(8, 10) + '/' + iso.slice(5, 7);
const fmtTime = iso => iso ? new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '----';
const fmtHours = h => h == null ? '----' : `${Math.floor(h)}:${String(Math.round((h % 1) * 60)).padStart(2, '0')} hr`;
const empty = (msg, icon = 'grid') => `<div class="empty"><div style="color:#b6bcc9">${ic(icon, 56)}</div><div style="margin-top:10px">${msg}</div></div>`;
const failed = err => `<div class="empty" style="color:var(--red)">${ib('alert', esc(err.message))}</div>`;
const opts = (items, first) => (first != null ? `<option value="">${first}</option>` : '') + items.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join('');
let locCache;
const locations = async () => (locCache ||= (await api('/locations')).locations);
const locOpts = async first => opts((await locations()).map(l => [l.id, l.name]), first);
const pager = (state, pages, total) => `<div class="pager"><span>Total Results: ${total}</span><span style="color:#0d9488">Page : ${state.page} of ${pages}</span><a href="#" data-pg="-1" style="color:#0d9488">Previous</a><a href="#" data-pg="1" style="color:#0d9488">Next</a></div>`;
function wirePager(root, state, pages, redraw) { $$('[data-pg]', root).forEach(a => a.onclick = e => { e.preventDefault(); const n = state.page + +a.dataset.pg; if (n >= 1 && n <= pages) { state.page = n; redraw(); } }); }
function openModal(html) { $('#modal-body').innerHTML = html; $('#modal').classList.add('open'); }
function closeModal() { $('#modal').classList.remove('open'); $('#modal-body').innerHTML = ''; }
const playVideo = (url, title = '') => openModal(`${title ? `<div style="color:#ddd;padding:8px 12px">${esc(title)}</div>` : ''}<video src="${url}" controls autoplay style="width:100%;max-height:70vh;background:#000"></video>`);

/* ---------- icons / nav ---------- */
const ICONS = {
  video: '<path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  grid: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
  ticket: '<path d="M21 10V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v4a2 2 0 0 1 0 4v4a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-4a2 2 0 0 1 0-4z"/><path d="M13 5v2M13 11v2M13 17v2"/>',
  message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  pie: '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
  store: '<path d="M3 9l1-5h16l1 5"/><path d="M4 9v11h16V9"/><path d="M9 20v-6h6v6"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
  filesearch: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><circle cx="11" cy="14" r="2.5"/><path d="M13 16l2 2"/>',
  film: '<rect x="2" y="2" width="20" height="20" rx="2.2"/><path d="M7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 17h5M17 7h5"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
  pin: '<path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5M12 15V3"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5M12 3v12"/>',
  printer: '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
  trend: '<path d="M23 6l-9.5 9.5-5-5L1 18"/><path d="M17 6h6v6"/>',
  alert: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeoff: '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24M1 1l22 22"/>',
  star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
  play: '<polygon points="5 3 19 12 5 21 5 3"/>',
  filter: '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};
const ic = (n, size = 18, fill = false) => `<svg class="ic" width="${size}" height="${size}" viewBox="0 0 24 24" fill="${fill ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n]}</svg>`;
const ib = (n, text, size = 16) => `<span class="ib">${ic(n, size)}${text}</span>`;

const LOGO = `<svg viewBox="0 0 64 64"><defs><linearGradient id="lg" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#0d9488"/><stop offset="1" stop-color="#2dd4bf"/></linearGradient></defs><path d="M6 20l14-7 8 12 24-18 8 7-30 40-8-2z" fill="url(#lg)"/><path d="M6 20l14 26 8 2V25L20 13z" fill="#0f172a"/></svg>`;
const NAV = [
  { i: 'video', t: 'Camera Feeds', links: [['Cameras', '#/cameras'], ['DVR Recordings', '#/dvr'], ['Camera Statistics', '#/camera-stats']] },
  { i: 'settings', t: 'Operational Intelligence', links: [['Audit Report', '#/audit'], ['Graphical Insights', '#/insights'], ['FR Attendance', '#/fr'], ['Retail Analytics', '#/retail'], ['Video Analysis', '#/analyze']] },
  { i: 'grid', t: 'Video Walls', links: [['Video Walls', '#/walls']] },
  { i: 'ticket', t: 'Ticket Management System', links: [['Tickets', '#/tickets']] },
  { i: 'message', t: 'VS corp Support', links: [['Support', '#/support']] },
];
const SEARCHABLE = [['Camera Statistics', '#/camera-stats'], ['Retail Analytics', '#/retail'], ['Graphical Insights', '#/insights'], ['Audit Report', '#/audit'], ['Cameras', '#/cameras'], ['DVR Recordings', '#/dvr'], ['FR Attendance', '#/fr'], ['Video Analysis (upload video)', '#/analyze'], ['Ticket Management System', '#/tickets'], ['Video Walls', '#/walls'], ['VS corp Support', '#/support']];

/* ---------- chart helpers (inline SVG) ---------- */
const smooth = pts => pts.map((p, i) => { if (!i) return `M${p[0]},${p[1]}`; const q = pts[i - 1], mx = (q[0] + p[0]) / 2; return `C${mx},${q[1]} ${mx},${p[1]} ${p[0]},${p[1]}`; }).join(' ');
const niceMax = v => { if (v <= 5) return 5; const p = 10 ** Math.floor(Math.log10(v)); return Math.ceil(v / p * 2) / 2 * p; };
function lineChart({ labels, series, w = 1100, h = 380, curve = true, xTitle }) {
  if (!labels.length) return empty('No data for this period');
  const L = 60, R = 20, T = 20, B = 60, mx = niceMax(Math.max(...series.flatMap(s => s.data), 1));
  const x = i => labels.length === 1 ? (L + w - R) / 2 : L + i * (w - L - R) / (labels.length - 1), y = v => T + (h - T - B) * (1 - v / mx);
  let g = '';
  for (let k = 0; k <= 4; k++) { const v = mx * k / 4; g += `<line x1="${L}" x2="${w - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e4e6ec"/><text x="${L - 12}" y="${y(v) + 4}" text-anchor="end" font-size="13">${Math.round(v)}</text>`; }
  labels.forEach((l, i) => g += `<text x="${x(i)}" y="${h - B + 26}" text-anchor="middle" font-size="13">${esc(l)}</text>`);
  series.forEach(s => { const pts = s.data.map((v, i) => [x(i), y(v)]); g += (pts.length > 1 ? `<path d="${curve ? smooth(pts) : 'M' + pts.map(p => p.join(',')).join('L')}" fill="none" stroke="${s.color}" stroke-width="2"/>` : '') + pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="${s.color}"><title>${esc(labels[i])} · ${s.name}: ${s.data[i]}</title></circle>`).join(''); });
  return `<div class="chart-scroll"><svg viewBox="0 0 ${w} ${h}" style="min-width:640px;width:100%">${g}${xTitle ? `<text x="${w / 2}" y="${h - 22}" text-anchor="middle" font-size="13">${xTitle}</text>` : ''}</svg></div><div class="legend">${series.map(s => `<span><i style="background:${s.color}"></i>${s.name}</span>`).join('')}</div>`;
}
function barChart({ labels, data, color = '#f59e0b', h = 320, w = 1100, unit = '', max }) {
  if (!labels.length) return empty('No data for this period');
  const L = 60, B = 50, T = 20, bw = 22, mx = max || niceMax(Math.max(...data, 1)), y = v => T + (h - T - B) * (1 - v / mx);
  let g = '';
  for (let k = 0; k <= 4; k++) { const v = mx * k / 4; g += `<line x1="${L}" x2="${w - 20}" y1="${y(v)}" y2="${y(v)}" stroke="#e4e6ec"/><text x="${L - 12}" y="${y(v) + 4}" text-anchor="end" font-size="13">${Math.round(v)}</text>`; }
  labels.forEach((l, i) => { const cx = L + (i + .5) * (w - L - 20) / labels.length; g += `<rect x="${cx - bw / 2}" y="${y(data[i])}" width="${bw}" height="${y(0) - y(data[i])}" fill="${color}"><title>${esc(l)}: ${data[i]}${unit}</title></rect><text x="${cx}" y="${h - B + 26}" text-anchor="middle" font-size="13">${esc(l)}</text>`; });
  return `<div class="chart-scroll"><svg viewBox="0 0 ${w} ${h}" style="min-width:560px;width:100%">${g}</svg></div><div class="legend"><span><i style="background:${color}"></i>Count</span></div>`;
}
function donut(parts, size = 190, ring = 34) {
  const tot = parts.reduce((a, p) => a + p.v, 0);
  if (!tot) return `<div class="pending">No data</div>`;
  const r = size / 2 - ring / 2, c = 2 * Math.PI * r; let off = 0;
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">${parts.map(p => { const len = p.v / tot * c; const s = `<circle r="${r}" cx="${size / 2}" cy="${size / 2}" fill="none" stroke="${p.c}" stroke-width="${ring}" stroke-dasharray="${len} ${c - len}" stroke-dashoffset="${-off}" transform="rotate(-90 ${size / 2} ${size / 2})"><title>${esc(p.n)}: ${p.v}</title></circle>`; off += len; return s; }).join('')}</svg>`;
}
function heat({ days, hours, cells }) {
  if (!cells.length) return empty('No footfall recorded for this period');
  const map = {}; let mx = 1; cells.forEach(c => { map[c.day + '|' + c.hour] = c.footfall; mx = Math.max(mx, c.footfall); });
  const cw = 90, ch = 27.5, L = 110, hl = h => { const n = h % 12 || 12; return `${String(n).padStart(2, '0')}${h < 12 || h === 24 ? 'AM' : 'PM'}`; };
  let g = '';
  hours.forEach((hr, r) => { g += `<text x="${L - 8}" y="${r * ch + 19}" text-anchor="end" font-size="13">${hl(hr)}-${hl(hr + 1)}</text>`; days.forEach((d, c) => { const v = map[d + '|' + hr] || 0, a = v / mx; g += `<rect x="${L + c * cw}" y="${r * ch}" width="${cw}" height="${ch}" fill="rgba(13,148,136,${.10 + a * .82})" stroke="#fff"><title>Date: ${d} · Time: ${hl(hr)}-${hl(hr + 1)} · Footfall: ${v}</title></rect><text x="${L + c * cw + cw / 2}" y="${r * ch + 18}" text-anchor="middle" font-size="12" fill="#123">${v}</text>`; }); });
  days.forEach((d, c) => g += `<text x="${L + c * cw + cw / 2}" y="${hours.length * ch + 26}" text-anchor="middle" font-size="13">${shortDay(d)}</text>`);
  return `<div class="chart-scroll"><svg viewBox="0 0 ${L + days.length * cw + 20} ${hours.length * ch + 40}" style="min-width:900px;width:100%">${g}</svg></div>`;
}

/* ---------- shell ---------- */
const crumb = (...parts) => `<nav class="crumbs">${parts.map((p, i) => i === parts.length - 1 ? `<span class="cur">${p[0]}</span>` : `<a href="${p[1]}">${p[0]}</a>`).join('')}</nav>`;
const card = (title, sub, inner, extra = '') => `<div class="card" style="margin-top:30px"><div class="row-line"><div><h3 style="font-weight:400;font-size:23px;margin:0">${title}</h3>${sub ? `<span style="color:#555;font-size:18px">${sub}</span>` : ''}</div>${extra}</div>${inner}</div>`;
function shell(body) {
  const id = store.get('vscorp-auth') || '', local = id.split('@')[0].replace(/[._\-\d]+/g, ' ').trim(), name = local ? local.replace(/\b\w/g, c => c.toUpperCase()) : id;
  const who = `<b style="font-weight:600;color:#e7e9f5">${esc(name)}</b><br><span style="font-size:12px;color:#8892b0">${esc(id)}</span>`;
  return `<aside class="sbar">
      <a class="sb-brand" href="#/">${LOGO}<span><b>VS corp</b><small>Retail Analytics</small></span></a>
      <nav class="sb-nav">${NAV.map(n => `<div class="sb-group"><h6>${ic(n.i, 15)}${n.t}</h6>${n.links.map(l => `<a href="${l[1]}">${l[0]}</a>`).join('')}</div>`).join('')}</nav>
      <div class="sb-user" id="user"><div class="avatar">${ic('user', 20)}</div><div>${who}</div><div class="menu" id="menu"><a href="#" data-a="logout">${ib('logout', 'Sign out')}</a></div></div>
    </aside>
    <header class="tbar"><div class="search"><input id="q" placeholder="Search for features" autocomplete="off"><span>${ic('search', 20)}</span><div class="search-results" id="sr"></div></div><div class="top-right"><span>NOTIFICATIONS</span></div></header>
    <main>${body}</main>`;
}
const camThumb = c => c.status === 'online' ? `<img src="/api/cameras/${c.id}/snapshot" loading="lazy" alt="" style="width:100%;height:100%;object-fit:cover;position:relative;z-index:1" onerror="this.parentNode.classList.add('off');this.remove()">` : '';

/* ---------- pages ---------- */
const pages = {};
pages.home = () => ({
  html: `<h2 class="sec">Features</h2><div class="feat">${[['Camera Feeds', 'video', '#/cameras'], ['Operational Intelligence', 'settings', '#/audit'], ['Video Walls', 'grid', '#/walls'], ['Ticket Management System', 'ticket', '#/tickets'], ['VS corp Support', 'message', '#/support']].map(t => `<a class="tile lg" href="${t[2]}"><span class="i">${ic(t[1], 40)}</span>${t[0]}</a>`).join('')}</div>
    <h2 class="sec" style="margin-top:34px">Quick Access</h2><div class="qa">${[['Camera Statistics', 'grid', '#/camera-stats'], ['Retail Analytics', 'store', '#/retail'], ['Graphical Insights', 'pie', '#/insights'], ['Audit Report', 'filesearch', '#/audit'], ['Cameras', 'video', '#/cameras'], ['Video Analysis', 'film', '#/analyze']].map(t => `<a class="tile sm" href="${t[2]}"><span class="i">${ic(t[1], 40)}</span>${t[0]}</a>`).join('')}</div>`,
});

pages.cameras = () => ({
  html: `${crumb(['Dashboard', '#/'], ['Camera Feeds', '#/cameras'], ['Cameras'])}
    <div class="chips" id="cam-chips"></div>
    <div class="card filters"><span class="ttl">${ib('filter', 'Filters', 18)}</span><label class="f">Select Location<select id="cf-loc"></select></label><label class="f">Camera Status<select id="cf-st"><option value="">All</option><option value="online">Connected</option><option value="offline">Disconnected</option></select></label><label class="f">Camera Name<input type="text" id="cf-name" placeholder="Search by camera name"></label><button class="btn red" id="cf-reset">Reset</button><button class="btn green" id="cf-go">${ib('search', 'Search')}</button></div>
    <div class="grid4" id="cam-grid"></div>`,
  async init() {
    $('#cf-loc').innerHTML = await locOpts('Select Location');
    const draw = async () => {
      try {
        const d = await api('/cameras' + qs({ location_id: $('#cf-loc').value, status: $('#cf-st').value, name: $('#cf-name').value }));
        const t = d.totals;
        $('#cam-chips').innerHTML = `<span class="chip blue">All Cameras: ${t.total}</span><span class="chip g">Connected: ${t.online}</span><span class="chip r">Disconnected: ${t.offline}</span><span class="chip">Total Bitrate Violations: ${t.bitrate_violations}</span><span class="upd">Last Updated: ${fmtTime(d.last_updated)}</span>`;
        $('#cam-grid').innerHTML = d.cameras.map(c => `<div class="cam"><div class="thumb ${c.status === 'online' ? '' : 'off'}">${camThumb(c)}</div><div class="cam-b"><h5>${esc(c.name)}</h5><div class="loc">${ic('pin', 14)} ${esc(c.location)}</div><div class="cam-row"><div>Status<b>${c.status === 'online' ? `<span class="tag on">ONLINE</span>${c.codec ? `<span class="tag h">${esc(c.codec)}</span>` : ''}` : '<span class="tag off">OFFLINE</span>'}</b></div><div>Bitrate<b>${c.bitrate_kbps == null || c.status !== 'online' ? 'N/A' : c.bitrate_violation ? `<span class="tag warn">${(c.bitrate_kbps / 1000).toFixed(2)} Mbps</span>` : `${c.bitrate_kbps.toFixed(2)} Kbps`}</b></div><div>Resolution<b>${c.status === 'online' && c.resolution ? esc(c.resolution) : 'N/A'}</b></div></div></div></div>`).join('') || `<div style="grid-column:1/-1">${empty('No cameras found')}</div>`;
      } catch (e) { $('#cam-grid').innerHTML = failed(e); }
    };
    $('#cf-go').onclick = draw; $('#cf-reset').onclick = () => { $('#cf-loc').value = ''; $('#cf-st').value = ''; $('#cf-name').value = ''; draw(); };
    draw();
  },
});

pages['camera-stats'] = () => ({
  html: `${crumb(['Dashboard', '#/'], ['Camera Feeds', '#/cameras'], ['Camera Statistics'])}
    <div class="tabs" id="cs-top"><button class="on">Camera Insights</button><button>Uptime Analysis</button><button>Camera Alerts</button></div><div id="cs-body"></div>`,
  async init() {
    const insights = async () => {
      $('#cs-body').innerHTML = `<div class="pending">Loading…</div>`;
      try {
        const d = await api('/cameras/summary'), c = d.cameras, l = d.locations, rt = d.by_source_type.find(x => x.source_type === 'RTSP') || { total: 0, active: 0 }, ag = d.by_source_type.find(x => x.source_type !== 'RTSP') || { total: 0, active: 0 };
        const cams = (await api('/cameras')).cameras;
        $('#cs-body').innerHTML = `<div class="row-line" style="margin-bottom:20px"><span style="font-size:18px;color:#555">Last Updated: ${fmtTime(d.last_updated)}</span><a class="lnk" href="/api/cameras" target="_blank">Export Data</a></div>
        <div class="kpis"><div class="card"><h3>Overview</h3><div style="display:flex;align-items:center;gap:26px">${donut([{ n: 'Active', v: c.active, c: '#10b981' }, { n: 'Inactive', v: c.total - c.active, c: '#e9ecef' }], 150, 14)}<div class="two"><div class="kv">${c.total}<small>Total Cameras</small></div><div class="kv g">${c.active}<small>Active Cameras</small></div><div class="kv">${l.total}<small>Total Locations</small></div><div class="kv y">${l.active}<small>Active Locations</small></div></div></div></div>
        <div class="card"><h3>RTSP Cameras</h3><div class="kv">${rt.total}<small>Total Cameras</small></div><div class="kv g">${rt.active}<small>Active Cameras</small></div></div>
        <div class="card"><h3>Streaming Agent Cameras</h3><div class="kv">${ag.total}<small>Total Cameras</small></div><div class="kv g">${ag.active}<small>Active Cameras</small></div></div>
        <div class="card"><h3>Total Bitrate Violations</h3><div class="kv r">${c.bitrate_violations}</div><small style="color:#555">Limit: ${d.bitrate_limit_kbps} Kbps</small></div></div>
        <div class="card row-line" style="margin:34px 0 26px"><span style="font-size:18px">Disconnected Locations : <a style="color:#0d9488">${d.disconnected_locations.length}</a></span><button class="lnk" id="vd">View Details ${ic('chevron', 16)}</button></div>
        <div id="disc" class="card" style="display:none;margin-bottom:26px">${d.disconnected_locations.map(x => `<div style="padding:6px 0">${esc(x.name)} — ${x.total} camera(s) offline</div>`).join('') || 'All locations are connected.'}</div>
        <div class="tabs" id="cs-sub"><button class="on">Location Stats</button><button>Camera Stats</button></div><div class="card" id="st-tbl"></div>`;
        $('#vd').onclick = () => { const x = $('#disc'); x.style.display = x.style.display === 'none' ? 'block' : 'none'; };
        const draw = i => { $('#st-tbl').innerHTML = i === 0 ? (d.by_location.length ? `<table class="tbl"><thead><tr><th>Location</th><th>Total</th><th>Active</th><th>Disconnected</th><th>Bitrate violations</th></tr></thead><tbody>${d.by_location.map(x => `<tr><td>${esc(x.name)}</td><td>${x.total}</td><td>${x.active}</td><td>${x.disconnected}</td><td>${x.bitrate_violations}</td></tr>`).join('')}</tbody></table>` : empty('No locations yet')) : (cams.length ? `<table class="tbl"><thead><tr><th>Camera</th><th>Location</th><th>Status</th><th>Bitrate</th><th>Resolution</th></tr></thead><tbody>${cams.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(x.location)}</td><td>${x.status === 'online' ? '<span class="tag on">ONLINE</span>' : '<span class="tag off">OFFLINE</span>'}</td><td>${x.bitrate_kbps != null ? x.bitrate_kbps + ' Kbps' : 'N/A'}</td><td>${esc(x.resolution || 'N/A')}</td></tr>`).join('')}</tbody></table>` : empty('No cameras yet')); };
        const sub = $$('#cs-sub button'); sub.forEach((b, i) => b.onclick = () => { sub.forEach(x => x.classList.toggle('on', x === b)); draw(i); }); draw(0);
      } catch (e) { $('#cs-body').innerHTML = failed(e); }
    };
    const top = $$('#cs-top button');
    top.forEach((b, i) => b.onclick = () => { top.forEach(x => x.classList.toggle('on', x === b)); i === 0 ? insights() : $('#cs-body').innerHTML = empty(`${b.textContent} is not available yet`); });
    insights();
  },
});

pages.dvr = () => {
  const st = { page: 1 };
  return {
    html: `${crumb(['Dashboard', '#/'], ['Camera Feeds', '#/cameras'], ['DVR Recordings'])}
    <div class="card filters"><span class="ttl">${ib('filter', 'Filters', 18)}</span><label class="f">Feed Name<input type="text" id="dv-n" placeholder="Search by Feed name"></label><label class="f">Select Date<input type="date" id="dv-d" value="${ymd(new Date())}"></label><label class="f">Select Location<select id="dv-l"></select></label><button class="btn green" id="dv-go">Search</button></div>
    <p style="text-align:right;margin:34px 26px 14px;font-size:19px"><b>Timezone</b> - Asia/Kolkata</p><div id="dv-out"></div>`,
    async init() {
      $('#dv-l').innerHTML = await locOpts('All locations');
      const draw = async () => {
        try {
          const d = await api('/recordings' + qs({ date: $('#dv-d').value, location_id: $('#dv-l').value, name: $('#dv-n').value, page: st.page }));
          $('#dv-out').innerHTML = d.feeds.length ? `<table class="tbl"><thead><tr><th>FEED NAME</th><th>FEED<br>SOURCE</th><th>LOCATION</th><th>DVR RECORDINGS (HOUR WISE)</th></tr></thead><tbody>${d.feeds.map(f => `<tr><td>${esc(f.name)}</td><td><span class="src">${esc(f.source_type)}</span></td><td>${esc(f.location)}</td><td><div class="slots">${f.slots.map(s => `<button class="slot" ${s.recording_id ? `data-rec="${s.recording_id}" data-t="${esc(f.name)} · ${s.label}"` : 'disabled style="opacity:.4;cursor:default"'}>${s.label}</button>`).join('')}</div></td></tr>`).join('')}</tbody></table>${pager(st, d.pages, d.total)}` : empty('No feeds found');
          $$('.slot[data-rec]').forEach(b => b.onclick = () => playVideo(`/api/recordings/${b.dataset.rec}/video`, b.dataset.t));
          wirePager($('#dv-out'), st, d.pages, draw);
        } catch (e) { $('#dv-out').innerHTML = failed(e); }
      };
      $('#dv-go').onclick = () => { st.page = 1; draw(); }; draw();
    },
  };
};

pages.audit = () => {
  const st = { page: 1, per: 20 };
  return {
    html: `${crumb(['Dashboard', '#/'], ['Operational Intelligence', '#/audit'], ['Audit Report'])}
    <div class="card"><div class="filters" style="justify-content:flex-start"><label class="f">Start Date<input type="date" id="au-sd" value="${daysAgo(1)}"></label><label class="f">Start Time<input type="time" step="1" id="au-st" value="00:00:00"></label><label class="f">End Date<input type="date" id="au-ed" value="${ymd(new Date())}"></label><label class="f">End Time<input type="time" step="1" id="au-et" value="23:59:59"></label><label class="f">Select Location<select id="au-loc"></select></label><label class="f">Select Events<select id="au-ev"></select></label></div>
    <div class="filters" style="justify-content:flex-start;margin-top:12px"><label class="f">Important<select id="au-im"><option value="">ALL</option><option value="true">Important</option></select></label><label class="f">Result<input type="text" id="au-r" placeholder="Search Result"></label><span style="flex:1"></span><button class="btn red" id="au-rs">Reset</button><button class="btn green" id="au-go">${ib('search', 'Search')}</button><a class="btn ghost" id="au-ex" style="display:grid;place-items:center">${ib('download', 'Export CSV')}</a></div></div><div id="au-out" style="margin-top:24px"></div>`,
    async init() {
      $('#au-loc').innerHTML = await locOpts('Select Location');
      try { $('#au-ev').innerHTML = opts((await api('/events/types')).event_types.map(t => [t, t]), 'Select Events'); } catch {}
      const filters = () => ({ start: $('#au-sd').value + 'T' + ($('#au-st').value || '00:00:00').padEnd(8, ':00'), end: $('#au-ed').value + 'T' + ($('#au-et').value || '23:59:59').padEnd(8, ':00'), location_id: $('#au-loc').value, event_type: $('#au-ev').value, important: $('#au-im').value, q: $('#au-r').value });
      const draw = async () => {
        try {
          const f = filters(), d = await api('/events' + qs({ ...f, page: st.page, per_page: st.per }));
          $('#au-ex').href = '/api/events/export' + qs(f);
          $('#au-out').innerHTML = d.items.length ? `<table class="tbl"><thead><tr><th>S.NO.</th><th>FEED</th><th>EVENT TYPE</th><th>IMAGE</th><th>RESULT</th><th>TICKET</th><th>PLAYBACK</th></tr></thead><tbody>${d.items.map((r, i) => `<tr><td>${(st.page - 1) * st.per + i + 1}</td><td>${ic('pin', 14)} ${esc(r.location || 'N/A')}<br>${ic('video', 14)} ${esc(r.camera || 'N/A')}</td><td>${esc(r.event_type)}<br>${fmtTime(r.ts)}</td><td>${r.image_url ? `<img class="face" src="${esc(r.image_url)}" alt="" style="object-fit:cover">` : '<span class="pending">No image</span>'}</td><td>${esc(r.result || '—')}</td><td>${r.ticket_id ? '#' + r.ticket_id : 'N/A'}</td><td>${r.recording_id ? `<button class="view" data-rec="${r.recording_id}">${ib('play', 'View', 13)}</button>` : '<span class="pending">—</span>'}</td></tr>`).join('')}</tbody></table>${pager(st, d.pages, d.total)}` : empty('No events found for these filters');
          $$('.view').forEach(b => b.onclick = () => playVideo(`/api/recordings/${b.dataset.rec}/video`));
          wirePager($('#au-out'), st, d.pages, draw);
        } catch (e) { $('#au-out').innerHTML = failed(e); }
      };
      $('#au-go').onclick = () => { st.page = 1; draw(); };
      $('#au-rs').onclick = () => { $('#au-loc').value = ''; $('#au-ev').value = ''; $('#au-r').value = ''; $('#au-im').value = ''; st.page = 1; draw(); };
      draw();
    },
  };
};

pages.insights = () => ({
  html: `${crumb(['Dashboard', '#/'], ['Operational Intelligence', '#/audit'], ['Graphical Insights'])}<div class="row-line" style="margin:-8px 0 14px;justify-content:flex-end"><button class="btn green" onclick="window.print()">${ib('printer', 'Print PDF')}</button></div>
    <div class="ev3" id="in-cards"><div class="pending">Loading…</div></div>
    <div class="row-line" style="margin:36px 0 20px;border-top:1px solid var(--line);padding-top:30px"><span style="font-size:24px">${ib('trend', 'Statistics', 22)}</span><div class="card filters" style="padding:12px 16px"><label class="f">Select Location<select id="in-loc"></select></label><label class="f">From<input type="date" id="in-s" value="${daysAgo(15)}"></label><label class="f">To<input type="date" id="in-e" value="${ymd(new Date())}"></label><button class="btn blue" id="in-go">Apply</button></div></div>
    <div class="ev3" style="grid-template-columns:1fr 1fr" id="in-charts"></div>`,
  async init() {
    $('#in-loc').innerHTML = await locOpts('All locations');
    const cardHtml = (t, sub, p, since) => `<div class="card ev"><h3>${t}</h3><small style="color:#555">${sub}</small><div class="big">${p.total}</div><div style="margin-bottom:22px">${p.change_pct == null ? '<small style="color:#555">No previous data to compare</small>' : `<b class="${p.change_pct > 0 ? 'dn' : 'up'}">${p.change_pct > 0 ? '↑' : '↓'} ${Math.abs(p.change_pct)}%</b> <small style="text-transform:none;color:#555">${since}</small>`}</div><hr style="border:0;border-top:1px solid var(--line)"><h4 style="font-weight:400;font-size:19px;margin:16px 0 12px">Event-Wise Count</h4>${Object.entries(p.by_type).map(([k, v]) => `<span class="pill">${esc(k)} : ${v}</span>`).join('') || '<span class="pending">No events</span>'}</div>`;
    const draw = async () => {
      try {
        const loc = $('#in-loc').value, s = await api('/events/summary' + qs({ location_id: loc }));
        $('#in-cards').innerHTML = cardHtml("Week's Event Violations", `TOTAL (${s.week.from} to ${s.week.to})`, s.week, `Since last week (${s.week.previous.from} to ${s.week.previous.to})`) + cardHtml("Yesterday's Event Violations", 'TOTAL', s.yesterday, 'Since day before yesterday') + cardHtml("Today's Event Violations", 'TOTAL', s.today, 'Since yesterday');
        const d = await api('/events/stats' + qs({ start: $('#in-s').value, end: $('#in-e').value, location_id: loc }));
        const colors = ['#0d9488', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];
        $('#in-charts').innerHTML = `<div class="card"><h3 style="font-weight:400;font-size:22px;margin:0 0 10px">Event Count</h3>${barChart({ labels: d.by_type.map(x => x.event_type), data: d.by_type.map(x => x.count), color: '#0d9488', h: 300 })}</div><div class="card"><h3 style="font-weight:400;font-size:22px;margin:0 0 10px">Event Violations by Type</h3><div style="display:grid;place-items:center;padding:20px">${donut(d.by_type.map((x, i) => ({ n: x.event_type, v: x.count, c: colors[i % colors.length] })), 230, 40)}</div><div class="legend">${d.by_type.map((x, i) => `<span><i style="background:${colors[i % colors.length]}"></i>${esc(x.event_type)}</span>`).join('')}</div></div><div class="card" style="grid-column:1/-1"><h3 style="font-weight:400;font-size:22px;margin:0 0 10px">Events per day</h3>${lineChart({ labels: d.by_day.map(x => shortDay(x.day)), series: [{ name: 'Events', color: '#ef4444', data: d.by_day.map(x => x.count) }], h: 300 })}</div>`;
      } catch (e) { $('#in-cards').innerHTML = failed(e); }
    };
    $('#in-go').onclick = draw; draw();
  },
});

pages.fr = () => ({
  html: `${crumb(['Dashboard', '#/'], ['Operational Intelligence', '#/audit'], ['FR Attendance'])}
    <div style="text-align:center;margin-bottom:34px"><div class="btnrow" style="justify-content:center;gap:0"><button class="btn dark" style="width:175px;border-radius:0" id="fr-a">Attendance</button><button class="btn ghost" style="width:175px;border-radius:0;border:1px solid #333" id="fr-r">Reports Panel</button></div></div><div id="fr-body"></div>`,
  async init() {
    const locs = await locOpts('All locations');
    const th = 'style="background:#fff;color:var(--blue);padding:12px 8px"';
    const att = async () => {
      $('#fr-body').innerHTML = `<div class="attn"><div class="stat">Employees on<br>Present / Total <b id="fr-p">–</b></div><div class="stat">Employees on<br>Absent / Total <b id="fr-ab">–</b></div><div class="card filters" style="justify-content:flex-start;padding:16px"><label class="f">Select Date<input type="date" id="fr-d" value="${ymd(new Date())}"></label><label class="f">Attendance<select id="fr-f"><option value="">All</option><option value="present">Present</option><option value="absent">Absent</option></select></label><label class="f">Select Location<select id="fr-l">${locs}</select></label><button class="btn blue" id="fr-s">${ib('search', 'Search')}</button><button class="btn green" onclick="window.print()">${ic('printer', 18)}</button></div></div>
      <div class="card"><div class="row-line" style="margin-bottom:12px"><span style="font-size:22px;color:var(--blue)">Employee attendance details</span><span><input type="text" id="fr-q" placeholder="Search Employee name" style="border-color:#0d9488;min-width:230px"> <button class="btn blue" id="fr-b" style="height:34px;font-size:14px">search</button></span></div><div id="fr-t"></div></div>`;
      const draw = async () => {
        try {
          const d = await api('/attendance' + qs({ date: $('#fr-d').value, status: $('#fr-f').value, location_id: $('#fr-l').value, q: $('#fr-q').value }));
          $('#fr-p').textContent = `${d.summary.present}/${d.summary.total}`; $('#fr-ab').textContent = `${d.summary.absent}/${d.summary.total}`;
          $('#fr-t').innerHTML = d.employees.length ? `<table class="tbl" style="color:var(--blue)"><thead><tr><th ${th}>S.No</th><th ${th}>Employee ID</th><th ${th}>Name</th><th ${th}>Clock-In</th><th ${th}>Clock-Out</th><th ${th}>Logs</th><th ${th}>Total Hours</th><th ${th}>Overtime</th></tr></thead><tbody>${d.employees.map((e, i) => e.present ? `<tr><td>${i + 1}</td><td>${esc(e.code)}</td><td>${esc(e.name)}</td><td>${fmtTime(e.clock_in)}<br>${esc(e.clock_in_location || '')}</td><td>${e.clock_out ? fmtTime(e.clock_out) + '<br>' + esc(e.clock_out_location || '') : '----'}</td><td><a href="#" data-log="${e.id}" style="color:#0d9488;text-decoration:underline">View Logs</a></td><td>${fmtHours(e.total_hours)}</td><td>${e.overtime_hours ? fmtHours(e.overtime_hours) : '----'}</td></tr>` : `<tr><td>${i + 1}</td><td>${esc(e.code)}</td><td>${esc(e.name)}</td><td colspan="5"><div class="abs">Absent</div></td></tr>`).join('')}</tbody></table>` : empty('No employees found');
          $$('[data-log]').forEach(a => a.onclick = async ev => { ev.preventDefault(); try { const l = await api(`/attendance/${a.dataset.log}/logs` + qs({ start: $('#fr-d').value, end: $('#fr-d').value })); openModal(`<div style="background:#fff;padding:20px;max-height:70vh;overflow:auto"><h3 style="margin-top:0">${esc(l.employee.name)} — logs</h3>${l.logs.map(x => `<div style="padding:6px 0">${x.kind === 'in' ? 'In' : 'Out'} · ${fmtTime(x.ts)} · ${esc(x.location || '')}</div>`).join('') || 'No logs'}</div>`); } catch (er) { openModal(`<div style="background:#fff;padding:20px">${esc(er.message)}</div>`); } });
        } catch (e) { $('#fr-t').innerHTML = failed(e); }
      };
      $('#fr-b').onclick = $('#fr-s').onclick = draw; draw();
    };
    const rep = async () => {
      $('#fr-body').innerHTML = `<div class="card"><h3 style="font-weight:400;font-size:22px;margin:0 0 16px">Daily attendance (last 30 days)</h3><div id="fr-rc"></div></div>`;
      try { const d = await api('/attendance/report'); $('#fr-rc').innerHTML = lineChart({ labels: d.days.map(x => shortDay(x.day)), series: [{ name: 'Present', color: '#10b981', data: d.days.map(x => x.present) }, { name: 'Absent', color: '#ef4444', data: d.days.map(x => x.absent) }], h: 320 }); } catch (e) { $('#fr-rc').innerHTML = failed(e); }
    };
    const sw = (a, b, f) => { a.className = 'btn dark'; a.style.color = ''; b.className = 'btn ghost'; f(); };
    $('#fr-a').onclick = () => sw($('#fr-a'), $('#fr-r'), att); $('#fr-r').onclick = () => sw($('#fr-r'), $('#fr-a'), rep); att();
  },
});

pages.retail = () => ({
  html: `${crumb(['Dashboard', '#/'], ['Operational Intelligence', '#/audit'], ['Retail Analytics'])}
    <div class="card filters"><label class="f">Select Location<select id="rt-loc" style="min-width:250px"></select></label><label class="f">From<input type="date" id="rt-s" value="${daysAgo(15)}"></label><label class="f">To<input type="date" id="rt-e" value="${ymd(new Date())}"></label><button class="btn blue" style="background:#0d9488" id="rt-go">${ib('search', 'Search')}</button></div>
    <div id="rt-out"><div class="pending" style="margin:20px">Loading…</div></div>`,
  async init() {
    $('#rt-loc').innerHTML = await locOpts('All locations');
    const chg = v => v == null ? '<span style="color:#555">no prior data</span>' : `<b class="${v < 0 ? 'dn' : 'up'}">${v < 0 ? '↘' : '↗'} ${Math.abs(v)}%</b>`;
    const draw = async () => {
      const p = { start: $('#rt-s').value, end: $('#rt-e').value, location_id: $('#rt-loc').value }, range = `(${p.start} to ${p.end})`;
      try {
        const [sum, heatD, ts, age, dwell, cams] = await Promise.all([api('/retail/summary' + qs(p)), api('/retail/heatmap' + qs(p)), api('/retail/timeseries' + qs(p)), api('/retail/age' + qs(p)), api('/retail/dwell' + qs(p)), api('/cameras' + qs({ location_id: p.location_id, status: 'online' }))]);
        const dm = sum.demographics, d = sum.compare_days, pts = ts.points, colors = ['#0d9488', '#06b6d4', '#10b981', '#f59e0b'];
        $('#rt-out').innerHTML = `<div class="metrics3">
        <div class="metric"><h3>Demographics</h3><div style="font-size:38px"><span style="color:#2563eb">${dm.male}</span> <small style="font-size:14px;color:#555">Male</small> <small style="font-size:14px;color:#555">${dm.male_pct}%</small> <span style="color:#10b981">${dm.female}</span> <small style="font-size:14px;color:#555">Female</small> <small style="font-size:14px;color:#555">${dm.female_pct}%</small></div><div class="d">${chg(dm.male_change_pct)} | ${chg(dm.female_change_pct)} Vs PREV ${d} Days</div></div>
        <div class="metric"><h3>Total Footfall</h3><div class="v">${sum.footfall.value}</div><div class="d">${chg(sum.footfall.change_pct)} Vs PREV ${d} Days</div></div>
        <div class="metric"><h3>Conversion Rate</h3><div class="v" style="font-size:46px">${sum.conversion.rate_pct.toFixed(2)}% <small style="font-size:18px;color:#555">(${sum.conversion.transactions} transactions)</small></div><div class="d">Vs PREV ${d} Days: ${sum.conversion.previous_rate_pct.toFixed(2)}%</div></div></div>
        ${cams.cameras.length ? `<div class="wall">${cams.cameras.slice(0, 4).map(c => `<div class="thumb">${camThumb(c)}<span class="ts">${esc(c.location)} · ${esc(c.name)}</span></div>`).join('')}</div>` : ''}
        ${card('Footfall Count - According to specific time and date', range, `<div style="margin-top:20px">${heat(heatD)}</div>`)}
        ${card('Footfall Analysis by Date Wise (Total)', range, `<div style="margin-top:14px">${lineChart({ labels: pts.map(x => shortDay(x.label)), series: [{ name: 'Male', color: '#2563eb', data: pts.map(x => x.male) }, { name: 'Female', color: '#34d399', data: pts.map(x => x.female) }, { name: 'Total Footfall', color: '#f59e0b', data: pts.map(x => x.total) }] })}</div>`)}
        ${card('Avg. Time spent by the customer (mm:ss)', '', `<div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:30px;margin-top:20px"><div style="background:#0d9488;color:#fff;border-radius:10px;padding:26px;width:312px;height:175px"><span style="font-size:23px">Entry to exit</span><div style="font-size:48px;margin-top:26px">${dwell.average ?? '--:--'}</div></div><div style="text-align:center;margin-right:60px"><b style="font-weight:400;font-size:20px">Avg. Visit Duration</b><br><small style="font-size:16px;text-transform:none">(By % group of people)</small><div style="margin:24px 0 18px">${donut(dwell.buckets.map((b, i) => ({ n: b.label, v: b.count, c: colors[i] })), 180, 32)}</div><div class="legend">${dwell.buckets.map((b, i) => `<span><i style="background:${colors[i]}"></i>${b.label}</span>`).join('')}</div></div></div>`)}
        ${card('Age Profiling', range, barChart({ labels: age.groups.map(g => g.label), data: age.groups.map(g => g.percent), unit: ' %', max: 100 }))}
        <div style="margin-bottom:30px">${card('Total Footfall Vs Transaction - Daily', range, lineChart({ labels: pts.map(x => shortDay(x.label)), series: [{ name: 'Footfall', color: '#f59e0b', data: pts.map(x => x.total) }, { name: 'Transaction', color: '#10b981', data: pts.map(x => x.transactions) }], curve: false, xTitle: 'Days' }))}</div>`;
      } catch (e) { $('#rt-out').innerHTML = failed(e); }
    };
    $('#rt-go').onclick = draw; draw();
  },
});

pages.tickets = () => {
  const st = { page: 1, tab: 0 };
  return {
    html: `${crumb(['Dashboard', '#/'], ['Ticket Management'])}
    <div class="tabs" id="tk-tabs"><button class="on">Tickets</button><button>Dashboard</button><button>Starred</button></div>
    <div id="tk-filters" class="filters" style="justify-content:flex-start"><input type="text" id="tk-q" placeholder="Search by ID / Title" style="width:250px"><select id="tk-l" style="width:220px"></select><select id="tk-s" style="width:170px"><option value="">Select status</option><option value="open">Open</option><option value="in_progress">In progress</option><option value="closed">Closed</option></select><select id="tk-p" style="width:170px"><option value="">Select priority</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select><input type="date" id="tk-a"><input type="date" id="tk-b"><button class="btn outline" id="tk-go">Apply</button><button class="btn outline red" id="tk-rs">Reset</button><button class="btn blue" id="tk-new">${ib('plus', 'New ticket')}</button></div><div id="tk-out" style="margin-top:24px"></div>`,
    async init() {
      $('#tk-l').innerHTML = await locOpts('Select Location');
      const draw = async () => {
        if (st.tab === 1) {
          $('#tk-filters').style.display = 'none';
          try { const s = await api('/tickets/summary'); $('#tk-out').innerHTML = `<div class="kpis" style="grid-template-columns:repeat(3,1fr)"><div class="card"><h3>Total</h3><div class="kv">${s.total}</div></div><div class="card"><h3>By status</h3>${Object.entries(s.by_status).map(([k, v]) => `<div>${k}: <b>${v}</b></div>`).join('') || '—'}</div><div class="card"><h3>By priority</h3>${Object.entries(s.by_priority).map(([k, v]) => `<div>${k}: <b>${v}</b></div>`).join('') || '—'}</div></div>`; } catch (e) { $('#tk-out').innerHTML = failed(e); }
          return;
        }
        $('#tk-filters').style.display = 'flex';
        try {
          const d = await api('/tickets' + qs({ q: $('#tk-q').value, location_id: $('#tk-l').value, status: $('#tk-s').value, priority: $('#tk-p').value, start: $('#tk-a').value, end: $('#tk-b').value, starred: st.tab === 2 ? 'true' : '', page: st.page }));
          $('#tk-out').innerHTML = d.items.length ? `<table class="tbl"><thead><tr><th>Star</th><th>ID</th><th>Title</th><th>Location</th><th>Priority</th><th>Status</th><th>Created</th></tr></thead><tbody>${d.items.map(t => `<tr><td><button data-star="${t.id}" data-v="${t.starred ? 0 : 1}" style="border:0;background:none;font-size:20px">${t.starred ? ic('star', 20, true) : ic('star', 20)}</button></td><td>#${t.id}</td><td>${esc(t.title)}<br><small style="text-transform:none;color:#555">${esc(t.description || '')}</small></td><td>${esc(t.location || '—')}</td><td>${esc(t.priority)}</td><td><select data-st="${t.id}" style="min-width:120px">${['open', 'in_progress', 'closed'].map(s => `<option ${s === t.status ? 'selected' : ''}>${s}</option>`).join('')}</select></td><td>${fmtTime(t.created_at)}</td></tr>`).join('')}</tbody></table>${pager(st, d.pages, d.total)}` : empty('No Data Found', 'search');
          $$('[data-star]').forEach(b => b.onclick = async () => { await api('/tickets/' + b.dataset.star, { method: 'PATCH', body: { starred: b.dataset.v === '1' } }); draw(); });
          $$('[data-st]').forEach(s => s.onchange = async () => { await api('/tickets/' + s.dataset.st, { method: 'PATCH', body: { status: s.value } }); });
          wirePager($('#tk-out'), st, d.pages, draw);
        } catch (e) { $('#tk-out').innerHTML = failed(e); }
      };
      const tabs = $$('#tk-tabs button'); tabs.forEach((b, i) => b.onclick = () => { tabs.forEach(x => x.classList.toggle('on', x === b)); st.tab = i; st.page = 1; draw(); });
      $('#tk-go').onclick = () => { st.page = 1; draw(); };
      $('#tk-rs').onclick = () => { ['tk-q', 'tk-l', 'tk-s', 'tk-p', 'tk-a', 'tk-b'].forEach(id => $('#' + id).value = ''); st.page = 1; draw(); };
      $('#tk-new').onclick = async () => {
        openModal(`<form id="nt" style="background:#fff;padding:22px;display:grid;gap:12px"><h3 style="margin:0">New ticket</h3><input type="text" name="title" placeholder="Title" required style="width:100%"><input type="text" name="description" placeholder="Description" style="width:100%"><select name="priority"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option><option value="critical">Critical</option></select><select name="location_id">${await locOpts('No location')}</select><p class="err" id="nt-e"></p><button class="btn blue">Create</button></form>`);
        $('#nt').onsubmit = async e => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target)); f.location_id = f.location_id ? +f.location_id : null; try { await api('/tickets', { method: 'POST', body: f }); closeModal(); draw(); } catch (er) { $('#nt-e').textContent = er.message; } };
      };
      draw();
    },
  };
};

pages.walls = () => ({
  html: `${crumb(['Dashboard', '#/'], ['Video Walls'])}<div id="wl"><div class="pending">Loading…</div></div>`,
  async init() {
    try { const d = await api('/cameras' + qs({ status: 'online' })); $('#wl').innerHTML = d.cameras.length ? `<div class="wall" style="grid-template-columns:repeat(3,1fr)">${d.cameras.map(c => `<div class="thumb">${camThumb(c)}<span class="ts">${esc(c.location)} · ${esc(c.name)}</span></div>`).join('')}</div>` : empty('No live cameras to display', 'grid'); } catch (e) { $('#wl').innerHTML = failed(e); }
  },
});
pages.support = () => ({ html: `${crumb(['Dashboard', '#/'], ['VS corp Support'])}${empty('Contact your VS corp administrator for support.', 'message')}` });

/* ---------- Video analysis: upload → annotated video + demographics ---------- */
pages.analyze = () => ({
  html: `${crumb(['Dashboard', '#/'], ['Operational Intelligence', '#/audit'], ['Video Analysis'])}
    <div class="an-grid"><form class="card" id="an-form"><h3 style="font-weight:400;font-size:24px;margin:0 0 16px">1 · Upload video</h3>
      <label class="drop" id="drop" for="an-file"><input id="an-file" type="file" accept="video/*" required><span class="up">${ic('upload', 34)}</span><b id="an-name">Drop a video here</b><small>or click to browse · MP4, AVI, MOV, MKV</small></label>
      <div class="opts"><label class="f">Store location<select id="o-loc"></select></label></div>
      <button class="btn blue" style="width:100%;height:48px" id="an-go">Analyze footage</button><p class="err" id="an-err" style="margin-top:12px"></p></form>
    <div class="card"><div class="row-line"><h3 style="font-weight:400;font-size:24px;margin:0">2 · Annotated video</h3><span class="chip" id="an-st">Waiting</span></div>
      <div class="row-line" style="margin-top:14px;font-size:13px;color:var(--muted)"><span id="an-msg">Upload a video to begin</span><b id="an-pct" style="color:var(--ink)">0%</b></div><div class="prog"><i id="an-bar"></i></div>
      <div class="vid" id="an-vid" style="margin-top:14px"><span id="an-empty">Annotated footage will appear here</span><video id="an-video" controls></video></div>
      <a class="btn dark" id="an-dl" style="display:none;margin-top:14px;padding:11px 16px;height:auto;text-align:center" download>${ib('download', 'Download annotated video')}</a></div></div>
    <div class="card" style="margin-top:22px"><h3 style="font-weight:400;font-size:24px;margin:0">3 · Demographics</h3>
      <div class="demo3"><div class="demo"><small>FOOTFALL (CROSSINGS)</small><b id="d-foot">--</b></div><div class="demo" style="border-color:#2563eb"><small>MALE</small><b id="d-m">--</b></div><div class="demo" style="border-color:#10b981"><small>FEMALE</small><b id="d-f">--</b></div><div class="demo" style="border-color:#f59e0b"><small>PEOPLE TRACKED</small><b id="d-t">--</b></div></div>
      <div id="d-split"><p class="pending">Gender split appears here once analysis completes.</p></div>
      <p class="pending" style="margin-top:14px">Results are also saved to Retail Analytics for the selected store location.</p></div>`,
  async init() {
    $('#o-loc').innerHTML = await locOpts('No location');
    const file = $('#an-file'), drop = $('#drop'); let timer;
    const setName = () => { if (file.files[0]) $('#an-name').textContent = file.files[0].name; };
    file.onchange = setName;
    ['dragenter', 'dragover'].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove('drag'); }));
    drop.addEventListener('drop', e => { file.files = e.dataTransfer.files; setName(); });
    const status = (s, p, m) => { $('#an-st').textContent = s; $('#an-pct').textContent = p + '%'; $('#an-msg').textContent = m || 'Waiting'; $('#an-bar').style.width = p + '%'; };
    const show = job => {
      const s = job.summary || {}, m = s.male || 0, f = s.female || 0, c = m + f;
      $('#d-foot').textContent = s.footfall ?? '--'; $('#d-m').textContent = m; $('#d-f').textContent = f; $('#d-t').textContent = s.tracked_people ?? '--';
      $('#d-split').innerHTML = c ? `<div class="row-line"><span>Male <b>${Math.round(m / c * 100)}%</b></span><span>Female <b>${Math.round(f / c * 100)}%</b></span></div><div class="bar2"><i style="width:${m / c * 100}%;background:#2563eb"></i><i style="width:${f / c * 100}%;background:#10b981"></i></div><small style="color:var(--muted)">Based on ${c} classified crossings</small>` : '<p class="pending">No classified crossings in this video.</p>';
      const v = $('#an-video'); v.src = job.output_url; v.style.display = 'block'; $('#an-empty').style.display = 'none';
      const d = $('#an-dl'); d.href = job.output_url; d.style.display = 'block';
    };
    const poll = id => {
      clearInterval(timer);
      const check = async () => {
        try {
          const job = await api('/jobs/' + id);
          status(job.status === 'completed' ? 'Ready' : job.status, job.progress, job.message);
          if (job.status === 'completed') { clearInterval(timer); $('#an-go').disabled = false; show(job); }
          else if (job.status === 'failed') { clearInterval(timer); $('#an-go').disabled = false; $('#an-err').textContent = job.message; }
        } catch { clearInterval(timer); $('#an-go').disabled = false; $('#an-err').textContent = 'Lost connection to the API server'; }
      };
      check(); timer = setInterval(check, 1500);
    };
    $('#an-form').onsubmit = async e => {
      e.preventDefault(); if (!file.files[0]) return;
      $('#an-err').textContent = ''; $('#an-go').disabled = true; status('Uploading', 0, 'Sending video to local processor');
      const data = new FormData(); data.append('video', file.files[0]);
      const p = { yolo_model: 'yolov8m.pt', location_id: $('#o-loc').value };
      try { const job = await api('/jobs' + qs(p), { method: 'POST', form: data }); poll(job.id); }
      catch (err) { $('#an-err').textContent = err.message; $('#an-go').disabled = false; status('Error', 0, ''); }
    };
    return () => clearInterval(timer);
  },
});

/* ---------- login (placeholder: any credentials sign in) ---------- */
function loginView() {
  const art = `<svg class="art" viewBox="0 0 420 330"><ellipse cx="210" cy="170" rx="180" ry="130" fill="#f6f7f9"/><rect x="60" y="190" width="120" height="80" fill="#ccfbf1"/><rect x="250" y="200" width="130" height="80" fill="#ccfbf1"/><rect x="110" y="70" width="230" height="30" fill="#fbbf24"/><rect x="110" y="55" width="70" height="20" fill="#0d9488"/><circle cx="220" cy="185" r="55" fill="#06b6d4" opacity=".8"/><path d="M205 165l32 20-32 20z" fill="#fff"/><circle cx="310" cy="80" r="30" fill="#10b981"/><rect x="330" y="215" width="20" height="90" fill="#0d9488"/><circle cx="335" cy="180" r="14" fill="#f2c8a0"/></svg>`;
  return `<div class="login"><section class="login-l"><h1>VS corp CCTV Retail Analytics</h1>${art}<div class="cookie" id="cookie"><h5>Cookie Settings</h5>By continuing to browse or by clicking “Accept”, you consent to our website's use of cookies to give you the most relevant experience by remembering your preferences and repeat visits.<div><button id="ck-d">I Decline</button><button class="a" id="ck-a">I Accept</button></div></div></section>
  <section class="login-r"><div class="lbox" id="lbox"></div></section></div>`;
}
function loginInit() {
  const box = $('#lbox'); let id = '';
  const step1 = () => { box.innerHTML = `${LOGO}<h2>Sign in to VS corp Panel</h2><input id="l-id" placeholder="Enter Email or Mobile Number" autofocus><button class="go" id="l-c">Continue</button>`; const go = () => { id = $('#l-id').value.trim(); if (id) step2(); }; $('#l-c').onclick = go; $('#l-id').onkeydown = e => e.key === 'Enter' && go(); };
  const step2 = () => { box.innerHTML = `${LOGO}<h2 style="font-size:25px">Select how you want to login</h2><button class="alt" id="l-pw">${ic('lock', 18)}<span>Login using Password</span></button>`; $('#l-pw').onclick = step3; };
  const step3 = () => { box.innerHTML = `${LOGO}<h2 style="font-size:24px">Enter password for<br><small style="font-size:16px;color:#555">${esc(id)}</small></h2><form id="l-form" autocomplete="on"><input type="text" name="username" value="${esc(id)}" autocomplete="username" hidden><div class="pw"><input id="l-pw" name="password" type="password" placeholder="Password" autocomplete="current-password"><button type="button" class="eye" id="l-eye" aria-label="Show password">${ic('eye', 20)}</button></div><button class="go" id="l-go" type="submit">Sign in</button></form>`; const go = () => { store.set('vscorp-auth', id); if (location.hash && location.hash !== '#/login') location.hash = '#/'; else { history.replaceState(null, '', '#/'); route(); } }; $('#l-form').onsubmit = e => { e.preventDefault(); go(); }; $('#l-eye').onclick = () => { const f = $('#l-pw'), show = f.type === 'password'; f.type = show ? 'text' : 'password'; $('#l-eye').innerHTML = ic(show ? 'eyeoff' : 'eye', 20); }; setTimeout(() => $('#l-pw').focus(), 0); };
  step1();
  const hide = () => { $('#cookie')?.remove(); store.set('vscorp-cookie', '1'); };
  $('#ck-a').onclick = $('#ck-d').onclick = hide; if (store.get('vscorp-cookie')) hide();
}

/* ---------- router ---------- */
let cleanup;
async function route() {
  if (cleanup) { cleanup(); cleanup = null; }
  const name = (location.hash.replace(/^#\/?/, '') || 'home');
  if (!store.get('vscorp-auth') || name === 'login') { app.innerHTML = loginView(); loginInit(); return; }
  const page = (pages[name] || pages.home)();
  app.innerHTML = shell(page.html);
  chrome();
  window.scrollTo(0, 0);
  if (page.init) { const c = await page.init(); if (typeof c === 'function') cleanup = c; }
}
function chrome() {
  const q = $('#q'), sr = $('#sr');
  q.oninput = () => { const v = q.value.toLowerCase(), hits = v ? SEARCHABLE.filter(s => s[0].toLowerCase().includes(v)) : []; sr.innerHTML = hits.map(h => `<a href="${h[1]}">${h[0]}</a>`).join(''); sr.style.display = hits.length ? 'block' : 'none'; };
  q.onblur = () => setTimeout(() => sr.style.display = 'none', 150);
  $('#user').onclick = e => { e.stopPropagation(); if (e.target.closest('[data-a]')) { e.preventDefault(); store.del('vscorp-auth'); location.hash = '#/login'; route(); return; } $('#menu').classList.toggle('open'); };
  document.onclick = () => $('#menu')?.classList.remove('open');
}
$('#modal-x').onclick = closeModal;
$('#modal').onclick = e => { if (e.target.id === 'modal') closeModal(); };
addEventListener('hashchange', route);
route();
