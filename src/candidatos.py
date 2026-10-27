"""Fase 3: generar el conjunto acotado de páginas candidatas (top N).

A partir del título y el texto histórico del enlace viejo (Fase 2) se hace UNA
búsqueda con la API de Tavily y se conservan como máximo MAX_CANDIDATOS URLs
HTTP(S) válidas y únicas, excluyendo el dominio viejo.

Forma de cada candidato (diccionario):
    {
        "url": str,
        "titulo": str,
        "snippet": str,
        "posicion_buscador": int,   # 1 = primer resultado del buscador
    }

La clave de la API se lee de la variable de entorno TAVILY_API_KEY o de un
archivo .env en la carpeta del proyecto (línea: TAVILY_API_KEY=tvly-...).
Las respuestas se guardan en datos/cache/ para no gastar créditos de más.

Uso para probar con todo el CSV:
    python -m src.candidatos                    (consulta = título + texto)
    python -m src.candidatos titulo             (consulta = título)
    python -m src.candidatos titulo+dominio     (consulta = título + nombre del sitio)
"""
import hashlib
import json
import os
import re
import time
import argparse
from urllib.parse import urlsplit, urlunsplit

import requests

from src.datos import dominio, leer_enlaces
from src.metadatos import obtener_metadatos

URL_API = "https://api.tavily.com/search"
MAX_CANDIDATOS = 10
CARPETA_CACHE = "datos/cache"
LARGO_CONSULTA = 200
TIMEOUT = 30
ESPERA_429 = 5


def _clave_api():
    clave = os.environ.get("TAVILY_API_KEY", "").strip()
    if not clave and os.path.exists(".env"):
        with open(".env", encoding="utf-8-sig") as f:
            for linea in f:
                nombre, _, valor = linea.strip().partition("=")
                if nombre.strip() == "TAVILY_API_KEY":
                    clave = valor.strip().strip('"').strip("'")
    if not clave:
        raise RuntimeError(
            "Falta la clave de Tavily. Crea un archivo .env en la carpeta del "
            "proyecto con la línea TAVILY_API_KEY=tvly-... (sin comillas)."
        )
    return clave


def _buscar(consulta, dominio_excluido, intentos=3):
    """Llama a Tavily con timeout, reintentos de red/429/5xx y valida JSON."""
    if intentos < 1:
        raise ValueError("intentos debe ser al menos 1")
    cuerpo = {
        "query": consulta,
        "max_results": MAX_CANDIDATOS,
        "search_depth": "basic",
        "exclude_domains": [dominio_excluido],
    }
    cabeceras = {"Authorization": f"Bearer {_clave_api()}"}
    for i in range(intentos):
        try:
            r = requests.post(URL_API, json=cuerpo, headers=cabeceras, timeout=TIMEOUT)
        except requests.RequestException as error:
            if i + 1 == intentos:
                raise RuntimeError(
                    f"No se pudo conectar con Tavily ({type(error).__name__}) tras {intentos} intentos."
                ) from error
            time.sleep(ESPERA_429 * (i + 1))
            continue

        if r.status_code == 429 or r.status_code >= 500:
            if i + 1 < intentos:
                time.sleep(ESPERA_429 * (i + 1))
                continue
        if r.status_code != 200:
            raise RuntimeError(f"Tavily respondió HTTP {r.status_code}: {r.text[:200]}")
        try:
            datos = r.json()
        except ValueError as error:
            raise RuntimeError("Tavily devolvió una respuesta JSON ilegible.") from error
        resultados = datos.get("results") if isinstance(datos, dict) else None
        if not isinstance(resultados, list):
            raise RuntimeError("Tavily devolvió una respuesta sin una lista 'results'.")
        return resultados
    raise RuntimeError(f"Tavily no respondió después de {intentos} intentos (HTTP {r.status_code}).")


MODOS = ("titulo", "titulo+dominio", "titulo+texto")
MODO_PREDETERMINADO = "titulo+dominio"


def armar_consulta(metadatos, modo=MODO_PREDETERMINADO):
    """Construye el texto de búsqueda.

    - "titulo+texto": título y fragmento histórico de la página.
    - "titulo": solo el título de la página vieja.
    - "titulo+dominio": el título más el nombre del sitio viejo (por ejemplo
      "pypi" en pypi.python.org), si el título todavía no lo menciona.
    """
    if modo not in MODOS:
        raise ValueError(f"Modo desconocido: {modo}. Usa uno de: {', '.join(MODOS)}")
    titulo = " ".join(str(metadatos.get("titulo", "")).split())
    texto = " ".join(str(metadatos.get("texto", "")).split())
    if modo == "titulo+texto" and texto:
        # El fragmento extraído suele empezar repitiendo el título.
        if titulo:
            texto = re.sub(re.escape(titulo), " ", texto, count=1, flags=re.IGNORECASE).strip()
        titulo = f"{titulo} {texto}".strip()
    if modo == "titulo+dominio":
        url_original = metadatos.get("url")
        nombre = dominio(url_original).split(".")[0] if isinstance(url_original, str) and url_original.strip() else ""
        if nombre and nombre.lower() not in titulo.lower():
            titulo = f"{titulo} {nombre}"
    consulta = titulo[:LARGO_CONSULTA].strip()
    if not consulta:
        raise ValueError("Los metadatos no contienen título ni texto para buscar.")
    return consulta


