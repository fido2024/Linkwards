"""Fase 5: evaluación experimental sobre los enlaces etiquetados del CSV.

Por defecto funciona en modo seguro de caché: no solicita metadatos a Wayback ni
candidatos a Tavily cuando falta una respuesta guardada. `--buscar-faltantes`
activa explícitamente esas consultas.
"""
import argparse
import csv
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from src import candidatos as candidatos_mod
from src import metadatos as metadatos_mod
from src.datos import dominio
from src.puntuacion import VARIANTES, ordenar_candidatos


RUTA_CSV = "datos/enlaces.csv"
RUTA_RESULTADOS = "resultados"
MODO = candidatos_mod.MODO_PREDETERMINADO
VARIANTE_PREDETERMINADA = "levenshtein"
COLUMNAS_RESULTADO = [
    "id", "url_vieja", "url_nueva_correcta", "estado", "detalle",
    "cantidad_candidatos", "correcta_en_candidatos", "rango_busqueda",
    "rango_heuristico", "top1_busqueda", "top5_busqueda",
    "top1_heuristico", "top5_heuristico", "primer_resultado_busqueda",
    "primer_resultado_heuristico", "primer_resultado_cambio",
    "duracion_segundos",
]


def _leer_registros(ruta_csv):
    with open(ruta_csv, encoding="utf-8-sig", newline="") as archivo:
        primera = archivo.readline()
        archivo.seek(0)
        separador = ";" if primera.count(";") > primera.count(",") else ","
        return [
            fila for fila in csv.DictReader(archivo, delimiter=separador)
            if any(str(valor or "").strip() for valor in fila.values())
        ]


def _url_utilizable(valor):
    if not isinstance(valor, str) or not valor.strip() or any(c.isspace() for c in valor.strip()):
        return False
    valor = valor.strip()
    try:
        partes = urlsplit(valor if "://" in valor else "https://" + valor)
        puerto = partes.port  # fuerza la validación de puertos malformados
        return (
            partes.scheme.lower() in ("http", "https")
            and bool(partes.hostname)
            and not partes.username
            and not partes.password
        )
    except ValueError:
        return False


def _ruta_cache_metadatos(url):
    clave = hashlib.md5(url.encode("utf-8")).hexdigest()
    return os.path.join(metadatos_mod.CARPETA_CACHE, f"meta_{clave}.json")


def _rango_correcto(lista, url_correcta):
    dominio_correcto = dominio(url_correcta)
    for rango, item in enumerate(lista, start=1):
        url = item.get("url", "")
        if url and dominio(url) == dominio_correcto:
            return rango
    return None


def _bool_o_vacio(valor):
    return "" if valor is None else bool(valor)


