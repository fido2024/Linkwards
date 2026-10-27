# Linkwards — preexperimento

Preexperimento académico para estudiar si un modelo heurístico puede recuperar la posible ubicación actual de enlaces web antiguos. Linkwards recupera metadatos históricos, genera un conjunto acotado de candidatos y los ordena con una puntuación heurística. La puntuación es un indicador de similitud, no una probabilidad estadística.

Proyecto: Sistema para la Detección de Disponibilidad, Migración de Dominio e Inactividad en Colecciones Personales de Enlaces Web. Taller de Grado I, UMSS. Autor: Vasquez Carata Fidel.

## Arquitectura

- **Núcleo experimental:** `src/metadatos.py` consulta capturas de Internet Archive y extrae metadatos; `src/candidatos.py` construye consultas y genera candidatos con Tavily; `src/puntuacion.py` puntúa y ordena candidatos; `src/evaluacion.py` evalúa el ordenamiento contra las URL etiquetadas; `src/datos.py` lee el conjunto de enlaces y normaliza dominios.
- **Interfaz:** `app.py` inicia la aplicación Streamlit; `src/interfaz.py` contiene la lógica de presentación y conecta la interfaz con los módulos del núcleo.
- **Demostraciones y verificación:** `src/demostrar_metadatos.py` demuestra la consulta de metadatos; `src/demostrar_candidatos.py` demuestra la generación de candidatos; `src/verificar_enlaces.py` comprueba enlaces del conjunto y su disponibilidad actual.
- **Pruebas:** `tests/` contiene pruebas automatizadas de metadatos, candidatos, puntuación, evaluación e interfaz.
- **Datos y resultados:** `datos/enlaces.csv` contiene los registros etiquetados; `datos/cache/` guarda respuestas locales; `resultados/` contiene informes y salidas de demostración/verificación.

## Núcleo y apoyo

El núcleo del pre-experimento está formado por `src/metadatos.py`, `src/candidatos.py`, `src/puntuacion.py`, `src/evaluacion.py` y `src/datos.py`: recupera metadatos, genera y ordena candidatos, y mide el resultado sobre el conjunto experimental. `datos/enlaces.csv` es el conjunto etiquetado de seis enlaces.

`main.py` es el punto de entrada principal para la evaluación por lotes. `app.py` presenta la demostración interactiva; `src/interfaz.py` coordina la lógica que usa esa página. `src/demostrar_metadatos.py`, `src/demostrar_candidatos.py` y `src/verificar_enlaces.py` son utilidades de demostración o verificación. `tests/` comprueba el comportamiento con datos simulados.

## Entorno en Windows PowerShell

Desde la carpeta raíz del proyecto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Si PowerShell impide activar el entorno, usa directamente el intérprete del entorno:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Puntos de entrada

### Evaluación por lotes con configuración predeterminada

```powershell
python main.py
```

`main.py` evalúa `datos/enlaces.csv` en la carpeta `resultados/`, imprime el modo y la variante al inicio y usa `titulo+dominio` con Levenshtein. La ejecución es cache-only: si faltan cachés, esos registros se informan como pendientes y no se buscan automáticamente.

### Evaluación con opciones de línea de comandos

```powershell
python -m src.evaluacion --help
```

Las opciones confirmadas en el parser son:

- `--csv`: CSV de entrada; predeterminado `datos/enlaces.csv`.
- `--resultados`: carpeta de salida; predeterminada `resultados`.
- `--variante`: `levenshtein` (predeterminada) o `rapidfuzz`.
- `--modo`: `titulo` (solo título), `titulo+dominio` (predeterminado) o `titulo+texto`.
- `--buscar-faltantes`: permite consultar Internet Archive o Tavily si falta una respuesta cacheada. Puede generar tráfico externo y consumir créditos de Tavily.

Comando exacto para reproducir la evaluación de referencia con las cachés disponibles (no activa búsquedas faltantes):

```powershell
python -m src.evaluacion --modo titulo+dominio --variante levenshtein
```

RapidFuzz sigue disponible si se selecciona explícitamente. Añadir `--buscar-faltantes` permite completar cachés y puede realizar solicitudes externas:

```powershell
python -m src.evaluacion --modo titulo+dominio --variante rapidfuzz --buscar-faltantes
```

La evaluación escribe archivos de salida con nombres derivados del modo y variante, por ejemplo `evaluacion_titulo_mas_dominio_rapidfuzz.csv` y `.json`. Evita ejecutar evaluaciones sobre una carpeta de resultados que necesites preservar, ya que el mismo nombre de salida se vuelve a escribir.

