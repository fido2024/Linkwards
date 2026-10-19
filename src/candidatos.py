"""Fase 3: generar el conjunto acotado de páginas candidatas (top N).

Forma de cada candidato (diccionario):
    {
        "url": str,
        "titulo": str,
        "snippet": str,
        "posicion_buscador": int,   # 1 = primer resultado del buscador
    }
"""

MAX_CANDIDATOS = 10


def generar_candidatos(metadatos):
    raise NotImplementedError("Fase 3")
