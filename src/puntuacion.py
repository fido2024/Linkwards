"""Fase 4: puntuar cada candidato y ordenarlos.

Componentes de la nota (cada uno entre 0 y 1):
    - similitud del nombre de dominio (Levenshtein)
    - similitud del título
    - reglas de proximidad (misma ruta final, nombre del sitio en el nuevo dominio)
"""

PESOS = {"dominio": 1.0, "titulo": 1.0, "proximidad": 1.0}


def puntuar_candidato(metadatos, candidato):
    raise NotImplementedError("Fase 4")


def ordenar_candidatos(metadatos, candidatos):
    raise NotImplementedError("Fase 4")
