"""Pruebas de evaluación con datos sintéticos aislados; no consultan APIs."""
import csv
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src import candidatos, evaluacion, metadatos


class EvaluacionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = os.path.join(self.tmp.name, "cache")
        self.salida = os.path.join(self.tmp.name, "resultados")
        os.makedirs(self.cache)
        self.patches = [
            patch("src.candidatos.CARPETA_CACHE", self.cache),
            patch("src.metadatos.CARPETA_CACHE", self.cache),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def _guardar_meta(self, url, titulo="Historical Guide", texto="Historical Guide installation guide"):
        meta = {"url": url, "titulo": titulo, "texto": texto}
        digest = hashlib.md5(url.encode("utf-8")).hexdigest()
        ruta = os.path.join(self.cache, f"meta_{digest}.json")
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump(meta, archivo)
        return meta

    def _guardar_candidatos(self, meta, resultados):
        ruta = candidatos.ruta_cache_candidatos(meta)
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump(resultados, archivo)
        return ruta

    def _csv(self, filas):
        ruta = os.path.join(self.tmp.name, "enlaces.csv")
        with open(ruta, "w", newline="", encoding="utf-8") as archivo:
            escritor = csv.DictWriter(
                archivo,
                fieldnames=["id", "url_vieja", "url_nueva_correcta", "tipo_cambio"],
                delimiter=";",
            )
            escritor.writeheader()
            escritor.writerows(filas)
        return ruta

    def test_metricas_comparan_busqueda_y_heuristica_y_guardan_archivos(self):
        vieja1 = "https://legacy.example.org/docs/install"
        nueva1 = "https://legacy-site.example/docs/install"
        meta1 = self._guardar_meta(vieja1)
        self._guardar_candidatos(meta1, [
            {"url": "https://unrelated.invalid/other", "title": "Unrelated Page", "content": ""},
            {"url": nueva1, "title": "Historical Guide", "content": ""},
        ])

        vieja2 = "https://empty.example.org/"
        self._guardar_candidatos(self._guardar_meta(vieja2), [])

        vieja3 = "https://missing.example.org/"
        meta3 = self._guardar_meta(vieja3)
        vieja4 = "https://corrupt.example.org/"
        meta4 = self._guardar_meta(vieja4)
        with open(candidatos.ruta_cache_candidatos(meta4), "w", encoding="utf-8") as archivo:
            archivo.write("{")

        filas = [
            {"id": "1", "url_vieja": vieja1, "url_nueva_correcta": nueva1, "tipo_cambio": "dominio"},
            {"id": "2", "url_vieja": vieja2, "url_nueva_correcta": "https://empty-new.example.org/", "tipo_cambio": "dominio"},
            {"id": "3", "url_vieja": vieja3, "url_nueva_correcta": "https://missing-new.example.org/", "tipo_cambio": "dominio"},
            {"id": "4", "url_vieja": "", "url_nueva_correcta": "https://incomplete.example.org/", "tipo_cambio": "dominio"},
            {"id": "5", "url_vieja": vieja4, "url_nueva_correcta": "https://corrupt-new.example.org/", "tipo_cambio": "dominio"},
        ]
        ruta_csv = self._csv(filas)

        with patch("src.candidatos._buscar", side_effect=AssertionError("no debe buscar")), patch("builtins.print"):
            resumen = evaluacion.evaluar(ruta_csv, directorio_resultados=self.salida)

        self.assertEqual(resumen["variante_puntuacion"], "levenshtein")
        self.assertEqual(resumen["registros_csv"], 5)
        self.assertEqual(resumen["registros_evaluables_con_respuesta"], 2)
        self.assertEqual(resumen["cobertura"], {"aciertos": 1, "denominador": 2, "tasa": 0.5})
        self.assertEqual(resumen["top1_busqueda"]["aciertos"], 0)
        self.assertEqual(resumen["top1_heuristico"]["aciertos"], 1)
        self.assertEqual(resumen["registros_sin_candidatos_validos"], 1)
        self.assertEqual(resumen["registros_sin_cache_candidatos"], 1)
        self.assertEqual(resumen["registros_con_error"], 0)
        nombre = "evaluacion_titulo_mas_dominio_levenshtein"
        self.assertTrue(os.path.isfile(os.path.join(self.salida, f"{nombre}.csv")))
        with open(os.path.join(self.salida, f"{nombre}.json"), encoding="utf-8") as archivo:
            documento = json.load(archivo)
        self.assertEqual(documento["tipo_resultado"], "cache_solo_sin_consultas_externas")
        self.assertIn("cache_candidatos_invalida", [fila["estado"] for fila in documento["registros"]])

    def test_sin_registros_evaluables_deja_tasas_como_none(self):
        ruta_csv = self._csv([{
            "id": "1", "url_vieja": "", "url_nueva_correcta": "https://destination.example/", "tipo_cambio": "",
        }])
        with patch("builtins.print"):
            resumen = evaluacion.evaluar(ruta_csv, directorio_resultados=self.salida)
        self.assertEqual(resumen["registros_evaluables_con_respuesta"], 0)
        self.assertIsNone(resumen["cobertura"]["tasa"])
        self.assertEqual(resumen["registros_con_urls_utilizables"], 0)

    def test_url_con_puerto_invalido_no_es_utilizable(self):
        self.assertFalse(evaluacion._url_utilizable("https://example.org:puerto/"))
        self.assertTrue(evaluacion._url_utilizable("example.org/recurso"))

    @patch("src.evaluacion.metadatos_mod.obtener_metadatos")
    def test_error_archive_se_distingue_de_metadatos_ausentes(self, obtener_metadatos):
        vieja = "https://legacy.example.org/"
        ruta_csv = self._csv([{
            "id": "1",
            "url_vieja": vieja,
            "url_nueva_correcta": "https://current.example.org/",
            "tipo_cambio": "dominio",
        }])
        obtener_metadatos.side_effect = metadatos.ErrorConexionInternetArchive(
            "fallo simulado"
        )

        with patch("builtins.print"):
            resumen = evaluacion.evaluar(
                ruta_csv,
                directorio_resultados=self.salida,
                buscar_faltantes=True,
            )

        obtener_metadatos.assert_called_once_with(vieja, estricto=True)
        self.assertEqual(resumen["registros_con_error"], 1)
        with open(os.path.join(self.salida, "evaluacion_titulo_mas_dominio_levenshtein.json"), encoding="utf-8") as archivo:
            documento = json.load(archivo)
        self.assertEqual(documento["registros"][0]["estado"], "error_metadatos")

    def test_variante_levenshtein_usa_cache_sin_llamadas_de_red_y_archivo_separado(self):
        vieja = "https://legacy.example.org/docs/install"
        nueva = "https://legacy-site.example/docs/install"
        meta = self._guardar_meta(vieja)
        self._guardar_candidatos(meta, [
            {"url": nueva, "title": "Historical Guide", "content": ""},
            {"url": "https://unrelated.invalid/other", "title": "Unrelated", "content": ""},
        ])
        ruta_csv = self._csv([{
            "id": "1", "url_vieja": vieja, "url_nueva_correcta": nueva, "tipo_cambio": "dominio",
        }])

        with patch("src.candidatos._buscar", side_effect=AssertionError("red Tavily inesperada")), \
             patch("src.metadatos.requests.get", side_effect=AssertionError("red Archive inesperada")), \
             patch("builtins.print"):
            resumen = evaluacion.evaluar(
                ruta_csv,
                directorio_resultados=self.salida,
                variante="levenshtein",
            )

        self.assertEqual(resumen["variante_puntuacion"], "levenshtein")
        self.assertEqual(resumen["registros_evaluables_con_respuesta"], 1)
        nombre = "evaluacion_titulo_mas_dominio_levenshtein"
        self.assertTrue(os.path.isfile(os.path.join(self.salida, f"{nombre}.csv")))
        self.assertTrue(os.path.isfile(os.path.join(self.salida, f"{nombre}.json")))
        self.assertFalse(os.path.exists(os.path.join(self.salida, "evaluacion_candidatos.json")))


if __name__ == "__main__":
    unittest.main()