### Interfaz interactiva

```powershell
python -m streamlit run app.py
```

La interfaz lee el informe experimental existente `resultados/evaluacion_candidatos.json`; no recalcula esas métricas al cargar la página. La recuperación de una URL solo empieza cuando se solicita desde la interfaz. Si no hay candidatos en caché, la generación puede consultar Tavily.

## Algoritmo de puntuación

`src/puntuacion.py` combina tres componentes con pesos predeterminados que suman 1:

| Componente | Peso | Señal |
| --- | ---: | --- |
| Dominio | 0.45 | Similitud entre hosts normalizados, sin comparar las rutas. |
| Título | 0.35 | Similitud entre el título histórico y el título del candidato, si ambos están disponibles. |
| Proximidad | 0.20 | Nombre del sitio (60% del componente) y similitud de ruta significativa (40%). |

La variante predeterminada en los puntos de entrada del proyecto (`main.py`, evaluación CLI e interfaz) es `levenshtein`, que aplica distancia Levenshtein explícita y la normaliza a similitud de 0 a 100. `rapidfuzz.fuzz.ratio` sigue disponible como opción explícita y como valor predeterminado de las funciones de puntuación de bajo nivel. Ambas variantes conservan los mismos pesos y la regla binaria del nombre del sitio.

Las señales ausentes no se cuentan como coincidencias. Si falta una señal de proximidad, se renormalizan las señales disponibles dentro de proximidad; si falta un componente completo, se omite y se renormalizan los pesos de los componentes presentes. La nota final es una heurística de similitud, no una probabilidad de que el candidato sea la URL correcta.

## Demostraciones y verificación

Estos comandos ejecutan código que puede hacer solicitudes externas. No los ejecutes si necesitas una sesión estrictamente offline.

```powershell
python -m src.demostrar_metadatos
python -m src.demostrar_candidatos
python -m src.verificar_enlaces
```

- `src.demostrar_metadatos` consulta Internet Archive para los casos definidos en el módulo y guarda la observación en `resultados/demostracion_metadatos.json`. Usa una caché temporal para la demostración.
- `src.demostrar_candidatos` obtiene metadatos para el caso de demostración y llama a la generación de candidatos. Puede consultar Internet Archive y Tavily si no hay cachés correspondientes. Guarda la salida en `resultados/demostracion_candidatos.json`.
- `src.verificar_enlaces` consulta Internet Archive y abre las URL antigua y esperada; guarda los resultados en `resultados/verificacion.csv`. Esa salida se vuelve a escribir al ejecutar el comando.

Las salidas documentan observaciones de ejecuciones anteriores; una nueva ejecución puede producir resultados diferentes.

## Configuración de Tavily

El cliente busca la variable `TAVILY_API_KEY` en el entorno del proceso o en el archivo `.env` de la raíz del proyecto. Configúrala localmente antes de una operación que requiera una consulta nueva. No incluyas el valor de la clave en el código, informes, capturas o repositorio. El archivo `.env` está excluido por `.gitignore`.

Para la sesión actual de PowerShell, define la variable sin guardar el secreto en el README:

```powershell
$env:TAVILY_API_KEY = "<tu-clave>"
```

Las claves no son necesarias para ejecutar pruebas unitarias o una evaluación que pueda resolverse íntegramente con caché.

## Caché y reproducibilidad

`datos/cache/` contiene respuestas locales de metadatos y candidatos. El directorio está excluido de Git (excepto el archivo `.gitkeep`), por lo que sus contenidos locales no se incorporan al repositorio de forma normal ni están disponibles necesariamente en otro equipo o clon.

La evaluación predeterminada no realiza solicitudes para completar cachés. Si falta la caché de metadatos o candidatos, el registro queda sin evaluar por esa causa y no forma parte del denominador de las métricas. Una respuesta cacheada vacía sí representa una respuesta observada y se contabiliza como registro evaluado sin candidatos. `--buscar-faltantes` permite consultas externas para completar respuestas ausentes.

Los informes guardados en `resultados/` registran ejecuciones anteriores, pero no equivalen a recalcular el experimento. En un clon limpio, como `datos/cache/` no está versionada, la evaluación cache-only puede omitir registros; no se puede afirmar que el experimento se reproduzca sin conexión sin proporcionar las cachés necesarias. Los informes tampoco contienen necesariamente todas las respuestas de caché empleadas.

