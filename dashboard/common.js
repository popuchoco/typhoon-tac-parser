function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
}

function downloadText(filename, text, type = "application/json") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = filename; link.click();
  URL.revokeObjectURL(url);
}

function formatCoord(lat, lon) {
  if (!Number.isFinite(Number(lat)) || !Number.isFinite(Number(lon))) return "-";
  const latH = Number(lat) >= 0 ? "N" : "S";
  const lonH = Number(lon) >= 0 ? "E" : "W";
  return `${Math.abs(Number(lat)).toFixed(3)}°${latH} ${Math.abs(Number(lon)).toFixed(3)}°${lonH}`;
}

const EARTH_KM_PER_DEGREE = 111.2;
// The styling and rendering are local to this app; the coastline geometry is
// bundled as a local GeoJSON export of the public-domain Natural Earth land
// layer.  It is not an NCDR raster or a hand-drawn block map.
// A 54° longitude window keeps the equirectangular canvas close to the
// reference map's Taiwan-area aspect ratio instead of stretching it across
// an unnecessarily wide 60° view.
const DEFAULT_MAP_VIEW = Object.freeze({ minLon: 101, maxLon: 155, minLat: 8, maxLat: 38 });
const TROPIC_OF_CANCER_LAT = 23.5;
const landGeoJson = window.TYPHOON_LAND_GEOJSON || null;

// This is the app's own vector reference line for the CWA warning area. It is
// intentionally an open coastal arc rather than an ellipse: the western and
// northern ends meet the mainland coast, where the warning area does not paint
// a second mask over Chinese land. Explicit lon/lat vertices keep its extent
// stable when the canvas is resized.
const CWA_WARNING_REFERENCE_PATH = Object.freeze([
  [120.93, 27.56], [121.14, 27.33], [121.32, 27.13], [121.48, 26.92],
  [121.65, 26.73], [121.86, 26.54], [122.08, 26.40], [122.30, 26.27],
  [122.55, 26.08], [122.79, 25.89], [122.98, 25.68], [123.09, 25.44],
  [123.14, 25.18], [123.14, 24.91], [123.09, 24.67], [123.03, 24.43],
  [122.94, 24.19], [122.84, 23.71], [122.72, 23.47], [122.62, 23.13],
  [122.42, 22.54], [122.20, 22.16], [121.96, 21.68], [121.78, 21.20],
  [121.62, 21.01], [121.37, 20.77], [121.08, 20.62], [120.85, 20.58],
  [120.64, 20.58], [120.43, 20.67], [120.23, 20.72], [120.02, 20.87],
  [119.86, 21.01], [119.71, 21.15], [119.55, 21.35], [119.40, 21.54],
  [119.09, 21.93], [118.88, 22.07], [118.72, 22.22], [118.51, 22.41],
  [118.36, 22.55], [118.25, 22.74], [118.15, 22.94], [118.00, 23.13],
  [117.84, 23.27], [117.68, 23.37],
]);

const CWA_WARNING_REFERENCE_POLYGON = CWA_WARNING_REFERENCE_PATH;

function appendProjectedRing(ctx, ring, project) {
  ring.forEach(([lon, lat], index) => {
    const point = project(lat, lon);
    if (index === 0) ctx.moveTo(point.x, point.y); else ctx.lineTo(point.x, point.y);
  });
  ctx.closePath();
}

function appendCwaWarningPath(ctx, project) {
  CWA_WARNING_REFERENCE_PATH.forEach(([lon, lat], index) => {
    const point = project(lat, lon);
    if (index === 0) ctx.moveTo(point.x, point.y); else ctx.lineTo(point.x, point.y);
  });
}

function drawOwnMapBase(ctx, project) {
  ctx.fillStyle = "#c5f1f3";
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  if (!landGeoJson) return;
  ctx.fillStyle = "#f1eed2";
  ctx.strokeStyle = "#7d8b83";
  ctx.lineWidth = 0.8;
  landGeoJson.features.forEach((feature) => {
    const polygons = feature.geometry?.type === "MultiPolygon" ? feature.geometry.coordinates : [];
    polygons.forEach((polygon) => {
      ctx.beginPath();
      polygon.forEach((ring) => {
        appendProjectedRing(ctx, ring, project);
      });
      ctx.fill("evenodd"); ctx.stroke();
    });
  });
}

