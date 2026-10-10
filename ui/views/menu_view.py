"""
===============================================================================
MÓDULO: ui/views/menu_view.py
DESCRIPCIÓN:
    Pantalla de menú principal de VitalStock (`PantallaMenu`).
    Presenta los accesos a:
    - Recomendación de pedido (restringido a Admin/Soporte)
    - Formato de inventario (disponible para todo el personal)
    - Gestión de Usuarios y Accesos (solo Admin/Soporte)
    - Panel de estado y bitácora del Receptor VitalYape.

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Importa de `config.py`: Constantes visuales y `ruta_db()`.
    - Importa de `ui/views/base_view.py`: Hereda de `PantallaBase`.
    - Importa de `ui/widgets.py`: `BotonMenu` y `Tarjeta`.
    - Importa e instancia diálogos de `ui/dialogs/`:
        * `VentanaInfoRed` (`network_dialog.py`)
        * `VentanaGestionUsuarios` (`users_dialog.py`)
        * `VentanaHistorialYape` (`yape_history_dialog.py`)
    - Es instanciada y gestionada por: `ui/app.py` (`VitalStockApp`).
===============================================================================
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import config
from ui.dialogs.network_dialog import VentanaInfoRed
from ui.dialogs.users_dialog import VentanaGestionUsuarios
from ui.dialogs.yape_history_dialog import VentanaHistorialYape
from ui.views.base_view import PantallaBase
from ui.widgets import BotonMenu, Tarjeta


class PantallaMenu(PantallaBase):
    """
    Vista principal de navegación y monitoreo del receptor Yape.

    Se comunica con:
        - `ui/app.py`: Navega hacia `PantallaPedido` y `PantallaInventario`,
          verifica permisos (`self.app.es_admin()`) y controla `self.app.servicio_yape`.
    """

    titulo = config.APP_NOMBRE
    subtitulo = config.APP_SUBTITULO

    def __init__(self, padre, app):
        """
        Construye las tarjetas de navegación y el panel de estado de VitalYape.
        """
        super().__init__(padre, app, con_volver=False)
        self.centro = tk.Frame(self.cuerpo, bg=config.COLOR_FONDO)
        self.centro.place(relx=0.5, rely=0.42, anchor="center")

        tk.Label(
            self.centro,
            text="¿Qué deseas hacer?",
            font=(config.FUENTE, 18, "bold"),
            fg=config.COLOR_TEXTO,
            bg=config.COLOR_FONDO,
        ).pack(pady=(0, 20))

        fila = tk.Frame(self.centro, bg=config.COLOR_FONDO)
        fila.pack()

        self.btn_pedido = BotonMenu(
            fila,
            "Recomendación de pedido",
            "Importa ventas, cruza con el stock actual y obtén sugerencias de compra.",
            self._al_click_pedido,
        )
        self.btn_pedido.pack(side="left", padx=12)

        self.btn_inventario = BotonMenu(
            fila,
            "Formato de inventario",
            "Genera la hoja A4 para el conteo físico de anaquel y almacén.",
            lambda: app.mostrar("PantallaInventario"),
        )
        self.btn_inventario.pack(side="left", padx=12)

        # Panel de administración de usuarios (visible únicamente para Admin / Soporte)
        self.frame_admin = tk.Frame(self.centro, bg=config.COLOR_FONDO)
        self.frame_admin.pack(fill="x", pady=(14, 0))
        self.btn_admin_usuarios = ttk.Button(
            self.frame_admin,
            text="👥 Gestión de Usuarios y Accesos",
            style="Secundario.TButton",
            command=self._abrir_gestion_usuarios,
        )
        self.btn_admin_usuarios.pack(side="right")

        # --- Panel del servicio VitalYape (Receptor local) ---
        self.yape_card = Tarjeta(self.centro, "Receptor VitalYape (Notificaciones de Pago)")
        self.yape_card.pack(fill="x", pady=(16, 0))
        fila_y = tk.Frame(self.yape_card, bg=config.COLOR_TARJETA)
        fila_y.pack(fill="x", padx=12, pady=(0, 10))

        self.lbl_yape = tk.Label(
            fila_y,
            text="● Escuchando",
            font=(config.FUENTE, 10, "bold"),
            fg=config.COLOR_OK,
            bg=config.COLOR_TARJETA,
        )
        self.lbl_yape.pack(side="left")

        self.lbl_yape_msg = tk.Label(
            fila_y,
            text="",
            font=(config.FUENTE, 9),
            fg=config.COLOR_TEXTO_SEC,
            bg=config.COLOR_TARJETA,
        )
        self.lbl_yape_msg.pack(side="left", padx=12)

        self.btn_yape_hist = ttk.Button(
            fila_y,
            text="Ver / Exportar Pagos",
            style="Secundario.TButton",
            command=self._ver_pagos_yape,
        )
        self.btn_yape_hist.pack(side="right", padx=(6, 0))

        # Opciones técnicas visibles solo para Admin (IP y control manual)
        self.btn_info_red = ttk.Button(
            fila_y,
            text="⚙️ Conexión Móvil",
            style="Secundario.TButton",
            command=self._abrir_info_red,
        )
        self.btn_yape = ttk.Button(
            fila_y,
            text="Detener receptor",
            style="Primario.TButton",
            command=self._alternar_yape,
        )

        tk.Label(
            self.cuerpo,
            text=f"Base de datos: {config.ruta_db()}",
            font=(config.FUENTE, 8),
            fg=config.COLOR_TEXTO_SEC,
            bg=config.COLOR_FONDO,
        ).pack(side="bottom", anchor="e")

    def al_mostrar(self) -> None:
        """
        Adapta los controles visibles según el rol del usuario autenticado (Admin vs Caja).

        Se comunica con:
            - `ui/views/base_view.py`: Llama a `super().al_mostrar()`.
            - `ui/app.py`: Consulta `self.app.es_admin()`.
        """
        super().al_mostrar()
        es_admin = self.app.es_admin()
        if es_admin:
            self.frame_admin.pack(fill="x", pady=(14, 0))
            self.btn_yape.pack(side="right", padx=(6, 0))
            self.btn_info_red.pack(side="right", padx=(6, 0))
            self.btn_pedido.lbl_d.configure(
                text="Importa ventas, cruza con el stock actual y obtén sugerencias de compra."
            )
        else:
            self.frame_admin.pack_forget()
            self.btn_info_red.pack_forget()
            self.btn_yape.pack_forget()
            self.btn_pedido.lbl_d.configure(
                text="🔒 Reservado para Administración (Compras y costos confidenciales)."
            )
        self.actualizar_estado_yape()

    def _al_click_pedido(self) -> None:
        """
        Verifica permisos de administrador antes de abrir `PantallaPedido`.

        Se comunica con:
            - `ui/app.py`: Llama a `self.app.mostrar("PantallaPedido")`.
        """
        if not self.app.es_admin():
            messagebox.showwarning(
                config.APP_NOMBRE,
                "Acceso Restringido\n\n"
                "La sección 'Recomendación de pedido' contiene costos, márgenes e historial "
                "estratégico de compras y está reservada para el rol Admin.\n\n"
                "Inicie sesión con cuenta de Administrador para ingresar.",
                parent=self,
            )
            return
        self.app.mostrar("PantallaPedido")

    def _abrir_gestion_usuarios(self) -> None:
        """
        Abre el diálogo modal `VentanaGestionUsuarios`.

        Se comunica con:
            - `ui/dialogs/users_dialog.py`: Instancia `VentanaGestionUsuarios`.
        """
        if not self.app.es_admin():
            return
        VentanaGestionUsuarios(self.winfo_toplevel(), self.app)

    def _abrir_info_red(self) -> None:
        """
        Abre el diálogo modal `VentanaInfoRed` con la IP y puerto del receptor.

        Se comunica con:
            - `ui/dialogs/network_dialog.py`: Instancia `VentanaInfoRed`.
        """
        if not self.app.es_admin():
            return
        VentanaInfoRed(self.winfo_toplevel(), self.app)

    def _alternar_yape(self) -> None:
        """
        Inicia o detiene manualmente el servidor HTTP receptor de Yape.

        Se comunica con:
            - `services/yape_service.py`: Invoca `iniciar()` o `detener()` en `self.app.servicio_yape`.
        """
        servicio = self.app.servicio_yape
        if servicio.activo:
            servicio.detener()
        else:
            servicio.iniciar()
        self.actualizar_estado_yape()

    def actualizar_estado_yape(self, mensaje: str | None = None) -> None:
        """
        Actualiza el indicador visual del receptor Yape en el menú principal.

        Se comunica con:
            - `ui/app.py`: Es llamado desde `_procesar_eventos_yape` cuando cambia el estado
              del servidor o llega una notificación.
        """
        activo = self.app.servicio_yape.activo
        self.lbl_yape.configure(
            text="● Escuchando" if activo else "● Detenido",
            fg=config.COLOR_OK if activo else config.COLOR_TEXTO_SEC,
        )
        self.btn_yape.configure(text="Detener receptor" if activo else "Iniciar receptor")
        if mensaje:
            self.lbl_yape_msg.configure(text=mensaje)
        else:
            if self.app.es_admin():
                self.lbl_yape_msg.configure(text="Receptor sincronizado con app móvil.")
            else:
                self.lbl_yape_msg.configure(text="Recepción de pagos Yape activa en caja.")

    def _ver_pagos_yape(self) -> None:
        """
        Abre o trae al frente la ventana de bitácora y auditoría de pagos Yape.

        Se comunica con:
            - `ui/dialogs/yape_history_dialog.py`: Instancia `VentanaHistorialYape`.
            - `ui/app.py`: Guarda la referencia en `self.app.ventana_historial_yape` para
              refrescarla en tiempo real cuando llegan nuevos Yapes.
        """
        if hasattr(self.app, "ventana_historial_yape") and self.app.ventana_historial_yape:
            try:
                self.app.ventana_historial_yape.lift()
                self.app.ventana_historial_yape.focus_force()
                return
            except Exception:
                pass
        self.app.ventana_historial_yape = VentanaHistorialYape(self.winfo_toplevel(), self.app)
