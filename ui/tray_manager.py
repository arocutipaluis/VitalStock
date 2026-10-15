"""
ui/tray_manager.py - Integración con la bandeja del sistema (System Tray) para VitalStock.

Mantiene un icono activo junto al reloj de Windows usando `pystray`, permitiendo que
VitalStock opere de forma silenciosa en segundo plano escuchando pagos de Yape y se
abra o cierre con autorización cuando el usuario lo solicite.

Comunicación con otros archivos del proyecto:
  - Importa `config.py` para obtener `APP_NOMBRE` y `ruta_base()`.
  - Es instanciado y controlado por `ui/app.py` (`VitalStockApp`).
  - Despacha acciones de interfaz hacia el hilo principal de Tkinter (`self.app.root.after`)
    invocando `mostrar_desde_bandeja()`, `ocultar_a_bandeja()` y `solicitar_cierre_seguro()` en `ui/app.py`.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from ui.app import VitalStockApp

try:
    import pystray
    from PIL import Image
    TRAY_DISPONIBLE = True
except ImportError:
    TRAY_DISPONIBLE = False


class GestorBandejaSistema:
    """Administra el icono y menú contextual en el área de notificación (System Tray) de Windows."""

    def __init__(self, app: VitalStockApp) -> None:
        """Guarda la referencia al controlador principal `VitalStockApp` (`ui/app.py`)."""
        self.app = app
        self.icono: pystray.Icon | None = None
        self._hilo: threading.Thread | None = None

    def _cargar_imagen_icono(self) -> Image.Image:
        """Localiza y redimensiona el icono institucional (`vitalstock.png` o `vitalstock.ico`).

        Comunicación entre módulos:
          - Consulta `config.ruta_base()` de `config.py` para hallar los recursos gráficos.
        """
        candidatos = [
            config.ruta_base() / "vitalstock.png",
            Path(getattr(sys, "_MEIPASS", "")) / "vitalstock.png",
            config.ruta_base() / "vitalstock.ico",
            Path(getattr(sys, "_MEIPASS", "")) / "vitalstock.ico",
        ]
        for ruta in candidatos:
            if ruta.is_file():
                try:
                    img = Image.open(str(ruta)).convert("RGBA")
                    return img.resize((64, 64), Image.Resampling.LANCZOS)
                except Exception:
                    pass

        # Si no encuentra archivo, generar un icono cuadrado verde institucional de respaldo
        img_respaldo = Image.new("RGBA", (64, 64), color=(31, 111, 92, 255))
        return img_respaldo

    def iniciar(self) -> bool:
        """Construye el menú de la bandeja e inicia el bucle de `pystray` en un hilo demonio.

        Comunicación entre módulos:
          - Invocado por `VitalStockApp.__init__()` en `ui/app.py`.
        """
        if not TRAY_DISPONIBLE:
            print("[VitalStock] Aviso: pystray o PIL no disponibles. Bandeja de sistema desactivada.")
            return False

        try:
            imagen = self._cargar_imagen_icono()
            menu = pystray.Menu(
                pystray.MenuItem("Abrir VitalStock", self._al_abrir, default=True),
                pystray.MenuItem("Ocultar a la Bandeja", self._al_ocultar),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Cerrar Sistema...", self._al_solicitar_cierre),
            )
            self.icono = pystray.Icon(
                "VitalStock",
                imagen,
                f"{config.APP_NOMBRE} · Receptor Activo",
                menu=menu,
            )

            self._hilo = threading.Thread(target=self.icono.run, daemon=True, name="VitalStock-TrayIcon")
            self._hilo.start()
            return True
        except Exception as exc:
            print(f"[VitalStock] Error iniciando System Tray: {exc}")
            return False

    def detener(self) -> None:
        """Detiene el bucle de `pystray` y remueve el icono de la barra de tareas de Windows.

        Comunicación entre módulos:
          - Invocado por `VitalStockApp.cerrar_definitivo()` en `ui/app.py`.
        """
        if self.icono:
            try:
                self.icono.stop()
            except Exception:
                pass
            self.icono = None

    def notificar(self, titulo: str, mensaje: str) -> None:
        """Muestra una notificación globo nativa de Windows desde el icono de la bandeja.

        Comunicación entre módulos:
          - Invocada por `VitalStockApp.ocultar_a_bandeja()` en `ui/app.py`.
        """
        if self.icono:
            try:
                self.icono.notify(mensaje, titulo)
            except Exception:
                pass

    def _al_abrir(self, _icon=None, _item=None) -> None:
        """Callback del menú de bandeja para restaurar la ventana principal en `ui/app.py`."""
        self.app.root.after(0, self.app.mostrar_desde_bandeja)

    def _al_ocultar(self, _icon=None, _item=None) -> None:
        """Callback del menú de bandeja para ocultar la ventana principal en `ui/app.py`."""
        self.app.root.after(0, self.app.ocultar_a_bandeja)

    def _al_solicitar_cierre(self, _icon=None, _item=None) -> None:
        """Callback del menú de bandeja para abrir el diálogo de cierre protegido en `ui/app.py`."""
        self.app.root.after(0, self.app.solicitar_cierre_seguro)
