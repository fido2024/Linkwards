"""Fase 2: recuperar qué era el enlace (título y texto) desde el Internet Archive.

Forma del resultado (diccionario):
    {
        "url": str,          # URL vieja
        "titulo": str,       # título de la página archivada
        "texto": str,        # descripción y fragmento de texto de la página
        "fecha_copia": str,  # fecha de la copia usada (AAAAMMDDhhmmss)
    }
Devuelve None si no hay ninguna copia con contenido útil.

Uso para probar con todo el CSV:
    python -m src.metadatos
"""
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from src.datos import leer_enlaces

CDX = "https://web.archive.org/cdx/search/cdx"
API_DISPONIBILIDAD = "https://archive.org/wayback/available"
CABECERAS = {"User-Agent": "Linkwards/0.1 (academic URL recovery prototype)"}
TIMEOUT = 30
CARPETA_CACHE = "datos/cache"
MAX_CAPTURAS = 36  # cuántas copias (una por mes) se prueban en cada ronda
MAX_RONDAS = 3     # si ninguna sirve, se retrocede en el tiempo hasta 3 veces
LARGO_TEXTO = 500
PAUSA = 1.0  # segundos entre consultas al Archive, para no ser bloqueado


class ErrorConexionInternetArchive(RuntimeError):
    """La consulta al Archive no pudo determinar si existe una captura."""

# Títulos típicos de páginas que NO sirven para saber qué era el sitio
TITULOS_INUTILES = (
    "for sale", "en venta", "suspended", "suspendido", "just a moment",
    "attention required", "parked", "403 forbidden", "404", "not found",
    "access denied", "index of /", "default web site page", "seized",
    "redirecting", "this domain", "coming soon", "under construction",
    "maintenance", "mantenimiento", "checking your browser", "expired",
    "domainpark", "geparkt",
)
MIN_TEXTO = 20  # una página con menos texto que esto no dice nada del sitio

# Frases de páginas de "dominio estacionado o en venta", en varios idiomas
FRASES_ESTACIONADA = (
    "for sale", "buy this domain", "domain may be", "domain is available",
    "domain has expired", "parked", "en venta", "à vendre", "zu verkaufen",
    "myytävänä", "verkkotunnus", "domainpark", "geparkt", "diese domain",
    "te koop", "à venda", "sedo", "godaddy", "hugedomains", "afternic",
    "default web page", "web server software is running", "welcome to nginx",
    "apache2 ubuntu default page",
)
# Títulos que, si son exactamente esto, son páginas por defecto de un servidor
TITULOS_POR_DEFECTO = ("it works", "welcome to nginx", "test page", "index of")


def _un_segundo_antes(timestamp):
    """'20220101000000' -> '20211231235959' (resta un segundo de verdad)."""
    t = datetime.strptime(timestamp, "%Y%m%d%H%M%S") - timedelta(seconds=1)
    return t.strftime("%Y%m%d%H%M%S")


def _get(url, params=None, intentos=4, timeout=TIMEOUT):
    """GET con reintentos. Espera más si el Archive pide ir más despacio (429)."""
    for i in range(intentos):
        try:
            r = requests.get(url, params=params, headers=CABECERAS, timeout=timeout)
            if r.status_code == 429:
                time.sleep(5 * (i + 1))
                continue
            if r.status_code < 500:
                return r
        except requests.RequestException:
            pass
        if i < intentos - 1:
            time.sleep(2)
    return None


