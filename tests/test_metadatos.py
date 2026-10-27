"""Pruebas locales de extracción y consulta de capturas sin acceso a red."""
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from src import metadatos


class MetadatosTests(unittest.TestCase):
    def test_extrae_titulo_descripcion_y_texto_sin_scripts(self):
        html = """<html><head><title>  Sitio de prueba </title>
        <meta name="description" content="Descripción útil"></head>
        <body><h1>Encabezado</h1><p>Contenido principal del sitio.</p>
        <script>secreto()</script></body></html>"""
        titulo, texto = metadatos._extraer(html)
        self.assertEqual(titulo, "Sitio de prueba")
        self.assertIn("Descripción útil", texto)
        self.assertIn("Contenido principal del sitio.", texto)
        self.assertNotIn("secreto", texto)

    @patch("src.metadatos._get")
    def test_consulta_availability_api(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {"archived_snapshots": {"closest": {
                "available": True,
                "timestamp": "20200102030405",
                "url": "http://example.org/",
            }}},
        )
        captura = metadatos._captura_disponible("example.org")
        self.assertEqual(captura["timestamp"], "20200102030405")
        mock_get.assert_called_once_with(
            metadatos.API_DISPONIBILIDAD, {"url": "example.org"}, intentos=2
        )

    @patch("src.metadatos._get")
    def test_api_sin_captura_devuelve_none(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200, json=lambda: {"archived_snapshots": {}}
        )
        self.assertIsNone(metadatos._captura_disponible("example.org"))

    @patch("src.metadatos._get", return_value=None)
    def test_modo_estricto_distingue_error_de_conexion_archive(self, mock_get):
        with self.assertRaises(metadatos.ErrorConexionInternetArchive):
            metadatos._captura_disponible("example.org", estricto=True)

    @patch("src.metadatos._get")
    def test_modo_estricto_conserva_none_si_api_confirma_ausencia(self, mock_get):
        mock_get.return_value = Mock(status_code=200, json=lambda: {"archived_snapshots": {}})
        self.assertIsNone(metadatos._captura_disponible("example.org", estricto=True))

    def _respuesta(self, status_code, datos=None, contenido=b""):
        return Mock(
            status_code=status_code,
            text=json.dumps(datos) if datos is not None else "error del servidor",
            content=contenido,
            json=Mock(return_value=datos),
        )

    @patch("src.metadatos._get")
    def test_cdx_json_valido_se_interpreta_por_nombre_de_columna(self, mock_get):
        datos = [
            ["timestamp", "original", "mimetype", "statuscode"],
            ["20241001010203", "https://www.overleaf.com/", "text/html", "200"],
        ]
        mock_get.return_value = self._respuesta(200, datos)

        capturas, detalle = metadatos._capturas("https://www.overleaf.com")

        self.assertEqual(detalle, "")
        self.assertEqual(capturas[0][0:2], ["20241001010203", "https://www.overleaf.com/"])
        self.assertTrue(capturas[0][2])  # digest determinista derivado si CDX no lo incluye
        parametros = mock_get.call_args.args[1]
        self.assertEqual(parametros["fl"], "timestamp,original,mimetype,statuscode,digest")

    @patch("src.metadatos._get")
    def test_cdx_error_http_se_reporta_sin_confundirlo_con_cero_capturas(self, mock_get):
        mock_get.return_value = self._respuesta(503)
        capturas, detalle = metadatos._capturas("https://www.overleaf.com")
        self.assertEqual(capturas, [])
        self.assertIn("HTTP 503", detalle)

    @patch("src.metadatos.PAUSA", 0)
    @patch("src.metadatos._get")
    def test_error_availability_fallback_a_cdx_valido_recupera_metadata(self, mock_get):
        datos = [
            ["timestamp", "original", "mimetype", "statuscode", "digest"],
            ["20241001010203", "https://www.overleaf.com/", "text/html", "200", "DIGEST1"],
        ]
        html = (
            b"<html><head><title>Overleaf, Online LaTeX Editor</title></head>"
            b"<body><p>Write and collaborate on scientific documents with Overleaf online.</p></body></html>"
        )
        mock_get.side_effect = [
            None,  # Availability API falla; la consulta continúa por CDX.
            self._respuesta(200, datos),
            self._respuesta(200, contenido=html),
        ]
        with tempfile.TemporaryDirectory() as temporal, patch.object(metadatos, "CARPETA_CACHE", temporal):
            resultado = metadatos.obtener_metadatos("https://www.overleaf.com", estricto=True)

        self.assertEqual(resultado["titulo"], "Overleaf, Online LaTeX Editor")
        self.assertEqual(resultado["fecha_copia"], "20241001010203")
        self.assertEqual(mock_get.call_count, 3)

    @patch("src.metadatos.PAUSA", 0)
    @patch("src.metadatos._get")
    def test_respuesta_cdx_vacia_es_sin_captura_no_error_de_conexion(self, mock_get):
        availability = self._respuesta(200, {"archived_snapshots": {}})
        cdx_sin_filas = self._respuesta(200, [["timestamp", "original", "mimetype", "statuscode", "digest"]])
        mock_get.side_effect = [availability, cdx_sin_filas, cdx_sin_filas]
        with tempfile.TemporaryDirectory() as temporal, patch.object(metadatos, "CARPETA_CACHE", temporal):
            resultado = metadatos.obtener_metadatos("https://www.overleaf.com", estricto=True)
        self.assertIsNone(resultado)

    @patch("src.metadatos._get")
    def test_error_availability_y_error_cdx_sigue_siendo_error_de_conexion(self, mock_get):
        mock_get.side_effect = [None, self._respuesta(503), self._respuesta(503)]
        with tempfile.TemporaryDirectory() as temporal, patch.object(metadatos, "CARPETA_CACHE", temporal):
            with self.assertRaises(metadatos.ErrorConexionInternetArchive):
                metadatos.obtener_metadatos("https://www.overleaf.com", estricto=True)


if __name__ == "__main__":
    unittest.main()
