"""Fase 1: verificar los enlaces del conjunto de prueba.

Para cada fila de datos/enlaces.csv revisa:
  1. Si el Internet Archive tiene copia de la URL vieja.
  2. Qué pasa hoy al abrir la URL vieja (si sigue redirigiendo al destino correcto).
  3. Si la URL nueva correcta realmente responde.
Guarda el resultado en resultados/verificacion.csv

Uso (desde la carpeta del proyecto):
    python -m src.verificar_enlaces
"""
import csv
import time
from urllib.parse import urlparse

import requests

RUTA_CSV = "datos/enlaces.csv"
RUTA_SALIDA = "resultados/verificacion.csv"
CABECERAS = {"User-Agent": "Mozilla/5.0 (pre-experimento academico UMSS)"}
TIMEOUT = 20
PAUSA = 1.0  # segundos entre enlaces, para no saturar los servidores


def con_esquema(url):
    url = url.strip()
    return url if url.startswith(("http://", "https://")) else "https://" + url


def dominio(url):
    host = urlparse(con_esquema(url)).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def copia_en_archive(url):
    """Devuelve (hay_copia, fecha). hay_copia es None si la consulta falló."""
    try:
        r = requests.get(
            "https://archive.org/wayback/available",
            params={"url": url},
            headers=CABECERAS,
            timeout=TIMEOUT,
        )
        snap = r.json().get("archived_snapshots", {}).get("closest")
    except (requests.RequestException, ValueError):
        return None, ""
    if snap and snap.get("available"):
        return True, snap["timestamp"]
    return False, ""


def abrir(url, intentos=3):
    """Devuelve (codigo_http, url_final). Si falla: (None, nombre_del_error).

    Reintenta si hay error de red o error del servidor (5xx), porque estos
    sitios suelen fallar de forma intermitente.
    """
    ultimo = (None, "SinRespuesta")
    for i in range(intentos):
        try:
            r = requests.get(
                con_esquema(url), headers=CABECERAS, timeout=TIMEOUT, allow_redirects=True
            )
            if r.status_code < 500:
                return r.status_code, r.url
            ultimo = (r.status_code, r.url)
        except requests.RequestException as e:
            ultimo = (None, type(e).__name__)
        if i < intentos - 1:
            time.sleep(2)
    return ultimo


def veredicto(hay_copia, cod_vieja, final_vieja, cod_nueva, url_nueva):
    if hay_copia is None:
        return "REVISAR (no se pudo consultar el Internet Archive)"
    if not hay_copia:
        return "DESCARTAR (sin copia en el Internet Archive)"
    if cod_nueva is None or cod_nueva >= 400:
        return "REVISAR (la URL nueva no responde)"
    if cod_vieja is not None and cod_vieja < 400 and dominio(final_vieja) == dominio(url_nueva):
        return "FACIL (la URL vieja aun redirige a la nueva)"
    return "BUENO"


def main():
    with open(RUTA_CSV, encoding="utf-8-sig") as f:
        primera = f.readline()
        f.seek(0)
        sep = ";" if primera.count(";") > primera.count(",") else ","
        filas = [
            fila
            for fila in csv.DictReader(f, delimiter=sep)
            if (fila.get("url_vieja") or "").strip()
        ]

    if not filas:
        print("datos/enlaces.csv no tiene enlaces todavía.")
        return

    resultados = []
    for fila in filas:
        vieja = fila["url_vieja"].strip()
        nueva = fila["url_nueva_correcta"].strip()
        print(f"[{fila['id']}] {vieja} ...", flush=True)

        hay_copia, fecha = copia_en_archive(con_esquema(vieja))
        cod_vieja, final_vieja = abrir(vieja)
        cod_nueva, _ = abrir(nueva)
        v = veredicto(hay_copia, cod_vieja, final_vieja, cod_nueva, nueva)

        print(f"    -> {v}")
        resultados.append({
            "id": fila["id"],
            "url_vieja": vieja,
            "tipo_cambio": fila.get("tipo_cambio", ""),
            "copia_archive": fecha if hay_copia else ("ERROR" if hay_copia is None else "NO"),
            "vieja_codigo": cod_vieja,
            "vieja_final": final_vieja,
            "nueva_codigo": cod_nueva,
            "veredicto": v,
        })
        time.sleep(PAUSA)

    with open(RUTA_SALIDA, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(resultados[0].keys()))
        w.writeheader()
        w.writerows(resultados)

    print("\nResumen:")
    for etiqueta in ("BUENO", "FACIL", "DESCARTAR", "REVISAR"):
        n = sum(1 for r in resultados if r["veredicto"].startswith(etiqueta))
        print(f"  {etiqueta}: {n}")
    print(f"\nDetalle guardado en {RUTA_SALIDA}")


if __name__ == "__main__":
    main()