function drawCwaWarningReference(ctx, project) {
  ctx.save();
  ctx.strokeStyle = "#73807b";
  ctx.lineWidth = 1.1;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.setLineDash([]);
  // The path is open at the mainland side, so there is no artificial closing
  // segment or land-colour mask across China.
  ctx.beginPath(); appendCwaWarningPath(ctx, project); ctx.stroke();
  ctx.setLineDash([]);
  const labelX = 14, labelY = ctx.canvas.height - 38;
  const label = "CWA 警報發布區參考線（約100 km）";
  ctx.font = "12px Segoe UI, Noto Sans TC, sans-serif";
  const boxWidth = ctx.measureText(label).width + 42;
  ctx.fillStyle = "rgba(255,255,255,.88)";
  ctx.strokeStyle = "#b9c6c1";
  ctx.beginPath(); ctx.roundRect(labelX, labelY, boxWidth, 24, 5); ctx.fill(); ctx.stroke();
  ctx.strokeStyle = "#73807b"; ctx.lineWidth = 1.1; ctx.setLineDash([]);
  ctx.beginPath(); ctx.moveTo(labelX + 9, labelY + 12); ctx.lineTo(labelX + 28, labelY + 12); ctx.stroke();
  ctx.setLineDash([]); ctx.fillStyle = "#56625e"; ctx.fillText(label, labelX + 34, labelY + 16);
  ctx.restore();
}

const WIND_RADIUS_STYLES = Object.freeze({
  "15M/S": { fill: "rgba(238, 175, 63, 0.12)", stroke: "#d29a32" },
  "30KT": { fill: "rgba(238, 175, 63, 0.12)", stroke: "#d29a32" },
  "50KT": { fill: "rgba(225, 119, 54, 0.14)", stroke: "#c96d31" },
  "64KT": { fill: "rgba(189, 70, 70, 0.16)", stroke: "#b94b4b" },
});
const WIND_RADIUS_QUADRANTS = Object.freeze({
  NORTHEAST: [[0, 90]],
  SOUTHEAST: [[90, 180]],
  SOUTHWEST: [[180, 270]],
  NORTHWEST: [[270, 360]],
  NORTH: [[270, 360], [0, 90]],
  SOUTH: [[90, 270]],
  EAST: [[0, 180]],
  WEST: [[180, 360]],
  ALL: [[0, 360]],
  ELSEWHERE: [[0, 360]],
});

function projectRadiusPoint(project, lat, lon, radiusKm, bearing) {
  const bearingRad = bearing * Math.PI / 180;
  const latOffset = radiusKm / EARTH_KM_PER_DEGREE * Math.cos(bearingRad);
  const lonScale = Math.max(Math.cos(lat * Math.PI / 180), 0.2);
  const lonOffset = radiusKm / (EARTH_KM_PER_DEGREE * lonScale) * Math.sin(bearingRad);
  return project(lat + latOffset, lon + lonOffset);
}

