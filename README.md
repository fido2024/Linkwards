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

## Cómo correrlo
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Estructura
- `datos/enlaces.csv`: conjunto de prueba (URL vieja, URL nueva correcta, tipo de cambio).
- `datos/cache/`: respuestas guardadas del Internet Archive y del buscador.
- `src/metadatos.py`: Fase 2, recuperación de título y texto desde el Internet Archive.
- `src/candidatos.py`: Fase 3, generación acotada de candidatos (top 10).
- `src/puntuacion.py`: Fase 4, puntuación y ordenamiento.
- `src/evaluacion.py`: Fase 5, métricas (Top-1, Top-5, cobertura, tiempo).
- `resultados/`: tablas generadas por la evaluación.

## Alcance
Solo el algoritmo. Sin interfaz web, base de datos, verificación periódica ni notificaciones.
