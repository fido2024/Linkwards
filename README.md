# Pre-experimento: Objetivo Específico 2

Prueba rápida del modelo heurístico que, ante un enlace migrado, genera un conjunto
acotado de páginas candidatas y las ordena para identificar el recurso de reemplazo.

Proyecto: Sistema para la Detección de Disponibilidad, Migración de Dominio e
Inactividad en Colecciones Personales de Enlaces Web.
Taller de Grado I, UMSS. Autor: Vasquez Carata Fidel.

## Pregunta que responde
¿Un modelo basado en distancias de cadenas, metadatos y reglas de proximidad ubica el
recurso de reemplazo correcto entre los primeros resultados de un conjunto acotado
de candidatos?

## Preparar el entorno (PowerShell en Windows)

Desde la carpeta del proyecto:

```bash
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Si PowerShell bloquea la activación, puede ejecutar los comandos sin activar el
entorno: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` y
`.\.venv\Scripts\python.exe -m unittest discover -s tests`.

## Fase implementada: metadatos del Internet Archive

Para consultar una URL individual:

```powershell
python -c "from src.metadatos import obtener_metadatos; print(obtener_metadatos('example.org', verbose=True))"
```

El módulo consulta primero la Wayback Availability API. Si la captura más
cercana no puede recuperarse o no contiene metadatos útiles, busca capturas
HTML anteriores mediante CDX. La extracción recupera título, descripción y un
fragmento de texto. Las respuestas correctas se guardan en `datos/cache/`.
Hay tiempos máximos de espera y reintentos; no se requiere clave de búsqueda.

Pruebas locales (no hacen solicitudes de red):

```powershell
python -m unittest discover -s tests -v
```

Demostración en vivo de los dos casos (requiere Internet):

```powershell
python -m src.demostrar_metadatos
```

La demostración usa una caché temporal y guarda la respuesta observada en
`resultados/demostracion_metadatos.json`, sin reemplazar el contenido de
`datos/cache/`. Para repetirla, vuelve a ejecutar el mismo comando. En la
ejecución registrada en ese archivo, `example.org` devolvió una captura con
título `Example Domain` y texto extraído; `linkwards-no-such-host.invalid` no
tuvo captura y no produjo metadatos. Son resultados de una consulta real, no
datos simulados; pueden cambiar si Internet Archive cambia sus capturas.

## Fase de generación de candidatos (Tavily)

El módulo recibe el diccionario producido por `obtener_metadatos` y, por
defecto, crea una consulta con el título más el nombre del sitio viejo (modo
`titulo+dominio`). También admite `titulo` y `titulo+texto`. Pide hasta
10 resultados, valida que cada URL use HTTP o HTTPS, quita duplicados exactos
tras normalizar esquema, host y puerto estándar, y conserva rutas o parámetros
diferentes. No se puntúan ni reordenan resultados en esta fase.

La clave se puede definir en la sesión de PowerShell o guardar como
`TAVILY_API_KEY=tvly-...` en `.env` en la raíz del proyecto. Para definirla en
la sesión actual:

```powershell
$env:TAVILY_API_KEY = "tvly-..."
```

`.env` está excluido por `.gitignore`; no publiques esa clave.

Para repetir la búsqueda real de demostración:

```powershell
python -m src.demostrar_candidatos
```

Lee los metadatos archivados de ShareLaTeX, consulta Tavily si no existe una
entrada de caché para la consulta y guarda la salida observada en
`resultados/demostracion_candidatos.json`. El archivo no contiene la clave.
Para ejecutar la fase con los enlaces del CSV:

```powershell
python -m src.candidatos
# Selección explícita del modo
python -m src.candidatos --modo titulo
python -m src.candidatos --modo titulo+texto
python -m src.candidatos --modo titulo+dominio
```