function drawWindRadii(ctx, project, point, thresholds) {
  const radii = Array.isArray(point.wind_radii) ? point.wind_radii : [];
  const grouped = new Map();
  radii.forEach((item) => {
    const value = item?.value || item;
    const threshold = Number(value?.threshold_kt);
    const radiusKm = Number(value?.radius_km);
    const quadrant = String(value?.quadrant || "").toUpperCase();
    const thresholdLabel = String(value?.threshold_label || (Number.isFinite(threshold) ? `${threshold}KT` : "")).toUpperCase();
    if (!thresholdLabel || !Number.isFinite(radiusKm) || radiusKm <= 0 || !WIND_RADIUS_QUADRANTS[quadrant]) return;
    if (!grouped.has(thresholdLabel)) grouped.set(thresholdLabel, {});
    grouped.get(thresholdLabel)[quadrant] = radiusKm;
  });
  if (!grouped.size) return;
  const center = project(Number(point.lat), Number(point.lon));
  [...grouped.entries()].sort(([a], [b]) => (Number.parseFloat(a) || 0) - (Number.parseFloat(b) || 0)).forEach(([threshold, quadrants]) => {
    const style = WIND_RADIUS_STYLES[threshold] || { fill: "rgba(105, 112, 118, 0.12)", stroke: "#69757b" };
    thresholds.add(threshold);
    const radiusForBearing = (bearing) => {
      const b = (bearing + 360) % 360;
      const candidates = [
        ["NORTHEAST", b >= 0 && b <= 90],
        ["SOUTHEAST", b >= 90 && b <= 180],
        ["SOUTHWEST", b >= 180 && b <= 270],
        ["NORTHWEST", b >= 270 && b <= 360],
        ["NORTH", b <= 90 || b >= 270],
        ["SOUTH", b >= 90 && b <= 270],
        ["EAST", b <= 180],
        ["WEST", b >= 180],
        ["ALL", true],
        ["ELSEWHERE", true],
      ];
      for (const [quadrant, matches] of candidates) {
        if (matches && Number.isFinite(Number(quadrants[quadrant]))) return Number(quadrants[quadrant]);
      }
      return null;
    };
    const edgePoints = [];
    for (let bearing = 0; bearing <= 360; bearing += 5) {
      const radiusKm = radiusForBearing(bearing);
      if (radiusKm === null) continue;
      const edge = projectRadiusPoint(project, Number(point.lat), Number(point.lon), radiusKm, bearing);
      edgePoints.push(edge);
    }
    if (edgePoints.length < 2) return;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(edgePoints[0].x, edgePoints[0].y);
    edgePoints.slice(1).forEach((edge) => ctx.lineTo(edge.x, edge.y));
    ctx.closePath();
    ctx.fillStyle = style.fill;
    ctx.strokeStyle = style.stroke;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 4]);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  });
}

function drawUncertaintyArea(ctx, project, point, uncertaintyKm) {
  if (!Number.isFinite(Number(uncertaintyKm)) || Number(uncertaintyKm) <= 0) return;
  ctx.save();
  ctx.beginPath();
  for (let bearing = 0; bearing <= 360; bearing += 5) {
    const edge = projectRadiusPoint(project, Number(point.lat), Number(point.lon), Number(uncertaintyKm), bearing);
    if (bearing === 0) ctx.moveTo(edge.x, edge.y); else ctx.lineTo(edge.x, edge.y);
  }
  ctx.closePath();
  ctx.globalAlpha = 0.12;
  ctx.fill();
  ctx.restore();
}

function drawWindRadiusLegend(ctx, thresholds, width, height) {
  const values = [...thresholds].sort((a, b) => (Number.parseFloat(a) || 0) - (Number.parseFloat(b) || 0));
  if (!values.length) return;
  ctx.save();
  ctx.font = "12px Segoe UI, Noto Sans TC, sans-serif";
  const label = `風圈半徑（${values.join("／")}）`;
  const boxWidth = Math.min(width - 28, ctx.measureText(label).width + 24);
  const boxX = 14;
  const boxY = height - 68;
  ctx.fillStyle = "rgba(255,255,255,.88)";
  ctx.strokeStyle = "#b9c6c1";
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.roundRect(boxX, boxY, boxWidth, 24, 5); ctx.fill(); ctx.stroke();
  let x = boxX + 9;
  values.forEach((value, index) => {
    const style = WIND_RADIUS_STYLES[value] || { stroke: "#69757b" };
    ctx.strokeStyle = style.stroke;
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 3]);
    ctx.beginPath(); ctx.moveTo(x, boxY + 12); ctx.lineTo(x + 16, boxY + 12); ctx.stroke();
    ctx.setLineDash([]);
    x += 21;
    ctx.fillStyle = "#56625e";
    const text = String(value);
    ctx.fillText(text, x, boxY + 16);
    x += ctx.measureText(text).width + (index === values.length - 1 ? 0 : 12);
  });
  ctx.restore();
}

