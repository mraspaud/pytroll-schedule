/* Schedule viewer: timeline of passes per satellite, with a coverage map per pass.
   DATA is injected by trollsched.viewer.build_page. */
const DATA = __DATA__;

// ---------------------------------------------------------------- data preparation
const ANT_COLORS = ["#8dd3c7", "#ffffb3", "#bebada", "#fb8072", "#80b1d3", "#fdb462",
                    "#b3de69", "#fccde5", "#d9d9d9", "#bc80bd", "#ccebc5", "#ffed6f"]; // ColorBrewer Set3
const antennas = [...new Set(DATA.passes.filter(p => !p.un).map(p => p.ant))].sort();
const antColor = Object.fromEntries(antennas.map((a, i) => [a, ANT_COLORS[i % ANT_COLORS.length]]));

// identical passes requested on several antennas become one bar with several antennas
const merged = new Map();
for (const p of DATA.passes) {
  const key = p.un ? "un|" + p.sat + "|" + Math.round(p.s) : p.sat + "|" + Math.round(p.s) + "|" + Math.round(p.e);
  if (merged.has(key)) merged.get(key).ants.push(p.ant);
  else merged.set(key, Object.assign({ants: [p.ant]}, p));
}
// unscheduled passes first so that they are drawn behind the scheduled ones
const passes = [...merged.values()].sort((a, b) => (b.un || 0) - (a.un || 0) || a.s - b.s);
const sats = [...new Set(passes.map(p => p.sat))].sort();
const satName = Object.fromEntries(passes.map(p => [p.sat, p.name]));
const byKey = new Map(DATA.passes.map(p => [p.sat + "|" + p.ant + "|" + Math.round(p.s), p]));

// passes overlapping on one antenna
for (const a of antennas) {
  const list = passes.filter(p => !p.un && p.ants.includes(a)).sort((x, y) => x.s - y.s);
  for (let i = 1; i < list.length; i++) if (list[i].s < list[i - 1].e) list[i].conflict = list[i - 1].conflict = true;
}

// ---------------------------------------------------------------- helpers
const pad = n => (n < 10 ? "0" : "") + n;
const hhmm = t => { const d = new Date(t * 1000); return pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()); };
const hhmmss = t => hhmm(t) + ":" + pad(new Date(t * 1000).getUTCSeconds());
const ymd = t => new Date(t * 1000).toISOString().slice(0, 10);
const dayLabel = t => ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date(t * 1000).getUTCDay()] + " " + ymd(t);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const passId = p => p.sat + "-" + Math.round(p.s);
const normalize = s => String(s).toLowerCase().replace(/[^a-z0-9]/g, ""); // like records.normalize
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function hexToHsl(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255, g = parseInt(hex.slice(3, 5), 16) / 255, b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
  if (max === min) return [0, 0, l * 100];
  const d = max - min, s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, s * 100, l * 100];
}
// antenna colour, a little darker the more of the area the pass covers (lighter when it covers little)
function passColor(ant, pct) {
  const [h, s, l] = hexToHsl(antColor[ant]);
  const shift = pct === undefined ? 0 : 7 - 14 * pct / 100;
  return `hsl(${h.toFixed(0)} ${s.toFixed(0)}% ${Math.min(96, Math.max(30, l + shift)).toFixed(0)}%)`;
}
function fillFor(p) {
  if (p.un) return "var(--row)";
  if (p.ants.length === 1) return passColor(p.ants[0], p.area_pct);
  return `url(#pat-${p.ants.slice().sort().join("_").replace(/[^a-z0-9_]/gi, "")})`;
}

// ---------------------------------------------------------------- timeline
const L = 86, R = 86, AXIS = 52, RH = 26, LANE = 14, PAD = 6;
let W = 1200, H = 0, T = AXIS, lanes = false;
let t0 = DATA.span[0], t1 = DATA.span[1];
const svg = document.getElementById("g"), tip = document.getElementById("tip"), wrap = document.getElementById("wrap");
const X = t => L + (t - t0) / (t1 - t0) * (W - L - R);

