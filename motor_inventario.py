"""
===============================================================================
MÓDULO: motor_inventario.py (Fachada de Compatibilidad)
DESCRIPCIÓN:
    Reexporta las funciones de `services/inventario_service.py` para mantener
    compatibilidad con scripts externos o pruebas que importen `motor_inventario`.

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Importa y reexporta de `services/inventario_service.py`:
      `generar_excel_inventario`, `generar_excel_pagos_yape`,
      `normalizar_orden` y `preparar_inventario`.
===============================================================================
"""

from __future__ import annotations

from services import inventario_service
from services.inventario_service import (
    generar_excel_inventario,
    generar_excel_pagos_yape,
    normalizar_orden,
    preparar_inventario,
)