function drawTrackMap(canvas, tracks, options = {}) {
  const width = 1000, height = 620;
  const ctx = canvas.getContext("2d");
  canvas.width = width; canvas.height = height;
  const minLon = options.minLon ?? DEFAULT_MAP_VIEW.minLon, maxLon = options.maxLon ?? DEFAULT_MAP_VIEW.maxLon;
  const minLat = options.minLat ?? DEFAULT_MAP_VIEW.minLat, maxLat = options.maxLat ?? DEFAULT_MAP_VIEW.maxLat;
  const project = (lat, lon) => ({ x: (Number(lon) - minLon) / (maxLon - minLon) * width, y: height - (Number(lat) - minLat) / (maxLat - minLat) * height });
  drawOwnMapBase(ctx, project);
  drawCwaWarningReference(ctx, project);
  ctx.strokeStyle = "#b7cbd5"; ctx.fillStyle = "#5f7180"; ctx.font = "12px Segoe UI, sans-serif";
  for (let lon = Math.ceil(minLon / 10) * 10; lon <= maxLon; lon += 10) {
    const p = project(minLat, lon); ctx.beginPath(); ctx.moveTo(p.x, 0); ctx.lineTo(p.x, height); ctx.stroke(); ctx.fillText(`${lon}E`, Math.min(p.x + 3, width - 32), height - 5);
  }
  for (let lat = Math.ceil(minLat / 10) * 10; lat <= maxLat; lat += 10) {
    const p = project(lat, minLon); ctx.beginPath(); ctx.moveTo(0, p.y); ctx.lineTo(width, p.y); ctx.stroke(); ctx.fillText(`${lat}N`, 4, Math.max(p.y - 4, 12));
  }
  if (TROPIC_OF_CANCER_LAT >= minLat && TROPIC_OF_CANCER_LAT <= maxLat) {
    const p = project(TROPIC_OF_CANCER_LAT, minLon);
    ctx.save();
    ctx.strokeStyle = "#b07b3d";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([8, 5]);
    ctx.beginPath(); ctx.moveTo(0, p.y); ctx.lineTo(width, p.y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#8a5d2b";
    ctx.font = "12px Segoe UI, Noto Sans TC, sans-serif";
    ctx.fillText("北回歸線 23.5°N", 8, Math.max(p.y - 6, 14));
    ctx.restore();
  }
  ctx.strokeStyle = "#718692"; ctx.strokeRect(0, 0, width, height);
  // Keep forecast tracks close to the reference map's fine-line style. The
  // canvas is rendered at a larger backing resolution and then resized for
  // the page, so these values remain legible without becoming oversized.
  const trackLineWidth = 2.6;
  const trackStartRadius = 4.8;
  const trackPointRadius = 3.6;
  const radiusThresholds = new Set();
  tracks.forEach((track) => {
    (track.points || [])
      .filter((point) => Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lon)))
      .forEach((point) => drawWindRadii(ctx, project, point, radiusThresholds));
  });
  tracks.forEach((track) => {
    const points = (track.points || []).filter((point) => Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lon)));
    if (!points.length) return;
    ctx.strokeStyle = track.color || "#d1495b"; ctx.fillStyle = track.color || "#d1495b";
    ctx.lineWidth = trackLineWidth; ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.beginPath(); points.forEach((point, index) => { const p = project(point.lat, point.lon); if (index === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); }); ctx.stroke();
    points.forEach((point, index) => {
      const p = project(point.lat, point.lon);
      if (point.uncertainty_km && options.showUncertainty !== false) drawUncertaintyArea(ctx, project, point, point.uncertainty_km);
      ctx.beginPath(); ctx.arc(p.x, p.y, index === 0 ? trackStartRadius : trackPointRadius, 0, Math.PI * 2); ctx.fill();
    });
  });
  drawWindRadiusLegend(ctx, radiusThresholds, width, height);
  const legend = tracks.filter((track) => (track.points || []).some((point) => Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lon))));
  if (legend.length) {
    ctx.save();
    const labels = legend.map((track) => String(track.legend || track.name || "路徑"));
    const maxTextWidth = Math.min(360, Math.max(...labels.map((label) => ctx.measureText(label).width), 0) + 38);
    const rowHeight = 24;
    const boxHeight = legend.length * rowHeight + 18;
    const boxX = width - maxTextWidth - 14;
    const boxY = 14;
    ctx.fillStyle = "rgba(255,255,255,.92)";
    ctx.strokeStyle = "#9fb5c0";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.roundRect(boxX, boxY, maxTextWidth, boxHeight, 7); ctx.fill(); ctx.stroke();
    ctx.font = "13px Segoe UI, Noto Sans TC, sans-serif";
    legend.forEach((track, index) => {
      const y = boxY + 19 + index * rowHeight;
      ctx.fillStyle = track.color || "#d1495b";
      ctx.fillRect(boxX + 10, y - 10, 12, 12);
      ctx.fillStyle = "#263742";
      ctx.fillText(String(track.legend || track.name || "路徑"), boxX + 29, y);
    });
    ctx.restore();
  }
}
