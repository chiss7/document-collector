"""
OAI-PMH Harvester — Revistas Ecuatorianas de Tecnología
Filtra artículos relacionados con IA y los consolida en un JSON.

Uso:
    pip install httpx
    python oai_harvester.py

    # Solo artículos desde una fecha:
    python oai_harvester.py --from 2023-01-01

    # Guardar en archivo específico:
    python oai_harvester.py --output mis_articulos.json
"""

import argparse
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from time import sleep

import httpx

# ---------------------------------------------------------------------------
# Configuración de revistas
# ---------------------------------------------------------------------------

REVISTAS = [
    {
        "nombre": "GEEKS DECC-Reports (ESPE)",
        "oai_url": "https://journal.espe.edu.ec/ojs/index.php/geeks/oai",
    },
    {
        "nombre": "Maskana (U. Cuenca)",
        "oai_url": "https://publicaciones.ucuenca.edu.ec/ojs/index.php/maskana/oai",
    },
    {
        "nombre": "Investigación, Tecnología e Innovación (U. Guayaquil)",
        "oai_url": "https://revistas.ug.edu.ec/index.php/iti/oai",
    },
    {
        "nombre": "Ingenius (U. Politécnica Salesiana)",
        "oai_url": "https://revistas.ups.edu.ec/index.php/ingenius/oai",
    },
]

# Palabras clave para filtrar artículos de IA
KEYWORDS_IA = [
    "inteligencia artificial",
    "machine learning",
    "aprendizaje automático",
    "aprendizaje profundo",
    "deep learning",
    "red neuronal",
    "neural network",
    "natural language processing",
    "procesamiento de lenguaje natural",
    "computer vision",
    "visión por computadora",
    "clasificación",
    "random forest",
    "support vector",
    "transformer",
    "reinforcement learning",
    "aprendizaje por refuerzo",
    "reconocimiento de patrones",
    "minería de datos",
    "data mining",
    "nlp",
    "llm",
    "chatbot",
    "detección de anomalías",
    "predicción",
    "regresión logística",
]

# Namespaces XML de OAI-PMH
NS = {
    "oai":    "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc":     "http://purl.org/dc/elements/1.1/",
}


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------

@dataclass
class Articulo:
    titulo:   str
    autores:  list[str]
    abstract: str
    fecha:    str
    url:      str
    pdf_url:  str
    formato:  str
    temas:    list[str]
    revista:  str
    keywords_encontradas: list[str]


# ---------------------------------------------------------------------------
# Helpers XML
# ---------------------------------------------------------------------------

def get_all(element, tag: str) -> list[str]:
    """Retorna todos los valores de un tag DC (puede repetirse)."""
    return [
        el.text.strip()
        for el in element.findall(f"dc:{tag}", NS)
        if el.text
    ]


def get_one(element, tag: str) -> str:
    values = get_all(element, tag)
    return values[0] if values else ""


# ---------------------------------------------------------------------------
# Filtro por IA
# ---------------------------------------------------------------------------

def keywords_encontradas(articulo_raw: dict) -> list[str]:
    """Devuelve las keywords de IA que aparecen en el artículo."""
    texto = " ".join([
        articulo_raw.get("titulo", ""),
        articulo_raw.get("abstract", ""),
        " ".join(articulo_raw.get("temas", [])),
    ]).lower()

    return [kw for kw in KEYWORDS_IA if kw.lower() in texto]


# ---------------------------------------------------------------------------
# Harvester OAI-PMH
# ---------------------------------------------------------------------------

