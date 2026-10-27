"""Ejecuta y guarda una demostración real de la fase de metadatos.

Uso: python -m src.demostrar_metadatos
Requiere acceso a Internet Archive; consulta un dominio de ejemplo y uno .invalid.
"""
import json
import os
import tempfile
from datetime import datetime, timezone

from src import metadatos

CASOS = ("example.org", "linkwards-no-such-host.invalid")
SALIDA = os.path.join("resultados", "demostracion_metadatos.json")


def main():
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    resultado = {
        "ejecutado_utc": datetime.now(timezone.utc).isoformat(),
        "casos": [],
    }
    cache_original = metadatos.CARPETA_CACHE
    try:
        # Un cache temporal evita que una ejecución anterior oculte la consulta real.
        with tempfile.TemporaryDirectory(prefix="linkwards-wayback-") as cache_temporal:
            metadatos.CARPETA_CACHE = cache_temporal
            for url in CASOS:
                print(f"Consultando {url} ...", flush=True)
                captura = metadatos._captura_disponible(url)
                meta = metadatos.obtener_metadatos(url, verbose=True)
                resultado["casos"].append({
                    "url": url,
                    "availability_api": captura,
                    "metadatos": meta,
                    "resultado": "metadatos_recuperados" if meta else "sin_metadatos_utiles",
                })
                print(f"  Resultado: {resultado['casos'][-1]['resultado']}", flush=True)
    finally:
        metadatos.CARPETA_CACHE = cache_original

    with open(SALIDA, "w", encoding="utf-8") as archivo:
        json.dump(resultado, archivo, ensure_ascii=False, indent=2)
    print(f"Demostración guardada en {SALIDA}")


if __name__ == "__main__":
    main()