function sunStops() { // gradient stops along the visible window from the station's sun elevation
  const sun = DATA.sun, out = [];
  const first = Math.max(0, Math.floor((t0 - sun.start) / sun.step) - 1);
  const last = Math.min(sun.elevation.length - 1, Math.ceil((t1 - sun.start) / sun.step) + 1);
  for (let i = first; i <= last; i++) {
    const t = sun.start + i * sun.step, e = sun.elevation[i];
    const night = Math.min(1, Math.max(0, (6 - e) / 18));  // 1 below -12 deg, 0 above +6 deg
    out.push(`<stop offset="${((X(t) - L) / (W - L - R) * 100).toFixed(2)}%" stop-color="var(--night)" stop-opacity="${(0.45 * night).toFixed(3)}"/>`);
  }
  return out.join("");
}

function draw() {
  W = wrap.clientWidth || 1200;
  T = AXIS + (lanes ? antennas.length * LANE + 6 : 0);
  H = T + sats.length * RH + PAD;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("height", H);
  let o = `<defs><clipPath id="cp"><rect x="${L}" y="0" width="${W - L - R}" height="${H}"/></clipPath>`;
  o += `<linearGradient id="sun" gradientUnits="userSpaceOnUse" x1="${L}" x2="${W - R}" y1="0" y2="0">${sunStops()}</linearGradient>`;
  const combos = new Set(passes.filter(p => p.ants.length > 1).map(p => p.ants.slice().sort().join("_")));
  for (const combo of combos) {
    const cols = combo.split("_").map(a => antColor[a]), w = 4 * cols.length;
    o += `<pattern id="pat-${combo.replace(/[^a-z0-9_]/gi, "")}" width="${w}" height="${w}" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">`;
    cols.forEach((col, i) => { o += `<rect x="${i * 4}" width="4" height="${w}" fill="${col}"/>`; });
    o += `</pattern>`;
  }
  o += `</defs>`;
  // rows
  sats.forEach((s, i) => {
    const y = T + i * RH;
    o += `<rect x="0" y="${y}" width="${W}" height="${RH}" fill="${i % 2 ? "var(--row)" : "transparent"}"/>`;
    o += `<text x="8" y="${y + 17}" class="rowlabel">${esc(satName[s])}</text>`;
    o += `<text x="${W - 8}" y="${y + 17}" class="rowlabel" text-anchor="end">${esc(satName[s])}</text>`;
  });
  if (lanes) antennas.forEach((a, i) => {
    const y = AXIS + i * LANE;
    o += `<text x="8" y="${y + 11}" class="lanelabel">${esc(a)}</text>`;
    o += `<line x1="${L}" y1="${y + LANE / 2}" x2="${W - R}" y2="${y + LANE / 2}" stroke="var(--line)"/>`;
  });
  // day/night band under the time labels
  o += `<rect x="${L}" y="${AXIS - 8}" width="${W - L - R}" height="6" fill="url(#sun)"/>`;
  o += `<g clip-path="url(#cp)">`;
  const pxPerSec = (W - L - R) / (t1 - t0);
  const step = [60, 300, 600, 900, 1800, 3600, 2 * 3600, 3 * 3600, 6 * 3600, 12 * 3600].find(st => st * pxPerSec >= 64) || 12 * 3600;
  for (let d = Math.floor(t0 / 86400) * 86400; d <= t1; d += 86400) {
    const x = X(d);
    o += `<line x1="${x}" y1="0" x2="${x}" y2="${H}" stroke="var(--border)"/>`;
    o += `<text x="${Math.max(x, L) + 4}" y="14" class="daylabel">${dayLabel(d)}</text>`;
  }
  for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) {
    if (t % 86400 === 0) continue;
    const x = X(t);
    o += `<line x1="${x}" y1="${AXIS - 14}" x2="${x}" y2="${H}" stroke="var(--line)"/>`;
    o += `<text x="${x + 3}" y="${AXIS - 12}" class="ticklabel">${hhmm(t)}</text>`;
  }
  if (lanes) passes.forEach(p => {
    if (p.un || p.e < t0 || p.s > t1) return;
    for (const a of p.ants) {
      const y = AXIS + antennas.indexOf(a) * LANE + 2;
      o += `<rect x="${X(p.s)}" y="${y}" width="${Math.max(1, X(p.e) - X(p.s))}" height="${LANE - 4}" fill="${antColor[a]}" stroke="rgba(0,0,0,.3)" stroke-width=".5"/>`;
    }
  });
  passes.forEach((p, i) => {
    if (p.e < t0 || p.s > t1) return;
    const y = T + sats.indexOf(p.sat) * RH + 5, x = X(p.s), w = Math.max(2, X(p.e) - x);
    o += `<g class="bar${p.un ? " un" : ""}${productState(p) === "missing" ? " missing" : ""}" data-i="${i}">`;
    if (p.fs !== undefined) {
      const fx = X(p.fs), fw = Math.max(2, X(p.fe) - fx);
      o += `<rect class="trim" x="${fx}" y="${y + 3}" width="${fw}" height="${RH - 16}" rx="2"/>`;
    }
    o += `<rect x="${x}" y="${y}" width="${w}" height="${RH - 10}" rx="3" fill="${fillFor(p)}"${p.conflict ? ' class="conflict"' : ""}/>`;
    if (p.orbit !== undefined && w > 44) o += `<text x="${x + w / 2}" y="${y + 12}" text-anchor="middle">${p.orbit}</text>`;
    o += `</g>`;
  });
  const now = Date.now() / 1000;
  if (now > t0 && now < t1) o += `<line x1="${X(now)}" y1="0" x2="${X(now)}" y2="${H}" stroke="var(--now)" stroke-width="1.5"/>`;
  o += `</g><line x1="${L}" y1="${T}" x2="${W - R}" y2="${T}" stroke="var(--border)"/>`;
  svg.innerHTML = o;
  const nUn = passes.filter(p => p.un).length;
  document.getElementById("status").textContent =
    `${ymd(t0)} ${hhmm(t0)} → ${ymd(t1)} ${hhmm(t1)} UTC · ${passes.length - nUn} scheduled, ${nUn} not`;
  drawList();
}

