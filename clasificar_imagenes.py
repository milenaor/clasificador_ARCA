#!/usr/bin/env python3
"""
Clasificador de imagenes coloniales - Proyecto ARCA

Toma una carpeta de imagenes, le pide a Claude (vision) que las clasifique
segun el esquema de columnas del proyecto ARCA (usando como referencia el
vocabulario real ya usado en la base de datos existente), y agrega los
resultados a un archivo CSV nuevo listo para revisar e importar.

Uso basico:
    python clasificar_imagenes.py "carpeta_con_imagenes"

Uso con metadatos administrativos conocidos (autor, fecha, titulo, etc.):
    python clasificar_imagenes.py "carpeta_con_imagenes" --metadata metadatos.csv

Ver README.md para mas detalle.
"""

import argparse
import base64
import csv
import json
import os
import sys
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

MODEL_DEFAULT = "claude-sonnet-5"

# Columnas administrativas que NO se pueden deducir de forma confiable solo
# mirando la imagen (autoria, fecha, ubicacion). Se dejan en blanco salvo que
# se provean por --metadata.
COLUMNAS_ADMINISTRATIVAS = [
    "registro",
    "titulo",
    "Fecha",
    "Autores",
    "Técnicas",
    "Ciudad_origen",
    "Pais_origen",
    "Ciudad_actual",
    "Pais_actual",
    "Lugar ubicacion",
]

# Columnas que el modelo SI debe clasificar a partir de la imagen.
COLUMNAS_CLASIFICACION = [
    "Categoria1",
    "Categoria2",
    "Categoria3",
    "Categoria4",
    "Categoria5",
    "Categoria6",
    "Simbolos",
    "Descriptores",
    "Donante",
    "Escenarios",
    "Personajes centrales",
    "Cartela_filacteria",
    "Tipo relato_visual",
    "Tipo_gestual",
    "Objetos personaje central",
    "Complejo_gestual",
    "Fisiognomica",
    "Fisiognomica_imagen",
    "Rostro posición",
    "Gesto1",
    "Gesto2",
    "Gesto3",
    "colectivo",
    "Género",
    "Edad: niñez",
    "Presencia: niños",
    "Edad: adolescencia-juventud",
    "Edad: adulto",
    "Edad: anciano",
    "Personaje: desnudo parcial / total",
    "Personaje: contacto corporal",
    "Presencia: animales",
    "Escena: simple/compuesta",
    "Imagen dentro de la imagen",
    "Personajes: sagrados/profanos",
]

BOOLEAN_FIELD_TO_COLUMN = {
    "edad_ninez": "Edad: niñez",
    "presencia_ninos": "Presencia: niños",
    "edad_adolescencia_juventud": "Edad: adolescencia-juventud",
    "edad_adulto": "Edad: adulto",
    "edad_anciano": "Edad: anciano",
    "desnudo_parcial_total": "Personaje: desnudo parcial / total",
    "contacto_corporal": "Personaje: contacto corporal",
    "presencia_animales": "Presencia: animales",
    "imagen_dentro_de_imagen": "Imagen dentro de la imagen",
}


