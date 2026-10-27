"""Búsqueda de demostración en vivo y persistencia de salida sin secretos.

Uso: python -m src.demostrar_candidatos
La búsqueda usa los metadatos ya guardados para sharelatex.com y la clave de
Tavily del entorno o del archivo local .env. La respuesta también queda en caché.
"""
import json
import os
from datetime import datetime, timezone

from src.candidatos import armar_consulta, generar_candidatos
from src.metadatos import obtener_metadatos

URL_HISTORICA = "sharelatex.com"
MODO = "titulo+texto"
SALIDA = os.path.join("resultados", "demostracion_candidatos.json")


def main():
    metadatos = obtener_metadatos(URL_HISTORICA)
    if not metadatos:
        raise SystemExit(f"No hay metadatos históricos disponibles para {URL_HISTORICA}.")

    consulta = armar_consulta(metadatos, MODO)
    candidatos = generar_candidatos(metadatos, MODO)
    resultado = {
        "ejecutado_utc": datetime.now(timezone.utc).isoformat(),
        "url_historica": URL_HISTORICA,
        "modo": MODO,
        "consulta": consulta,
        "cantidad": len(candidatos),
        "candidatos": candidatos,
    }
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as archivo:
        json.dump(resultado, archivo, ensure_ascii=False, indent=2)
    print(f"Consulta ejecutada: {consulta}")
    print(f"Candidatos válidos: {len(candidatos)}")
    print(f"Resultado guardado en {SALIDA}; la clave no se incluye.")


if __name__ == "__main__":
    main()