def _procesar_registro(fila, buscar_faltantes, variante=VARIANTE_PREDETERMINADA, modo=MODO):
    inicio = time.perf_counter()
    identificador = str(fila.get("id", "")).strip()
    vieja = str(fila.get("url_vieja", "")).strip()
    nueva = str(fila.get("url_nueva_correcta", "")).strip()
    resultado = {
        "id": identificador,
        "url_vieja": vieja,
        "url_nueva_correcta": nueva,
        "estado": "registro_incompleto",
        "detalle": "",
        "cantidad_candidatos": 0,
        "correcta_en_candidatos": None,
        "rango_busqueda": None,
        "rango_heuristico": None,
        "top1_busqueda": None,
        "top5_busqueda": None,
        "top1_heuristico": None,
        "top5_heuristico": None,
        "primer_resultado_busqueda": "",
        "primer_resultado_heuristico": "",
        "primer_resultado_cambio": None,
    }

    if not _url_utilizable(vieja) or not _url_utilizable(nueva):
        resultado["detalle"] = "Se requiere una URL antigua y una URL nueva correcta HTTP(S) utilizable."
        resultado["duracion_segundos"] = round(time.perf_counter() - inicio, 6)
        return resultado

    cache_meta = _ruta_cache_metadatos(vieja)
    if not os.path.isfile(cache_meta) and not buscar_faltantes:
        resultado.update(estado="sin_cache_metadatos", detalle="No hay metadatos históricos en caché; no se consultó Internet Archive.")
        resultado["duracion_segundos"] = round(time.perf_counter() - inicio, 6)
        return resultado
    try:
        meta = metadatos_mod.obtener_metadatos(vieja, estricto=True)
    except Exception as error:
        resultado.update(estado="error_metadatos", detalle=f"{type(error).__name__}: {error}")
        resultado["duracion_segundos"] = round(time.perf_counter() - inicio, 6)
        return resultado
    if not isinstance(meta, dict) or not (meta.get("url") or meta.get("titulo") or meta.get("texto")):
        resultado.update(estado="sin_metadatos", detalle="No se pudieron obtener metadatos útiles.")
        resultado["duracion_segundos"] = round(time.perf_counter() - inicio, 6)
        return resultado

    try:
        cache_candidatos = candidatos_mod.ruta_cache_candidatos(meta, modo)
        if not buscar_faltantes:
            if not os.path.isfile(cache_candidatos):
                resultado.update(estado="sin_cache_candidatos", detalle="No hay candidatos en caché; no se consultó Tavily.")
                resultado["duracion_segundos"] = round(time.perf_counter() - inicio, 6)
                return resultado
            try:
                with open(cache_candidatos, encoding="utf-8") as archivo:
                    cache = json.load(archivo)
                if not isinstance(cache, list):
                    raise ValueError("La caché de candidatos no contiene una lista.")
            except (OSError, ValueError) as error:
                resultado.update(estado="cache_candidatos_invalida", detalle=f"{type(error).__name__}: {error}")
                resultado["duracion_segundos"] = round(time.perf_counter() - inicio, 6)
                return resultado
        items = candidatos_mod.generar_candidatos(meta, modo)
    except Exception as error:
        resultado.update(estado="error_busqueda", detalle=f"{type(error).__name__}: {error}")
        resultado["duracion_segundos"] = round(time.perf_counter() - inicio, 6)
        return resultado

    if not items:
        resultado.update(estado="evaluado_sin_candidatos", detalle="La respuesta no produjo candidatos válidos.")
        base = []
    else:
        resultado["estado"] = "evaluado"
        base = sorted(items, key=lambda item: item.get("posicion_buscador", 0))

    try:
        ordenados = ordenar_candidatos(vieja, base, meta, variante=variante)
    except Exception as error:
        resultado.update(estado="error_puntuacion", detalle=f"{type(error).__name__}: {error}")
        resultado["duracion_segundos"] = round(time.perf_counter() - inicio, 6)
        return resultado

    rango_base = _rango_correcto(base, nueva)
    rango_heuristico = _rango_correcto(ordenados, nueva)
    primero_base = base[0].get("url", "") if base else ""
    primero_heuristico = ordenados[0].get("url", "") if ordenados else ""
    resultado.update({
        "cantidad_candidatos": len(base),
        "correcta_en_candidatos": rango_base is not None,
        "rango_busqueda": rango_base,
        "rango_heuristico": rango_heuristico,
        "top1_busqueda": rango_base == 1,
        "top5_busqueda": rango_base is not None and rango_base <= 5,
        "top1_heuristico": rango_heuristico == 1,
        "top5_heuristico": rango_heuristico is not None and rango_heuristico <= 5,
        "primer_resultado_busqueda": primero_base,
        "primer_resultado_heuristico": primero_heuristico,
        "primer_resultado_cambio": primero_base != primero_heuristico if base else None,
    })
    resultado["duracion_segundos"] = round(time.perf_counter() - inicio, 6)
    return resultado


def _tasa(aciertos, denominador):
    return None if denominador == 0 else aciertos / denominador


def _resumir(filas, total):
    estados_evaluados = {"evaluado", "evaluado_sin_candidatos"}
    observados = [fila for fila in filas if fila["estado"] in estados_evaluados]
    denominador = len(observados)
    cubiertos = sum(fila["correcta_en_candidatos"] is True for fila in observados)
    top1_busqueda = sum(fila["top1_busqueda"] is True for fila in observados)
    top5_busqueda = sum(fila["top5_busqueda"] is True for fila in observados)
    top1_heuristico = sum(fila["top1_heuristico"] is True for fila in observados)
    top5_heuristico = sum(fila["top5_heuristico"] is True for fila in observados)
    primeros_comparables = [fila for fila in observados if fila["cantidad_candidatos"] > 0]
    errores = sum(fila["estado"].startswith("error_") for fila in filas)
    return {
        "registros_csv": total,
        "registros_con_urls_utilizables": sum(fila["estado"] != "registro_incompleto" for fila in filas),
        "registros_evaluables_con_respuesta": denominador,
        "registros_con_error": errores,
        "registros_sin_cache_metadatos": sum(fila["estado"] == "sin_cache_metadatos" for fila in filas),
        "registros_sin_cache_candidatos": sum(fila["estado"] == "sin_cache_candidatos" for fila in filas),
        "registros_sin_candidatos_validos": sum(fila["estado"] == "evaluado_sin_candidatos" for fila in filas),
        "registros_correcta_ausente_de_candidatos": denominador - cubiertos,
        "registros_correcta_presente_pero_no_top1_busqueda": cubiertos - top1_busqueda,
        "registros_correcta_presente_pero_no_top1_heuristico": cubiertos - top1_heuristico,
        "cobertura": {"aciertos": cubiertos, "denominador": denominador, "tasa": _tasa(cubiertos, denominador)},
        "top1_busqueda": {"aciertos": top1_busqueda, "denominador": denominador, "tasa": _tasa(top1_busqueda, denominador)},
        "top5_busqueda": {"aciertos": top5_busqueda, "denominador": denominador, "tasa": _tasa(top5_busqueda, denominador)},
        "top1_heuristico": {"aciertos": top1_heuristico, "denominador": denominador, "tasa": _tasa(top1_heuristico, denominador)},
        "top5_heuristico": {"aciertos": top5_heuristico, "denominador": denominador, "tasa": _tasa(top5_heuristico, denominador)},
        "primer_resultado_cambio": {
            "cambios": sum(fila["primer_resultado_cambio"] is True for fila in primeros_comparables),
            "sin_cambio": sum(fila["primer_resultado_cambio"] is False for fila in primeros_comparables),
            "denominador": len(primeros_comparables),
        },
        "tiempo_medio_segundos_por_registro_evaluable": (
            sum(fila["duracion_segundos"] for fila in observados) / denominador if denominador else None
        ),
    }