// ---------------------------------------------------------------- pass list
function stripes(cols) { // CSS equivalent of the striped SVG pattern
  return `repeating-linear-gradient(45deg,${cols.map((c, i) => `${c} ${i * 3}px ${(i + 1) * 3}px`).join(",")})`;
}
function swatch(p) {
  if (p.un) return "var(--row)";
  if (p.ants.length > 1) return stripes(p.ants.slice().sort().map(a => antColor[a]));
  return passColor(p.ants[0], p.area_pct);
}
function drawList() {
  const rows = passes.filter(p => p.e > t0 && p.s < t1).sort((a, b) => a.s - b.s);
  const hasArea = passes.some(p => p.area_pct !== undefined);
  let o = `<table><thead><tr><th>Satellite</th><th>Antenna</th><th>Date</th><th>AOS</th><th>LOS</th><th>Length</th>` +
    `<th>Orbit</th><th>Dir</th><th>Max el</th>${hasArea ? "<th>Area</th>" : ""}<th></th></tr></thead><tbody>`;
  for (const p of rows) {
    const i = passes.indexOf(p), dur = Math.round(p.e - p.s);
    const note = p.un ? "not scheduled" : productState(p) === "missing" ? "no product" : p.fs !== undefined ? "trimmed" : p.conflict ? "overlap" : "";
    o += `<tr class="${p.un ? "un" : ""}" data-i="${i}"><td><i class="sw${p.un ? " un" : ""}" style="background:${swatch(p)}"></i>${esc(p.name)}</td>` +
      `<td>${esc(p.un ? "–" : p.ants.join(" + "))}</td><td>${ymd(p.s)}</td><td>${hhmmss(p.s)}</td><td>${hhmmss(p.e)}</td>` +
      `<td>${Math.floor(dur / 60)}:${pad(dur % 60)}</td><td>${p.orbit ?? ""}</td><td>${p.dir ? p.dir[0].toUpperCase() : ""}</td>` +
      `<td>${p.max_el !== undefined ? p.max_el + "°" : ""}</td>${hasArea ? `<td>${p.area_pct !== undefined ? p.area_pct.toFixed(0) + " %" : ""}</td>` : ""}` +
      `<td class="note">${note}</td></tr>`;
  }
  document.getElementById("list").innerHTML = o + "</tbody></table>";
}