def load_json(name):
    with open(SCRIPT_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def fieldnames():
    return ["archivo_imagen"] + COLUMNAS_ADMINISTRATIVAS + COLUMNAS_CLASIFICACION + ["notas_para_revision_humana"]


def load_referencias():
    """Carga los 7 archivos de referencia y arma el system prompt. Compartido por CLI y app web."""
    vocab = load_json("vocabularios.json")
    gestos = load_json("gestos.json")
    categoria_tree = load_json("categoria_tree.json")
    personajes = load_json("personajes_conocidos.json")
    simbolos = load_json("simbolos_conocidos.json")
    descriptores = load_json("descriptores_conocidos.json")
    objetos = load_json("objetos_conocidos.json")
    system_prompt = build_system_prompt(
        vocab, gestos, categoria_tree, personajes, simbolos, descriptores, objetos
    )
    return {
        "vocab": vocab,
        "gestos": gestos,
        "categoria_tree": categoria_tree,
        "personajes": personajes,
        "simbolos": simbolos,
        "descriptores": descriptores,
        "objetos": objetos,
        "system_prompt": system_prompt,
    }


def build_categoria_paths(tree, prefix=None):
    """Aplana el arbol de Categoria1..6 en una lista de rutas completas."""
    prefix = prefix or []
    paths = []
    if not tree:
        return [tuple(prefix)]
    for key, sub in tree.items():
        paths.extend(build_categoria_paths(sub, prefix + [key]))
    return paths


def build_system_prompt(vocab, gestos, categoria_tree, personajes, simbolos, descriptores, objetos):
    categoria_paths = build_categoria_paths(categoria_tree)
    # Formato compacto: "Categoria1 > Categoria2 > Categoria3 > ..."
    categoria_lines = "\n".join(
        " > ".join(p) for p in sorted(categoria_paths)
    )

    gesto_lines = "\n".join(f"- {g['gesto']}" for g in gestos)

    top_personajes = "\n".join(f"- {p}" for p in personajes[:400])
    top_simbolos = "\n".join(f"- {s}" for s in simbolos)
    top_descriptores = "\n".join(f"- {d}" for d in descriptores)
    top_objetos = "\n".join(f"- {o}" for o in objetos)

    return f"""Eres un asistente experto en iconografia colonial hispanoamericana (siglos XVI-XIX),
ayudando a catalogar imagenes para el proyecto ARCA (Jaime Borja).

Tu tarea: mirar la imagen de una pintura/grabado colonial y clasificarla segun
el esquema de columnas de la base de datos ARCA, devolviendo un JSON estricto
mediante la herramienta `clasificar_pintura`.

REGLAS GENERALES
- Usa preferentemente los valores de las listas controladas que te doy abajo,
  porque son el vocabulario REAL ya usado en ~27,000 registros de la base de
  datos existente. Reutilizar valores existentes evita duplicados y variantes
  inconsistentes (p.ej. "Agustin" vs "Agustín" vs "San Agustín").
- Solo propon un valor nuevo (fuera de las listas) cuando de verdad no exista
  nada parecido; en ese caso marca el campo `revisar` correspondiente en true
  para que un humano lo confirme.
- Los personajes se listan INDIVIDUALMENTE, nunca agrupados (ej: si aparecen
  "la Virgen y dos angeles" se listan como ["Virgen", "Angel"], no como una
  sola entrada). Excepcion: parejas indisolubles de una misma escena conocida
  (ej. "Judit y Holofernes") pueden ir juntas si asi aparecen en la lista de
  personajes conocidos.
- Si un personaje es un santo y no esta ya en la lista de conocidos con el
  titulo "San/Santa", pon el nombre y el titulo AL FINAL (ej. "Agustín (SAN)"),
  siguiendo la convencion del proyecto.
- Ten en cuenta la DERECHA de la pintura = IZQUIERDA de quien observa, al
  describir gestos o posiciones relativas.
- Los gestos son aproximados; elige el mas cercano de la lista. Si hay un
  gesto claro que no calza con ninguno de la lista, descríbelo en el mismo
  formato ("Accion mano/brazo: sentido") y marca `gesto_revisar` en true.
- Si un campo no aplica a la imagen (p.ej. no hay cartela ni texto alguno),
  usa el valor "Ninguna"/"No aplica" segun corresponda, no lo dejes ambiguo.
- Para las columnas categoricas de Edad, Desnudo, Contacto corporal, Animales
  e "Imagen dentro de la imagen" responde simplemente true/false: el script
  se encarga de traducirlo al formato de la base de datos.
- Escena: simple/compuesta -> "compuesta" si cuenta una historia, es alegorica,
  historiada, o tiene muchos elementos visuales; "simple" en caso contrario.
- No inventes fecha, autor, titulo ni lugar: esos campos los gestiona el
  catalogador aparte y no se te piden aqui.

## Categoria1 > Categoria2 > Categoria3 > Categoria4 > Categoria5 > Categoria6
Elige la ruta EXISTENTE que mejor describa el tema iconografico principal de
la pintura (santo representado, episodio mariologico, pasaje cristologico,
tipo de retrato, etc). No necesitas llenar los 6 niveles: usa tantos como la
ruta existente tenga y deja el resto vacio. Rutas existentes (una por linea,
de mas general a mas especifica):
{categoria_lines}

## Donante (una opcion)
{chr(10).join('- ' + d for d in vocab['donante'])}

## Escenarios (una opcion, la dominante)
{chr(10).join('- ' + e for e in vocab['escenarios'])}

## Tipo relato_visual (una opcion, la mas representativa)
{chr(10).join('- ' + t for t in vocab['tipo_relato_visual'])}

## Tipo_gestual (una opcion)
{chr(10).join('- ' + t for t in vocab['tipo_gestual'])}
("Gesto" = hay gesto corporal significativo; "Objeto" = el sentido se
transmite por un objeto/atributo sin gesto destacable; "Gesto-objeto" = ambos;
"No aplica" = ni gesto ni objeto relevante)

## Complejo_gestual (una opcion)
{chr(10).join('- ' + t for t in vocab['complejo_gestual'])}

## Fisiognomica = postura corporal (una opcion)
{chr(10).join('- ' + t for t in vocab['postura_cuerpo'])}

## Fisiognomica_imagen = encuadre (una opcion)
{chr(10).join('- ' + t for t in vocab['encuadre_imagen'])}

## Rostro posición (una opcion)
{chr(10).join('- ' + t for t in vocab['rostro_posicion'])}

## Cartela_filacteria (una opcion)
{chr(10).join('- ' + t for t in vocab['cartela_filacteria'])}

## Gestos conocidos (Gesto1/Gesto2/Gesto3, hasta 3, en orden de importancia)
{gesto_lines}

## Personajes centrales mas frecuentes en la base (reutiliza si aplica)
{top_personajes}

## Simbolos conocidos (reutiliza si aplica)
{top_simbolos}

## Descriptores conocidos (reutiliza si aplica)
{top_descriptores}

## Objetos de personaje central conocidos (reutiliza si aplica)
{top_objetos}
"""


CLASSIFY_TOOL = {
    "name": "clasificar_pintura",
    "description": "Registra la clasificacion iconografica/formal de una pintura colonial segun el esquema ARCA.",
    "input_schema": {
        "type": "object",
        "properties": {
            "categoria_ruta": {
                "type": "array",
                "items": {"type": "string"},
                "description": "1 a 6 elementos: Categoria1, Categoria2, ... en orden, siguiendo una de las rutas existentes (o nueva si es necesario).",
            },
            "categoria_nueva": {"type": "boolean", "description": "true si la ruta de categoria no existia en la lista y es una propuesta nueva"},
            "simbolos": {"type": "array", "items": {"type": "string"}},
            "descriptores": {"type": "array", "items": {"type": "string"}},
            "donante": {"type": "string"},
            "escenarios": {"type": "array", "items": {"type": "string"}, "description": "normalmente 1 solo valor, dominante"},
            "personajes_centrales": {"type": "array", "items": {"type": "string"}},
            "cartela_filacteria": {"type": "string"},
            "tipo_relato_visual": {"type": "string"},
            "tipo_gestual": {"type": "string"},
            "objetos_personaje_central": {"type": "array", "items": {"type": "string"}},
            "complejo_gestual": {"type": "string"},
            "postura_cuerpo": {"type": "string", "description": "campo Fisiognomica"},
            "encuadre_imagen": {"type": "string", "description": "campo Fisiognomica_imagen"},
            "rostro_posicion": {"type": "string"},
            "gestos": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 3,
                "description": "hasta 3 gestos, en el formato de la lista de gestos conocidos",
            },
            "gesto_revisar": {"type": "boolean"},
            "colectivo": {"type": "string", "enum": ["Personaje colectivo", "Personaje individual", "No aplica"]},
            "genero": {"type": "string", "enum": ["Género masculino", "Género femenino", "Género masculino/femenino", "No aplica"]},
            "edad_ninez": {"type": "boolean"},
            "presencia_ninos": {"type": "boolean"},
            "edad_adolescencia_juventud": {"type": "boolean"},
            "edad_adulto": {"type": "boolean"},
            "edad_anciano": {"type": "boolean"},
            "desnudo_parcial_total": {"type": "boolean"},
            "contacto_corporal": {"type": "boolean"},
            "presencia_animales": {"type": "boolean"},
            "escena_compuesta": {"type": "boolean", "description": "true = 'Escena: compuesta', false = 'Escena: simple'"},
            "imagen_dentro_de_imagen": {"type": "boolean"},
            "personajes_sagrados_profanos": {
                "type": "string",
                "enum": ["Personajes: sagrados", "Personajes: profanos", "Personajes: sagrados y profanos"],
            },
            "notas_para_revision_humana": {
                "type": "string",
                "description": "cualquier duda, ambiguedad o campo de baja confianza que un humano deba revisar",
            },
        },
        "required": [
            "categoria_ruta",
            "donante",
            "escenarios",
            "cartela_filacteria",
            "tipo_relato_visual",
            "tipo_gestual",
            "complejo_gestual",
            "postura_cuerpo",
            "encuadre_imagen",
            "rostro_posicion",
            "colectivo",
            "genero",
            "personajes_sagrados_profanos",
            "escena_compuesta",
        ],
    },
}


