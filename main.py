"""
main.py - Punto de entrada principal, control de instancia única y arranque en segundo plano.

Comportamiento de ejecución:
  1. Al iniciar la PC (o en la primera ejecución de `VitalStock.exe`), la aplicación arranca
     por defecto minimizada en segundo plano (solo en la bandeja del sistema / System Tray),
     manteniendo activo el receptor HTTP de pagos Yape sin interrumpir al usuario.
  2. Si `VitalStock` ya está ejecutándose en segundo plano y el usuario vuelve a abrir el
     acceso directo de `VitalStock.exe`, este módulo detecta la instancia activa comunicándose
     con `services/yape_service.py` (`GET /mostrar`), le ordena abrir la ventana principal en
     pantalla y finaliza el proceso duplicado de inmediato.

Comunicación con otros archivos del proyecto:
  - Importa `config.py` para conocer el puerto local del servicio (`PUERTO_YAPE_DEFECTO`).
  - Se comunica por HTTP local con `services/yape_service.py` (`ServicioNotificacionesYape`).
  - Importa e instancia `VitalStockApp` desde `ui/app.py`.
"""

from __future__ import annotations

import sys
import urllib.request

import config
from ui.app import VitalStockApp


def _activar_dpi_windows() -> None:
    """Activa el escalado de alto DPI en Windows para que las fuentes e iconos se vean nítidos.

    Comunicación entre módulos:
      - Invocada internamente por `main()` antes de crear la ventana raíz Tkinter en `ui/app.py`.
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _intentar_despertar_instancia_existente() -> bool:
    """Verifica si VitalStock ya está corriendo en segundo plano y le ordena mostrar su ventana.

    Realiza una petición `GET` local hacia `http://127.0.0.1:<PUERTO>/mostrar`. Si obtiene
    respuesta exitosa, significa que ya hay una instancia activa en la bandeja del sistema,
    la cual restaurará su ventana principal gracias al evento procesado en `ui/app.py`.

    Comunicación entre módulos:
      - Lee `config.PUERTO_YAPE_DEFECTO` desde `config.py`.
      - Se comunica vía socket HTTP local con `ServicioNotificacionesYape` en `services/yape_service.py`,
        el cual a su vez notifica a `VitalStockApp._procesar_eventos_yape()` en `ui/app.py`.
    """
    url = f"http://127.0.0.1:{config.PUERTO_YAPE_DEFECTO}/mostrar"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass
    return False


def main() -> None:
    """Función principal de arranque de VitalStock.

    - Si ya existe una instancia en segundo plano, la despierta y muestra su interfaz.
    - Si es el primer arranque (por ejemplo, al encender la PC), inicia directamente
      en segundo plano en la bandeja del sistema a menos que se pase `--open` / `--ventana`.

    Comunicación entre módulos:
      - Invoca `_intentar_despertar_instancia_existente()` (hacia `services/yape_service.py`).
      - Instancia y ejecuta `VitalStockApp` definida en `ui/app.py`.
    """
    _activar_dpi_windows()

    # 1. Si ya está corriendo en segundo plano (bandeja), abrir su ventana al dar clic al acceso directo
    if _intentar_despertar_instancia_existente():
        return

    # 2. En el primer inicio (al prender la PC), iniciar minimizado en la bandeja por defecto
    argumentos = [arg.lower() for arg in sys.argv[1:]]
    forzar_ventana = any(arg in ("--open", "--ventana", "--show", "-o") for arg in argumentos)
    iniciar_minimizada = not forzar_ventana

    app = VitalStockApp(iniciar_minimizada=iniciar_minimizada)
    app.ejecutar()


if __name__ == "__main__":
    main()
