"""Pruebas de candidatos con respuestas simuladas: no consumen créditos Tavily."""
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from src import candidatos


METADATOS = {
    "url": "https://old.example.org/page",
    "titulo": "Historical Project",
    "texto": "Historical Project software documentation and user guide",
}


def respuesta(status=200, datos=None, texto=""):
    return Mock(status_code=status, json=Mock(return_value=datos), text=texto)


class ConsultaTests(unittest.TestCase):
    def test_consulta_default_usa_titulo_y_dominio_historico(self):
        consulta = candidatos.armar_consulta(METADATOS)
        self.assertIn("Historical Project", consulta)
        self.assertIn("old", consulta)

    def test_consulta_titulo_texto_usa_texto_historico(self):
        consulta = candidatos.armar_consulta(METADATOS, "titulo+texto")
        self.assertIn("Historical Project", consulta)
        self.assertIn("software documentation", consulta)

    def test_modos_anteriores_se_conservan_y_consulta_tiene_limite(self):
        self.assertEqual(candidatos.armar_consulta(METADATOS, "titulo"), "Historical Project")
        consulta = candidatos.armar_consulta(METADATOS, "titulo+dominio")
        self.assertIn("old", consulta)
        titulo_ya_contiene_dominio = {**METADATOS, "titulo": "Old Historical Project"}
        self.assertEqual(
            candidatos.armar_consulta(titulo_ya_contiene_dominio, "titulo+dominio"),
            "Old Historical Project",
        )
        largos = {**METADATOS, "texto": "palabra " * 1000}
        self.assertLessEqual(len(candidatos.armar_consulta(largos)), candidatos.LARGO_CONSULTA)

    def test_consulta_sin_metadatos_y_modo_desconocido_fallan_claramente(self):
        with self.assertRaisesRegex(ValueError, "no contienen"):
            candidatos.armar_consulta({"titulo": "", "texto": ""})
        with self.assertRaisesRegex(ValueError, "Modo desconocido"):
            candidatos.armar_consulta(METADATOS, "desconocido")


class BusquedaTests(unittest.TestCase):
    @patch("src.candidatos._clave_api", return_value="fake-key")
    @patch("src.candidatos.requests.post")
    def test_busqueda_valida_configuracion_y_retorna_resultados(self, post, _clave):
        datos = {"results": [{"url": "https://new.example.org/", "title": "New"}]}
        post.return_value = respuesta(datos=datos)
        self.assertEqual(candidatos._buscar("consulta", "old.example.org"), datos["results"])
        argumentos = post.call_args.kwargs
        self.assertEqual(argumentos["json"]["query"], "consulta")
        self.assertEqual(argumentos["json"]["max_results"], 10)
        self.assertEqual(argumentos["json"]["exclude_domains"], ["old.example.org"])
        self.assertEqual(argumentos["timeout"], candidatos.TIMEOUT)
        self.assertEqual(argumentos["headers"]["Authorization"], "Bearer fake-key")

    @patch("src.candidatos._clave_api", return_value="fake-key")
    @patch("src.candidatos.requests.post")
    def test_respuesta_vacia_es_valida(self, post, _clave):
        post.return_value = respuesta(datos={"results": []})
        self.assertEqual(candidatos._buscar("consulta", "old.example.org"), [])

    @patch("src.candidatos.time.sleep")
    @patch("src.candidatos._clave_api", return_value="fake-key")
    @patch("src.candidatos.requests.post")
    def test_reintenta_rate_limit(self, post, _clave, _sleep):
        post.side_effect = [respuesta(429), respuesta(datos={"results": []})]
        self.assertEqual(candidatos._buscar("consulta", "old.example.org"), [])
        self.assertEqual(post.call_count, 2)

    @patch("src.candidatos._clave_api", return_value="fake-key")
    @patch("src.candidatos.requests.post", side_effect=requests.Timeout())
    def test_error_de_red_se_convierte_en_error_claro(self, _post, _clave):
        with self.assertRaisesRegex(RuntimeError, "Timeout"):
            candidatos._buscar("consulta", "old.example.org", intentos=1)

    @patch("src.candidatos._clave_api", return_value="fake-key")
    @patch("src.candidatos.requests.post")
    def test_error_http_y_json_malformado(self, post, _clave):
        post.return_value = respuesta(401, datos={"detail": "invalid key"}, texto="unauthorized")
        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            candidatos._buscar("consulta", "old.example.org", intentos=1)
        post.return_value = Mock(status_code=200, json=Mock(side_effect=ValueError()), text="{")
        with self.assertRaisesRegex(RuntimeError, "JSON ilegible"):
            candidatos._buscar("consulta", "old.example.org", intentos=1)

    @patch("src.candidatos._clave_api", return_value="fake-key")
    @patch("src.candidatos.requests.post")
    def test_schema_de_respuesta_invalido(self, post, _clave):
        post.return_value = respuesta(datos={"results": {"url": "https://example.org"}})
        with self.assertRaisesRegex(RuntimeError, "lista 'results'"):
            candidatos._buscar("consulta", "old.example.org", intentos=1)


class CandidatosTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_patch = patch("src.candidatos.CARPETA_CACHE", self.tmp.name)
        self.cache_patch.start()

    def tearDown(self):
        self.cache_patch.stop()
        self.tmp.cleanup()

    def test_filtra_urls_invalidas_deduplica_y_conserva_urls_distintas(self):
        crudos = [
            {"url": "https://NEW.example.org:443/path", "title": "A", "content": "one"},
            {"url": "https://new.EXAMPLE.org/path", "title": "A duplicate", "content": "same URL"},
            {"url": "https://new.example.org/Path", "title": "Case-sensitive path"},
            {"url": "https://new.example.org/path?version=2", "title": "Different query"},
            {"url": "http://old.example.org/page", "title": "Old domain"},
            {"url": "ftp://new.example.org/file", "title": "Wrong scheme"},
            {"url": "https:///missing-host", "title": "Missing host"},
            {"url": "https://bad host.example/path", "title": "Whitespace"},
            {"url": "not a result"},
        ]
        with patch("src.candidatos._buscar", return_value=crudos) as buscar:
            items = candidatos.generar_candidatos(METADATOS)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["url"], "https://new.example.org/path")
        self.assertEqual(items[1]["url"], "https://new.example.org/Path")
        self.assertEqual(items[2]["url"], "https://new.example.org/path?version=2")
        self.assertEqual([item["posicion_buscador"] for item in items], [1, 2, 3])
        buscar.assert_called_once()

    def test_cache_se_reutiliza_y_resultado_vacio_se_cachea(self):
        with patch("src.candidatos._buscar", return_value=[]) as buscar:
            self.assertEqual(candidatos.generar_candidatos(METADATOS), [])
            self.assertEqual(candidatos.generar_candidatos(METADATOS), [])
        buscar.assert_called_once()

    def test_cache_malformada_se_recupera_consultando_api(self):
        consulta = candidatos.armar_consulta(METADATOS)
        viejo = candidatos.dominio(METADATOS["url"])
        digest = hashlib.md5(f"{consulta}|{viejo}".encode("utf-8")).hexdigest()
        ruta = os.path.join(self.tmp.name, f"cand_{digest}.json")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("{")
        respuesta_api = [{"url": "https://new.example.org/", "title": "New"}]
        with patch("src.candidatos._buscar", return_value=respuesta_api) as buscar:
            items = candidatos.generar_candidatos(METADATOS)
        buscar.assert_called_once()
        self.assertEqual(len(items), 1)
        with open(ruta, encoding="utf-8") as f:
            self.assertEqual(json.load(f), respuesta_api)


if __name__ == "__main__":
    unittest.main()