def _normalizar_url(url):
    """Valida HTTP(S) y normaliza esquema, host y puerto predeterminado.

    Conserva ruta, query y fragmento para no colapsar URLs que puedan apuntar a
    recursos o estados distintos.
    """
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url or any(caracter.isspace() for caracter in url):
        return None
    try:
        partes = urlsplit(url)
        esquema = partes.scheme.lower()
        host = partes.hostname
        puerto = partes.port
    except ValueError:
        return None
    if esquema not in ("http", "https") or not host or partes.username or partes.password:
        return None
    host = host.lower()
    if ":" in host:  # IPv6 necesita corchetes al reconstruir netloc
        host = f"[{host}]"
    netloc = host
    if puerto and not (esquema == "http" and puerto == 80) and not (esquema == "https" and puerto == 443):
        netloc = f"{netloc}:{puerto}"
    path = partes.path or "/"
    return urlunsplit((esquema, netloc, path, partes.query, partes.fragment))


def generar_candidatos(metadatos, modo=MODO_PREDETERMINADO):
    consulta = armar_consulta(metadatos, modo)
    viejo = dominio(metadatos["url"])

    os.makedirs(CARPETA_CACHE, exist_ok=True)
    ruta = ruta_cache_candidatos(metadatos, modo)

    crudos = None
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as f:
                cache = json.load(f)
            if isinstance(cache, list):
                crudos = cache
        except (OSError, ValueError):
            # Una caché incompleta no impide consultar de nuevo al proveedor.
            crudos = None
    if crudos is None:
        crudos = _buscar(consulta, viejo)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(crudos, f, ensure_ascii=False, indent=2)

    candidatos = []
    urls_vistas = set()
    for r in crudos:
        if not isinstance(r, dict):
            continue
        url = _normalizar_url(r.get("url", ""))
        if not url:
            continue
        # _normalizar_url ya unifica esquema/host/puerto; ruta y query siguen
        # siendo sensibles a mayúsculas y se mantienen para no perder recursos.
        clave_url = url
        if clave_url in urls_vistas or dominio(url) == viejo:
            continue
        urls_vistas.add(clave_url)
        candidatos.append({
            "url": url,
            "titulo": r.get("title", ""),
            "snippet": r.get("content", ""),
            "posicion_buscador": len(candidatos) + 1,
        })
    return candidatos[:MAX_CANDIDATOS]


def ruta_cache_candidatos(metadatos, modo=MODO_PREDETERMINADO):
    """Ruta del archivo de caché para los metadatos y modo de búsqueda dados."""
    consulta = armar_consulta(metadatos, modo)
    viejo = dominio(metadatos["url"])
    clave = hashlib.md5(f"{consulta}|{viejo}".encode("utf-8")).hexdigest()
    return os.path.join(CARPETA_CACHE, f"cand_{clave}.json")


def posicion_correcta(candidatos, url_nueva):
    """Posición (1, 2, ...) del primer candidato cuyo dominio es EXACTAMENTE el
    dominio correcto (ignorando 'www.'), o None si no aparece.

    Un subdominio distinto (por ejemplo acrjournals.onlinelibrary.wiley.com
    frente a onlinelibrary.wiley.com) no cuenta como acierto.
    """
    nuevo = dominio(url_nueva)
    for c in candidatos:
        if dominio(c["url"]) == nuevo:
            return c["posicion_buscador"]
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera candidatos con Tavily para los enlaces del CSV.")
    parser.add_argument("modo_posicional", nargs="?", choices=MODOS, help="Modo (compatibilidad con la CLI anterior)")
    parser.add_argument("--modo", choices=MODOS, default=None, help="Modo de consulta; predeterminado: titulo+dominio")
    args = parser.parse_args()
    if args.modo and args.modo_posicional:
        parser.error("indica el modo con --modo o como argumento posicional, no ambos")
    modo = args.modo or args.modo_posicional or MODO_PREDETERMINADO
    print(f"Modo de consulta: {modo}\n")
    resumen = []
    for fila in leer_enlaces():
        vieja = fila["url_vieja"].strip()
        print(f"[{fila['id']}] {vieja}  ->  esperado: {fila['url_nueva_correcta'].strip()}")
        meta = obtener_metadatos(vieja)
        if meta is None:
            print("    sin metadatos utiles (se omite)")
            continue
        print(f"    consulta: {armar_consulta(meta, modo)}")
        candidatos = generar_candidatos(meta, modo)
        pos = posicion_correcta(candidatos, fila["url_nueva_correcta"])
        for c in candidatos:
            marca = "  <-- CORRECTO" if c["posicion_buscador"] == pos else ""
            print(f"    {c['posicion_buscador']:>2}. {c['url'][:70]}{marca}")
        print(f"    => correcto entre los candidatos: {'SI, posicion ' + str(pos) if pos else 'NO'}")
        resumen.append(pos)
        time.sleep(3)

    n = len(resumen)
    if n:
        print(f"\nResumen ({n} enlaces con metadatos, modo {modo}):")
        print(f"  Cobertura (correcto entre los candidatos): {sum(p is not None for p in resumen)}/{n}")
        print(f"  Buscador en 1.er lugar : {sum(p == 1 for p in resumen)}/{n}")
        print(f"  Buscador entre los 5   : {sum(p is not None and p <= 5 for p in resumen)}/{n}")  # Tavily permite unas 20 consultas por minuto
