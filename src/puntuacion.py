"""Fase 4: puntuación heurística y ordenamiento de candidatos.

La nota es un indicador de similitud (0–100), no una probabilidad estadística.
Los pesos predeterminados suman 1:

* dominio (0.45): similitud RapidFuzz entre hosts normalizados; las rutas nunca
  entran en esta comparación.
* título (0.35): similitud RapidFuzz entre el título histórico y el del
  candidato, si ambos existen.
* proximidad (0.20): reglas sobre el nombre del sitio (60% de este componente)
  y la ruta significativa (40%). Las reglas que no se puedan calcular se
  excluyen y las restantes se renormalizan dentro del componente.

Si falta un componente completo, se excluye del promedio final y se renormalizan
los pesos de los componentes disponibles. Un dato ausente nunca recibe por sí
mismo una puntuación de coincidencia.
"""
import math
import re
import unicodedata
from urllib.parse import urlsplit

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein


# Configuración reemplazable por experimentos; los tres valores deben sumar 1.
PESOS = {"dominio": 0.45, "titulo": 0.35, "proximidad": 0.20}
PESOS_PROXIMIDAD = {"nombre_sitio": 0.60, "ruta": 0.40}
VARIANTES = ("rapidfuzz", "levenshtein")

ETIQUETAS_SUBDOMINIO_COMUNES = {
    "www", "www2", "m", "mobile", "amp", "api", "app", "blog", "docs",
    "documentation", "help", "support", "forum", "forums", "news", "shop",
    "store", "mail", "ftp", "dev", "stage", "staging", "test", "old", "new",
}


def _url(valor):
    """Acepta una URL o un diccionario con la clave `url`."""
    if isinstance(valor, dict):
        valor = valor.get("url")
    if not isinstance(valor, str) or not valor.strip():
        return None
    valor = valor.strip()
    try:
        return urlsplit(valor if "://" in valor else "https://" + valor)
    except ValueError:
        return None


