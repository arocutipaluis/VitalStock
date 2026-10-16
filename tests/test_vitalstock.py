"""
===============================================================================
MÓDULO: tests/test_vitalstock.py
DESCRIPCIÓN:
    Suite de pruebas unitarias, de integración y de casos esquina (Corner Cases)
    para auditar la calidad técnica y robustez de VitalStock.

EJECUCIÓN:
    python -m unittest discover -s tests -v
===============================================================================
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

# Asegurar que el directorio raíz de VitalStock V1 esté en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config
import database
from services import auth_service, inventario_service, pedido_service, yape_service


class VitalStockTestCase(unittest.TestCase):
    """Pruebas integrales con base de datos SQLite temporal aislada por cada test."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_historial.db"
        os.environ["VITALSTOCK_DB"] = str(self.db_path)
        database.inicializar_db()

    def tearDown(self) -> None:
        os.environ.pop("VITALSTOCK_DB", None)
        self.temp_dir.cleanup()

    # ----------------------------------------------------------------------- #
    # 1. Pruebas de Fecha/Hora Real de Yape y Sincronización Offline
    # ----------------------------------------------------------------------- #
    def test_convertir_fecha_hora_yape_formato_vitalnotifier(self) -> None:
        """Verifica que el timestamp DD/MM/YYYY HH:MM:SS de VitalNotifier se convierta sin alterar la hora."""
        f_vis, f_iso = database.convertir_fecha_hora_yape("15/10/2026 10:35:12")
        self.assertEqual(f_vis, "15/10/2026 10:35:12")
        self.assertEqual(f_iso, "2026-10-15 10:35:12")

    def test_persistencia_yape_preserva_hora_real_diferida(self) -> None:
        """Simula un pago Yape realizado cuando el celular estuvo fuera de red y sincronizado días después."""
        row_id = yape_service.registrar_pago_yape(
            remitente="JUAN PEREZ",
            monto=25.50,
            fecha_hora="15/10/2026 10:35:12",
            codigo_seg="1234",
            mensaje_raw="¡Te transfirieron S/ 25.50 de JUAN PEREZ! Cód: 1234",
        )
        self.assertGreater(row_id, 0)

        pagos = yape_service.consultar_pagos_yape(fecha_inicio="15/10/2026", fecha_fin="15/10/2026")
        self.assertEqual(len(pagos), 1)
        self.assertEqual(pagos[0]["remitente"], "JUAN PEREZ")
        self.assertAlmostEqual(pagos[0]["monto"], 25.50)
        self.assertEqual(pagos[0]["fecha_hora"], "15/10/2026 10:35:12")
        self.assertEqual(pagos[0]["fecha_registro"], "2026-10-15 10:35:12")
        self.assertEqual(pagos[0]["codigo_seg"], "1234")

    # ----------------------------------------------------------------------- #
    # 2. Pruebas del Parser de Notificaciones Yape (Formatos Oficiales y Borde)
    # ----------------------------------------------------------------------- #
    def test_parser_formato_oficial_bcp_yape(self) -> None:
        """Prueba el formato oficial de notificación de Yape con asterisco y código de seguridad."""
        texto = "Confirmación de Pago Maria Lop* te envió un pago por S/ 42.80. El cód. de seguridad es: 796"
        remitente, monto, cod = yape_service.parsear_texto_notificacion_yape(texto)
        self.assertEqual(remitente, "Maria Lop*")
        self.assertAlmostEqual(monto, 42.80)
        self.assertEqual(cod, "796")

    def test_parser_formato_transferencia_alternativo(self) -> None:
        """Prueba el formato alternativo '¡Te transfirieron S/ ... de ...! Cód: ...'."""
        texto = "¡Te transfirieron S/ 25.50 de JUAN PEREZ! Cód: 1234"
        remitente, monto, cod = yape_service.parsear_texto_notificacion_yape(texto)
        self.assertEqual(remitente, "JUAN PEREZ")
        self.assertAlmostEqual(monto, 25.50)
        self.assertEqual(cod, "1234")

    # ----------------------------------------------------------------------- #
    # 3. Pruebas de Seguridad, Autenticación y Roles (RBAC + Corner Cases)
    # ----------------------------------------------------------------------- #
    def test_autenticacion_exitosa_y_bloqueo_sql_injection(self) -> None:
        """Verifica login válido y resistencia ante intentos de inyección SQL en el usuario/clave."""
        u_admin = auth_service.autenticar_usuario("admin", "admin123")
        self.assertIsNotNone(u_admin)
        self.assertEqual(u_admin["rol"], config.ROL_ADMIN)

        # Intento de SQL Injection clásico
        u_sqli = auth_service.autenticar_usuario("' OR '1'='1", "' OR '1'='1")
        self.assertIsNone(u_sqli)

    def test_rol_soporte_oculto_en_listado_estandar(self) -> None:
        """Verifica que el usuario de mantenimiento ('bowly') no aparezca en la lista visible para Admin."""
        visibles = auth_service.listar_usuarios(incluir_soporte=False)
        usernames = [u["username"] for u in visibles]
        self.assertNotIn("bowly", usernames)

        todos = auth_service.listar_usuarios(incluir_soporte=True)
        usernames_todos = [u["username"] for u in todos]
        self.assertIn("bowly", usernames_todos)

    def test_validacion_campos_vacios_y_clave_corta(self) -> None:
        """Prueba casos esquina al crear usuarios con campos vacíos o contraseñas inseguras (< 4 chars)."""
        with self.assertRaises(ValueError):
            auth_service.crear_usuario("", "123456", config.ROL_CAJA, "Sin Usuario")
        with self.assertRaises(ValueError):
            auth_service.crear_usuario("cajera2", "12", config.ROL_CAJA, "Clave Corta")

    # ----------------------------------------------------------------------- #
    # 4. Pruebas de Motor de Pedidos y Clasificación de Inventario
    # ----------------------------------------------------------------------- #
    def test_normalizacion_secciones_inventario(self) -> None:
        """Verifica que los nombres antiguos de anaqueles se normalicen a las 4 secciones canónicas."""
        self.assertEqual(config.normalizar_anaquel("Vitrinas (Anaquel 1)"), config.SECCION_VITRINA)
        self.assertEqual(config.normalizar_anaquel("Detrás de caja"), config.SECCION_CAJA)
        self.assertEqual(config.normalizar_anaquel("Almacén"), config.SECCION_ALMACEN)
        self.assertTrue(config.es_filtro_todos("Todas las Secciones"))
        self.assertFalse(config.es_filtro_todos(config.SECCION_VITRINA))

    def test_preparar_inventario_todas_las_secciones(self) -> None:
        """Comprueba que el filtro 'Todas las Secciones' incluya todos los productos con stock > 0."""
        df_stock = pd.DataFrame([
            {"codigo": "P001", "producto": "PARACETAMOL 500MG", "tipo": "PORTUGAL", "ufrac": 1, "cant": 10, "frac": 0},
            {"codigo": "P002", "producto": "IBUPROFENO 400MG", "tipo": "MEDIFARMA", "ufrac": 1, "cant": 0, "frac": 0},
        ])
        df_prep = inventario_service.preparar_inventario(
            df_stock, orden="Laboratorio", solo_con_stock=True, filtro_anaquel="Todas las Secciones"
        )
        self.assertEqual(len(df_prep), 1)
        self.assertEqual(df_prep.iloc[0]["codigo"], "P001")


if __name__ == "__main__":
    unittest.main()
