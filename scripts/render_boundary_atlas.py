"""Render all changed components and unchanged components with parent exceptions."""

import hashlib
import json
from pathlib import Path
from madrid_demography.acquisition import read_lock, digest
from madrid_demography.boundary_audit import read_sections


def main():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.collections import LineCollection

    report_path = Path("docs/audit/boundary-review.json")
    report = json.loads(report_path.read_text())
    sources = {s["id"]: s for s in read_lock("sources.lock.yml")["sources"]}
    geometries = {}
    for year in (2015, 2025):
        sid = f"sections_{year}"
        source = sources[sid]
        path = Path("data/raw") / sid / source["sha256"]
        if digest(path) != report["source_hashes"][sid]:
            raise ValueError("Atlas source differs from reviewed geometry")
        geometries[year], _ = read_sections(path)
    cases = [
        c
        for c in report["components"]
        if c["classification"] != "unchanged" or not c["stable_raw_parent_code"]
    ]
    cases.sort(key=lambda c: (c["stable_raw_parent_code"], c["zone_id"]))
    output = Path("reports/boundary-review-atlas.pdf")
    output.parent.mkdir(exist_ok=True)
    images = Path("data/audit/boundary-atlas")
    images.mkdir(parents=True, exist_ok=True)
    per_page = 24
    with PdfPages(
        output,
        metadata={
            "Title": "Madrid 2015–2025 boundary and parent review atlas",
            "Author": "Madrid demographic audit",
            "Subject": "Research candidates; historical parent boundary evidence pending",
        },
    ) as pdf:
        for start in range(0, len(cases), per_page):
            fig, axes = plt.subplots(6, 4, figsize=(14, 18))
            for offset, ax in enumerate(axes.flat):
                index = start + offset
                if index >= len(cases):
                    ax.axis("off")
                    continue
                c = cases[index]
                for year, side, color, width in (
                    (2015, "old", "#2166ac", 1.0),
                    (2025, "new", "#d95f02", 0.7),
                ):
                    lines = []
                    for gid in c[f"{side}_ids"]:
                        geometry = geometries[year][gid]
                        polygons = (
                            list(geometry.geoms)
                            if geometry.geom_type == "MultiPolygon"
                            else [geometry]
                        )
                        for polygon in polygons:
                            lines.append(list(polygon.exterior.coords))
                            lines.extend(
                                list(ring.coords) for ring in polygon.interiors
                            )
                    ax.add_collection(
                        LineCollection(lines, colors=color, linewidths=width, alpha=0.8)
                    )
                ax.autoscale()
                ax.set_aspect("equal")
                ax.margins(0.08)
                ax.set_xticks([])
                ax.set_yticks([])
                label = (
                    "PARENT EXCEPTION"
                    if not c["stable_raw_parent_code"]
                    else "code stable; boundaries pending"
                )
                ax.set_title(
                    f"{index + 1}. {c['zone_id']}\n{len(c['old_ids'])} → {len(c['new_ids'])} sections | {label}",
                    fontsize=7,
                    color="#a50f15" if not c["stable_raw_parent_code"] else "#222222",
                )
                parents = lambda side: ",".join(b for d, b in c[f"{side}_parents"])
                ax.set_xlabel(
                    f"barrio {parents('old')} → {parents('new')}\nunion difference {c['symmetric_difference_ratio']:.2g}; people {c['old_known_population']:,} → {c['new_known_population']:,}",
                    fontsize=6,
                )
            fig.suptitle(
                f"Madrid boundary review — page {start // per_page + 1}\n2015 blue · 2025 orange · projected EPSG:25830 · raw parent codes are not independent boundary evidence",
                fontsize=12,
            )
            fig.tight_layout(rect=[0, 0, 1, 0.95])
            pdf.savefig(fig)
            fig.savefig(images / f"page-{start // per_page + 1}.png", dpi=120)
            plt.close(fig)
    metadata = dict(
        production_ready=False,
        report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
        atlas_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        pages=(len(cases) + per_page - 1) // per_page,
        plotted_components=len(cases),
        plotted_zone_ids=[c["zone_id"] for c in cases],
        visual_approval="not_an_analytical_release_approval",
    )
    Path("docs/audit/boundary-atlas.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    print(output, len(cases), "components", metadata["pages"], "pages")


if __name__ == "__main__":
    main()
