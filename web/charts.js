const $ = (s) => document.querySelector(s);
const nf = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 });
const fmt = (v) => (v == null ? "—" : nf.format(v));
const svg = (tag, attrs, text) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
};
export function summarize(profile, low, high, minExpected) {
  const rows = profile.filter((r) => r.age >= low && r.age <= high),
    eligible = rows.filter((r) => r.cohort_eligible);
  const valid = eligible.length > 0 && eligible.length === rows.length;
  const expected = eligible.reduce((s, r) => s + r.expected, 0),
    actual = rows.reduce((s, r) => s + r.actual, 0);
  const residual = valid ? actual - expected : null;
  return {
    actual,
    expected: valid ? expected : null,
    residual,
    residual_per_1000:
      valid && expected >= minExpected && expected
        ? (1000 * residual) / expected
        : null,
  };
}
function bands(profile, low, high, width) {
  const result = [];
  for (let age = low; age <= high; age += width) {
    const end = Math.min(age + width - 1, high),
      rows = profile.filter((r) => r.age >= age && r.age <= end);
    if (!rows.length) continue;
    const stats = summarize(rows, age, end, 0),
      nation = { ESP: 0, EXT: 0 };
    for (const r of rows)
      if (r.residual != null) nation[r.nationality] += r.residual;
    result.push({
      age,
      end,
      label: age === end ? `${age}` : `${age}–${end}`,
      ...stats,
      ...nation,
    });
  }
  return result;
}
export function render(area, low, high, width, manifest) {
  const groups = bands(area.profile, low, high, width),
    root = $("#age-chart");
  root.replaceChildren();
  const eligible = groups.filter((g) => g.residual != null);
  const max = Math.max(
      ...eligible.flatMap((g) => [
        Math.abs(g.ESP),
        Math.abs(g.EXT),
        Math.abs(g.residual),
      ]),
      1,
    ),
    zero = 170,
    scale = 125 / max,
    spacing = 900 / (groups.length || 1),
    points = [];
  root.append(
    svg("title", {}, `Residual por edad de ${area.name}`),
    svg(
      "desc",
      {},
      "Barras ESP y EXT, línea combinada. Consulta la tabla para los valores.",
    ),
    svg("line", { x1: 45, x2: 960, y1: zero, y2: zero, stroke: "#444" }),
    svg("text", { x: 5, y: zero + 4 }, "0"),
  );
  groups.forEach((g, i) => {
    const x = 50 + i * spacing;
    if (g.residual != null) {
      for (const [nat, fill, offset] of [
        ["ESP", "#075646", 2],
        ["EXT", "#a6421d", spacing / 2],
      ]) {
        const value = g[nat],
          h = Math.abs(value) * scale;
        const rect = svg("rect", {
          x: x + offset,
          y: value >= 0 ? zero - h : zero,
          width: Math.max(spacing / 2 - 3, 1),
          height: h,
          fill,
        });
        rect.append(
          svg(
            "title",
            {},
            `${g.label} · ${nat}: residual ${fmt(value)}; observada ${fmt(g.actual)}; esperada ${fmt(g.expected)}. ${area.boundary_status}`,
          ),
        );
        root.append(rect);
      }
      points.push(`${x + spacing / 2},${zero - g.residual * scale}`);
    }
    if (i % Math.max(1, Math.ceil(groups.length / 15)) === 0)
      root.append(
        svg(
          "text",
          {
            x: x + spacing / 2,
            y: 335,
            "text-anchor": "middle",
            "font-size": 11,
          },
          g.label,
        ),
      );
  });
  if (points.length)
    root.append(
      svg("polyline", {
        points: points.join(" "),
        fill: "none",
        stroke: "#202a24",
        "stroke-width": 3,
      }),
    );
  $("#chart-summary").textContent = eligible.length
    ? `Selección ${low}–${high}. ${eligible.filter((g) => g.residual > 0).length} grupos positivos y ${eligible.filter((g) => g.residual < 0).length} negativos. La tabla conserva edades y denominadores.`
    : "Solo población observada; no hay residual para las edades excluidas.";
  const comparison = $("#comparison-chart");
  comparison.replaceChildren();
  const maxPop = Math.max(
      ...groups.flatMap((g) => [g.actual, g.expected || 0]),
      1,
    ),
    observed = [],
    expected = [];
  groups.forEach((g, i) => {
    const x = 50 + (i + 0.5) * spacing;
    observed.push(`${x},${210 - (g.actual / maxPop) * 180}`);
    if (g.expected != null)
      expected.push(`${x},${210 - (g.expected / maxPop) * 180}`);
  });
  comparison.append(
    svg("title", {}, "Comparación de población observada y esperada"),
    svg("polyline", {
      points: observed.join(" "),
      fill: "none",
      stroke: "#075646",
      "stroke-width": 3,
    }),
    svg("polyline", {
      points: expected.join(" "),
      fill: "none",
      stroke: "#a6421d",
      "stroke-width": 3,
      "stroke-dasharray": "8 5",
    }),
    svg(
      "text",
      { x: 50, y: 245 },
      "Continua: observada · Discontinua: esperada",
    ),
  );
  const body = $("#profile-table");
  body.replaceChildren();
  for (const g of groups) {
    const tr = document.createElement("tr");
    for (const value of [
      g.label,
      fmt(g.actual),
      fmt(g.expected),
      fmt(g.residual),
      g.residual == null ? "—" : fmt(g.ESP),
      g.residual == null ? "—" : fmt(g.EXT),
    ]) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    body.append(tr);
  }
  const composition = $("#composition");
  composition.replaceChildren();
  for (const year of [manifest.start_year, manifest.end_year]) {
    const p = document.createElement("p");
    p.textContent = `${year} · mismas edades ${low}–${high} (composición observada, no comparación de cohortes)`;
    composition.append(p);
    for (let age = low; age <= high; age += 5) {
      const top = Math.min(age + 4, high),
        counts = { ESP: 0, EXT: 0 };
      for (const r of area.composition)
        if (r.year === year && r.age >= age && r.age <= top)
          counts[r.nationality] += r.population;
      const total = counts.ESP + counts.EXT;
      if (!total) continue;
      const row = document.createElement("div");
      row.className = "composition-row";
      const label = document.createElement("span");
      label.textContent = `${age}–${top}`;
      const bar = document.createElement("div");
      bar.className = "composition-bar";
      bar.setAttribute(
        "aria-label",
        `${age}–${top}: ESP ${fmt(counts.ESP)}, EXT ${fmt(counts.EXT)}`,
      );
      for (const [nat, cls] of [
        ["ESP", "esp"],
        ["EXT", "ext"],
      ]) {
        const part = document.createElement("span");
        part.className = cls;
        part.style.width = `${(100 * counts[nat]) / total}%`;
        part.title = `${nat}: ${fmt(counts[nat])} (${Math.round((100 * counts[nat]) / total)}%)`;
        bar.append(part);
      }
      const values = document.createElement("span");
      values.textContent = `ESP ${fmt(counts.ESP)} · EXT ${fmt(counts.EXT)}`;
      row.append(label, bar, values);
      composition.append(row);
    }
  }
}
