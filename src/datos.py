"""Lectura del conjunto de prueba (datos/enlaces.csv)."""
import csv
from urllib.parse import urlparse


def leer_enlaces(ruta="datos/enlaces.csv"):
    """Devuelve la lista de filas del CSV como diccionarios.

    Detecta solo si el archivo usa coma o punto y coma como separador
    (Excel en español suele guardar con punto y coma).
    """
    with open(ruta, encoding="utf-8-sig") as f:
        primera = f.readline()
        f.seek(0)
        sep = ";" if primera.count(";") > primera.count(",") else ","
        return [
            fila
            for fila in csv.DictReader(f, delimiter=sep)
            if (fila.get("url_vieja") or "").strip()
        ]


def dominio(url):
    """Devuelve el dominio de una URL en minúsculas y sin 'www.'."""
    u = url.strip()
    host = urlparse(u if u.startswith(("http://", "https://")) else "https://" + u).netloc.lower()
    return host[4:] if host.startswith("www.") else host
