"""
ui/styles.py - Configuración de estilos visuales `ttk.Style` para VitalStock.

Comunicación con otros archivos del proyecto:
  - Importa `config.py` para obtener la paleta de colores institucionales y la fuente tipográfica.
  - Es invocado al iniciar la aplicación desde `ui/app.py` (`VitalStockApp.__init__`).
  - Los estilos definidos aquí (`Primario.TButton`, `Secundario.TButton`, `Peligro.TButton`,
    `Barra.TButton`, `Treeview`) son consumidos por todas las vistas en `ui/views/*`
    y diálogos en `ui/dialogs/*`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import config


def configurar_estilos(root: tk.Tk) -> None:
    """Configura el tema base `'clam'`, botones, casillas de verificación y tablas `Treeview`.

    Comunicación entre módulos:
      - Lee constantes visuales desde `config.py`.
      - Invocada una sola vez por `VitalStockApp.__init__()` en `ui/app.py`.
    """
    estilo = ttk.Style(root)
    estilo.theme_use("clam")

    estilo.configure(".", font=(config.FUENTE, 10), background=config.COLOR_FONDO)

    # Botones
    estilo.configure(
        "Primario.TButton",
        background=config.COLOR_PRIMARIO,
        foreground="white",
        borderwidth=0,
        padding=(14, 7),
        font=(config.FUENTE, 10, "bold"),
    )
    estilo.map(
        "Primario.TButton",
        background=[("active", config.COLOR_PRIMARIO_HOVER), ("pressed", config.COLOR_PRIMARIO_HOVER)],
    )

    estilo.configure(
        "Secundario.TButton",
        background=config.COLOR_TARJETA,
        foreground=config.COLOR_PRIMARIO,
        bordercolor=config.COLOR_PRIMARIO,
        padding=(12, 6),
    )
    estilo.map("Secundario.TButton", background=[("active", config.COLOR_DROP_ACTIVO)])

    estilo.configure(
        "Peligro.TButton",
        background=config.COLOR_TARJETA,
        foreground=config.COLOR_ERROR,
        padding=(12, 6),
    )
    estilo.map("Peligro.TButton", background=[("active", "#fdecea")])

    estilo.configure(
        "Barra.TButton",
        background=config.COLOR_PRIMARIO_HOVER,
        foreground="white",
        borderwidth=0,
        padding=(10, 4),
    )
    estilo.map("Barra.TButton", background=[("active", "#124437")])

    estilo.configure("Tarjeta.TCheckbutton", background=config.COLOR_TARJETA)
    estilo.map("Tarjeta.TCheckbutton", background=[("active", config.COLOR_TARJETA)])

    # Treeview
    estilo.configure(
        "Treeview",
        rowheight=24,
        font=(config.FUENTE, 9),
        background=config.COLOR_TARJETA,
        fieldbackground=config.COLOR_TARJETA,
        bordercolor=config.COLOR_BORDE,
    )
    estilo.configure(
        "Treeview.Heading",
        background=config.COLOR_PRIMARIO,
        foreground="white",
        font=(config.FUENTE, 9, "bold"),
        relief="flat",
        padding=(4, 5),
    )
    estilo.map("Treeview.Heading", background=[("active", config.COLOR_PRIMARIO_HOVER)])
    estilo.map("Treeview", background=[("selected", "#9cc9bb")], foreground=[("selected", config.COLOR_TEXTO)])