Las respuestas de búsqueda, incluso una lista vacía, se guardan en
`datos/cache/`; una consulta cacheada no vuelve a llamar a Tavily. Los errores
de red y HTTP 5xx, y los 429, se reintentan hasta tres veces con timeout de 30
segundos. Las pruebas de `src.candidatos` usan respuestas simuladas y no
consumen créditos. La demostración real registrada obtuvo 10 URLs válidas y
únicas; la lista exacta está en el JSON enlazado arriba. `MAX_CANDIDATOS` es 10,
dentro del máximo de 20 resultados de la [referencia oficial de Tavily](https://docs.tavily.com/documentation/api-reference/endpoint/search).

## Fase 4: puntuación y ordenamiento heurístico

`puntuar_candidato(original, candidato, metadatos)` devuelve una nota de 0 a
100. No es una probabilidad estadística. Los valores predeterminados están en
`src/puntuacion.py` y suman 1:

| Componente | Peso | Cálculo |
| --- | ---: | --- |
| Dominio | 0.45 | `rapidfuzz.fuzz.ratio` entre los hosts normalizados (sin `www` ni rutas). |
| Título | 0.35 | `rapidfuzz.fuzz.ratio` entre título histórico y título del candidato, si ambos existen. |
| Proximidad | 0.20 | Señales de nombre del sitio (60%) y similitud de ruta (40%); las señales ausentes se renormalizan dentro de este componente. |

Los componentes que no se pueden calcular se omiten y los pesos disponibles
se renormalizan en el promedio final. Así, un título ausente no aporta una
coincidencia perfecta. La comparación de rutas se mantiene separada de la de
dominios. `ordenar_candidatos(original, candidatos, metadatos)` devuelve copias
de los candidatos, agrega `puntuacion` y los ordena de mayor a menor; conserva
el orden original en empates y no elimina duplicados (esa tarea ya corresponde
a la generación de candidatos).

Ejecuta todas las pruebas, incluidas las de puntuación, sin hacer llamadas a
Tavily o Internet Archive:

```powershell
python -m unittest discover -s tests -v
```

Para volver a puntuar los candidatos guardados en la demostración de Tavily
(requiere que los metadatos de ShareLaTeX estén en la caché de `datos/cache/`):

```powershell
python -c "import json; from src.metadatos import obtener_metadatos; from src.puntuacion import ordenar_candidatos; d=json.load(open('resultados/demostracion_candidatos.json',encoding='utf-8')); m=obtener_metadatos(d['url_historica']); r=ordenar_candidatos(d['url_historica'],d['candidatos'],m); print(chr(10).join(str((x['puntuacion'],x['url'])) for x in r))"
```

## Fase 5: evaluación experimental

Ejecuta la evaluación del CSV desde PowerShell:

```powershell
python -m src.evaluacion
```

Por defecto usa solo cachés y no llama a Wayback ni a Tavily. El modo predeterminado
es `titulo+dominio`; admite `titulo` y `titulo+texto`. Guarda detalle y resumen
en nombres que incluyen modo y variante, como
`resultados/evaluacion_titulo_mas_dominio_rapidfuzz.csv`. Si faltan
cachés, los registros se marcan como pendientes y se excluyen del denominador
de métricas; una lista de candidatos vacía sí cuenta como evaluada y como fallo.

Las tasas Top-1, Top-5 y cobertura usan como denominador los registros con URLs
utilizables, metadatos y una respuesta de candidatos disponible (incluidas las
respuestas vacías). Los errores, metadatos ausentes, cachés ausentes y filas
incompletas se informan aparte, no como aciertos ni como ausencia observada del
enlace correcto. La comparación base usa el primer resultado válido del
buscador; la comparación heurística usa el primero después de ordenar.

Para permitir explícitamente búsquedas donde no haya caché:

```powershell
python -m src.evaluacion --buscar-faltantes
```

Ese modo puede consultar Internet Archive y Tavily, y Tavily puede consumir
créditos. Para cada registro sin caché se hace una búsqueda lógica. El cliente
de Tavily puede repetir una petición hasta tres intentos ante errores de red,
HTTP 429 o 5xx; por ello, cinco registros pendientes pueden producir hasta 15
peticiones HTTP. Las pruebas unitarias de evaluación usan candidatos simulados
en carpetas temporales y no realizan conexiones externas.

Para comparar los tres modos con Levenshtein y permitir consultas de Tavily
solo cuando la caché de ese modo no exista:

```powershell
python -m src.evaluacion --modo titulo --variante levenshtein --buscar-faltantes
python -m src.evaluacion --modo titulo+dominio --variante levenshtein --buscar-faltantes
python -m src.evaluacion --modo titulo+texto --variante levenshtein --buscar-faltantes
```

Los archivos se nombran `evaluacion_{modo}_levenshtein.csv` y `.json` (el signo
`+` del modo se representa como `_mas_`). La caché se separa por consulta/modo;
una respuesta existente se reutiliza sin volver a consultar Tavily.

### Ejecución real registrada con caché y búsquedas faltantes

El 2026-10-23 se ejecutó `python -m src.evaluacion --buscar-faltantes`. Antes
de ejecutarlo, había seis filas con URLs utilizables, metadatos en caché,
candidatos para el ID 2 y faltaban candidatos para los IDs 1, 3, 4, 5 y 6.
La clave de Tavily estaba configurada y el servicio aceptó las búsquedas. No se
registra ni se imprime el secreto. Se guardaron los resultados obtenidos en la
caché; la evaluación terminó con seis registros evaluables y cero errores.

| Métrica | Orden original del buscador | Después del reordenamiento |
| --- | ---: | ---: |
| Top-1 | 0/6 (0 %) | 2/6 (33,3 %) |
| Top-5 | 2/6 (33,3 %) | 2/6 (33,3 %) |
| Cobertura de la URL correcta entre candidatos | 2/6 (33,3 %) | 2/6 (33,3 %) |

La URL correcta faltó en 4/6 registros (IDs 2, 3, 5 y 6). En los otros dos
casos sí estaba en la lista: el buscador la ubicó en posiciones 3 (ID 1) y 2
(ID 4), y el reordenamiento la colocó en posición 1 en ambos. Entre los seis
registros, el heurístico cambió el primer candidato en 6/6 casos. Esto muestra
una mejora de Top-1 en este conjunto pequeño, sin cambio en Top-5; la cobertura
limitada a 2/6 y el tamaño de muestra no permiten afirmar que el método mejore
el buscador de forma general. Los registros de salida están en
`resultados/evaluacion_candidatos.csv` y `.json`.

El CSV usa punto y coma o coma; el lector detecta ambos. Las columnas previstas
son `url_vieja`, `url_nueva_correcta` y `tipo_cambio` (el conjunto actual además
tiene `id` y `notas`). No reemplazar el conjunto con filas ficticias.

## Estructura
- `datos/enlaces.csv`: conjunto de prueba (URL vieja, URL nueva correcta, tipo de cambio).
- `datos/cache/`: respuestas guardadas del Internet Archive y del buscador.
- `src/metadatos.py`: Fase 2, recuperación de título y texto desde el Internet Archive.
- `src/demostrar_metadatos.py`: demostración reproducible con un caso con captura y otro sin ella.
- `src/candidatos.py`: Fase 3, generación acotada de candidatos (top 10).
- `src/demostrar_candidatos.py`: consulta real reproducible y salida de demostración sin secretos.
- `src/puntuacion.py`: Fase 4, puntuación heurística y ordenamiento.
- `src/evaluacion.py`: Fase 5, comparación Top-1, Top-5, cobertura, cambio del primer resultado y tiempo.
- `resultados/`: tablas generadas por la evaluación.

## Alcance
Las fases de metadatos, generación de candidatos, puntuación heurística y
evaluación experimental están implementadas. La evaluación actual es pequeña y
exploratoria; no equivale a una validación estadística general.

## Interfaz web del prototipo

Streamlit está incluido en `requirements.txt`. Desde PowerShell, instala las
dependencias y arranca la interfaz local:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

O, sin activar el entorno virtual:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

La búsqueda empieza únicamente al pulsar **Recuperar URL**. El proceso usa
`obtener_metadatos`, `generar_candidatos` y `ordenar_candidatos`; por tanto,
conserva las cachés existentes. Si no hay candidatos cacheados, la generación
puede llamar a Tavily y consumir créditos. La clave se lee de
`TAVILY_API_KEY` o `.env`, no se solicita ni se presenta en la interfaz.

La sección de evaluación lee `resultados/evaluacion_candidatos.json` sin
ejecutar la evaluación ni recalcular sus métricas. Los denominadores y el
resumen de cobertura ausente se presentan junto a Top-1 y Top-5. La puntuación
de cada candidato es heurística, no una probabilidad estadística.

## Variante Levenshtein para comparación

La línea base sigue siendo `rapidfuzz.fuzz.ratio`. Para una evaluación
comparativa local que reutiliza únicamente metadatos y candidatos cacheados,
ejecuta desde PowerShell:

```powershell
python -m src.evaluacion --variante levenshtein --resultados resultados
```

La variante usa `rapidfuzz.distance.Levenshtein.distance` y convierte la
distancia en similitud con `100 * (1 - distancia / max(longitud_a,
longitud_b))`. Si ambas cadenas están vacías, la función devuelve 100; si solo
una está vacía, devuelve 0. En el cálculo de puntuación, los datos vacíos se
omiten y los pesos disponibles se renormalizan, igual que en la línea base.
Ambas variantes conservan los pesos y reglas de proximidad actuales.

La ejecución normal es cache-only: no usar `--buscar-faltantes` para esta
comparación. Los resultados anteriores de Levenshtein se conservan; las nuevas
salidas incluyen el modo en el nombre. Los archivos
`resultados/evaluacion_candidatos.csv` y `.json` permanecen como línea base de
la interfaz y de la evaluación inicial.