def _capturas(url, hasta=None, excluir=None):
    """Copias HTML con código 200, de la más reciente a la más antigua.

    Quita las copias con contenido idéntico a una más reciente (así no se
    descarga cien veces el mismo aviso). Si se da "hasta", solo mira copias de
    esa fecha hacia atrás; "excluir" es un conjunto de contenidos ya vistos.
    Devuelve (lista, detalle): cada
    elemento de la lista es [timestamp, url_original, digest] y detalle explica
    por qué la lista salió vacía.
    """
    base = {
        "url": url,
        "output": "json",
        "fl": "timestamp,original,mimetype,statuscode,digest",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "timestamp:6",  # a lo mucho una copia por mes
    }
    if hasta:
        base["to"] = hasta
    excluir = excluir if excluir is not None else set()
    detalle = "no hubo respuesta del Archive"
    # Primero pide las últimas copias; si eso no devuelve nada, pide todas
    for extra in ({"limit": f"-{MAX_CAPTURAS}", "fastLatest": "true"}, {}):
        r = _get(CDX, {**base, **extra})
        if r is None:
            detalle = "el Archive no respondio (tiempo agotado)"
            continue
        if r.status_code != 200:
            detalle = f"el Archive respondio HTTP {r.status_code}"
            continue
        if not r.text.strip():
            detalle = "respuesta vacia del Archive"
            continue
        try:
            filas_json = r.json()
            if not isinstance(filas_json, list) or not filas_json:
                raise ValueError("CDX no devolvió una tabla JSON.")
            encabezados = filas_json[0]
            if not isinstance(encabezados, list):
                raise ValueError("CDX no devolvió encabezados de columna.")
            columnas = {str(nombre): indice for indice, nombre in enumerate(encabezados)}
            if "timestamp" not in columnas or "original" not in columnas:
                raise ValueError("La respuesta CDX no incluye timestamp y original.")
            filas = []
            for fila in filas_json[1:]:
                if not isinstance(fila, list) or len(fila) < len(encabezados):
                    raise ValueError("CDX devolvió una fila con formato inválido.")
                mimetype = fila[columnas["mimetype"]] if "mimetype" in columnas else "text/html"
                statuscode = fila[columnas["statuscode"]] if "statuscode" in columnas else "200"
                if str(statuscode) != "200" or str(mimetype) != "text/html":
                    continue
                timestamp = str(fila[columnas["timestamp"]])
                original = str(fila[columnas["original"]])
                digest = (
                    str(fila[columnas["digest"]])
                    if "digest" in columnas
                    else hashlib.md5(f"{timestamp}|{original}".encode("utf-8")).hexdigest()
                )
                filas.append([timestamp, original, digest])
        except (ValueError, TypeError, KeyError):
            detalle = "respuesta ilegible del Archive"
            continue
        if not filas:
            detalle = "el Archive no tiene copias HTML con codigo 200"
            continue
        filas.sort(key=lambda fila: fila[0], reverse=True)
        vistos, unicas = set(excluir), []
        for fila in filas:
            if fila[2] in vistos:
                continue
            vistos.add(fila[2])
            unicas.append(fila)
        if not unicas:
            detalle = "todas las copias restantes repiten contenido ya revisado"
            continue
        return unicas[:MAX_CAPTURAS], ""
    return [], detalle


def _captura_disponible(url, estricto=False):
    """Consulta la Availability API y devuelve su captura más cercana, si existe."""
    try:
        respuesta = _get(API_DISPONIBILIDAD, {"url": url}, intentos=2)
        if respuesta is None or respuesta.status_code != 200:
            if estricto:
                estado = "sin respuesta" if respuesta is None else f"HTTP {respuesta.status_code}"
                raise ErrorConexionInternetArchive(f"Internet Archive no respondió correctamente ({estado}).")
            return None
        captura = respuesta.json().get("archived_snapshots", {}).get("closest")
        if captura and captura.get("available") and captura.get("timestamp"):
            return captura
    except ErrorConexionInternetArchive:
        raise
    except (ValueError, AttributeError) as error:
        if estricto:
            raise ErrorConexionInternetArchive("Internet Archive devolvió una respuesta ilegible.") from error
        pass
    return None


def _extraer(html):
    """Saca (titulo, texto) de un HTML."""
    soup = BeautifulSoup(html, "html.parser")

    titulo = ""
    if soup.title and soup.title.string:
        titulo = soup.title.string
    if not titulo.strip():
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            titulo = og["content"]
    if not titulo.strip():
        h1 = soup.find("h1")
        if h1:
            titulo = h1.get_text()
    titulo = " ".join(titulo.split())

    descripcion = ""
    for atributos in ({"name": "description"}, {"property": "og:description"}):
        meta = soup.find("meta", attrs=atributos)
        if meta and meta.get("content"):
            descripcion = meta["content"]
            break

    for etiqueta in soup(["script", "style", "noscript"]):
        etiqueta.decompose()
    cuerpo = " ".join(soup.get_text(" ").split())
    texto = " ".join((descripcion + " " + cuerpo).split())[:LARGO_TEXTO]
    return titulo, texto


