"""Fetch the public bank's 2015 district/age controls in untruncated batches."""

import gzip
import hashlib
import html
import json
from pathlib import Path
import re
from datetime import datetime, timezone
from urllib.request import build_opener, HTTPCookieProcessor, Request
from http.cookiejar import CookieJar

BASE = "https://servpub.madrid.es/CSEBD_WBINTER/"


def main():
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    page = (
        opener.open(BASE + "seleccionSerie.html?numSerie=0301000000001", timeout=45)
        .read()
        .decode("utf-8")
    )

    def value(identifier):
        match = re.search(
            r'<input[^>]*id="' + identifier + r'"[^>]*value="([^"]*)"', page
        )
        if not match:
            raise ValueError(f"Missing UI field {identifier}")
        return html.unescape(match.group(1))

    folder = Path("docs/audit/monthly-age-controls")
    folder.mkdir(parents=True, exist_ok=True)
    for first, last in ((1, 10), (11, 21)):
        payload = {
            key: value(key)
            for key in ("fuente", "numSerie", "numId", "nombreSerie", "tipoSerie")
        }
        payload.update(
            listaEpigrafesConsulta=[payload["nombreSerie"]],
            anioSeleccion="2015",
            mesSeleccion="1",
            listaIdsDistritos=[str(i) for i in range(first, last + 1)],
            listaIdsBarrios=["00 TODOS"],
            listaIdsSecciones=[],
            listaEdades=[str(i) for i in range(90)],
            listaTramos=[],
            listaNacionalidades=["Total"],
            listaSexos=["Total"],
            tiposDato="Valores Absolutos",
            tiposPorcentaje="",
            accionFormulario="consultarDatosBarrio",
            checkDistrito="true",
            checkBarrio="false",
            checkSeccion="false",
            checkEdad="true",
            checkTramo="false",
            checkNacionalidad="false",
            checkSexo="false",
        )
        body = json.dumps(payload).encode()
        with opener.open(
            Request(
                BASE + "detalleSerie.html", body, {"Content-Type": "application/json"}
            ),
            timeout=45,
        ) as response:
            raw = response.read()
            encoding = response.headers.get_content_charset() or "iso-8859-1"
        parsed = json.loads(raw.decode(encoding))
        if parsed.get("status") != "success" or parsed.get("errorTitulo"):
            raise ValueError(f"Incomplete bank response: {parsed.get('errorTitulo')}")
        if len(parsed["listaConsulta"]) != (last - first + 1) * 90:
            raise ValueError("Unexpected monthly control coverage")
        stem = f"districts-{first:02d}-{last:02d}"
        (folder / (stem + ".json.gz")).write_bytes(gzip.compress(raw, mtime=0))
        receipt = dict(
            url=BASE + "detalleSerie.html",
            method="POST",
            request=payload,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            response_encoding=encoding,
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
        )
        (folder / (stem + ".receipt.json")).write_text(
            json.dumps(receipt, indent=2) + "\n"
        )
        print(stem, len(parsed["listaConsulta"]), flush=True)


if __name__ == "__main__":
    main()