// ---------------------------------------------------------------- legend, header, controls
document.getElementById("legend").innerHTML =
  antennas.map(a => `<span><i class="sw" style="background:${antColor[a]}"></i>${esc(a)}</span>`).join("") +
  (antennas.length > 1 ? `<span><i class="sw" style="background:${stripes(antennas.map(a => antColor[a]))}"></i>several antennas</span>` : "") +
  `<span><i class="sw conflict"></i>overlap on one antenna</span>` +
  (passes.some(p => p.un) ? `<span><i class="sw un"></i>not scheduled</span>` : "") +
  (passes.some(p => p.area_pct !== undefined) ? `<span class="hint">darker = more of the area covered</span>` : "");
document.getElementById("meta").textContent =
  `generated ${DATA.generated}` + (DATA.sources.length ? ` · ${DATA.sources.join(", ")}` : "");

const fitDay = () => { const d = Math.floor(Date.now() / 86400000) * 86400; t0 = d; t1 = d + 86400; draw(); };
document.getElementById("today").onclick = fitDay;
document.getElementById("week").onclick = () => { t0 = DATA.span[0]; t1 = DATA.span[1]; draw(); };
document.getElementById("now").onclick = () => { const n = Date.now() / 1000, s = Math.min(t1 - t0, 6 * 3600); t0 = n - s / 3; t1 = t0 + s; draw(); };
document.getElementById("lanes").onchange = ev => { lanes = ev.target.checked; draw(); };
window.addEventListener("resize", () => { if (document.getElementById("status")) draw(); });

svg.addEventListener("wheel", ev => {
  ev.preventDefault();
  const r = svg.getBoundingClientRect(), fx = (ev.clientX - r.left) / r.width * W;
  const tc = t0 + (fx - L) / (W - L - R) * (t1 - t0), k = ev.deltaY > 0 ? 1.25 : 0.8;
  const ns = Math.min(DATA.span[1] - DATA.span[0] + 2 * 3600, Math.max(1800, (t1 - t0) * k));
  t0 = tc - (tc - t0) * ns / (t1 - t0); t1 = t0 + ns; draw();
}, {passive: false});
let dragX = null, moved = false;
svg.addEventListener("mousedown", ev => { dragX = ev.clientX; moved = false; });
window.addEventListener("mouseup", () => { dragX = null; });
svg.addEventListener("mousemove", ev => {
  if (dragX !== null) {
    const r = svg.getBoundingClientRect(), dt = (ev.clientX - dragX) / r.width * W / (W - L - R) * (t1 - t0);
    if (Math.abs(ev.clientX - dragX) > 2) moved = true;
    t0 -= dt; t1 -= dt; dragX = ev.clientX; draw(); tip.style.display = "none"; return;
  }
  hoverTarget(ev);
});
svg.addEventListener("mouseleave", () => { tip.style.display = "none"; });
svg.addEventListener("click", ev => { if (!moved) openTarget(ev); });
const list = document.getElementById("list");
list.addEventListener("mousemove", hoverTarget);
list.addEventListener("mouseleave", () => { tip.style.display = "none"; });
list.addEventListener("click", openTarget);
function hoverTarget(ev) {
  const g = ev.target.closest("[data-i]");
  if (!g) { tip.style.display = "none"; return; }
  showTip(passes[+g.dataset.i], ev);
}
function openTarget(ev) {
  const g = ev.target.closest("[data-i]");
  if (g) window.open(location.pathname + "?pass=" + encodeURIComponent(passId(passes[+g.dataset.i])), "_blank");
}

