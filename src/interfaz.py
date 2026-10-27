"""Adaptadores de presentación para la interfaz web de Linkwards.

Este módulo coordina las funciones de negocio existentes y prepara datos para
la UI. No contiene llamadas de red propias: estas siguen encapsuladas en
metadatos y candidatos, incluida su caché.
"""
import json
from urllib.parse import urlsplit

from src import candidatos, metadatos
from src.datos import dominio
from src.puntuacion import ordenar_candidatos


def validar_url(valor):
    """Devuelve una URL HTTP(S) normalizada o None si la entrada no es válida."""
    if not isinstance(valor, str):
        return None
    valor = valor.strip()
    if not valor or any(caracter.isspace() for caracter in valor):
        return None
    if "://" not in valor:
        valor = "https://" + valor
    try:
        partes = urlsplit(valor)
        puerto = partes.port  # valida puertos malformados
    except ValueError:
        return None
    if (
        partes.scheme.lower() not in ("http", "https")
        or not partes.hostname
        or partes.username
        or partes.password
    ):
        return None
    host = partes.hostname.lower()
    netloc = f"[{host}]" if ":" in host else host
    if puerto is not None:
        netloc += f":{puerto}"
    return partes._replace(scheme=partes.scheme.lower(), netloc=netloc).geturl()


def recuperar(url_entrada):
    """Recupera metadatos, candidatos y orden heurístico para una URL."""
    url = validar_url(url_entrada)
    if not url:
        return {"estado": "url_invalida", "detalle": "Introduce una URL HTTP o HTTPS válida."}

    try:
        meta = metadatos.obtener_metadatos(url, estricto=True)
    except metadatos.ErrorConexionInternetArchive:
        return {
            "estado": "error_conexion_archive",
            "detalle": "Internet Archive no respondió correctamente; no se puede confirmar si hay capturas.",
        }
    except Exception:
        return {
            "estado": "error_metadatos",
            "detalle": "No se pudo completar la consulta al archivo histórico.",
        }
    if not isinstance(meta, dict) or not (meta.get("titulo") or meta.get("texto")):
        return {
            "estado": "sin_captura",
            "detalle": "No se encontraron metadatos históricos utilizables para esta URL.",
        }

    try:
        items = candidatos.generar_candidatos(meta)
    except RuntimeError as error:
        mensaje = str(error).lower()
        if "falta la clave de tavily" in mensaje:
            return {
                "estado": "falta_configuracion_tavily",
                "detalle": "No hay candidatos en caché y Tavily no está configurado. Configura TAVILY_API_KEY en el entorno o en .env.",
                "metadatos": meta,
            }
        return {
            "estado": "error_conexion_busqueda",
            "detalle": "No se pudo completar la búsqueda de candidatos. Revisa la conexión y la disponibilidad de Tavily.",
            "metadatos": meta,
        }
    except Exception:
        return {
            "estado": "error_candidatos",
            "detalle": "Ocurrió un error al preparar los candidatos.",
            "metadatos": meta,
        }

    if not items:
        return {
            "estado": "sin_candidatos",
            "detalle": "La búsqueda terminó, pero no produjo candidatos HTTP(S) válidos.",
            "metadatos": meta,
            "candidatos": [],
        }

    ordenados = ordenar_candidatos(url, items, meta)
    return {
        "estado": "completado",
        "detalle": "Recuperación completada.",
        "metadatos": meta,
        "candidatos": ordenados,
    }


def candidatos_para_tabla(candidatos_ordenados):
    """Proyecta candidatos ordenados a columnas legibles para la interfaz."""
    filas = []
    for posicion, candidato in enumerate(candidatos_ordenados or [], start=1):
        url = candidato.get("url", "")
        filas.append({
            "Posición": posicion,
            "Dominio": dominio(url) if url else "",
            "Puntuación heurística": candidato.get("puntuacion", 0.0),
            "Título": candidato.get("titulo", ""),
            "URL": url,
        })
    return filas


def cargar_metricas(ruta="resultados/evaluacion_candidatos.json"):
    """Lee métricas ya calculadas, sin ejecutar ni recalcular la evaluación."""
    try:
        with open(ruta, encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, ValueError):
        return None


def formatear_fecha_captura(fecha):
    """Formatea timestamps Wayback YYYYMMDDhhmmss conservando el dato original."""
    if not isinstance(fecha, str) or len(fecha) < 8 or not fecha[:8].isdigit():
        return fecha or "No disponible"
    return f"{fecha[0:4]}-{fecha[4:6]}-{fecha[6:8]}"

