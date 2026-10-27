"""Pruebas de puntuación heurística sin conexiones externas."""
import unittest
from unittest.mock import patch

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from src import puntuacion


ORIGINAL = "https://legacy.example.org/manual/install"
METADATOS = {"url": ORIGINAL, "titulo": "Example Installation Guide"}


def candidato(url, titulo="Example Installation Guide"):
    return {"url": url, "titulo": titulo, "snippet": "texto de prueba", "posicion_buscador": 1}


class PuntuacionTests(unittest.TestCase):
    def test_similitud_levenshtein_usa_distancia_normalizada_explicita(self):
        self.assertEqual(puntuacion.similitud_levenshtein("kitten", "sitting"), 100 * (1 - 3 / 7))
        self.assertEqual(Levenshtein.distance("kitten", "sitting"), 3)

    def test_similitud_levenshtein_identicas_y_cadenas_vacias(self):
        self.assertEqual(puntuacion.similitud_levenshtein("abc", "abc"), 100.0)
        self.assertEqual(puntuacion.similitud_levenshtein("", "abc"), 0.0)
        self.assertEqual(puntuacion.similitud_levenshtein("", ""), 100.0)

    def test_variante_predeterminada_conserva_rapidfuzz_ratio(self):
        item = candidato("https://new-example.net/manual/install", "Historical Install Guide")
        base = puntuacion._puntuaciones_componentes(ORIGINAL, item, METADATOS)
        explicita = puntuacion._puntuaciones_componentes(ORIGINAL, item, METADATOS, "rapidfuzz")
        self.assertEqual(base, explicita)
        self.assertEqual(base["dominio"], float(fuzz.ratio("legacy.example.org", "new-example.net")))

    def test_variante_levenshtein_aplica_a_dominio_titulo_y_ruta(self):
        item = candidato("https://legacy-site.example/manual/instal", "Example Installation Guides")
        componentes = puntuacion._puntuaciones_componentes(
            ORIGINAL, item, METADATOS, variante="levenshtein"
        )
        self.assertEqual(
            componentes["dominio"],
            puntuacion.similitud_levenshtein("legacy.example.org", "legacy-site.example"),
        )
        self.assertEqual(
            componentes["titulo"],
            puntuacion.similitud_levenshtein("example installation guide", "example installation guides"),
        )
        ruta_sim = puntuacion.similitud_levenshtein("manual/install", "manual/instal")
        self.assertEqual(componentes["proximidad"], 100 * 0.60 + ruta_sim * 0.40)

    def test_ambas_variantes_omiten_titulo_ausente_y_renormalizan_pesos(self):
        item = candidato("https://new.example.org/manual/install", "")
        baseline = puntuacion.puntuar_candidato(ORIGINAL, item, None)
        levenshtein = puntuacion.puntuar_candidato(ORIGINAL, item, None, variante="levenshtein")
        self.assertGreaterEqual(baseline, 0)
        self.assertGreaterEqual(levenshtein, 0)
        self.assertNotIn("titulo", puntuacion._puntuaciones_componentes(ORIGINAL, item, None, "levenshtein"))

    def test_coincidencia_fuerte(self):
        item = candidato("https://legacy-site.example/manual/install")
        score = puntuacion.puntuar_candidato(ORIGINAL, item, METADATOS)
        self.assertGreaterEqual(score, 85)
        self.assertLessEqual(score, 100)

    def test_coincidencia_debil(self):
        item = candidato("https://unrelated.invalid/other", "Completely Different Product")
        score = puntuacion.puntuar_candidato(ORIGINAL, item, METADATOS)
        self.assertLess(score, 35)

    def test_dominios_se_comparan_sin_incluir_rutas(self):
        candidato_url = "https://legacy.example.org/a-completely-different-route"
        componentes = puntuacion._puntuaciones_componentes(
            "https://legacy.example.org/original-route", candidato(candidato_url), METADATOS
        )
        self.assertEqual(componentes["dominio"], 100.0)
        self.assertLess(componentes["proximidad"], 100.0)

    def test_dominios_diferentes_reciben_similitud_de_host(self):
        item = candidato("https://new-example.net/manual/install")
        componentes = puntuacion._puntuaciones_componentes(ORIGINAL, item, METADATOS)
        self.assertEqual(
            componentes["dominio"],
            float(fuzz.ratio("legacy.example.org", "new-example.net")),
        )
        self.assertLess(componentes["dominio"], 100)

    def test_ruta_conservada_mejora_la_proximidad(self):
        misma = puntuacion._puntuaciones_componentes(
            ORIGINAL, candidato("https://legacy-new.example.org/manual/install"), METADATOS
        )
        distinta = puntuacion._puntuaciones_componentes(
            ORIGINAL, candidato("https://legacy-new.example.org/different/topic"), METADATOS
        )
        self.assertEqual(misma["proximidad"], 100.0)
        self.assertLess(distinta["proximidad"], misma["proximidad"])

    def test_titulo_ausente_se_omite_y_pesos_disponibles_se_renormalizan(self):
        item = candidato("https://new.example.org/", titulo="")
        componentes = puntuacion._puntuaciones_componentes(ORIGINAL, item, None)
        self.assertNotIn("titulo", componentes)
        esperado = (
            componentes["dominio"] * puntuacion.PESOS["dominio"]
            + componentes["proximidad"] * puntuacion.PESOS["proximidad"]
        ) / (puntuacion.PESOS["dominio"] + puntuacion.PESOS["proximidad"])
        self.assertEqual(puntuacion.puntuar_candidato(ORIGINAL, item, None), round(esperado, 2))

    def test_metadatos_ausentes_no_impiden_usar_url_original(self):
        item = candidato("https://new.example.org/manual/install", "")
        score = puntuacion.puntuar_candidato(ORIGINAL, item, None)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_orden_descendente_es_estable_para_duplicados_y_empates(self):
        fuerte = candidato("https://legacy-site.example/manual/install")
        debil = candidato("https://unrelated.invalid/other", "Unrelated")
        candidatos = [debil, fuerte, dict(fuerte)]
        ordenados = puntuacion.ordenar_candidatos(ORIGINAL, candidatos, METADATOS)
        notas = [item["puntuacion"] for item in ordenados]
        self.assertEqual(notas, sorted(notas, reverse=True))
        self.assertEqual([item["url"] for item in ordenados[:2]], [fuerte["url"], fuerte["url"]])
        self.assertEqual(ordenados[2]["url"], debil["url"])
        self.assertTrue(all("puntuacion" not in item for item in candidatos))

    def test_pesos_configurados_suman_uno(self):
        self.assertAlmostEqual(sum(puntuacion.PESOS.values()), 1.0)
        self.assertAlmostEqual(sum(puntuacion.PESOS_PROXIMIDAD.values()), 1.0)

    def test_pesos_invalidos_generan_error_explicito(self):
        with patch.dict(puntuacion.PESOS, {"dominio": 0.5, "titulo": 0.5, "proximidad": 0.5}):
            with self.assertRaisesRegex(ValueError, "deben sumar 1"):
                puntuacion.puntuar_candidato(ORIGINAL, candidato("https://new.example.org/"), METADATOS)


if __name__ == "__main__":
    unittest.main()