// ---------------------------------------------------------------- near-sided perspective map
const MAP = DATA.map;
let SZ = 256, base = null;
const lat0 = MAP.lat * Math.PI / 180, lon0 = MAP.lon * Math.PI / 180, P = (6371 + MAP.height_km) / 6371;
const cosL = Math.cos(lat0), sinL = Math.sin(lat0);
const rmax = P / (P + 1) * Math.sqrt(1 - 1 / (P * P)); // disc radius at the horizon, in Earth radii
let SCALE = (SZ / 2 - 2) / rmax;
function setMapSize(n) { if (n !== SZ) { SZ = n; SCALE = (SZ / 2 - 2) / rmax; base = null; } }
function proj(lon, lat) { // [x, y, visible]; hidden points are clamped onto the horizon rim
  const la = lat * Math.PI / 180, lo = lon * Math.PI / 180 - lon0;
  const cosc = sinL * Math.sin(la) + cosL * Math.cos(la) * Math.cos(lo);
  let x = Math.cos(la) * Math.sin(lo), y = cosL * Math.sin(la) - sinL * Math.cos(la) * Math.cos(lo);
  const vis = cosc >= 1 / P;
  if (vis) { const k = (P - 1) / (P - cosc); x *= k; y *= k; }
  else { const n = Math.hypot(x, y) || 1e-9; x *= rmax / n; y *= rmax / n; }
  return [SZ / 2 + x * SCALE, SZ / 2 - y * SCALE, vis];
}
function ringPath(c, ring, close) { // trace a ring, walking the rim between consecutive hidden points
  let any = false, prev = null;
  for (const [lon, lat] of ring) {
    const q = proj(lon, lat); any = any || q[2];
    if (prev && !q[2] && !prev[2]) {
      const a0 = Math.atan2(prev[1] - SZ / 2, prev[0] - SZ / 2), a1 = Math.atan2(q[1] - SZ / 2, q[0] - SZ / 2);
      let d = a1 - a0; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI;
      const n = Math.ceil(Math.abs(d) / 0.1);
      for (let i = 1; i < n; i++) { const a = a0 + d * i / n; c.lineTo(SZ / 2 + rmax * SCALE * Math.cos(a), SZ / 2 + rmax * SCALE * Math.sin(a)); }
    }
    prev ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]); prev = q;
  }
  if (close) c.closePath();
  return any;
}
const toXYZ = (lon, lat) => { const la = lat * Math.PI / 180, lo = lon * Math.PI / 180; return [Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)]; };
const fromXYZ = v => { const n = Math.hypot(v[0], v[1], v[2]); return [Math.atan2(v[1], v[0]) * 180 / Math.PI, Math.asin(v[2] / n) * 180 / Math.PI]; };
function densify(ring, n, open) { // great-circle interpolation between consecutive vertices
  const out = [], last = open ? ring.length - 1 : ring.length;
  for (let i = 0; i < last; i++) {
    const a = toXYZ(...ring[i]), b = toXYZ(...ring[(i + 1) % ring.length]);
    for (let j = 0; j < n; j++) { const f = j / n; out.push(fromXYZ([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f])); }
  }
  if (open) out.push(ring[ring.length - 1]);
  return out;
}
function clipToDisc(c) { c.beginPath(); c.arc(SZ / 2, SZ / 2, SZ / 2 - 2, 0, 2 * Math.PI); c.clip(); }
function drawBase() {
  base = document.createElement("canvas"); base.width = base.height = SZ;
  const c = base.getContext("2d");
  c.fillStyle = cssVar("--sea"); c.beginPath(); c.arc(SZ / 2, SZ / 2, SZ / 2 - 2, 0, 2 * Math.PI); c.fill();
  c.save(); clipToDisc(c);
  c.fillStyle = cssVar("--land"); c.strokeStyle = cssVar("--border"); c.lineWidth = 0.6;
  for (const ring of MAP.lines) { c.beginPath(); if (ringPath(c, ring, true)) { c.fill(); c.stroke(); } }
  c.strokeStyle = "rgba(128,128,128,.35)"; c.lineWidth = 0.5;
  for (let lat = -80; lat <= 80; lat += 20) { c.beginPath(); ringPath(c, [...Array(181)].map((_, i) => [i * 2 - 180, lat]), false); c.stroke(); }
  for (let lon = -180; lon < 180; lon += 30) { c.beginPath(); ringPath(c, [...Array(91)].map((_, i) => [lon, i * 2 - 90]), false); c.stroke(); }
  if (MAP.area) { c.strokeStyle = cssVar("--area"); c.lineWidth = 1.2; c.setLineDash([4, 3]); c.beginPath(); ringPath(c, densify(MAP.area, 4), true); c.stroke(); c.setLineDash([]); }
  c.restore();
}
const nightCache = new Map();
function drawNight(c, sun) { // soft shadow over the night side, one alpha value per pixel
  const key = SZ + "|" + sun;
  if (!nightCache.has(key)) {
    const cv = document.createElement("canvas"); cv.width = cv.height = SZ;
    const g = cv.getContext("2d"), img = g.createImageData(SZ, SZ), d = img.data;
    const sv = toXYZ(sun[0], sun[1]), cx = SZ / 2, cy = SZ / 2;
    const east = [-Math.sin(lon0), Math.cos(lon0), 0], north = [-sinL * Math.cos(lon0), -sinL * Math.sin(lon0), cosL];
    const centre = [cosL * Math.cos(lon0), cosL * Math.sin(lon0), sinL], k0 = (P - 1) * (P - 1);
    const [nr, ng, nb] = (cssVar("--night").match(/\w\w/g) || ["1d", "2d", "4e"]).map(h => parseInt(h, 16));
    for (let j = 0; j < SZ; j++) for (let i = 0; i < SZ; i++) {
      const x = (i + 0.5 - cx) / SCALE, y = (cy - j - 0.5) / SCALE, rho2 = x * x + y * y;
      if (rho2 > rmax * rmax) continue;
      // invert the near-sided perspective: cos of the angular distance from the map centre
      const a = rho2 + k0, b = -2 * P * rho2, cc = rho2 * P * P - k0;
      const u = (-b + Math.sqrt(Math.max(0, b * b - 4 * a * cc))) / (2 * a);
      const r = Math.sqrt(Math.max(0, 1 - u * u)) / (Math.sqrt(rho2) || 1e-9);
      const v = [0, 1, 2].map(m => u * centre[m] + r * (x * east[m] + y * north[m]));
      const elevation = Math.asin(Math.max(-1, Math.min(1, v[0] * sv[0] + v[1] * sv[1] + v[2] * sv[2]))) * 180 / Math.PI;
      const night = Math.min(1, Math.max(0, (6 - elevation) / 18)); // full shade below -12 deg, none above +6
      if (night <= 0) continue;
      const o = (j * SZ + i) * 4;
      d[o] = nr; d[o + 1] = ng; d[o + 2] = nb; d[o + 3] = Math.round(70 * night);
    }
    g.putImageData(img, 0, 0);
    if (nightCache.size > 64) nightCache.clear();
    nightCache.set(key, cv);
  }
  c.drawImage(nightCache.get(key), 0, 0);
}
function drawArrow(c, track, color) { // the sub-satellite track, dashed, with a small arrowhead at the end
  const pts = densify(track, 8, true).map(([lon, lat]) => proj(lon, lat));
  c.strokeStyle = color; c.lineWidth = Math.max(1, SZ / 400); c.setLineDash([SZ / 100, SZ / 100]);
  c.beginPath(); pts.forEach((q, i) => (i ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]))); c.stroke(); c.setLineDash([]);
  const end = pts[pts.length - 1], before = pts[pts.length - 2], a = Math.atan2(end[1] - before[1], end[0] - before[0]), s = Math.max(5, SZ / 60);
  c.fillStyle = color; c.beginPath(); c.moveTo(end[0], end[1]);
  c.lineTo(end[0] - s * Math.cos(a - 0.45), end[1] - s * Math.sin(a - 0.45));
  c.lineTo(end[0] - s * Math.cos(a + 0.45), end[1] - s * Math.sin(a + 0.45)); c.closePath(); c.fill();
}
function stripePattern(c, cols) { // diagonal stripes, one per antenna, as a canvas fill
  const w = Math.max(4, Math.round(SZ / 40)), n = cols.length, pc = document.createElement("canvas");
  pc.width = w * n; pc.height = w;
  const g = pc.getContext("2d"); cols.forEach((col, i) => { g.fillStyle = col; g.fillRect(i * w, 0, w, w); });
  const pat = c.createPattern(pc, "repeat"); pat.setTransform(new DOMMatrix().rotate(45)); return pat;
}
function drawPassMap(canvas, p) {
  if (!base) drawBase();
  const c = canvas.getContext("2d"); c.drawImage(base, 0, 0);
  c.save(); clipToDisc(c);
  if (p.sun) drawNight(c, p.sun);
  const img = productImage(p);
  if (img) c.drawImage(img, 2, 2, SZ - 4, SZ - 4);
  if (p.fcov) {
    c.strokeStyle = "#777"; c.fillStyle = "rgba(128,128,128,.35)"; c.lineWidth = 1; c.setLineDash([3, 2]);
    c.beginPath(); ringPath(c, densify(p.fcov, 8), true); c.fill(); c.stroke(); c.setLineDash([]);
  }
  const col = p.un ? "#d9d9d9" : antColor[p.ants[0]];
  c.strokeStyle = "#333"; c.lineWidth = 1.5;
  c.fillStyle = p.un || p.ants.length < 2 ? col + "66" : stripePattern(c, p.ants.map(a => antColor[a] + "66"));
  c.beginPath(); ringPath(c, densify(p.cov, 8), true); if (!img) c.fill(); c.stroke();
  if (p.track) drawArrow(c, p.track, "rgba(40,40,40,.6)");
  c.restore();
}