def encode_image(path: Path):
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }[path.suffix.lower()]
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return media_type, data


def classify_image(client, model, system_prompt, image_path: Path, max_retries=3):
    media_type, data = encode_image(image_path)
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=2048,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[CLASSIFY_TOOL],
                tool_choice={"type": "tool", "name": "clasificar_pintura"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": data,
                                },
                            },
                            {
                                "type": "text",
                                "text": f"Clasifica esta pintura colonial ({image_path.name}) segun el esquema ARCA.",
                            },
                        ],
                    }
                ],
            )
            for block in resp.content:
                if block.type == "tool_use":
                    return block.input
            raise RuntimeError("La respuesta no incluyo una llamada a la herramienta")
        except Exception as e:  # noqa: BLE001
            last_err = e
            wait = 2 ** attempt
            print(f"  [!] intento {attempt}/{max_retries} fallo ({e}); reintentando en {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"No se pudo clasificar {image_path.name}: {last_err}")


def row_from_result(result: dict) -> dict:
    """Convierte la salida estructurada del modelo al formato de columnas ARCA."""
    row = {}

    ruta = (result.get("categoria_ruta") or [])[:6]
    for i in range(6):
        row[f"Categoria{i+1}"] = ruta[i] if i < len(ruta) else ""

    row["Simbolos"] = ", ".join(result.get("simbolos") or [])
    row["Descriptores"] = ", ".join(result.get("descriptores") or [])
    row["Donante"] = result.get("donante", "")
    row["Escenarios"] = ", ".join(result.get("escenarios") or [])
    row["Personajes centrales"] = ", ".join(result.get("personajes_centrales") or [])
    row["Cartela_filacteria"] = result.get("cartela_filacteria", "")
    row["Tipo relato_visual"] = result.get("tipo_relato_visual", "")
    row["Tipo_gestual"] = result.get("tipo_gestual", "")
    row["Objetos personaje central"] = ", ".join(result.get("objetos_personaje_central") or [])
    row["Complejo_gestual"] = result.get("complejo_gestual", "")
    row["Fisiognomica"] = result.get("postura_cuerpo", "")
    row["Fisiognomica_imagen"] = result.get("encuadre_imagen", "")
    row["Rostro posición"] = result.get("rostro_posicion", "")

    gestos = (result.get("gestos") or [])[:3]
    for i in range(3):
        row[f"Gesto{i+1}"] = gestos[i] if i < len(gestos) else ""

    row["colectivo"] = result.get("colectivo", "")
    row["Género"] = result.get("genero", "")

    for field, column in BOOLEAN_FIELD_TO_COLUMN.items():
        row[column] = column if result.get(field) else ""

    row["Escena: simple/compuesta"] = (
        "Escena: compuesta" if result.get("escena_compuesta") else "Escena: simple"
    )
    row["Personajes: sagrados/profanos"] = result.get("personajes_sagrados_profanos", "")

    return row


def load_metadata(path):
    if not path:
        return {}
    meta = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delim)
        for r in reader:
            key = r.get("archivo_imagen") or r.get("archivo") or r.get("filename")
            if key:
                meta[key.strip()] = r
    return meta