def _host(valor):
    partes = _url(valor)
    if not partes:
        return None
    try:
        host = partes.hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.rstrip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def _normalizar_texto(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    valor = unicodedata.normalize("NFKC", valor).casefold()
    return " ".join(valor.split()) or None


def similitud_levenshtein(a, b):
    """Similitud Levenshtein normalizada en escala 0–100.

    Si ambas cadenas están vacías devuelve 100; si solo una está vacía,
    devuelve 0. Los componentes de puntuación omiten normalmente valores
    vacíos antes de llamar esta función.
    """
    if not isinstance(a, str) or not isinstance(b, str):
        raise TypeError("similitud_levenshtein requiere dos cadenas.")
    longitud = max(len(a), len(b))
    if longitud == 0:
        return 100.0
    distancia = Levenshtein.distance(a, b)
    return 100.0 * (1.0 - distancia / longitud)


def _nombre_sitio(host):
    """Estima el nombre desde la primera etiqueta no genérica del host.

    Es una regla sencilla, no una extracción exacta de dominio registrable.
    """
    if not host:
        return None
    etiquetas = host.split(".")
    for etiqueta in etiquetas:
        if etiqueta not in ETIQUETAS_SUBDOMINIO_COMUNES and not etiqueta.isdigit():
            return etiqueta
    return None


def _tokens_host(host):
    tokens = set()
    for etiqueta in (host or "").split("."):
        tokens.update(token for token in etiqueta.split("-") if token)
    return tokens


def _ruta_significativa(partes):
    if not partes:
        return None
    segmentos = [segmento for segmento in partes.path.split("/") if segmento]
    segmentos = [
        unicodedata.normalize("NFKC", segmento).casefold()
        for segmento in segmentos
        if segmento.casefold() not in {"index", "index.html", "index.htm", "index.php", "home", "default"}
    ]
    if not segmentos:
        return None
    return "/".join(segmentos)


def _validar_pesos(pesos, nombre="PESOS", claves_esperadas=None):
    if not isinstance(pesos, dict) or not pesos:
        raise ValueError(f"{nombre} debe ser un diccionario de pesos.")
    if claves_esperadas is not None and set(pesos) != set(claves_esperadas):
        raise ValueError(f"{nombre} debe definir exactamente: {', '.join(claves_esperadas)}.")
    if any(not isinstance(peso, (int, float)) or not math.isfinite(peso) or peso < 0 for peso in pesos.values()):
        raise ValueError(f"{nombre} solo admite pesos finitos no negativos.")
    if not math.isclose(sum(pesos.values()), 1.0, abs_tol=1e-9):
        raise ValueError(f"Los pesos de {nombre} deben sumar 1.")


def _promedio_ponderado(disponibles, pesos):
    activos = {nombre: pesos[nombre] for nombre in disponibles if pesos.get(nombre, 0) > 0}
    total = sum(activos.values())
    if total <= 0:
        return None
    return sum(disponibles[nombre] * peso for nombre, peso in activos.items()) / total


def _puntuaciones_componentes(original, candidato, metadatos=None, variante="rapidfuzz"):
    if variante not in VARIANTES:
        raise ValueError(f"Variante desconocida: {variante}. Usa una de: {', '.join(VARIANTES)}")
    if not isinstance(candidato, dict):
        return {}
    metadatos = metadatos if isinstance(metadatos, dict) else {}
    original_url = original or metadatos.get("url")
    url_candidato = candidato.get("url")
    host_original = _host(original_url)
    host_candidato = _host(url_candidato)
    componentes = {}
    similitud = fuzz.ratio if variante == "rapidfuzz" else similitud_levenshtein

    if host_original and host_candidato:
        componentes["dominio"] = float(similitud(host_original, host_candidato))

    titulo_original = _normalizar_texto(metadatos.get("titulo"))
    titulo_candidato = _normalizar_texto(candidato.get("titulo"))
    if titulo_original and titulo_candidato:
        componentes["titulo"] = float(similitud(titulo_original, titulo_candidato))

    reglas = {}
    nombre = _nombre_sitio(host_original)
    if nombre and host_candidato:
        nombre_normalizado = re.sub(r"[^a-z0-9]", "", nombre)
        tokens = _tokens_host(host_candidato)
        reglas["nombre_sitio"] = 100.0 if nombre in tokens or nombre_normalizado in re.sub(r"[^a-z0-9]", "", host_candidato) else 0.0

    ruta_original = _ruta_significativa(_url(original_url))
    ruta_candidata = _ruta_significativa(_url(url_candidato))
    if ruta_original and ruta_candidata:
        reglas["ruta"] = float(similitud(ruta_original, ruta_candidata))

    proximidad = _promedio_ponderado(reglas, PESOS_PROXIMIDAD)
    if proximidad is not None:
        componentes["proximidad"] = proximidad
    return componentes


def puntuar_candidato(original, candidato, metadatos, variante="rapidfuzz"):
    """Devuelve la nota heurística 0–100 de un candidato.

    `original` puede ser la URL vieja o un diccionario con `url`. `candidato`
    sigue la estructura de `src.candidatos` (`url`, `titulo`, `snippet`, etc.) y
    `metadatos` es el resultado de `obtener_metadatos`.
    """
    _validar_pesos(PESOS, claves_esperadas=("dominio", "titulo", "proximidad"))
    _validar_pesos(PESOS_PROXIMIDAD, "PESOS_PROXIMIDAD", ("nombre_sitio", "ruta"))
    componentes = _puntuaciones_componentes(original, candidato, metadatos, variante)
    nota = _promedio_ponderado(componentes, PESOS)
    if nota is None or not math.isfinite(nota):
        return 0.0
    return round(min(100.0, max(0.0, nota)), 2)


def ordenar_candidatos(original, candidatos, metadatos, variante="rapidfuzz"):
    """Copia candidatos, agrega `puntuacion` y ordena de mayor a menor.

    El orden de entrada se conserva para los empates. Los duplicados se dejan
    intactos: la deduplicación pertenece a la generación de candidatos.
    """
    if candidatos is None:
        return []
    puntuados = []
    for indice, candidato in enumerate(candidatos):
        copia = dict(candidato) if isinstance(candidato, dict) else {"valor": candidato}
        copia["puntuacion"] = puntuar_candidato(original, candidato, metadatos, variante)
        puntuados.append((indice, copia))
    puntuados.sort(key=lambda elemento: elemento[1]["puntuacion"], reverse=True)
    return [candidato for _, candidato in puntuados]