## Resultados experimentales guardados

Los CSV de evaluación existentes contienen seis filas cada uno. La tabla resume los JSON correspondientes; todas las métricas usan el denominador de seis registros evaluables en estos archivos. “Buscador” conserva el orden original y “modelo” es el orden después de puntuar. La URL correcta se identifica en el código por igualdad exacta del dominio normalizado entre candidato y destino esperado (se ignora `www.`), no por igualdad de la URL completa. Por eso, “cobertura” indica que aparece un candidato del dominio esperado, no que se haya identificado la página exacta de reemplazo.

| Informe | Modo | Variante identificada en JSON | Buscador Top-1 | Buscador Top-5 | Modelo Top-1 | Modelo Top-5 | Cobertura de dominio |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `evaluacion_candidatos.json` | `titulo+texto` | No indicada | 0/6 | 2/6 | 2/6 | 2/6 | 2/6 |
| `evaluacion_titulo_levenshtein.json` | `titulo` | Levenshtein | 0/6 | 4/6 | 2/6 | 5/6 | 5/6 |
| `evaluacion_titulo_mas_dominio_levenshtein.json` | `titulo+dominio` | Levenshtein | 0/6 | 4/6 | 2/6 | 6/6 | 6/6 |
| `evaluacion_titulo_mas_texto_levenshtein.json` | `titulo+texto` | Levenshtein | 0/6 | 2/6 | 2/6 | 2/6 | 2/6 |
| `evaluacion_levenshtein.json` | `titulo+texto` | Levenshtein | 0/6 | 2/6 | 2/6 | 2/6 | 2/6 |

`evaluacion_candidatos.json` incluye el modo `titulo+texto` y `buscar_faltantes: true`, pero no identifica la variante de puntuación; no debe etiquetarse retrospectivamente como RapidFuzz o Levenshtein sin evidencia adicional. `evaluacion_levenshtein.json` es un informe distinto, con variante Levenshtein y modo `titulo+texto` registrados en el resumen.

Los resultados por modo y variante se deben leer como informes separados; no son intercambiables ni deben combinarse. Los JSON incluyen los resúmenes agregados. Los CSV correspondientes guardan el detalle por enlace.

### Definición de las métricas

Según `src/evaluacion.py`, Top-1 cuenta los registros evaluables donde el primer candidato (buscador o modelo reordenado) tiene el dominio esperado. Top-5 cuenta aquellos donde ese dominio aparece hasta la posición cinco en el orden correspondiente. La cobertura cuenta si aparece en cualquier posición de la lista. Las tres tasas dividen sus aciertos entre registros con URL antigua y destino utilizables, metadatos disponibles y respuesta de candidatos disponible; una respuesta vacía cuenta como evaluada sin acierto. Cachés faltantes, errores y registros incompletos se informan aparte y se excluyen del denominador.

## Pruebas automatizadas

El directorio `tests/` usa el estilo de `unittest` de la biblioteca estándar de Python:

```powershell
python -m unittest discover -s tests -v
```

Las dependencias de `requirements.txt` no incluyen `pytest`; `unittest` no requiere instalar un paquete adicional. Las pruebas de red usan respuestas simuladas o reemplazan las funciones de acceso externo.

## Limitaciones conocidas

- El acierto se mide por igualdad del dominio normalizado, no por igualdad de la URL exacta. Puede contar una página distinta del mismo dominio como acierto.
- La muestra contiene seis enlaces; los resultados son exploratorios y no permiten generalizar a colecciones grandes.
- La nota del ID 1 en `datos/enlaces.csv` indica que la URL nueva todavía no tiene confirmación oficial.
- La regla del nombre del sitio puede favorecer candidatos que conservan el nombre viejo. En el ejemplo ShareLaTeX, el sitio de una universidad que aún dice ShareLaTeX obtiene 72,37, mientras que `overleaf.com` obtiene 45,25.
- El método compara cadenas y metadatos; no comprende el significado de los textos. Es una heurística, no un emparejamiento semántico en sentido estricto.
- Los informes dependen de las capturas, consultas, respuestas y cachés disponibles. `datos/cache/` está excluida de Git, de modo que un clon limpio puede no reproducir una evaluación cache-only.
- La evaluación no simula usuarios autenticados ni carga multiusuario; los tiempos cache-only no representan latencia de los servicios externos.
