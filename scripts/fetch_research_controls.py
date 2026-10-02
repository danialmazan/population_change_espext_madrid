"""Snapshot city/age and full-population monthly controls for research windows."""

import gzip
import hashlib
import html
import json
import re
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE = "https://servpub.madrid.es/CSEBD_WBINTER/"


def main():
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    page = (
        opener.open(BASE + "seleccionSerie.html?numSerie=0301000000001", timeout=45)
        .read()
        .decode()
    )

    def value(key):
        m = re.search(r'<input[^>]*id="' + key + r'"[^>]*value="([^"]*)"', page)
        if not m:
            raise ValueError("Public bank schema changed")
        return html.unescape(m.group(1))

    folder = Path("docs/audit/research-controls")
    folder.mkdir(parents=True, exist_ok=True)
    for year in range(2014, 2026):
        for kind in ("ages", "total"):
            stem = f"{year}-{kind}"
            receipt_path = folder / (stem + ".receipt.json")
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
                raw = gzip.decompress((folder / (stem + ".json.gz")).read_bytes())
                if hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
                    raise ValueError("Changed cached control")
                continue
            body = {
                k: value(k)
                for k in ("fuente", "numSerie", "numId", "nombreSerie", "tipoSerie")
            }
            body.update(
                listaEpigrafesConsulta=[body["nombreSerie"]],
                anioSeleccion=str(year),
                mesSeleccion="1",
                listaIdsDistritos=["00 TODOS"],
                listaIdsBarrios=["00 TODOS"],
                listaIdsSecciones=[],
                listaEdades=[str(a) for a in range(100)]
                if kind == "ages"
                else ["00 TODOS"],
                listaTramos=[],
                listaNacionalidades=["Total"],
                listaSexos=["Total"],
                tiposDato="Valores Absolutos",
                tiposPorcentaje="",
                accionFormulario="consultarDatosBarrio",
                checkDistrito="false",
                checkBarrio="false",
                checkSeccion="false",
                checkEdad="true" if kind == "ages" else "false",
                checkTramo="false",
                checkNacionalidad="false",
                checkSexo="false",
            )
            with opener.open(
                Request(
                    BASE + "detalleSerie.html",
                    json.dumps(body).encode(),
                    {"Content-Type": "application/json"},
                ),
                timeout=45,
            ) as response:
                raw = response.read()
                encoding = response.headers.get_content_charset() or "iso-8859-1"
            result = json.loads(raw.decode(encoding))
            if (
                result.get("status") != "success"
                or result.get("errorTitulo")
                or len(result["listaConsulta"]) != (100 if kind == "ages" else 1)
            ):
                raise ValueError("Incomplete monthly control")
            (folder / (stem + ".json.gz")).write_bytes(gzip.compress(raw, mtime=0))
            receipt = {
                "url": BASE + "detalleSerie.html",
                "method": "POST",
                "request": body,
                "response_encoding": encoding,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(year, "monthly controls retained", flush=True)


if __name__ == "__main__":
    main()
