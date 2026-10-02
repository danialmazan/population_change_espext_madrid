const $ = (s) => document.querySelector(s);
const number = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 });
const signed = new Intl.NumberFormat("es-ES", {
  maximumFractionDigits: 0,
  signDisplay: "exceptZero",
});
const quality = {
  unchanged: "Sin cambios",
  exact_harmonisation: "Agregación exacta",
  estimated_harmonisation: "Asignación estimada",
  unreliable: "No fiable",
};
const levels = {
  section: "Zona de sección comparable",
  barrio: "Barrio",
  district: "Distrito",
  city: "Madrid",
};
const state = {
  catalog: null,
  manifest: null,
  base: null,
  index: [],
  indicators: [],
  shapes: [],
  areaId: null,
  level: "district",
  preset: "cohorts",
  indicator: "residual_per_1000",
  reliability: "exact",
  low: 10,
  high: 99,
  controller: null,
  loadToken: 0,
  profileToken: 0,
  cache: new Map(),
};
const fmt = (v, sign = false) =>
  v == null ? "—" : (sign ? signed : number).format(v);
function options(select, rows) {
  select.replaceChildren(
    ...rows.map(([value, label]) => {
      const o = document.createElement("option");
      o.value = value;
      o.textContent = label;
      return o;
    }),
  );
}
async function json(url, signal) {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
  return response.json();
}
function asset(ref) {
  return new URL(typeof ref === "string" ? ref : ref.url, state.base).href;
}
function fail(error) {
  if (error.name === "AbortError") return;
  $("#error").hidden = false;
  $("#error").textContent = "No se pudieron cargar los datos: " + error.message;
}
function rows() {
  return state.index.filter((a) => a.level === state.level);
}
function selectedStats(area) {
  if (area.boundary_status === "unreliable") {
    const raw = state.indicators.find(
      (r) => r.area_id === area.id && r.preset === state.preset,
    );
    return {
      actual: raw?.actual ?? null,
      expected: null,
      residual: null,
      residual_per_1000: null,
    };
  }
  if (state.preset !== "custom")
    return (
      state.indicators.find(
        (r) => r.area_id === area.id && r.preset === state.preset,
      ) || {
        actual: null,
        expected: null,
        residual: null,
        residual_per_1000: null,
      }
    );
  return (
    state.customStats?.get(area.id) || {
      actual: null,
      expected: null,
      residual: null,
      residual_per_1000: null,
    }
  );
}
function decode(topology) {
  const arcs = topology.arcs.map((arc) => {
    let x = 0,
      y = 0;
    return arc.map((p) => {
      x += p[0];
      y += p[1];
      return [
        x * topology.transform.scale[0] + topology.transform.translate[0],
        y * topology.transform.scale[1] + topology.transform.translate[1],
      ];
    });
  });
  function ring(indices) {
    return indices.flatMap((id, i) => {
      const coords = id < 0 ? [...arcs[~id]].reverse() : arcs[id];
      return i ? coords.slice(1) : coords;
    });
  }
  return topology.objects.areas.geometries.map((g) => ({
    id: g.id,
    polygons:
      g.type === "Polygon"
        ? [g.arcs.map(ring)]
        : g.arcs.map((p) => p.map(ring)),
  }));
}
function color(value, extent) {
  if (value == null) return "#bfc5bf";
  const weight = Math.min(Math.abs(value) / (extent || 1), 1);
  const base = [239, 235, 225],
    end = value < 0 ? [166, 66, 29] : [7, 86, 70];
  return `rgb(${base.map((x, i) => Math.round(x + (end[i] - x) * weight))})`;
}
function robustExtent(values) {
  const sorted = values
    .filter((v) => v != null)
    .map(Math.abs)
    .sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) * 0.95)] || 1;
}
function svgElement(tag, attrs, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
}
function renderMap() {
  const svg = $("#map");
  svg.replaceChildren();
  const records = rows(),
    valid = new Set(records.map((a) => a.id));
  const shapes = state.shapes.filter((g) => valid.has(g.id));
  const points = shapes.flatMap((g) => g.polygons.flat(2));
  if (!points.length) {
    $("#map-summary").textContent =
      "Sin geometría disponible. Usa la tabla de áreas.";
    return;
  }
  const xs = points.map((p) => p[0]),
    ys = points.map((p) => p[1]);
  const xmin = xs.reduce((v,x)=>Math.min(v,x),Infinity),
    xmax = xs.reduce((v,x)=>Math.max(v,x),-Infinity),
    ymin = ys.reduce((v,y)=>Math.min(v,y),Infinity),
    ymax = ys.reduce((v,y)=>Math.max(v,y),-Infinity);
  const scale = Math.min(640 / (xmax - xmin || 1), 460 / (ymax - ymin || 1));
  const project = (p) => [
    30 + (p[0] - xmin) * scale,
    490 - (p[1] - ymin) * scale,
  ];
  const extent = robustExtent(
    records.map((a) => selectedStats(a)[state.indicator]),
  );
  const defs = svgElement("defs", {}),
    pattern = svgElement("pattern", {
      id: "estimated-hatch",
      width: 8,
      height: 8,
      patternUnits: "userSpaceOnUse",
    });
  pattern.append(
    svgElement("path", {
      d: "M-1,1 L1,-1 M0,8 L8,0 M7,9 L9,7",
      stroke: "#111",
      "stroke-width": 2,
    }),
  );
  defs.append(pattern);
  svg.append(defs);
  for (const geom of shapes) {
    const area = records.find((a) => a.id === geom.id),
      value = selectedStats(area)[state.indicator];
    const d = geom.polygons
      .map((poly) =>
        poly
          .map(
            (r) =>
              r
                .map((p, i) => `${i ? "L" : "M"}${project(p).join(",")}`)
                .join(" ") + " Z",
          )
          .join(" "),
      )
      .join(" ");
    const path = svgElement("path", {
      d,
      fill:
        area.boundary_status === "unreliable"
          ? "#bfc5bf"
          : color(value, extent),
      stroke: area.id === state.areaId ? "#111" : "#fff",
      "stroke-width": area.id === state.areaId ? 3 : 1,
      tabindex: 0,
      role: "button",
      "aria-label": `${area.name}: ${fmt(value, true)}. ${quality[area.boundary_status]}`,
      "fill-rule": "evenodd",
    });
    path.append(
      svgElement(
        "title",
        {},
        `${area.name}: ${fmt(value, true)} · ${quality[area.boundary_status]}${Math.abs(value) > extent ? " · escala recortada" : ""}`,
      ),
    );
    path.addEventListener("click", () => selectArea(area.id));
    path.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectArea(area.id);
      }
    });
    svg.append(path);
    if (area.boundary_status === "estimated_harmonisation")
      svg.append(
        svgElement("path", {
          d,
          fill: "url(#estimated-hatch)",
          "pointer-events": "none",
          "fill-rule": "evenodd",
        }),
      );
  }
  $("#map-title").textContent = levels[state.level];
  $("#map-summary").textContent =
    `${records.length} áreas. Escala simétrica hasta ±${fmt(extent)}; valores extremos recortados en color. Rayado: estimadas. Gris: no fiables o tasa suprimida.`;
}
function renderTerritory() {
  const container = $("#territory");
  container.replaceChildren();
  const sorted = rows()
    .slice()
    .sort(
      (a, b) =>
        (selectedStats(b)[state.indicator] ?? -Infinity) -
        (selectedStats(a)[state.indicator] ?? -Infinity),
    );
  const tbody = $("#distribution");
  tbody.replaceChildren();
  for (const area of sorted) {
    const stats = selectedStats(area),
      value =
        area.boundary_status === "unreliable" && state.indicator !== "actual"
          ? null
          : stats[state.indicator];
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${area.name} · ${fmt(value, true)}`;
    button.className = area.id === state.areaId ? "active" : "";
    button.addEventListener("click", () => selectArea(area.id));
    container.append(button);
    const tr = document.createElement("tr");
    const first = document.createElement("td");
    const link = document.createElement("button");
    link.textContent = area.name;
    link.addEventListener("click", () => selectArea(area.id));
    first.append(link);
    tr.append(first);
    for (const cellValue of [
      fmt(value, true),
      fmt(stats.expected),
      quality[area.boundary_status],
    ]) {
      const td = document.createElement("td");
      td.textContent = cellValue;
      tr.append(td);
    }
    tbody.append(tr);
  }
  $("#distribution-caption").textContent =
    `${levels[state.level]} · edades ${state.low}–${state.high} · ${state.manifest.start_year}–${state.manifest.end_year}`;
}
async function profile(area, signal) {
  const url = asset(area.profile_url);
  if (!state.cache.has(url)) state.cache.set(url, await json(url, signal));
  return state.cache.get(url);
}
async function selectArea(id) {
  state.areaId = id;
  $("#area").value = id;
  renderMap();
  renderTerritory();
  const token = ++state.profileToken;
  state.controller?.abort();
  state.controller = new AbortController();
  try {
    const area = state.index.find((a) => a.id === id);
    if (!area) return;
    const data = await profile(area, state.controller.signal);
    if (token !== state.profileToken) return;
    const stats = selectedStats(area);
    $("#area-name").textContent = area.name;
    $("#quality").textContent =
      `${quality[area.boundary_status]} · ${area.boundary_method} · ${fmt(area.affected_share * 100)}% de población inicial afectada. ${area.reliability_note}`;
    $("#residual").textContent = fmt(stats.residual, true);
    $("#rate").textContent =
      stats.residual_per_1000 == null
        ? "Tasa suprimida o sin cohorte comparable"
        : `${fmt(stats.residual_per_1000, true)} por 1.000 esperados`;
    $("#actual").textContent = fmt(stats.actual);
    $("#expected").textContent = fmt(stats.expected);
    $("#under-ten").textContent = fmt(area.observed_under_interval);
    $("#born-label").textContent =
      `0–${state.manifest.interval_years - 1} · nacidos durante el periodo`;
    $("#terminal-note").textContent =
      `Edades ${state.manifest.config.terminal_age}+: ${fmt(area.observed_terminal)} observadas, excluidas del residual.`;
    $("#sensitivity").textContent = data.sensitivities.length
      ? "Variantes (cohortes y límites de edad indicados): " +
        data.sensitivities
          .map(
            (s) =>
              `${s.scenario}: residual ${fmt(s.residual, true)} (esperados Δ ${fmt(s.expected_difference, true)})`,
          )
          .join("; ")
      : "Consulta la auditoría para las variantes de supervivencia.";
    const charts = await import("./charts.js");
    if (token !== state.profileToken) return;
    charts.render(
      data.area,
      state.low,
      state.high,
      Number($("#age-group").value),
      state.manifest,
    );
  } catch (e) {
    fail(e);
  }
}
async function customRange() {
  const low = Number($("#age-min").value),
    high = Number($("#age-max").value);
  if (
    !Number.isInteger(low) ||
    !Number.isInteger(high) ||
    low < 0 ||
    high > 130 ||
    low > high
  ) {
    fail(
      new Error(
        "El intervalo de edad debe estar entre 0 y 130, con inicio ≤ final",
      ),
    );
    return;
  }
  state.low = low;
  state.high = high;
  state.preset = "custom";
  state.customStats = new Map();
  const token = state.loadToken;
  const charts = await import("./charts.js");
  // Profiles are fetched lazily; bounded workers prevent a custom range from flooding the server.
  const pending = rows().slice();
  await Promise.all(
    Array.from({ length: Math.min(4, pending.length) }, async () => {
      while (pending.length) {
        const area = pending.shift();
        const payload = await profile(area);
        if (token !== state.loadToken) return;
        state.customStats.set(
          area.id,
          charts.summarize(
            payload.area.profile,
            low,
            high,
            state.manifest.config.min_expected,
          ),
        );
      }
    }),
  );
  if (token !== state.loadToken) return;
  $("#error").hidden = true;
  renderMap();
  renderTerritory();
  await selectArea(state.areaId);
}
async function loadGeometry(token) {
  const level = state.level,
    ref = state.manifest.geometry[level];
  const shapes = ref ? decode(await json(asset(ref))) : [];
  if (token !== state.loadToken || level !== state.level) return;
  state.shapes = shapes;
  renderMap();
}
async function loadIndicators() {
  const token = state.loadToken, level = state.level, preset = state.preset;
  const ref = state.manifest.indicators_by_level_preset?.[level]?.[preset];
  if (!ref) return true;
  const indicators = await json(asset(ref));
  if (token !== state.loadToken || level !== state.level || preset !== state.preset) return false;
  state.indicators = indicators;
  return true;
}
async function changeLevel() {
  state.level = $("#level").value;
  if (!(await loadIndicators())) return;
  const available = rows();
  options(
    $("#area"),
    available.map((a) => [a.id, a.name]),
  );
  state.areaId = available[0]?.id;
  if (state.preset === "custom") await customRange();
  await loadGeometry(state.loadToken);
  renderTerritory();
  await selectArea(state.areaId);
}
async function loadWindow() {
  const token = ++state.loadToken;
  state.profileToken++;
  state.controller?.abort();
  $("#error").hidden = true;
  state.cache.clear();
  const window = state.catalog.windows.find((w) => w.id === $("#window").value);
  const url = new URL(
    state.reliability === "all" ? window.inclusive_manifest : window.manifest,
    new URL("data/", location.href),
  );
  const manifest = await json(url);
  if (token !== state.loadToken) return;
  state.base = url;
  state.manifest = manifest;
  const [index, indicators] = await Promise.all([
    json(asset(manifest.index)),
    json(asset(manifest.indicators)),
  ]);
  if (token !== state.loadToken) return;
  state.index = index;
  state.indicators = indicators;
  const research = manifest.dataset_kind === "research";
  levels.barrio = research ? "Ámbito común de barrios" : "Barrio";
  levels.district = research ? "Ámbito común de distritos" : "Distrito";
  $("#source-attribution").hidden = !research;
  $("#source-attribution").textContent = "Fuentes: Ayuntamiento de Madrid, padrón municipal y Banco de Datos Municipal; Instituto Nacional de Estadística (INE), tablas de mortalidad y secciones censales. Consulta del 2 de octubre de 2026. Reutilización de datos estadísticos bajo CC BY 4.0 según las fuentes. Transformaciones: agregación condicional, supervivencia y ámbitos comunes de investigación; sin aprobación estadística oficial.";
  const demo = manifest.dataset_kind !== "official" || !manifest.release_passed;
  $("#demo-banner").hidden = !demo;
  $("#demo-banner b").textContent = manifest.dataset_kind === "research" ? "Resultados de investigación" : demo ? "Vista de demostración" : "";
  $("#demo-message").textContent = manifest.notice || "";
  $("#year-pill").textContent = `${manifest.start_year} → ${manifest.end_year}`;
  $("#coverage").textContent =
    manifest.coverage_note ||
    (state.reliability === "all"
      ? "Incluye estimaciones y zonas no fiables. Consulta sus indicadores de calidad."
      : "Geografía exacta.");
  options(
    $("#level"),
    Object.keys(levels)
      .filter((l) => index.some((a) => a.level === l))
      .map((l) => [l, levels[l]]),
  );
  $("#level").value = index.some((a) => a.level === state.level)
    ? state.level
    : manifest.default_level;
  options(
    $("#preset"),
    manifest.presets.map((p) => [p.id, p.label]),
  );
  state.preset = "cohorts";
  $("#preset").value = state.preset;
  state.low = manifest.interval_years;
  state.high = manifest.config.terminal_age - 1;
  $("#age-min").value = state.low;
  $("#age-max").value = state.high;
  const links = $("#data-links");
  links.replaceChildren();
  for (const [label, url] of [
    ["Descargar CSV", manifest.downloads.csv],
    ["Descargar Parquet", manifest.downloads.parquet],
    ["QA", manifest.qa.url],
    ["Fuentes", manifest.sources.url],
    ["Método", manifest.method.url],
    ["Auditoría", "audit.html"],
    ["Manifiesto", "manifest.json"],
  ]) {
    const a = document.createElement("a");
    a.href = asset(url);
    a.textContent = label;
    links.append(a);
  }
  $("#version").textContent =
    `Zona: ${manifest.config.zone_version} · Mortalidad: ${manifest.dataset_kind === "demonstration" ? "simulada" : manifest.config.mortality_region} · Código: ${manifest.build_commit.slice(0, 12)} · Carga inicial comprimida: ${fmt(manifest.performance.initial_gzip_bytes / 1000)} KB.`;
  await changeLevel();
}
async function init() {
  state.catalog = await json(new URL("data/catalog.json", location.href));
  options(
    $("#window"),
    state.catalog.windows.map((w) => [w.id, w.label]),
  );
  $("#window").addEventListener("change", () => loadWindow().catch(fail));
  $("#reliability").addEventListener("change", () => {
    state.reliability = $("#reliability").value;
    loadWindow().catch(fail);
  });
  $("#level").addEventListener("change", () => changeLevel().catch(fail));
  $("#area").addEventListener("change", () => selectArea($("#area").value));
  $("#indicator").addEventListener("change", () => {
    state.indicator = $("#indicator").value;
    renderMap();
    renderTerritory();
  });
  $("#preset").addEventListener("change", async () => {
    state.preset = $("#preset").value;
    const preset = state.manifest.presets.find((p) => p.id === state.preset);
    state.low = preset.min;
    state.high =
      state.preset === "cohorts"
        ? state.manifest.config.terminal_age - 1
        : preset.max;
    $("#age-min").value = state.low;
    $("#age-max").value = state.high;
    try {
      if (!(await loadIndicators())) return;
      renderMap();
      renderTerritory();
      await selectArea(state.areaId);
    } catch (error) { fail(error); }
  });
  $("#custom-age").addEventListener("click", () => customRange().catch(fail));
  $("#age-group").addEventListener("change", () => selectArea(state.areaId));
  await loadWindow();
}
init().catch(fail);
