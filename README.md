# Clasificador de imagenes coloniales - Proyecto ARCA

Herramienta que usa Claude (con vision) para sugerir la clasificacion
iconografica de pinturas/grabados coloniales nuevos, siguiendo el esquema de
columnas de la base de datos ARCA. Genera un CSV nuevo con los resultados,
listo para revisar y luego sumar a la base de datos real.

Hay dos formas de usarla:

- **Interfaz web** (`app.py` + `index.html`) — recomendada para uso normal:
  arrastras imagenes en el navegador, revisas/editas cada campo sugerido, y
  guardas. Ver seccion "Interfaz web" abajo.
- **Linea de comandos** (`clasificar_imagenes.py`) — para procesar una
  carpeta entera de golpe sin revisión interactiva. Ver seccion "Linea de
  comandos" abajo.

Ambas comparten los mismos archivos de referencia (vocabularios, gestos,
arbol de categorias) y escriben al mismo formato de CSV de salida.

## Que hace y que NO hace

- SI clasifica, a partir de la imagen: Categoria1-6, Simbolos, Descriptores,
  Donante, Escenarios, Personajes centrales, Cartela_filacteria, Tipo
  relato_visual, Tipo_gestual, Objetos personaje central, Complejo_gestual,
  Fisiognomica (postura), Fisiognomica_imagen (encuadre), Rostro posicion,
  Gesto1-3, colectivo, Genero, las columnas de Edad/Presencia/Contacto/
  Desnudo/Animales, Escena simple/compuesta, Imagen dentro de la imagen, y
  Personajes sagrados/profanos.
- NO inventa: registro, titulo, Fecha, Autores, Tecnicas, Ciudad_origen,
  Pais_origen, Ciudad_actual, Pais_actual, Lugar ubicacion. Estos campos
  administrativos requieren investigacion documental (autoria, procedencia)
  que no se puede deducir de forma confiable solo mirando la imagen — la
  guia del proyecto es explicita en que la fecha, por ejemplo, depende de
  la actividad conocida del autor. Si ya conoces estos datos para las
  imagenes nuevas, pasalos con `--metadata` (ver abajo) y se incluyen tal
  cual en el CSV de salida.
- Es un asistente, no un reemplazo del catalogador. Los resultados deben
  revisarse antes de incorporarse a la base de datos definitiva — por eso
  el script NUNCA escribe directamente sobre
  `Arca exel completo mayo 2026 (1).csv`, sino que crea un archivo nuevo
  (`clasificaciones_nuevas.csv`) para revision manual y posterior copiado/
  importacion.

## Como esta fundamentado el clasificador

En vez de basarse solo en la guia (`GUIA PROYECT0 ARCA.pdf`), que describe
los criterios pero no siempre define listas cerradas, este clasificador usa
el vocabulario REAL ya usado en los ~27,000 registros existentes de
`Arca exel completo mayo 2026 (1).csv`. Esto se extrajo a archivos de
referencia:

- `vocabularios.json` — listas controladas reales (Donante, Escenarios,
  Tipo relato_visual, posturas, encuadres, etc.)
- `categoria_tree.json` — el arbol completo de rutas Categoria1 > ... >
  Categoria6 ya usadas (894 rutas unicas), para que el modelo reutilice
  categorias existentes en vez de inventar nuevas.
- `gestos.json` — los ~200 gestos ya catalogados en Gesto1/2/3, con su
  frecuencia de uso.
- `personajes_conocidos.json`, `simbolos_conocidos.json`,
  `descriptores_conocidos.json`, `objetos_conocidos.json` — listas de
  valores ya usados en esos campos abiertos, para fomentar reutilizacion
  y evitar duplicados/variantes (ej. "Agustin" vs "San Agustin").

Si la base de datos crece o cambia el vocabulario, podes regenerar estos
archivos corriendo:

```
python actualizar_referencias.py "ruta/a/Arca exel completo mayo 2026 (1).csv"
```

## Instalacion

1. Python 3.10+ (ya tenes 3.13 instalado).
2. Instalar dependencias:
   ```
   pip install -r requirements.txt
   ```