def main():
    parser = argparse.ArgumentParser(description="Clasifica imagenes coloniales segun el esquema ARCA usando Claude (vision).")
    parser.add_argument("carpeta_imagenes", help="Carpeta con las imagenes nuevas a clasificar")
    parser.add_argument("--output", default=None, help="CSV de salida (default: clasificaciones_nuevas.csv junto al script)")
    parser.add_argument("--metadata", default=None, help="CSV opcional con columnas administrativas conocidas (archivo_imagen;registro;titulo;Fecha;Autores;...)")
    parser.add_argument("--model", default=MODEL_DEFAULT, help=f"Modelo Claude a usar (default: {MODEL_DEFAULT})")
    parser.add_argument("--limit", type=int, default=None, help="Procesar solo las primeras N imagenes (para pruebas)")
    parser.add_argument("--dry-run", action="store_true", help="No llama a la API; solo muestra que imagenes se procesarian")
    args = parser.parse_args()

    carpeta = Path(args.carpeta_imagenes)
    if not carpeta.is_dir():
        print(f"No existe la carpeta: {carpeta}")
        sys.exit(1)

    output_path = Path(args.output) if args.output else SCRIPT_DIR / "clasificaciones_nuevas.csv"

    imagenes = sorted(
        p for p in carpeta.iterdir() if p.suffix.lower() in IMG_EXTENSIONS
    )
    if args.limit:
        imagenes = imagenes[: args.limit]

    if not imagenes:
        print("No se encontraron imagenes en la carpeta indicada.")
        sys.exit(0)

    ya_procesadas = set()
    file_exists = output_path.exists()
    if file_exists:
        with open(output_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for r in reader:
                if r.get("archivo_imagen"):
                    ya_procesadas.add(r["archivo_imagen"])

    pendientes = [p for p in imagenes if p.name not in ya_procesadas]
    print(f"{len(imagenes)} imagenes encontradas, {len(pendientes)} pendientes de clasificar.")

    if args.dry_run:
        for p in pendientes:
            print(" -", p.name)
        return

    if not pendientes:
        print("Nada que hacer.")
        return

    system_prompt = load_referencias()["system_prompt"]

    metadata = load_metadata(args.metadata)

    try:
        import anthropic
    except ImportError:
        print("Falta el paquete 'anthropic'. Instala dependencias con:")
        print("    pip install -r requirements.txt")
        sys.exit(1)

    client = anthropic.Anthropic()  # usa ANTHROPIC_API_KEY del entorno

    with open(output_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames(), delimiter=";")
        if not file_exists:
            writer.writeheader()

        for i, img_path in enumerate(pendientes, 1):
            print(f"[{i}/{len(pendientes)}] {img_path.name} ...")
            try:
                result = classify_image(client, args.model, system_prompt, img_path)
            except Exception as e:  # noqa: BLE001
                print(f"  [ERROR] {e}")
                continue

            row = {"archivo_imagen": img_path.name}
            meta_row = metadata.get(img_path.name, {})
            for col in COLUMNAS_ADMINISTRATIVAS:
                row[col] = meta_row.get(col, "")
            row.update(row_from_result(result))
            row["notas_para_revision_humana"] = result.get("notas_para_revision_humana", "")
            if result.get("categoria_nueva"):
                row["notas_para_revision_humana"] = (
                    "[CATEGORIA NUEVA - revisar] " + row["notas_para_revision_humana"]
                )
            if result.get("gesto_revisar"):
                row["notas_para_revision_humana"] = (
                    "[GESTO NO ESTANDAR - revisar] " + row["notas_para_revision_humana"]
                )

            writer.writerow(row)
            f.flush()
            print(f"  OK -> {row.get('Categoria1','')} / {row.get('Tipo relato_visual','')}")

    print(f"\nListo. Resultados en: {output_path}")


if __name__ == "__main__":
    main()
