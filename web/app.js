const state = { data: null, level: "district", areaId: null, indicator: "residual_per_1000" };
const $ = (selector) => document.querySelector(selector);
const format = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0, signDisplay: "exceptZero" });
const plain = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 });

function color(value, extent) {
  const ratio = Math.min(Math.abs(value) / (extent || 1), 1);
  const target = value >= 0 ? [7, 86, 70] : [232, 111, 81];
  const base = [216, 210, 196];
  return `rgb(${base.map((channel, i) => Math.round(channel + (target[i] - channel) * (.3 + ratio * .7))).join(",")})`;
}

function areas() { return state.data.areas.filter((area) => area.level === state.level); }
function activeArea() { return state.data.areas.find((area) => area.id === state.areaId) || areas()[0]; }

function renderControls() {
  const select = $("#area");
  select.innerHTML = areas().map((area) => `<option value="${area.id}">${area.name}</option>`).join("");
  if (!areas().some((area) => area.id === state.areaId)) state.areaId = areas()[0]?.id;
  select.value = state.areaId;
}

function renderTerritory() {
  const records = areas();
  const extent = Math.max(...records.map((area) => Math.abs(area[state.indicator] || 0)), 1);
  $("#map-title").textContent = state.level === "city" ? "Madrid total" : "Distritos";
  $("#territory").innerHTML = records.map((area) => {
    const value = area[state.indicator] || 0;
    const unit = state.indicator === "residual_per_1000" ? "‰" : "";
    return `<button role="listitem" data-id="${area.id}" class="${area.id === state.areaId ? "active" : ""}" style="background:${color(value, extent)}"><span>${area.name}</span><b>${format.format(value)}${unit}</b></button>`;
  }).join("");
  document.querySelectorAll("#territory button").forEach((button) => button.addEventListener("click", () => {
    state.areaId = button.dataset.id; $("#area").value = state.areaId; render();
  }));
}

function renderSummary(area) {
  $("#area-name").textContent = area.name;
  $("#quality").textContent = area.boundary_status === "estimated_harmonisation" ? "◒ Armonización estimada" : "● Geografía comparable";
  $("#residual").textContent = format.format(area.residual);
  $("#rate").textContent = `${format.format(area.residual_per_1000)} por 1.000 esperados`;
  $("#actual").textContent = plain.format(area.actual);
  $("#expected").textContent = plain.format(area.expected);
  $("#under-ten").textContent = plain.format(area.observed_under_interval);
}

function renderChart(area) {
  const svg = $("#age-chart");
  const grouped = new Map();
  area.profile.filter((row) => row.cohort_eligible).forEach((row) => {
    const group = grouped.get(row.age) || { ESP: 0, EXT: 0 };
    group[row.nationality] += row.residual;
    grouped.set(row.age, group);
  });
  const bands = [];
  for (let start = 10; start < 100; start += 5) {
    const rows = [...grouped].filter(([age]) => age >= start && age < start + 5).map(([, value]) => value);
    bands.push({ age: start, ESP: rows.reduce((sum, row) => sum + row.ESP, 0), EXT: rows.reduce((sum, row) => sum + row.EXT, 0) });
  }
  const max = Math.max(...bands.flatMap((band) => [Math.abs(band.ESP), Math.abs(band.EXT), Math.abs(band.ESP + band.EXT)]), 1);
  const zero = 175, scale = 135 / max, left = 55, width = 890 / bands.length;
  let markup = `<line x1="45" x2="970" y1="${zero}" y2="${zero}" stroke="#9ea49d"/><text x="10" y="${zero + 4}" font-size="10" fill="#65716c">0</text>`;
  const points = [];
  bands.forEach((band, index) => {
    const x = left + index * width;
    [["ESP", "#075646", 3], ["EXT", "#e86f51", width / 2]].forEach(([key, fill, offset]) => {
      const value = band[key], height = Math.abs(value) * scale;
      markup += `<rect x="${x + offset}" y="${value >= 0 ? zero - height : zero}" width="${Math.max(width / 2 - 4, 2)}" height="${height}" fill="${fill}"><title>${band.age}–${band.age + 4}: ${key} ${format.format(value)}</title></rect>`;
    });
    const total = band.ESP + band.EXT;
    points.push(`${x + width / 2},${zero - total * scale}`);
    if (index % 2 === 0) markup += `<text x="${x + width / 2}" y="335" text-anchor="middle" font-size="10" fill="#65716c">${band.age}</text>`;
  });
  markup += `<polyline points="${points.join(" ")}" fill="none" stroke="#edb552" stroke-width="3"/>`;
  markup += `<text x="965" y="350" text-anchor="end" font-size="10" fill="#65716c">edad en 2025 →</text>`;
  svg.innerHTML = `<title>Residual demográfico de ${area.name}</title><desc>Barras españolas y extranjeras y línea total en grupos de cinco años.</desc>${markup}`;
}

function render() {
  renderControls(); renderTerritory(); const area = activeArea(); if (!area) return; renderSummary(area); renderChart(area);
}

async function init() {
  try {
    const response = await fetch("data/analysis.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    if (state.data.dataset_kind !== "official") {
      $("#demo-banner").hidden = false;
      $("#demo-message").textContent = state.data.notice || "Los valores no son estadísticas oficiales.";
    }
    $("#level").addEventListener("change", (event) => { state.level = event.target.value; state.areaId = null; render(); });
    $("#indicator").addEventListener("change", (event) => { state.indicator = event.target.value; renderTerritory(); });
    $("#area").addEventListener("change", (event) => { state.areaId = event.target.value; render(); });
    render();
  } catch (error) {
    $("#territory").innerHTML = `<p>No se pudieron cargar los datos: ${error.message}</p>`;
  }
}

init();