3. Configurar tu API key de Anthropic (https://console.anthropic.com/) como
   variable de entorno. En PowerShell:
   ```
   $env:ANTHROPIC_API_KEY = "tu-api-key-aqui"
   ```
   (para que quede permanente entre sesiones, agregala a las variables de
   entorno de usuario de Windows en vez de escribirla cada vez)

## Interfaz web

1. Instala dependencias (ver "Instalacion" arriba). No hace falta configurar
   la API key por variable de entorno para usar la interfaz web: se pega
   directamente en la pagina (paso 4).
2. Arranca el servidor local:
   ```
   python app.py
   ```
3. Abri http://127.0.0.1:5000 en tu navegador (Chrome, Edge, Firefox).
4. En la barra debajo del titulo, pega tu API key de Anthropic
   (`sk-ant-...`) y apreta "Guardar key". Queda guardada en la memoria de
   este servidor (no se escribe a disco) y en el `localStorage` de tu
   navegador, para que no tengas que pegarla de nuevo la proxima vez que
   abras la pagina (aunque reinicies `python app.py`). "Borrar" la quita de
   ambos lugares.
5. Arrastra una o varias imagenes al recuadro, o hace click para elegirlas
   desde el explorador de archivos.
5. Cada imagen se clasifica automaticamente al cargarla (se ve "Clasificando...").
   Cuando termina, hace click en "ver/editar campos" para revisar y corregir
   lo que sugirio la IA (categorias, simbolos, gestos, edades, etc.) y
   completar a mano los metadatos administrativos (titulo, autor, fecha,
   lugar) si los conoces.
6. Cuando estés conforme, apreta "Guardar" en esa tarjeta, o "Guardar listas"
   arriba para guardar todas las que ya terminaron de clasificarse de una vez.
7. Los resultados guardados van a `clasificaciones_nuevas.csv` (mismo formato
   que la version de linea de comandos) y las imagenes originales se copian a
   la carpeta `imagenes_procesadas/`.
8. Para cerrar el servidor, volve a la ventana de PowerShell donde lo
   arrancaste y apreta `Ctrl+C`.

La app queda corriendo solo en tu maquina (127.0.0.1 = localhost); nadie mas
en la red puede acceder a ella ni a tu API key.

## Linea de comandos

Clasificar todas las imagenes nuevas de una carpeta:

```
python clasificar_imagenes.py "C:\ruta\a\imagenes_nuevas"
```

Esto crea/actualiza `clasificaciones_nuevas.csv` en esta misma carpeta, con
una fila por imagen. Si volves a correr el script sobre la misma carpeta,
las imagenes que ya aparecen en `clasificaciones_nuevas.csv` se saltan
automaticamente (no se reprocesan ni se duplican).

Opciones utiles:

```
--output ruta.csv       Cambia donde se guardan los resultados
--metadata meta.csv      CSV con columnas administrativas conocidas (ver abajo)
--model claude-sonnet-5  Cambia el modelo (default: claude-sonnet-5)
--limit 5                Procesa solo las primeras 5 imagenes (para probar)
--dry-run                Solo lista que imagenes se procesarian, sin llamar a la API
```

### Metadatos administrativos conocidos

Si ya sabes el titulo, autor, fecha o lugar de las imagenes nuevas, crea un
CSV (separado por `;` o `,`) con una columna `archivo_imagen` que coincida
con el nombre de archivo de la imagen, mas las columnas que quieras
completar (`registro`, `titulo`, `Fecha`, `Autores`, `Técnicas`,
`Ciudad_origen`, `Pais_origen`, `Ciudad_actual`, `Pais_actual`,
`Lugar ubicacion`), y pasalo con `--metadata`:

```
python clasificar_imagenes.py "carpeta" --metadata metadatos.csv
```

Estos valores se copian tal cual al CSV de salida; el script no los valida
ni corrige.

## Despues de clasificar: revision e incorporacion a la base de datos

1. Abrir `clasificaciones_nuevas.csv` (en Excel, cuidando que abra con
   delimitador `;`) y revisar fila por fila, en particular:
   - Filas con notas en `notas_para_revision_humana` (el modelo marca ahi
     categorias nuevas, gestos no estandar, o cualquier duda).
   - Personajes centrales, Simbolos, Descriptores: confirmar que no haya
     duplicados de personajes/simbolos ya existentes con otro nombre.
   - Fechas/autor/titulo si no se paso `--metadata`.
2. Una vez revisado, copiar las filas aprobadas dentro de
   `Arca exel completo mayo 2026 (1).csv` (o del sistema que uses para
   importar a ARCA/Omeka), asignando el numero de `registro` correspondiente.
3. Opcional: correr `actualizar_referencias.py` de nuevo para que las
   proximas clasificaciones incluyan estas nuevas entradas como referencia.

## Limitaciones conocidas

- Los gestos historicos (chironomia, gestos de manos/dedos) son sutiles y
  a veces ambiguos incluso para un experto humano; el modelo hace su mejor
  esfuerzo pero puede marcar `gesto_revisar`. Revisa siempre Gesto1/2/3.
- La ruta de Categoria1-6 se elige de entre las 894 rutas ya existentes en
  la base; si la pintura trata un tema genuinamente nuevo, el modelo puede
  proponer una ruta nueva marcando `categoria_nueva` — confirma manualmente
  antes de darla por buena.
- El costo y tiempo de procesamiento dependen del numero de imagenes y del
  modelo elegido. Para tandas grandes, correr primero con `--limit 5` para
  revisar la calidad antes de procesar todo.