def evaluar(
    ruta_csv=RUTA_CSV,
    buscar_faltantes=False,
    directorio_resultados=RUTA_RESULTADOS,
    variante=VARIANTE_PREDETERMINADA,
    modo=MODO,
):
    """Evalúa la colección etiquetada y guarda CSV por enlace y JSON agregado.

    La caché es obligatoria por defecto para evitar llamadas y cargos. Poner
    `buscar_faltantes=True` activa consultas de metadatos y/o Tavily cuando
    falten entradas.
    """
    if variante not in VARIANTES:
        raise ValueError(f"Variante desconocida: {variante}. Usa una de: {', '.join(VARIANTES)}")
    if modo not in candidatos_mod.MODOS:
        raise ValueError(f"Modo desconocido: {modo}. Usa uno de: {', '.join(candidatos_mod.MODOS)}")
    inicio = time.perf_counter()
    filas_csv = _leer_registros(ruta_csv)
    filas = [_procesar_registro(fila, buscar_faltantes, variante, modo) for fila in filas_csv]
    resumen = _resumir(filas, len(filas_csv))
    resumen["tiempo_total_segundos"] = round(time.perf_counter() - inicio, 6)
    resumen["modo"] = modo
    resumen["buscar_faltantes"] = bool(buscar_faltantes)
    resumen["variante_puntuacion"] = variante

    os.makedirs(directorio_resultados, exist_ok=True)
    slug_modo = modo.replace("+", "_mas_")
    prefijo = f"evaluacion_{slug_modo}_{variante}"
    ruta_detalle = os.path.join(directorio_resultados, f"{prefijo}.csv")
    ruta_resumen = os.path.join(directorio_resultados, f"{prefijo}.json")
    with open(ruta_detalle, "w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS_RESULTADO)
        escritor.writeheader()
        escritor.writerows(filas)
    documento = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "conjunto": ruta_csv,
        "tipo_resultado": "cache_solo_sin_consultas_externas" if not buscar_faltantes else "cache_mas_consultas_externas",
        "definiciones": {
            "denominador_metricas": "registros con URLs válidas, metadatos disponibles y una respuesta de candidatos válida en caché o recién obtenida; una lista vacía sí cuenta como respuesta y como fallo de cobertura",
            "top1_top5_busqueda": "posición de la URL correcta en el orden original del buscador",
            "top1_top5_heuristico": "posición de la URL correcta después de ordenar por puntuación heurística",
            "cobertura": "registros evaluables donde el dominio correcto aparece entre candidatos, dividido por registros evaluables",
            "rango_correcto": "posición del primer candidato cuyo dominio normalizado coincide exactamente con el dominio esperado",
            "tiempo": "segundos por registro; en modo cache-only mide lectura, preparación y puntuación sin latencia de red",
            "variante_puntuacion": variante,
            "similitud_levenshtein": "100 * (1 - distancia_Levenshtein(a,b) / max(len(a),len(b))); ambas cadenas vacías=100 y solo una vacía=0",
        },
        "resumen": resumen,
        "registros": filas,
    }
    with open(ruta_resumen, "w", encoding="utf-8") as archivo:
        json.dump(documento, archivo, ensure_ascii=False, indent=2)

    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"Detalle: {ruta_detalle}")
    print(f"Resumen: {ruta_resumen}")
    return resumen


def main():
    parser = argparse.ArgumentParser(description="Evalúa el ordenamiento de candidatos de Linkwards.")
    parser.add_argument("--csv", default=RUTA_CSV, help="CSV de enlaces etiquetados")
    parser.add_argument("--resultados", default=RUTA_RESULTADOS, help="Carpeta de salida")
    parser.add_argument(
        "--variante", choices=VARIANTES, default=VARIANTE_PREDETERMINADA,
        help="Algoritmo de similitud (predeterminado: levenshtein)",
    )
    parser.add_argument("--modo", choices=candidatos_mod.MODOS, default=MODO, help="Modo de consulta; predeterminado: titulo+dominio")
    parser.add_argument(
        "--buscar-faltantes", action="store_true",
        help="Permite consultar Wayback/Tavily si faltan cachés (puede consumir tiempo/créditos).",
    )
    args = parser.parse_args()
    evaluar(
        args.csv,
        buscar_faltantes=args.buscar_faltantes,
        directorio_resultados=args.resultados,
        variante=args.variante,
        modo=args.modo,
    )


if __name__ == "__main__":
    main()
