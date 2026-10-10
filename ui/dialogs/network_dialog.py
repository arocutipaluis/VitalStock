"""
===============================================================================
MÓDULO: ui/dialogs/network_dialog.py
DESCRIPCIÓN:
    Ventana informativa y de control de red para sincronizar la aplicación móvil
    VitalNotifier con el servidor local de esta computadora (exclusivo Admin/Soporte).

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Importa de `config.py`: Colores, fuentes y constantes de la aplicación.
    - Importa de `services/yape_service.py`: `obtener_ip_local` para detectar la IP LAN.
    - Es instanciado desde: `ui/views/menu_view.py` (`PantallaMenu._abrir_info_red`).
    - Interactúa con: `ui/app.py` (`app.servicio_yape`) para iniciar/detener el receptor HTTP.
===============================================================================
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import config
from services.yape_service import obtener_ip_local


class VentanaInfoRed(tk.Toplevel):
    """
    Muestra la dirección IP local, puerto HTTP y URL del endpoint `/yape`
    para configurar la app móvil VitalNotifier (Solo Admin / Soporte).

    Se comunica con:
        - `services/yape_service.py`: Obtiene la IP LAN con `obtener_ip_local()` y
          controla `app.servicio_yape`.
        - `ui/views/menu_view.py`: Refresca el indicador de estado en `PantallaMenu`.
    """

    def __init__(self, maestro: tk.Tk | tk.Toplevel, app) -> None:
        """
        Inicializa la ventana modal con los parámetros de red actuales.

        Se comunica con:
            - `services/yape_service.py`: Consulta `obtener_ip_local()`, `puerto` y `activo`.
        """
        super().__init__(maestro)
        self.app = app
        self.title(f"{config.APP_NOMBRE} · Conexión VitalNotifier (IP y Red)")
        self.geometry("480x370")
        self.resizable(False, False)
        self.configure(bg=config.COLOR_FONDO)
        self.transient(maestro)

        ancho, alto = 480, 370
        x = max(10, maestro.winfo_x() + (maestro.winfo_width() - ancho) // 2)
        y = max(10, maestro.winfo_y() + (maestro.winfo_height() - alto) // 2)
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

        barra = tk.Frame(self, bg=config.COLOR_PRIMARIO, height=50)
        barra.pack(fill="x")
        barra.pack_propagate(False)
        tk.Label(
            barra,
            text="⚙️  Parámetros de Red y Sincronización Móvil",
            font=(config.FUENTE, 11, "bold"),
            fg="white",
            bg=config.COLOR_PRIMARIO,
        ).pack(side="left", padx=16)

        cuerpo = tk.Frame(
            self,
            bg=config.COLOR_TARJETA,
            padx=18,
            pady=16,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDE,
        )
        cuerpo.pack(fill="both", expand=True, padx=16, pady=14)

        ip = obtener_ip_local()
        puerto = self.app.servicio_yape.puerto
        activo = self.app.servicio_yape.activo

        tk.Label(
            cuerpo,
            text="Dirección IP de esta PC en la Botica:",
            font=(config.FUENTE, 9, "bold"),
            fg=config.COLOR_TEXTO,
            bg=config.COLOR_TARJETA,
        ).pack(anchor="w")
        f_ip = tk.Frame(cuerpo, bg="#edf4f1", padx=10, pady=8)
        f_ip.pack(fill="x", pady=(4, 10))
        tk.Label(
            f_ip, text=f"{ip} : {puerto}", font=(config.FUENTE, 14, "bold"), fg=config.COLOR_PRIMARIO, bg="#edf4f1"
        ).pack(side="left")

        tk.Label(
            cuerpo,
            text="URL para la app móvil:",
            font=(config.FUENTE, 9, "bold"),
            fg=config.COLOR_TEXTO,
            bg=config.COLOR_TARJETA,
        ).pack(anchor="w")
        ent_url = ttk.Entry(cuerpo, font=(config.FUENTE, 9))
        ent_url.insert(0, f"http://{ip}:{puerto}/yape")
        ent_url.configure(state="readonly")
        ent_url.pack(fill="x", pady=(3, 10))

        estado_txt = "● Servidor receptor en ejecución (Escuchando)" if activo else "● Servidor receptor detenido"
        color_est = config.COLOR_OK if activo else config.COLOR_ERROR
        tk.Label(
            cuerpo, text=estado_txt, font=(config.FUENTE, 9, "bold"), fg=color_est, bg=config.COLOR_TARJETA
        ).pack(anchor="w", pady=(0, 10))

        ayuda = (
            "📌 Instrucciones para VitalNotifier:\n"
            "1. Conecta el celular de caja a la misma red Wi-Fi que esta computadora.\n"
            "2. En la app móvil, ingresa la IP indicada arriba y presiona Probar.\n"
            "3. Esta información se mantiene oculta para personal de Caja por seguridad."
        )
        tk.Label(
            cuerpo, text=ayuda, font=(config.FUENTE, 8), fg=config.COLOR_TEXTO_SEC, bg=config.COLOR_TARJETA, justify="left"
        ).pack(anchor="w")

        f_botones = tk.Frame(cuerpo, bg=config.COLOR_TARJETA)
        f_botones.pack(fill="x", pady=(12, 0))

        txt_btn = "Detener Receptor" if activo else "Iniciar Receptor"
        btn_toggle = ttk.Button(f_botones, text=txt_btn, style="Secundario.TButton", command=self._toggle_servidor)
        btn_toggle.pack(side="left")

        ttk.Button(f_botones, text="Cerrar", style="Primario.TButton", command=self.destroy).pack(side="right")

    def _toggle_servidor(self) -> None:
        """
        Alterna el estado del servidor HTTP receptor de Yape (iniciar / detener).

        Se comunica con:
            - `services/yape_service.py`: Llama a `servicio.iniciar()` o `servicio.detener()`.
            - `ui/views/menu_view.py`: Llama a `menu.actualizar_estado_yape()` para actualizar la UI.
        """
        servicio = self.app.servicio_yape
        if servicio.activo:
            servicio.detener()
        else:
            servicio.iniciar()
        menu = self.app.pantallas.get("PantallaMenu")
        if menu:
            menu.actualizar_estado_yape()
        self.destroy()
