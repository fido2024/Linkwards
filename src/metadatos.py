"""Fase 2: recuperar qué era el enlace (título y texto) desde el Internet Archive.

Forma del resultado (diccionario):
    {
        "url": str,          # URL vieja
        "titulo": str,       # título de la página archivada
        "texto": str,        # fragmento de texto de la página archivada
        "fecha_copia": str,  # fecha de la copia usada
    }
Devuelve None si el Internet Archive no tiene copia.
"""


def obtener_metadatos(url_vieja):
    raise NotImplementedError("Fase 2")
