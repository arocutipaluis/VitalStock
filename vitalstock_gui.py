"""
===============================================================================
MÓDULO: vitalstock_gui.py (Wrapper de Punto de Entrada)
DESCRIPCIÓN:
     Punto de entrada alternativo de compatibilidad que delega la ejecución a `main.py`.
    Permite iniciar la aplicación con `python vitalstock_gui.py` o `python main.py`.

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Importa y ejecuta `main.main()` desde `main.py`.
===============================================================================
"""

from __future__ import annotations

import main

if __name__ == "__main__":
    main.main()
