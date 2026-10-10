"""
===============================================================================
MÓDULO: ui/views/base_view.py
DESCRIPCIÓN:
    Clase base (`PantallaBase`) para todas las vistas principales de VitalStock.
    Proporciona la barra superior institucional con botón de retorno al menú,
    título, subtítulo, insignia de sesión actual y botón para cambiar de usuario.

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Importa de `config.py`: Colores, fuentes y constantes de roles.
    - Es heredada por:
        * `ui/views/menu_view.py` (`PantallaMenu`)
        * `ui/views/pedido_view.py` (`PantallaPedido`)
        * `ui/views/inventario_view.py` (`PantallaInventario`)
    - Interactúa con: `ui/app.py` (`VitalStockApp`) para navegar entre pantallas
      (`app.mostrar`) y cambiar de usuario (`app.solicitar_login`).
===============================================================================
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import config


class PantallaBase(tk.Frame):
    """
    Contenedor base con barra de navegación superior y área de contenido (`self.cuerpo`).

    Se comunica con:
        - `ui/app.py`: Lee `self.app.usuario_actual`, invoca `self.app.mostrar("PantallaMenu")`
          y `self.app.solicitar_login()`.
    """

    titulo = ""
    subtitulo = ""

    def __init__(self, padre, app, con_volver: bool = True):
        """
        Inicializa la estructura base de la pantalla.

        Parámetros:
            padre: Contenedor Tkinter padre (`VitalStockApp.contenedor`).
            app: Instancia principal de `VitalStockApp` (`ui/app.py`).
            con_volver: Si es `True`, muestra el botón `← Menú` en la barra superior.
        """
        super().__init__(padre, bg=config.COLOR_FONDO)
        self.app = app
        barra = tk.Frame(self, bg=config.COLOR_PRIMARIO, height=56)
        barra.pack(fill="x")
        barra.pack_propagate(False)

        if con_volver:
            ttk.Button(
                barra,
                text="← Menú",
                style="Barra.TButton",
                command=lambda: app.mostrar("PantallaMenu"),
            ).pack(side="left", padx=(12, 4), pady=10)

        tk.Label(
            barra,
            text=self.titulo,
            font=(config.FUENTE, 15, "bold"),
            fg="white",
            bg=config.COLOR_PRIMARIO,
        ).pack(side="left", padx=10)
        tk.Label(
            barra,
            text=self.subtitulo,
            font=(config.FUENTE, 10),
            fg="#cfe5de",
            bg=config.COLOR_PRIMARIO,
        ).pack(side="left")

        # Insignia de usuario actual y botón para cambiar de sesión
        self.frame_user = tk.Frame(barra, bg=config.COLOR_PRIMARIO)
        self.frame_user.pack(side="right", padx=14)

        self.lbl_user_info = tk.Label(
            self.frame_user,
            text="",
            font=(config.FUENTE, 9, "bold"),
            fg="white",
            bg=config.COLOR_PRIMARIO,
        )
        self.lbl_user_info.pack(side="left", padx=(0, 10))

        self.btn_cerrar_sesion = ttk.Button(
            self.frame_user,
            text="Cambiar usuario",
            style="Barra.TButton",
            command=self.app.solicitar_login,
        )
        self.btn_cerrar_sesion.pack(side="left")

        self.cuerpo = tk.Frame(self, bg=config.COLOR_FONDO)
        self.cuerpo.pack(fill="both", expand=True, padx=16, pady=12)

    def refrescar_usuario(self) -> None:
        """
        Actualiza la etiqueta superior con el nombre y rol del usuario autenticado.

        Se comunica con:
            - `ui/app.py`: Lee `self.app.usuario_actual`.
            - `config.py`: Evalúa `ROL_SOPORTE`, `ROL_ADMIN` y `ROL_CAJA`.
        """
        u = self.app.usuario_actual
        if u:
            rol = u.get("rol", "")
            if rol == config.ROL_SOPORTE:
                badge = "Soporte 🛠️"
            elif rol == config.ROL_ADMIN:
                badge = "Admin 👑"
            else:
                badge = "Caja 🛒"
            nom = u.get("nombre") or u.get("username")
            self.lbl_user_info.configure(text=f"👤 {nom} ({badge})")
        else:
            self.lbl_user_info.configure(text="")

    def al_mostrar(self) -> None:
        """
        Hook de ciclo de vida invocado automáticamente por `VitalStockApp.mostrar()`
        cada vez que la pantalla pasa al frente.
        """
        self.refrescar_usuario()
