import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import interfaz


class ValidacionYPresentacionTests(unittest.TestCase):
    def test_valida_http_https_y_agrega_esquema_por_defecto(self):
        self.assertEqual(interfaz.validar_url("example.org/ruta"), "https://example.org/ruta")
        self.assertEqual(interfaz.validar_url("HTTP://EXAMPLE.org"), "http://example.org")
        self.assertIsNone(interfaz.validar_url("javascript:alert(1)"))
        self.assertIsNone(interfaz.validar_url("https://usuario:clave@example.org"))
        self.assertIsNone(interfaz.validar_url("https://example.org:puerto"))

    def test_candidatos_para_tabla_conserva_puntuacion_y_dominio(self):
        filas = interfaz.candidatos_para_tabla([
            {"url": "https://www.example.org/a", "titulo": "Ejemplo", "puntuacion": 87.5}
        ])
        self.assertEqual(filas[0]["Posición"], 1)
        self.assertEqual(filas[0]["Dominio"], "example.org")
        self.assertEqual(filas[0]["Puntuación heurística"], 87.5)

    def test_fecha_wayback(self):
        self.assertEqual(interfaz.formatear_fecha_captura("20180416123456"), "2018-04-16")
        self.assertEqual(interfaz.formatear_fecha_captura(""), "No disponible")

    def test_metricas_se_cargan_sin_recalcular(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "metricas.json"
            esperado = {"resumen": {"top1_busqueda": {"aciertos": 0, "denominador": 6}}}
            ruta.write_text(json.dumps(esperado), encoding="utf-8")
            self.assertEqual(interfaz.cargar_metricas(ruta), esperado)


class RecuperacionTests(unittest.TestCase):
    def test_url_invalida_no_consulta_servicios(self):
        with patch.object(interfaz.metadatos, "obtener_metadatos") as obtener:
            resultado = interfaz.recuperar("no es url")
        self.assertEqual(resultado["estado"], "url_invalida")
        obtener.assert_not_called()

    def test_sin_metadatos_se_distingue_de_candidatos_ausentes(self):
        with patch.object(interfaz.metadatos, "obtener_metadatos", return_value=None):
            resultado = interfaz.recuperar("example.org")
        self.assertEqual(resultado["estado"], "sin_captura")

    def test_error_archive_se_distingue_de_ausencia_de_captura(self):
        with patch.object(
            interfaz.metadatos,
            "obtener_metadatos",
            side_effect=interfaz.metadatos.ErrorConexionInternetArchive("fallo"),
        ):
            resultado = interfaz.recuperar("example.org")
        self.assertEqual(resultado["estado"], "error_conexion_archive")

    def test_sin_candidatos_no_falla_y_conserva_metadatos(self):
        meta = {"url": "https://example.org", "titulo": "Ejemplo", "fecha_copia": "20200101000000"}
        with patch.object(interfaz.metadatos, "obtener_metadatos", return_value=meta), patch.object(
            interfaz.candidatos, "generar_candidatos", return_value=[]
        ):
            resultado = interfaz.recuperar("example.org")
        self.assertEqual(resultado["estado"], "sin_candidatos")
        self.assertEqual(resultado["metadatos"], meta)

    def test_clave_faltante_muestra_instruccion_sin_exponer_valor(self):
        meta = {"url": "https://example.org", "titulo": "Ejemplo"}
        with patch.object(interfaz.metadatos, "obtener_metadatos", return_value=meta), patch.object(
            interfaz.candidatos,
            "generar_candidatos",
            side_effect=RuntimeError("Falta la clave de Tavily. Configura TAVILY_API_KEY."),
        ):
            resultado = interfaz.recuperar("example.org")
        self.assertEqual(resultado["estado"], "falta_configuracion_tavily")
        self.assertNotIn("tvly-", resultado["detalle"])

    def test_error_de_busqueda_no_expone_detalle_crudo(self):
        meta = {"url": "https://example.org", "titulo": "Ejemplo"}
        with patch.object(interfaz.metadatos, "obtener_metadatos", return_value=meta), patch.object(
            interfaz.candidatos,
            "generar_candidatos",
            side_effect=RuntimeError("Tavily respondió HTTP 401 con token secreto"),
        ):
            resultado = interfaz.recuperar("example.org")
        self.assertEqual(resultado["estado"], "error_conexion_busqueda")
        self.assertNotIn("token secreto", resultado["detalle"])

    def test_recuperacion_completa_reutiliza_y_ordena(self):
        meta = {"url": "https://example.org", "titulo": "Ejemplo"}
        candidatos = [{"url": "https://example.net", "titulo": "Ejemplo", "posicion_buscador": 1}]
        ordenados = [{**candidatos[0], "puntuacion": 75.0}]
        with patch.object(interfaz.metadatos, "obtener_metadatos", return_value=meta), patch.object(
            interfaz.candidatos, "generar_candidatos", return_value=candidatos
        ) as generar, patch.object(interfaz, "ordenar_candidatos", return_value=ordenados):
            resultado = interfaz.recuperar("example.org")
        self.assertEqual(resultado["estado"], "completado")
        generar.assert_called_once_with(meta)
        self.assertEqual(resultado["candidatos"], ordenados)


if __name__ == "__main__":
    unittest.main()
