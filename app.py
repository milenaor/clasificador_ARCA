#!/usr/bin/env python3
"""
Interfaz web local del clasificador de imagenes coloniales - Proyecto ARCA.

Corre un servidor local (Flask) que sirve una pagina HTML donde podes
arrastrar/soltar imagenes, ver la clasificacion sugerida por Claude, editarla,
y guardarla en clasificaciones_nuevas.csv.

Uso:
    python app.py

Despues abri http://127.0.0.1:5000 en el navegador.
"""

import csv
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import clasificar_imagenes as ci

SCRIPT_DIR = Path(__file__).resolve().parent
IMAGES_DIR = SCRIPT_DIR / "imagenes_procesadas"
IMAGES_DIR.mkdir(exist_ok=True)
OUTPUT_CSV = SCRIPT_DIR / "clasificaciones_nuevas.csv"

app = Flask(__name__)

_REF = None  # se carga perezosamente (lazy) en el primer request
_RUNTIME_API_KEY = None  # pegada desde la interfaz; solo vive en memoria de este proceso


def get_referencias():
    global _REF
    if _REF is None:
        _REF = ci.load_referencias()
    return _REF


def get_api_key():
    return _RUNTIME_API_KEY or os.environ.get("ANTHROPIC_API_KEY")


def ya_clasificadas():
    nombres = set()
    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for r in reader:
                if r.get("archivo_imagen"):
                    nombres.add(r["archivo_imagen"])
    return nombres


@app.get("/")
def index():
    html = (SCRIPT_DIR / "index.html").read_text(encoding="utf-8")
    return app.response_class(html, mimetype="text/html")


@app.get("/api/status")
def status():
    return jsonify(
        {
            "api_key_configurada": bool(get_api_key()),
            "ya_clasificadas": sorted(ya_clasificadas()),
            "output_csv": str(OUTPUT_CSV),
        }
    )


@app.post("/api/config")
def config():
    global _RUNTIME_API_KEY
    payload = request.get_json(force=True) or {}
    key = (payload.get("api_key") or "").strip()
    _RUNTIME_API_KEY = key or None
    return jsonify({"ok": True, "api_key_configurada": bool(get_api_key())})


@app.get("/api/vocab")
def vocab():
    ref = get_referencias()
    return jsonify(
        {
            "vocab": ref["vocab"],
            "gestos": [g["gesto"] for g in ref["gestos"]],
            "categoria1": sorted({p[0] for p in ci.build_categoria_paths(ref["categoria_tree"]) if p}),
            "personajes": ref["personajes"],
            "simbolos": ref["simbolos"],
            "descriptores": ref["descriptores"],
            "objetos": ref["objetos"],
            "columnas_administrativas": ci.COLUMNAS_ADMINISTRATIVAS,
        }
    )


@app.post("/api/clasificar")
def clasificar():
    if "imagen" not in request.files:
        return jsonify({"error": "no se recibio ninguna imagen"}), 400
    file = request.files["imagen"]
    filename = file.filename
    ext = Path(filename).suffix.lower()
    if ext not in ci.IMG_EXTENSIONS:
        return jsonify({"error": f"extension no soportada: {ext}"}), 400

    dest = IMAGES_DIR / filename
    file.save(dest)

    try:
        import anthropic
    except ImportError:
        return jsonify({"error": "Falta el paquete 'anthropic'. Corre: pip install -r requirements.txt"}), 500

    api_key = get_api_key()
    if not api_key:
        return jsonify({"error": "Todavia no pegaste tu API key de Anthropic (arriba, en la barra de estado)"}), 400

    ref = get_referencias()
    client = anthropic.Anthropic(api_key=api_key)
    try:
        result = ci.classify_image(client, ci.MODEL_DEFAULT, ref["system_prompt"], dest)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500

    row = {"archivo_imagen": filename}
    for col in ci.COLUMNAS_ADMINISTRATIVAS:
        row[col] = ""
    row.update(ci.row_from_result(result))
    notas = result.get("notas_para_revision_humana", "") or ""
    if result.get("categoria_nueva"):
        notas = "[CATEGORIA NUEVA - revisar] " + notas
    if result.get("gesto_revisar"):
        notas = "[GESTO NO ESTANDAR - revisar] " + notas
    row["notas_para_revision_humana"] = notas

    return jsonify({"row": row})


@app.post("/api/guardar")
def guardar():
    payload = request.get_json(force=True)
    rows = payload.get("rows") or []
    if not rows:
        return jsonify({"error": "no se recibieron filas"}), 400

    fieldnames = ci.fieldnames()
    file_exists = OUTPUT_CSV.exists()
    with open(OUTPUT_CSV, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    return jsonify({"ok": True, "guardadas": len(rows)})


@app.get("/imagenes_procesadas/<path:filename>")
def servir_imagen(filename):
    return send_from_directory(IMAGES_DIR, filename)


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[!] ANTHROPIC_API_KEY no esta configurada como variable de entorno.")
        print("    Podes pegarla directamente en la pagina web cuando la abras.")
    print("Abri http://127.0.0.1:5000 en tu navegador")
    app.run(debug=True, port=5000)