// ---------------------------------------------------------------- pass details
function lostTo(p) {
  const items = (p.lost_to || []).map(id => byKey.get(id)).filter(Boolean);
  if (!items.length) return "";
  return `<div class="muted">lost to ${items.map(q => `${esc(q.name)} on ${esc(q.ant)} ${hhmm(q.s)}`).join(", ")}</div>`;
}
function passInfoHtml(p) {
  const ants = p.un ? "not scheduled" : "on " + p.ants.join(" + "), dur = Math.round(p.e - p.s);
  const geometry = [];
  if (p.dir) geometry.push(p.dir);
  if (p.max_el !== undefined) geometry.push(`max el ${p.max_el}°`);
  if (p.aos_az !== undefined) geometry.push(`az ${p.aos_az}° → ${p.los_az}°`);
  if (p.area_pct !== undefined) geometry.push(`area ${p.area_pct.toFixed(0)} %` + (p.full_area_pct !== undefined ? ` (untrimmed ${p.full_area_pct.toFixed(0)} %)` : ""));
  return `<b>${esc(p.name)}</b> <span class="muted">${esc(ants)}${p.orbit !== undefined ? ` · orbit ${p.orbit}` : ""}</span>` +
    `<div>${ymd(p.s)} &nbsp; AOS ${hhmmss(p.s)} → LOS ${hhmmss(p.e)} UTC</div>` +
    `<div>${Math.floor(dur / 60)} min ${dur % 60} s · station ${esc(p.station)}${p.conflict ? ' · <span class="warn">overlaps another pass</span>' : ""}</div>` +
    (geometry.length ? `<div class="muted">${geometry.join(" · ")}</div>` : "") +
    (p.fs !== undefined ? `<div class="muted">trimmed: visible ${hhmmss(p.fs)} → ${hhmmss(p.fe)}, ${Math.max(0, Math.round(p.s - p.fs))} s cut at start, ${Math.max(0, Math.round(p.fe - p.e))} s at end</div>` : "") +
    lostTo(p) + productsHtml(p);
}
let shown = null, pagePass = null; // the canvas (and, on the single-pass page, the pass) currently shown
function showMap(canvas, p) { shown = {canvas, p}; drawPassMap(canvas, p); }
function showTip(p, ev) {
  setMapSize(256);
  tip.innerHTML = passInfoHtml(p) + (p.cov ? `<canvas width="${SZ}" height="${SZ}"></canvas>` : `<div class="muted">no coverage available</div>`) +
    `<div class="muted hint">click to open in a new tab</div>`;
  if (p.cov) showMap(tip.querySelector("canvas"), p);
  tip.style.display = "block";
  const r = wrap.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
  let x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 14;
  if (x + tw > r.width) x = ev.clientX - r.left - tw - 14;
  if (ev.clientY + 14 + th > window.innerHeight) y = Math.max(-r.top + 8, ev.clientY - r.top - th - 14);
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
function showPassPage(id) { // single-pass page: schedule.html?pass=<sat>-<unix AOS>
  const p = passes.find(q => passId(q) === id);
  document.body.innerHTML = "";
  const el = document.createElement("div"); el.className = "passpage";
  if (!p) { el.innerHTML = `<p>No pass with id <code>${esc(id)}</code>.</p><p><a href="${location.pathname}">Back to the schedule</a></p>`; document.body.appendChild(el); return; }
  document.title = `${p.name} ${ymd(p.s)} ${hhmm(p.s)} UTC`;
  pagePass = p;
  el.innerHTML = `<p><a href="${location.pathname}">← schedule</a></p><div class="passinfo">${passInfoHtml(p)}</div>`;
  const size = Math.min(760, window.innerWidth - 48);
  if (p.cov) { const cv = document.createElement("canvas"); cv.width = cv.height = size; cv.className = "bigmap"; el.appendChild(cv); setMapSize(size); showMap(cv, p); }
  else el.insertAdjacentHTML("beforeend", `<p class="muted">No coverage available.</p>`);
  el.insertAdjacentHTML("beforeend", `<div class="products"></div>`);
  document.body.appendChild(el);
}
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { base = null; });

