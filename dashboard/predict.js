let latestForecast = null;
const highRows = document.querySelector("#highRows");
const nearbyRows = document.querySelector("#nearbyRows");
const inertia = document.querySelector("#inertia");
const inertiaValue = document.querySelector("#inertiaValue");

function addHighRow(values = {}) {
  const row = document.createElement("div"); row.className = "repeat-row";
  row.innerHTML = `<label>緯度<input class="high-lat" type="number" step="0.1" value="${values.lat ?? ""}"></label><label>經度<input class="high-lon" type="number" step="0.1" value="${values.lon ?? ""}"></label><label>半徑 KM<input class="high-radius" type="number" step="10" value="${values.radius_km ?? 700}"></label><label>引導 KT<input class="high-speed" type="number" step="1" value="${values.steering_speed_kt ?? 12}"></label><button type="button" class="danger remove-row">移除</button>`;
  row.querySelector(".remove-row").addEventListener("click", () => row.remove()); highRows.appendChild(row);
}

function addNearbyRow(values = {}) {
  const row = document.createElement("div"); row.className = "repeat-row";
  row.innerHTML = `<label>緯度<input class="near-lat" type="number" step="0.1" value="${values.lat ?? ""}"></label><label>經度<input class="near-lon" type="number" step="0.1" value="${values.lon ?? ""}"></label><label>作用半徑 KM<input class="near-radius" type="number" step="10" value="${values.interaction_radius_km ?? 800}"></label><label>作用速度 KT<input class="near-speed" type="number" step="1" value="${values.interaction_speed_kt ?? 8}"></label><button type="button" class="danger remove-row">移除</button>`;
  row.querySelector(".remove-row").addEventListener("click", () => row.remove()); nearbyRows.appendChild(row);
}

function numberFrom(id, fallback = null) { const value = document.querySelector(`#${id}`).value; return value === "" ? fallback : Number(value); }

function collectPayload() {
  return {
    current_lat: numberFrom("currentLat"), current_lon: numberFrom("currentLon"), previous_lat: numberFrom("previousLat"), previous_lon: numberFrom("previousLon"), previous_interval_hours: numberFrom("previousInterval", 6),
    initial_direction: document.querySelector("#initialDirection").value, initial_speed_kt: numberFrom("initialSpeed", 0), inertia: Number(inertia.value), westerly_south_lat: numberFrom("westerlyLat", 20), westerly_speed_kt: numberFrom("westerlySpeed", 12), step_hours: numberFrom("stepHours", 6), horizon_hours: numberFrom("horizonHours", 240),
    highs: [...highRows.querySelectorAll(".repeat-row")].map((row) => ({ lat: Number(row.querySelector(".high-lat").value), lon: Number(row.querySelector(".high-lon").value), radius_km: Number(row.querySelector(".high-radius").value), steering_speed_kt: Number(row.querySelector(".high-speed").value) })).filter((item) => Number.isFinite(item.lat) && Number.isFinite(item.lon)),
    nearby_systems: [...nearbyRows.querySelectorAll(".repeat-row")].map((row) => ({ lat: Number(row.querySelector(".near-lat").value), lon: Number(row.querySelector(".near-lon").value), interaction_radius_km: Number(row.querySelector(".near-radius").value), interaction_speed_kt: Number(row.querySelector(".near-speed").value) })).filter((item) => Number.isFinite(item.lat) && Number.isFinite(item.lon)),
  };
}

function renderForecast(result) {
  latestForecast = result; const points = result.points || [];
  document.querySelector("#forecastStatus").innerHTML = `<span class="good">已產生 ${points.length} 個位置點。</span> ${escapeHtml(result.note)}`;
  drawTrackMap(document.querySelector("#forecastCanvas"), [{ name: "手動預測", color: "#d1495b", points }], { showUncertainty: true });
  const rows = points.map((point) => `<tr><td>${point.hour} h</td><td>${formatCoord(point.lat, point.lon)}</td><td>${point.uncertainty_km} km</td></tr>`).join("");
  document.querySelector("#forecastTable").innerHTML = `<table><thead><tr><th>時效</th><th>座標</th><th>參考誤差半徑</th></tr></thead><tbody>${rows}</tbody></table>`;
}

inertia.addEventListener("input", () => { inertiaValue.value = Number(inertia.value).toFixed(2); });
document.querySelector("#addHigh").addEventListener("click", () => addHighRow());
document.querySelector("#addNearby").addEventListener("click", () => addNearbyRow());
document.querySelector("#clearForm").addEventListener("click", () => { highRows.replaceChildren(); nearbyRows.replaceChildren(); });
document.querySelector("#resetForecast").addEventListener("click", () => {
  document.querySelector("#forecastForm").reset();
  highRows.replaceChildren();
  nearbyRows.replaceChildren();
  addHighRow({ lat: 25, lon: 135, radius_km: 900, steering_speed_kt: 12 });
  inertiaValue.value = Number(inertia.value).toFixed(2);
  latestForecast = null;
  document.querySelector("#forecastStatus").textContent = "尚未產生路徑。";
  document.querySelector("#forecastTable").textContent = "產生路徑後顯示。";
  drawTrackMap(document.querySelector("#forecastCanvas"), [], { showUncertainty: true });
});
document.querySelector("#forecastForm").addEventListener("submit", async (event) => {
  event.preventDefault(); const status = document.querySelector("#forecastStatus"); status.textContent = "計算中…";
  try {
    const response = await fetch("/api/manual-forecast", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(collectPayload()) });
    const payload = await response.json(); if (!response.ok) throw new Error(payload.error || "預測失敗"); renderForecast(payload);
  } catch (error) { status.innerHTML = `<span class="bad">${escapeHtml(error.message)}</span>`; }
});
document.querySelector("#downloadForecast").addEventListener("click", () => { if (latestForecast) downloadText("manual_forecast.json", JSON.stringify(latestForecast, null, 2)); });
addHighRow({ lat: 25, lon: 135, radius_km: 900, steering_speed_kt: 12 });
