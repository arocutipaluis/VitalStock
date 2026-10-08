"""
ui/widgets.py - Componentes gráficos y controles reutilizables de Tkinter para VitalStock.

Proporciona controles personalizados como `ZonaDrop` (arrastrar y soltar archivos),
`Tarjeta` (contenedores estilizados), `BotonMenu` y `crear_treeview` con ordenamiento
interactivo alfabético y numérico al hacer clic en los encabezados de columna.

Comunicación con otros archivos del proyecto:
  - Importa `config.py` (colores, fuentes y tipos de archivo permitidos).
  - Exporta `DND_DISPONIBLE` y `TkinterDnD` hacia `ui/app.py`.
  - Es consumido por `ui/views/menu_view.py`, `ui/views/pedido_view.py`, `ui/views/inventario_view.py`,
    `ui/dialogs/users_dialog.py` y `ui/dialogs/yape_history_dialog.py`.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
import unicodedata
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np

import config

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_DISPONIBLE = True
except ImportError:
    DND_FILES, TkinterDnD = None, None
    DND_DISPONIBLE = False


def fmt_num(valor, decimales: int = 2) -> str:
    """Formatea valores numéricos mostrando enteros sin decimales e infinito como `'∞'`.

    Comunicación entre módulos:
      - Invocada por `ui/views/pedido_view.py` y `ui/views/inventario_view.py` al poblar tablas.
    """
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return ""
    if np.isinf(numero):
        return "∞"
    if np.isnan(numero):
        return ""
    if numero.is_integer():
        return f"{int(numero):,}"
    return f"{numero:,.{decimales}f}"


def abrir_archivo(ruta: Path) -> None:
    """Abre un archivo generado (ej. un reporte Excel `.xlsx`) con el programa predeterminado de Windows.

    Comunicación entre módulos:
      - Invocada por `ui/views/pedido_view.py`, `ui/views/inventario_view.py` y
        `ui/dialogs/yape_history_dialog.py` tras exportar un archivo Excel.
    """
    try:
        if sys.platform.startswith("win"):
            os.startfile(ruta)  # type: ignore[attr-defined]
    except OSError as exc:
        messagebox.showerror(config.APP_NOMBRE, f"No se pudo abrir el archivo:\n{exc}")


def crear_treeview(
    padre,
    columnas: list[tuple[str, str, int, str]],
    permitir_ordenar: bool = True,
) -> ttk.Treeview:
    """Crea una tabla `ttk.Treeview` con barras de desplazamiento y ordenamiento interactivo por columna.

    Comunicación entre módulos:
      - Utiliza colores de `config.py` y delega el clic de encabezado en `_ordenar_treeview()`.
      - Invocada por `ui/views/pedido_view.py`, `ui/views/inventario_view.py`,
        `ui/dialogs/users_dialog.py` y `ui/dialogs/yape_history_dialog.py`.
    """
    marco = tk.Frame(padre, bg=config.COLOR_FONDO)
    marco.pack(fill="both", expand=True)
    tree = ttk.Treeview(marco, columns=[c[0] for c in columnas], show="headings", selectmode="extended")
    tree._titulos_originales = {col_id: titulo for col_id, titulo, _w, _a in columnas}  # type: ignore[attr-defined]
    tree._sort_col_dir = {}  # type: ignore[attr-defined]

    for col_id, titulo, ancho, anchor in columnas:
        tree.heading(col_id, text=titulo)
        tree.column(col_id, width=ancho, minwidth=40, anchor=anchor, stretch=(col_id == "producto"))
        if permitir_ordenar:
            tree.heading(col_id, command=lambda c=col_id: _ordenar_treeview(tree, c))

    sy = ttk.Scrollbar(marco, orient="vertical", command=tree.yview)
    sx = ttk.Scrollbar(marco, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    tree.grid(row=0, column=0, sticky="nsew")
    sy.grid(row=0, column=1, sticky="ns")
    sx.grid(row=1, column=0, sticky="ew")
    marco.rowconfigure(0, weight=1)
    marco.columnconfigure(0, weight=1)
    return tree


def _ordenar_treeview(tree: ttk.Treeview, col: str) -> None:
    """Ordena las filas de un `Treeview` de forma numérica o alfabética al pulsar su encabezado."""
    items = [(tree.set(k, col), k) for k in tree.get_children("")]
    if not items:
        return

    dirs = getattr(tree, "_sort_col_dir", {})
    actual = dirs.get(col, None)
    descendente = not actual if actual is not None else False
    dirs[col] = descendente
    tree._sort_col_dir = dirs  # type: ignore[attr-defined]

    def parse_clave(val):
        s = str(val).strip().replace(",", "")
        try:
            return (0, float(s))
        except ValueError:
            return (1, unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower())

    items.sort(key=lambda t: parse_clave(t[0]), reverse=descendente)

    for idx, (_val, k) in enumerate(items):
        tree.move(k, "", idx)
        tags = list(tree.item(k, "tags") or ())
        if "alterna" in tags:
            tags.remove("alterna")
        if idx % 2 == 1:
            tags.append("alterna")
        tree.item(k, tags=tags)

    titulos = getattr(tree, "_titulos_originales", {})
    for c in tree["columns"]:
        orig = titulos.get(c, c)
        if c == col:
            flecha = "  ▼" if descendente else "  ▲"
            tree.heading(c, text=orig + flecha)
        else:
            tree.heading(c, text=orig)


class ZonaDrop(tk.Frame):
    """Zona interactiva para arrastrar y soltar archivos (`tkinterdnd2`) o seleccionarlos mediante clic.

    Comunicación entre módulos:
      - Instanciada en `ui/views/pedido_view.py` y `ui/views/inventario_view.py` para recibir reportes.
    """

    def __init__(self, padre, titulo: str, al_recibir, multiple: bool = False, alto: int = 110):
        """Inicializa la zona de carga y vincula los eventos de clic y Drag-and-Drop."""
        super().__init__(
            padre,
            bg=config.COLOR_TARJETA,
            highlightthickness=2,
            highlightbackground=config.COLOR_BORDE,
            cursor="hand2",
            height=alto,
        )
        self.pack_propagate(False)
        self._al_recibir = al_recibir
        self._multiple = multiple

        ayuda = (
            "Arrastra el archivo aquí o haz clic para buscar"
            if DND_DISPONIBLE
            else "Haz clic para seleccionar el archivo"
        )
        self.lbl_icono = tk.Label(self, text="⇩", font=(config.FUENTE, 18, "bold"), fg=config.COLOR_PRIMARIO, bg=config.COLOR_TARJETA)
        self.lbl_titulo = tk.Label(self, text=titulo, font=(config.FUENTE, 11, "bold"), fg=config.COLOR_TEXTO, bg=config.COLOR_TARJETA)
        self.lbl_ayuda = tk.Label(self, text=ayuda, font=(config.FUENTE, 9), fg=config.COLOR_TEXTO_SEC, bg=config.COLOR_TARJETA)
        self.lbl_estado = tk.Label(
            self,
            text="Sin archivo",
            font=(config.FUENTE, 9, "italic"),
            fg=config.COLOR_TEXTO_SEC,
            bg=config.COLOR_TARJETA,
            wraplength=320,
        )
        for w in (self.lbl_icono, self.lbl_titulo, self.lbl_ayuda, self.lbl_estado):
            w.pack(pady=(2, 0))

        self._widgets = (self, self.lbl_icono, self.lbl_titulo, self.lbl_ayuda, self.lbl_estado)
        for w in self._widgets:
            w.bind("<Button-1>", self._buscar)
            if DND_DISPONIBLE:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._soltar)
                w.dnd_bind("<<DropEnter>>", lambda e: self._resaltar(True) or e.action)
                w.dnd_bind("<<DropLeave>>", lambda e: self._resaltar(False) or e.action)

    def _resaltar(self, activo: bool) -> None:
        """Cambia el color de fondo y borde cuando un archivo entra o sale de la zona."""
        color = config.COLOR_DROP_ACTIVO if activo else config.COLOR_TARJETA
        self.configure(highlightbackground=config.COLOR_PRIMARIO if activo else config.COLOR_BORDE)
        for w in self._widgets:
            w.configure(bg=color)

    def _soltar(self, evento):
        """Procesa las rutas de archivos soltados con el mouse y las entrega al callback."""
        self._resaltar(False)
        rutas = [r for r in self.tk.splitlist(evento.data) if r]
        if rutas:
            self._entregar(rutas if self._multiple else rutas[:1])
        return evento.action

    def _buscar(self, _evento=None):
        """Abre el explorador de archivos nativo de Windows al hacer clic en la zona."""
        if self._multiple:
            rutas = list(filedialog.askopenfilenames(title="Seleccionar reportes", filetypes=config.TIPOS_REPORTE))
        else:
            ruta = filedialog.askopenfilename(title="Seleccionar reporte", filetypes=config.TIPOS_REPORTE)
            rutas = [ruta] if ruta else []
        if rutas:
            self._entregar(rutas)

    def _entregar(self, rutas: list[str]) -> None:
        """Muestra el cursor de espera y ejecuta el callback `_al_recibir` de la vista."""
        self.winfo_toplevel().configure(cursor="watch")
        self.update_idletasks()
        try:
            self._al_recibir(rutas)
        finally:
            self.winfo_toplevel().configure(cursor="")

    def set_estado(self, texto: str, ok: bool = True) -> None:
        """Actualiza la etiqueta inferior de estado con color de éxito o error."""
        self.lbl_estado.configure(
            text=texto,
            fg=config.COLOR_OK if ok else config.COLOR_ERROR,
            font=(config.FUENTE, 9, "bold" if ok else "italic"),
        )


class Tarjeta(tk.Frame):
    """Contenedor visual blanco con borde suave y título opcional.

    Comunicación entre módulos:
      - Utilizada en todas las vistas (`ui/views/*`) y diálogos (`ui/dialogs/*`).
    """

    def __init__(self, padre, titulo: str | None = None, **kwargs):
        """Inicializa el marco con los colores institucionales definidos en `config.py`."""
        super().__init__(
            padre,
            bg=config.COLOR_TARJETA,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDE,
            **kwargs,
        )
        if titulo:
            tk.Label(
                self,
                text=titulo,
                font=(config.FUENTE, 10, "bold"),
                fg=config.COLOR_PRIMARIO,
                bg=config.COLOR_TARJETA,
            ).pack(anchor="w", padx=12, pady=(10, 4))


class BotonMenu(tk.Frame):
    """Botón grande tipo tarjeta interactiva para la pantalla de menú principal.

    Comunicación entre módulos:
      - Instanciado en `ui/views/menu_view.py` (`PantallaMenu`) para navegar hacia
        `PantallaPedido` y `PantallaInventario`.
    """

    def __init__(self, padre, titulo: str, descripcion: str, comando):
        """Crea la tarjeta con título, descripción y efectos de resaltado al pasar el cursor."""
        super().__init__(
            padre,
            bg=config.COLOR_TARJETA,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDE,
            cursor="hand2",
            width=320,
            height=130,
        )
        self.pack_propagate(False)
        self._comando = comando
        self.lbl_t = tk.Label(self, text=titulo, font=(config.FUENTE, 14, "bold"), fg=config.COLOR_PRIMARIO, bg=config.COLOR_TARJETA)
        self.lbl_d = tk.Label(
            self,
            text=descripcion,
            font=(config.FUENTE, 10),
            fg=config.COLOR_TEXTO_SEC,
            bg=config.COLOR_TARJETA,
            wraplength=280,
            justify="center",
        )
        self.lbl_t.pack(pady=(28, 6))
        self.lbl_d.pack()
        for w in (self, self.lbl_t, self.lbl_d):
            w.bind("<Button-1>", lambda _e: self._comando())
            w.bind("<Enter>", lambda _e: self._hover(True))
            w.bind("<Leave>", lambda _e: self._hover(False))

    def _hover(self, activo: bool) -> None:
        """Resalta el borde de la tarjeta cuando el puntero del mouse pasa sobre ella."""
        self.configure(
            highlightbackground=config.COLOR_PRIMARIO if activo else config.COLOR_BORDE,
            highlightthickness=2 if activo else 1,
        )