def _dominio(url):
    u = url.strip()
    host = urlparse(u if u.startswith(("http://", "https://")) else "https://" + u).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _motivo_rechazo(titulo, texto, url_vieja):
    """Devuelve por qué la copia no sirve, o None si sirve."""
    t = titulo.lower()
    if len(titulo) < 3:
        return "sin titulo"
    if any(malo in t for malo in TITULOS_INUTILES):
        return "titulo inutil"
    if t.strip(" !.") in TITULOS_POR_DEFECTO:
        return "pagina por defecto de un servidor"
    if len(texto) < MIN_TEXTO:
        return "casi sin texto"
    if t == _dominio(url_vieja):
        return "el titulo es solo el dominio (pagina estacionada)"
    if any(f in texto.lower()[:300] for f in FRASES_ESTACIONADA):
        return "pagina de dominio en venta o estacionado"
    return None


def obtener_metadatos(url_vieja, verbose=False, estricto=False):
    """Recupera metadatos históricos.

    Con `estricto=True`, eleva ErrorConexionInternetArchive cuando el servicio
    no responde o su respuesta no permite determinar si existe una captura.
    El modo predeterminado conserva la compatibilidad histórica y devuelve None.
    """
    os.makedirs(CARPETA_CACHE, exist_ok=True)
    clave = hashlib.md5(url_vieja.encode("utf-8")).hexdigest()
    ruta = os.path.join(CARPETA_CACHE, f"meta_{clave}.json")

    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)

    # La Availability API proporciona una primera captura de forma sencilla.
    # Si falla, CDX todavía puede responder y se usa como alternativa.
    if estricto:
        try:
            captura = _captura_disponible(url_vieja, estricto=True)
        except ErrorConexionInternetArchive:
            captura = None
    else:
        captura = _captura_disponible(url_vieja)
    if captura:
        timestamp = captura["timestamp"]
        original = captura.get("url") or url_vieja
        r = _get(
            f"https://web.archive.org/web/{timestamp}id_/{original}",
            intentos=2,
            timeout=15,
        )
        if r is not None and r.status_code == 200:
            titulo, texto = _extraer(r.content)
            if _motivo_rechazo(titulo, texto, url_vieja) is None:
                meta = {"url": url_vieja, "titulo": titulo, "texto": texto, "fecha_copia": timestamp}
                with open(ruta, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                return meta

    # Si la captura más cercana no tiene contenido útil, el índice CDX permite
    # buscar capturas históricas anteriores y omitir copias repetidas.
    hasta = None
    vistos = set()
    error_descarga_captura = False
    for ronda in range(MAX_RONDAS):
        capturas, detalle = _capturas(url_vieja, hasta, vistos)
        if verbose:
            print(f"    ronda {ronda + 1}: {len(capturas)} copias distintas por revisar")
        if not capturas:
            if verbose:
                print(f"    motivo: {detalle}")
            if estricto and any(texto in detalle for texto in (
                "no hubo respuesta", "respondio HTTP", "respuesta ilegible", "respuesta vacia"
            )):
                raise ErrorConexionInternetArchive("Internet Archive no pudo completar la búsqueda de capturas.")
            return None

        for timestamp, original, digest in capturas:
            vistos.add(digest)
            time.sleep(PAUSA)
            # El sufijo id_ pide la página original, sin la barra del Archive
            r = _get(
                f"https://web.archive.org/web/{timestamp}id_/{original}",
                intentos=2,
                timeout=15,
            )
            if r is None or r.status_code != 200:
                error_descarga_captura = True
                if verbose:
                    estado = "sin respuesta" if r is None else f"HTTP {r.status_code}"
                    print(f"    {timestamp}: no se pudo descargar ({estado})")
                continue
            titulo, texto = _extraer(r.content)
            motivo = _motivo_rechazo(titulo, texto, url_vieja)
            if motivo:
                if verbose:
                    print(f"    {timestamp}: descartada ({motivo}) | {titulo[:50]}")
                continue
            meta = {
                "url": url_vieja,
                "titulo": titulo,
                "texto": texto,
                "fecha_copia": timestamp,
            }
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            return meta

        # Ninguna sirvió: la siguiente ronda empieza justo antes de la más antigua
        hasta = _un_segundo_antes(capturas[-1][0])
    if estricto and error_descarga_captura:
        raise ErrorConexionInternetArchive("Internet Archive encontró capturas, pero no pudo descargarlas.")
    return None


if __name__ == "__main__":
    for fila in leer_enlaces():
        print(f"[{fila['id']}] {fila['url_vieja']}")
        meta = obtener_metadatos(fila["url_vieja"].strip(), verbose=True)
        if meta is None:
            print("    -> sin metadatos utiles")
        else:
            print(f"    copia : {meta['fecha_copia']}")
            print(f"    titulo: {meta['titulo']}")
            print(f"    texto : {meta['texto'][:150]}")
        time.sleep(1)