def harvest_revista(nombre: str, oai_url: str, from_date: str | None = None) -> list[Articulo]:
    """
    Recorre todos los registros de una revista vía OAI-PMH.
    Maneja paginación con resumptionToken automáticamente.
    """
    print(f"\n{'='*60}")
    print(f"  Harvesting: {nombre}")
    print(f"  URL: {oai_url}")
    print(f"{'='*60}")

    articulos: list[Articulo] = []
    params: dict = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}

    if from_date:
        params["from"] = from_date

    pagina = 1

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        while True:
            print(f"  → Página {pagina}...", end=" ", flush=True)

            try:
                response = client.get(oai_url, params=params)
                response.raise_for_status()
            except httpx.HTTPError as e:
                print(f"ERROR: {e}")
                break

            try:
                root = ET.fromstring(response.text)
            except ET.ParseError as e:
                print(f"ERROR XML: {e}")
                break

            # Verificar errores OAI
            error_el = root.find(".//oai:error", NS)
            if error_el is not None:
                print(f"OAI Error [{error_el.get('code')}]: {error_el.text}")
                break

            records = root.findall(".//oai:record", NS)
            print(f"{len(records)} registros encontrados")

            for record in records:
                # Saltear registros eliminados
                header = record.find("oai:header", NS)
                if header is not None and header.get("status") == "deleted":
                    continue

                dc = record.find(".//oai_dc:dc", NS)
                if dc is None:
                    continue

                # Print DC completo para debugging y ver su estructura
                #print(ET.tostring(dc, encoding='unicode'))

                # dc:identifier puede repetirse (landing page + a veces DOI)
                identifiers = get_all(dc, "identifier")
 
                # dc:relation suele traer la URL directa al galley (PDF) en OJS:
                # .../article/view/{id}/{galley_id}  (sin extensión .pdf)
                relations = get_all(dc, "relation")
 
                def es_galley_pdf(u: str) -> bool:
                    if u.lower().endswith(".pdf"):
                        return True
                    # patrón típico de OJS: .../article/view/123/456
                    partes = u.rstrip("/").split("/")
                    return len(partes) >= 2 and partes[-1].isdigit() and partes[-2].isdigit()
 
                landing_url = next(
                    (u for u in identifiers if not es_galley_pdf(u)),
                    identifiers[0] if identifiers else ""
                )
 
                pdf_candidates = [u for u in (relations + identifiers) if es_galley_pdf(u)]

                raw = {
                    "titulo":   get_one(dc, "title"),
                    "autores":  get_all(dc, "creator"),
                    "abstract": get_one(dc, "description"),
                    "fecha":    get_one(dc, "date"),
                    "url":      landing_url or (identifiers[0] if identifiers else ""),
                    "pdf_url":  pdf_candidates[0] if pdf_candidates else "",
                    "formato":  get_one(dc, "format"),
                    "temas":    get_all(dc, "subject"),
                }

                # Filtrar por IA
                kws = keywords_encontradas(raw)
                if not kws:
                    continue

                articulos.append(Articulo(
                    titulo=raw["titulo"],
                    autores=raw["autores"],
                    abstract=raw["abstract"],
                    fecha=raw["fecha"],
                    url=raw["url"],
                    pdf_url=raw["pdf_url"],
                    formato=raw["formato"],
                    temas=raw["temas"],
                    revista=nombre,
                    keywords_encontradas=kws,
                ))

            # Paginación
            token_el = root.find(".//oai:resumptionToken", NS)
            if token_el is None or not token_el.text:
                break  # No hay más páginas

            # Con resumptionToken no se envían otros params
            params = {"verb": "ListRecords", "resumptionToken": token_el.text}
            pagina += 1
            sleep(1)  # Ser amable con el servidor

    print(f"  ✓ Artículos de IA encontrados: {len(articulos)}")
    return articulos


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="OAI-PMH Harvester — Revistas Ecuador IA")
    parser.add_argument(
        "--from", dest="from_date", default=None,
        help="Fecha de inicio (YYYY-MM-DD). Ej: --from 2023-01-01"
    )
    parser.add_argument(
        "--output", default="articulos_ia_ecuador.json",
        help="Archivo de salida JSON (default: articulos_ia_ecuador.json)"
    )
    parser.add_argument(
        "--last-harvest", action="store_true",
        help="Usar la última fecha de harvest guardada (incremental)"
    )
    args = parser.parse_args()

    # Modo incremental: leer última fecha de harvest
    harvest_state_file = Path(".harvest_state.json")
    from_date = args.from_date

    if args.last_harvest and harvest_state_file.exists():
        state = json.loads(harvest_state_file.read_text())
        from_date = state.get("last_date")
        print(f"Modo incremental: harvesting desde {from_date}")

    # Harvest todas las revistas
    todos: list[Articulo] = []
    for revista in REVISTAS:
        articulos = harvest_revista(
            nombre=revista["nombre"],
            oai_url=revista["oai_url"],
            from_date=from_date,
        )
        todos.extend(articulos)
        sleep(2)  # Pausa entre revistas

    # Deduplicar por URL
    vistos: set[str] = set()
    sin_duplicados: list[Articulo] = []
    for a in todos:
        key = a.url or a.titulo
        if key not in vistos:
            vistos.add(key)
            sin_duplicados.append(a)

    # Ordenar por fecha descendente
    sin_duplicados.sort(key=lambda a: a.fecha or "", reverse=True)

    # Guardar JSON
    output_path = Path(args.output)
    output_data = {
        "generado": str(date.today()),
        "from_date": from_date,
        "total": len(sin_duplicados),
        "por_revista": {
            r["nombre"]: sum(1 for a in sin_duplicados if a.revista == r["nombre"])
            for r in REVISTAS
        },
        "articulos": [asdict(a) for a in sin_duplicados],
    }

    output_path.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Guardar estado para próximo harvest incremental
    harvest_state_file.write_text(
        json.dumps({"last_date": str(date.today())})
    )

    # Resumen
    print(f"\n{'='*60}")
    print(f"  RESUMEN")
    print(f"{'='*60}")
    print(f"  Total artículos de IA: {len(sin_duplicados)}")
    for revista in REVISTAS:
        count = output_data["por_revista"][revista["nombre"]]
        print(f"  · {revista['nombre']}: {count}")
    print(f"\n  Guardado en: {output_path.resolve()}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