// ---------------------------------------------------------------- products: what was received and processed
// When DATA.products is set, <products.url>index.js next to the page is loaded (and reloaded every
// products.poll seconds) as a script calling viewer.add("products", [...]).  Each item has the
// satellite name, the data start and end (unix seconds), and optionally an image in the map's
// projection, a full-size link and a name; items are matched to passes by satellite and time overlap.
const PRODUCTS = DATA.products && DATA.products.url !== undefined ? DATA.products : null;
let productsLoaded = false;
const images = new Map();
window.viewer = {add(kind, items) { if (kind === "products") applyProducts(items); }};
function applyProducts(items) {
  for (const p of passes) p.products = [];
  for (const it of (items || [])) {
    const sat = normalize(it.sat);
    for (const p of passes) if (normalize(p.sat) === sat && it.start < p.e && it.end > p.s) p.products.push(it);
  }
  for (const p of passes) p.products.sort((a, b) => a.start - b.start);
  const legend = document.getElementById("legend"); // absent on the single-pass page
  if (!productsLoaded && legend) legend.insertAdjacentHTML("beforeend",
    `<span><i class="sw" style="background:var(--row);border:1px dashed var(--now)"></i>no product received</span>`);
  productsLoaded = true;
  if (shown && document.body.contains(shown.canvas)) drawPassMap(shown.canvas, shown.p);
  if (legend) draw();
  else if (pagePass) {
    document.querySelector(".passinfo").innerHTML = passInfoHtml(pagePass);
    document.querySelector(".products").innerHTML = productLinks(pagePass);
  }
}
function productState(p) { // "received", "missing" (past, scheduled, nothing came) or ""
  if (!productsLoaded || p.un) return "";
  if (p.products && p.products.length) return "received";
  return p.e < Date.now() / 1000 - 1800 ? "missing" : "";
}
function productImage(p) { // the loaded image to draw on the map, if any
  const it = (p.products || []).find(q => q.image);
  if (!it) return null;
  const url = PRODUCTS.url + it.image;
  if (!images.has(url)) {
    const im = new Image();
    im.onload = () => { if (shown && document.body.contains(shown.canvas)) drawPassMap(shown.canvas, shown.p); };
    im.src = url;
    images.set(url, im);
  }
  const im = images.get(url);
  return im.complete && im.naturalWidth ? im : null;
}
function productsHtml(p) {
  const state = productState(p);
  if (state === "missing") return `<div class="warn">no product received</div>`;
  if (state !== "received") return "";
  const s = Math.min(...p.products.map(q => q.start)), e = Math.max(...p.products.map(q => q.end));
  return `<div>data ${hhmmss(s)} → ${hhmmss(e)} UTC` +
    (s - p.s > 60 || p.e - e > 60 ? ` <span class="warn">(${Math.round(Math.max(0, s - p.s))} s late start, ${Math.round(Math.max(0, p.e - e))} s early end)</span>` : "") +
    `</div><div class="muted">${p.products.map(q => esc(q.name || q.image || q.link || "product")).join(", ")}</div>`;
}
function productLinks(p) {
  if (!p.products || !p.products.length) return "";
  return `<p>${p.products.map(q => {
    const href = q.link || q.image;
    return href ? `<a href="${esc(PRODUCTS.url + href)}" target="_blank">${esc(q.name || href)}</a>` : esc(q.name || "product");
  }).join(" · ")}</p>`;
}
function loadProducts() {
  const s = document.createElement("script");
  s.src = PRODUCTS.url + "index.js?t=" + Date.now();
  s.onload = s.onerror = () => s.remove();
  document.head.appendChild(s);
}
if (PRODUCTS) { loadProducts(); setInterval(loadProducts, Math.max(10, PRODUCTS.poll || 120) * 1000); }

// ---------------------------------------------------------------- start
const wanted = new URLSearchParams(location.search).get("pass");
if (wanted) showPassPage(wanted);
else if (Date.now() / 1000 > DATA.span[0] && Date.now() / 1000 < DATA.span[1]) fitDay();
else document.getElementById("week").click();
