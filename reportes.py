"""
===============================================================================
MÓDULO: reportes.py (Fachada de Compatibilidad)
DESCRIPCIÓN:
    Reexporta las funciones y constantes de lectura de reportes de
    `services/reportes_service.py` para mantener compatibilidad con módulos previos.

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Importa y reexporta de `services/reportes_service.py`:
      `leer_stock`, `leer_ventas`, `detectar_formato`, `extraer_rango_fechas`,
      `ReporteError` y constantes de columnas.
===============================================================================
"""

from __future__ import annotations

from services import reportes_service
from services.reportes_service import (
    COLUMNAS_STOCK,
    COLUMNAS_VENTAS,
    FORMATO_HTML,
    FORMATO_XLS,
    FORMATO_XLSX,
    MAPEO_SINONIMOS,
    ReporteError,
    detectar_formato,
    extraer_rango_fechas,
    leer_stock,
    leer_ventas,
)
