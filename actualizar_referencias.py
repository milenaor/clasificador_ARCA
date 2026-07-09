#!/usr/bin/env python3
"""
Regenera los archivos de referencia (vocabularios.json, gestos.json,
categoria_tree.json, *_conocidos.json) a partir de la base de datos ARCA
actual. Correr esto de nuevo cuando la base de datos crezca o cambien los
vocabularios, para que el clasificador siga usando valores reales y
actualizados.

Uso:
    python actualizar_referencias.py "ruta/a/Arca exel completo....csv"
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def read_db(path):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(path, encoding=enc, newline="") as f:
                reader = csv.reader(f, delimiter=";")
                header = next(reader)
                rows = list(reader)
            return header, rows
        except UnicodeDecodeError:
            continue
    raise RuntimeError("No se pudo leer el CSV con utf-8-sig ni latin-1")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database_csv", help="CSV completo de la base de datos ARCA (separado por ';')")
    args = parser.parse_args()

    header, rows = read_db(args.database_csv)
    idx = {h: i for i, h in enumerate(header)}

    def col(name):
        i = idx[name]
        return [r[i] for r in rows if len(r) > i]

    def top(name):
        cnt = Counter(v.strip() for v in col(name) if v.strip())
        return [k for k, c in cnt.most_common() if "," not in k]

    vocab = {
        "donante": top("Donante"),
        "escenarios": top("Escenarios"),
        "tipo_relato_visual": top("Tipo relato_visual"),
        "tipo_gestual": top("Tipo_gestual"),
        "complejo_gestual": top("Complejo_gestual"),
        "postura_cuerpo": top("Fisiognomica"),
        "encuadre_imagen": top("Fisiognomica_imagen"),
        "rostro_posicion": top("Rostro posición"),
        "colectivo": ["Personaje colectivo", "Personaje individual", "No aplica"],
        "genero": [
            "Género masculino",
            "Género femenino",
            "Género masculino/femenino",
            "No aplica",
        ],
        "cartela_filacteria": top("Cartela_filacteria"),
        "personajes_sagrados_profanos": [
            "Personajes: sagrados",
            "Personajes: profanos",
            "Personajes: sagrados y profanos",
        ],
        "escena_simple_compuesta": ["Escena: simple", "Escena: compuesta"],
        "columnas_booleanas": {
            "edad_ninez": "Edad: niñez",
            "presencia_ninos": "Presencia: niños",
            "edad_adolescencia_juventud": "Edad: adolescencia-juventud",
            "edad_adulto": "Edad: adulto",
            "edad_anciano": "Edad: anciano",
            "desnudo_parcial_total": "Personaje: desnudo parcial / total",
            "contacto_corporal": "Personaje: contacto corporal",
            "presencia_animales": "Presencia: animales",
            "imagen_dentro_de_imagen": "Imagen dentro de la imagen",
        },
    }
    (SCRIPT_DIR / "vocabularios.json").write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    gestos_cnt = Counter()
    for c in ["Gesto1", "Gesto2", "Gesto3"]:
        gestos_cnt.update(v.strip() for v in col(c) if v.strip())
    EXCLUDE = {"No", "Desconocido", "Múltiples gestos"}
    gestos_list = [
        {"gesto": k, "frecuencia": c}
        for k, c in gestos_cnt.most_common()
        if k not in EXCLUDE
    ]
    (SCRIPT_DIR / "gestos.json").write_text(
        json.dumps(gestos_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    tree = {}
    for r in rows:
        path_vals = [r[idx[f"Categoria{i}"]].strip() for i in range(1, 7)]
        node = tree
        for v in path_vals:
            if not v:
                break
            node = node.setdefault(v, {})
    (SCRIPT_DIR / "categoria_tree.json").write_text(
        json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    for colname, fname in [
        ("Personajes centrales", "personajes_conocidos.json"),
        ("Simbolos", "simbolos_conocidos.json"),
        ("Descriptores", "descriptores_conocidos.json"),
        ("Objetos personaje central", "objetos_conocidos.json"),
    ]:
        cnt = Counter()
        for v in col(colname):
            for part in v.split(","):
                p = part.strip()
                if p:
                    cnt[p] += 1
        data = [k for k, c in cnt.most_common()]
        (SCRIPT_DIR / fname).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    (SCRIPT_DIR / "db_header.json").write_text(
        json.dumps(header, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Referencias actualizadas a partir de {len(rows)} registros.")


if __name__ == "__main__":
    main()
