from src.candidatos import MODO_PREDETERMINADO
from src.evaluacion import evaluar, VARIANTE_PREDETERMINADA

if __name__ == "__main__":
    print(f"Modo de consulta: {MODO_PREDETERMINADO}")
    print(f"Variante de puntuación: {VARIANTE_PREDETERMINADA}")
    evaluar(
        "datos/enlaces.csv",
        modo=MODO_PREDETERMINADO,
        variante=VARIANTE_PREDETERMINADA,
    )
