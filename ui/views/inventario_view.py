"""
===============================================================================
MÓDULO: ui/views/inventario_view.py
DESCRIPCIÓN:
    Pantalla de generación del formato físico de inventario y gestión de secciones
    (`PantallaInventario`). Organizada en 3 pestañas:
    1. Hojas de Inventario: Carga reporte de stock, previsualiza por sección y exporta
       a Excel A4 dividido en sub-tablas por laboratorio.
    2. Gestor de Secciones: Permite buscar productos en el catálogo y moverlos de
       sección individualmente o por laboratorio completo.
    3. Productos Nuevos: Detecta productos del stock que aún no tienen sección
       asignada para clasificarlos rápidamente.

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Importa de `config.py`: Lista oficial `ANAQUELES`, `es_filtro_todos`, colores y fuentes.
    - Importa de `services/inventario_service.py`: Funciones de clasificación por anaquel,
      preparación de vista y exportación a Excel (`generar_excel_inventario`).
    - Importa de `services/reportes_service.py`: `leer_stock` para leer el archivo `.xls`/`.html`.
    - Importa de `ui/views/base_view.py`: Hereda de `PantallaBase`.
    - Importa de `ui/widgets.py`: `Tarjeta`, `ZonaDrop`, `crear_treeview` y `abrir_archivo`.
    - Es instanciada y gestionada por: `ui/app.py` (`VitalStockApp`).
===============================================================================
"""

from __future__ import annotations

import tkinter as tk
import unicodedata
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd

import config
from services import inventario_service, reportes_service
from ui.views.base_view import PantallaBase
from ui.widgets import Tarjeta, ZonaDrop, abrir_archivo, crear_treeview


class PantallaInventario(PantallaBase):
    """
    Vista con pestañas para generar hojas de conteo físico y administrar ubicaciones en botica.

    Se comunica con:
        - `services/inventario_service.py`: Consulta y actualiza ubicaciones en SQLite y exporta Excel.
        - `services/reportes_service.py`: Parsea el reporte de stock cargado por el usuario.
    """

    titulo = "Formato de inventario"
    subtitulo = "División por secciones y tablas de laboratorio para conteo físico"

    COLUMNAS_VISTA = [
        ("codigo", "Código", 100, "w"),
        ("producto", "Producto", 400, "w"),
        ("tipo", "Laboratorio", 180, "w"),
        ("anaquel", "Sección Asignada", 220, "w"),
    ]

    COLUMNAS_GESTOR = [
        ("codigo", "Código", 100, "w"),
        ("producto", "Producto", 390, "w"),
        ("laboratorio", "Laboratorio", 180, "w"),
        ("anaquel", "Sección Actual", 210, "w"),
        ("fecha_mod", "Último Cambio", 130, "center"),
    ]

    COLUMNAS_NUEVOS = [
        ("codigo", "Código", 100, "w"),
        ("producto", "Producto", 380, "w"),
        ("tipo", "Laboratorio", 190, "w"),
    ]

    OPCIONES_ORDEN = ["Laboratorio", "Producto", "Código"]

    def __init__(self, padre, app):
        """
        Construye el `ttk.Notebook` con las 3 pestañas de gestión de inventario.
        """
        super().__init__(padre, app)
        self.df_stock: pd.DataFrame | None = None
        self.df_vista: pd.DataFrame | None = None
        self.df_nuevos: pd.DataFrame | None = None

        # Contenedor con pestañas (Notebook)
        self.notebook = ttk.Notebook(self.cuerpo)
        self.notebook.pack(fill="both", expand=True, padx=4, pady=4)

        # 1. Pestaña: Hojas de Inventario
        self.tab_conteo = tk.Frame(self.notebook, bg=config.COLOR_FONDO)
        self.notebook.add(self.tab_conteo, text="  📋 Hojas de Inventario  ")
        self._construir_pestana_conteo()

        # 2. Pestaña: Gestor de Secciones
        self.tab_gestor = tk.Frame(self.notebook, bg=config.COLOR_FONDO)
        self.notebook.add(self.tab_gestor, text="  🏷️ Gestor de Secciones  ")
        self._construir_pestana_gestor()

        # 3. Pestaña: Productos Nuevos
        self.tab_nuevos = tk.Frame(self.notebook, bg=config.COLOR_FONDO)
        self.notebook.add(self.tab_nuevos, text="  ⚠️ Productos Nuevos (0)  ")
        self._construir_pestana_nuevos()

        # Cargar catálogo inicial en el gestor
        self.root = padre.winfo_toplevel()
        self.root.after(300, self._cargar_datos_gestor)

    # ----------------------------------------------------------------------- #
    # PESTAÑA 1: HOJAS DE INVENTARIO
    # ----------------------------------------------------------------------- #
    def _construir_pestana_conteo(self) -> None:
        """
        Construye los controles de la Pestaña 1 (ZonaDrop de stock, filtros de sección/orden y vista previa).
        """
        superior = tk.Frame(self.tab_conteo, bg=config.COLOR_FONDO)
        superior.pack(fill="x", pady=(4, 6))
        superior.columnconfigure(0, weight=1)

        self.zona_stock = ZonaDrop(
            superior,
            "Arrastre aquí el Reporte de STOCK actual (.xls / .html)",
            self._recibir_stock,
            alto=125,
        )
        self.zona_stock.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        opciones = Tarjeta(superior, "Opciones de Conteo Ciego")
        opciones.grid(row=0, column=1, sticky="nsew")
        g = tk.Frame(opciones, bg=config.COLOR_TARJETA)
        g.pack(padx=10, pady=(0, 8), fill="x")

        # Local
        tk.Label(g, text="Local / Sede:", font=(config.FUENTE, 9), bg=config.COLOR_TARJETA, fg=config.COLOR_TEXTO).grid(
            row=0, column=0, sticky="w", pady=2
        )
        self.var_local = tk.StringVar(value="")
        ttk.Entry(g, textvariable=self.var_local, width=22).grid(row=0, column=1, padx=6, pady=2, sticky="w")

        # Selector de Sección a Exportar
        tk.Label(
            g, text="Exportar:", font=(config.FUENTE, 9, "bold"), bg=config.COLOR_TARJETA, fg=config.COLOR_PRIMARIO
        ).grid(row=1, column=0, sticky="w", pady=2)
        opciones_anaquel = ["Todas las Secciones"] + list(config.ANAQUELES)
        self.var_anaquel_export = tk.StringVar(value=opciones_anaquel[0])
        cb_anaq = ttk.Combobox(
            g, textvariable=self.var_anaquel_export, values=opciones_anaquel, state="readonly", width=22
        )
        cb_anaq.grid(row=1, column=1, padx=6, pady=2, sticky="w")
        cb_anaq.bind("<<ComboboxSelected>>", lambda _e: self._actualizar_vista_conteo())

        # Orden
        tk.Label(g, text="Ordenar por:", font=(config.FUENTE, 9), bg=config.COLOR_TARJETA, fg=config.COLOR_TEXTO).grid(
            row=2, column=0, sticky="w", pady=2
        )
        self.var_orden = tk.StringVar(value=self.OPCIONES_ORDEN[0])
        cb_ord = ttk.Combobox(g, textvariable=self.var_orden, values=self.OPCIONES_ORDEN, state="readonly", width=22)
        cb_ord.grid(row=2, column=1, padx=6, pady=2, sticky="w")
        cb_ord.bind("<<ComboboxSelected>>", lambda _e: self._actualizar_vista_conteo())

        # Solo con stock > 0
        self.var_solo_stock = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            g,
            text="Solo stock > 0",
            variable=self.var_solo_stock,
            style="Tarjeta.TCheckbutton",
            command=self._actualizar_vista_conteo,
        ).grid(row=3, column=1, padx=6, pady=2, sticky="w")

        # Botón Exportar
        btn_exp = ttk.Button(
            g, text="📄 Exportar a Excel (A4)", style="Primario.TButton", command=self._exportar_inventario_ciego
        )
        btn_exp.grid(row=0, column=2, rowspan=4, padx=(10, 0), sticky="nsew")

        # Resumen informativo
        self.lbl_resumen_conteo = tk.Label(
            self.tab_conteo,
            text="Cargue un reporte de stock para previsualizar los productos clasificados por anaquel.",
            font=(config.FUENTE, 9),
            fg=config.COLOR_TEXTO_SEC,
            bg=config.COLOR_FONDO,
        )
        self.lbl_resumen_conteo.pack(anchor="w", padx=4, pady=(6, 4))

        # Tabla de previsualización
        self.tree_conteo = crear_treeview(self.tab_conteo, self.COLUMNAS_VISTA)
        self.tree_conteo.tag_configure("alterna", background=config.COLOR_FONDO)

    def _recibir_stock(self, rutas: list[str]) -> None:
        """
        Lee el reporte de stock seleccionado, clasifica los productos por sección y
        detecta si existen productos nuevos sin sección asignada.

        Se comunica con:
            - `services/reportes_service.py`: Llama a `leer_stock(ruta)`.
            - `services/inventario_service.py`: Llama a `clasificar_stock_con_anaqueles(df_stock)`.
        """
        ruta = rutas[0]
        try:
            self.df_stock = reportes_service.leer_stock(ruta)
        except Exception as exc:
            self.zona_stock.set_estado("Error al leer el archivo", ok=False)
            messagebox.showerror(config.APP_NOMBRE, f"No se pudo leer el stock:\n\n{exc}")
            return

        self.zona_stock.set_estado(f"{Path(ruta).name} · {len(self.df_stock):,} productos")

        # Clasificar y verificar productos nuevos
        _df_clas, self.df_nuevos = inventario_service.clasificar_stock_con_anaqueles(self.df_stock)
        total_nuevos = len(self.df_nuevos)

        if total_nuevos > 0:
            self.notebook.tab(self.tab_nuevos, text=f"  ⚠️ Productos Nuevos ({total_nuevos})  ")
            self._actualizar_pestana_nuevos()
            messagebox.showinfo(
                config.APP_NOMBRE,
                f"Se detectaron {total_nuevos} productos nuevos en el reporte que no tienen anaquel asignado.\n\n"
                "Ve a la pestaña '⚠️ Productos Nuevos' para indicar en qué anaquel se guardan.",
            )
        else:
            self.notebook.tab(self.tab_nuevos, text="  ✅ Sin Productos Nuevos  ")
            self._actualizar_pestana_nuevos()

        self._actualizar_vista_conteo()

    def _actualizar_vista_conteo(self) -> None:
        """
        Refresca la tabla de vista previa según la sección, orden y filtro de stock elegidos.

        Se comunica con:
            - `config.py`: Usa `es_filtro_todos(seleccion)`.
            - `services/inventario_service.py`: Llama a `preparar_inventario(...)`.
        """
        self.tree_conteo.delete(*self.tree_conteo.get_children())
        if self.df_stock is None:
            return

        seleccion = self.var_anaquel_export.get()
        filtro_anaq = "Todas las Secciones" if config.es_filtro_todos(seleccion) else seleccion

        try:
            self.df_vista = inventario_service.preparar_inventario(
                self.df_stock,
                orden=self.var_orden.get(),
                solo_con_stock=self.var_solo_stock.get(),
                filtro_anaquel=filtro_anaq,
            )
        except Exception as exc:
            messagebox.showerror(config.APP_NOMBRE, f"Error al preparar la vista:\n\n{exc}")
            return

        for i, r in enumerate(self.df_vista.itertuples(index=False)):
            self.tree_conteo.insert(
                "",
                "end",
                tags=("alterna",) if i % 2 else (),
                values=(
                    r.codigo,
                    r.producto,
                    r.tipo,
                    r.anaquel,
                ),
            )

        total_mostrar = len(self.df_vista)
        total_reporte = len(self.df_stock)
        self.lbl_resumen_conteo.configure(
            text=f"Mostrando {total_mostrar:,} productos para {seleccion} (Total reporte: {total_reporte:,})  ·  "
            "Organizado en tablas por laboratorio con columnas de conteo y sistema en blanco para conteo puro."
        )

    def _exportar_inventario_ciego(self) -> None:
        """
        Solicita ruta de guardado y genera el archivo Excel de inventario físico.

        Se comunica con:
            - `services/inventario_service.py`: Llama a `generar_excel_inventario(...)`.
            - `ui/widgets.py`: Llama a `abrir_archivo(salida)`.
        """
        if self.df_stock is None:
            messagebox.showwarning(config.APP_NOMBRE, "Primero cargue el reporte de stock.")
            return

        seleccion = self.var_anaquel_export.get()
        anaq_param = "Todas las Secciones" if config.es_filtro_todos(seleccion) else seleccion

        local = self.var_local.get().strip()
        sufijo_local = f"_{local}" if local else ""

        def _formatear_nombre_archivo(txt: str) -> str:
            s = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode("ascii")
            return "".join(c if c.isalnum() else "_" for c in s).strip("_")

        if config.es_filtro_todos(anaq_param):
            nombre_seccion_archivo = "General"
        else:
            nombre_seccion_archivo = _formatear_nombre_archivo(anaq_param)

        nombre_def = f"Inventario_{nombre_seccion_archivo}{sufijo_local}_{datetime.now():%Y%m%d}.xlsx"

        ruta = filedialog.asksaveasfilename(
            title="Guardar formato de inventario",
            defaultextension=".xlsx",
            initialfile=nombre_def,
            filetypes=[("Excel", "*.xlsx")],
        )
        if not ruta:
            return

        try:
            salida = inventario_service.generar_excel_inventario(
                self.df_stock,
                ruta,
                orden=self.var_orden.get(),
                local=local,
                solo_con_stock=self.var_solo_stock.get(),
                anaquel_seleccionado=anaq_param,
            )
        except Exception as exc:
            messagebox.showerror(config.APP_NOMBRE, f"No se pudo generar el Excel:\n\n{exc}")
            return

        msg = (
            f"Formato de inventario generado exitosamente:\n{salida}\n\n"
            "✓ Tablas divididas por laboratorios (estilo Irene).\n"
            "✓ Incluye columna SISTEMA (en blanco para conteo físico puro).\n"
            "✓ Columnas de código, producto, laboratorio, f. vencimiento, anaquel, almacén, total y observaciones.\n"
            "✓ Formato A4 horizontal listo para imprimir.\n\n"
            "¿Desea abrir el archivo ahora?"
        )
        if messagebox.askyesno(config.APP_NOMBRE, msg):
            abrir_archivo(salida)

    # ----------------------------------------------------------------------- #
    # PESTAÑA 2: GESTOR DE SECCIONES (REASIGNACIÓN Y MOVIMIENTOS)
    # ----------------------------------------------------------------------- #
    def _construir_pestana_gestor(self) -> None:
        """
        Construye el buscador, filtro de secciones, tabla del catálogo y barra de reasignación.
        """
        top = tk.Frame(self.tab_gestor, bg=config.COLOR_FONDO)
        top.pack(fill="x", padx=6, pady=(6, 4))

        # Buscador
        tk.Label(top, text="Buscar:", font=(config.FUENTE, 9, "bold"), bg=config.COLOR_FONDO, fg=config.COLOR_TEXTO).pack(
            side="left", padx=(0, 4)
        )
        self.var_busqueda_gestor = tk.StringVar()
        ent_busq = ttk.Entry(top, textvariable=self.var_busqueda_gestor, width=28)
        ent_busq.pack(side="left", padx=(0, 10))
        ent_busq.bind("<KeyRelease>", lambda _e: self._cargar_datos_gestor())

        # Filtro por sección
        tk.Label(top, text="Sección:", font=(config.FUENTE, 9), bg=config.COLOR_FONDO, fg=config.COLOR_TEXTO).pack(
            side="left", padx=(0, 4)
        )
        self.var_filtro_gestor = tk.StringVar(value="Todos")
        cb_filtro = ttk.Combobox(
            top,
            textvariable=self.var_filtro_gestor,
            values=["Todos"] + list(config.ANAQUELES),
            state="readonly",
            width=22,
        )
        cb_filtro.pack(side="left", padx=(0, 12))
        cb_filtro.bind("<<ComboboxSelected>>", lambda _e: self._cargar_datos_gestor())

        self.lbl_contador_gestor = tk.Label(
            top, text="Cargando catálogo...", font=(config.FUENTE, 9), fg=config.COLOR_TEXTO_SEC, bg=config.COLOR_FONDO
        )
        self.lbl_contador_gestor.pack(side="right")

        # Tabla de catálogo
        self.tree_gestor = crear_treeview(self.tab_gestor, self.COLUMNAS_GESTOR)
        self.tree_gestor.tag_configure("alterna", background=config.COLOR_FONDO)

        # Barra inferior de acciones de reasignación
        barra_acc = tk.Frame(self.tab_gestor, bg=config.COLOR_TARJETA, bd=1, relief="solid")
        barra_acc.pack(fill="x", padx=6, pady=6)

        tk.Label(
            barra_acc,
            text="Mover seleccionado(s) a:",
            font=(config.FUENTE, 9, "bold"),
            bg=config.COLOR_TARJETA,
            fg=config.COLOR_TEXTO,
        ).pack(side="left", padx=(10, 6), pady=8)

        self.var_nuevo_anaquel = tk.StringVar(value=config.SECCION_VITRINA)
        cb_nuevo = ttk.Combobox(
            barra_acc, textvariable=self.var_nuevo_anaquel, values=config.ANAQUELES, state="readonly", width=25
        )
        cb_nuevo.pack(side="left", padx=4, pady=8)

        ttk.Button(
            barra_acc, text="Mover Producto(s)", style="Primario.TButton", command=self._mover_productos_seleccionados
        ).pack(side="left", padx=8, pady=8)

        ttk.Button(
            barra_acc, text="Reasignar TODO el Laboratorio", command=self._reasignar_laboratorio_completo
        ).pack(side="left", padx=6, pady=8)

        ttk.Button(barra_acc, text="Refrescar", command=self._cargar_datos_gestor).pack(side="right", padx=10, pady=8)

    def _cargar_datos_gestor(self) -> None:
        """
        Consulta el catálogo de ubicaciones en SQLite y pobla `self.tree_gestor`.

        Se comunica con:
            - `services/inventario_service.py`: Llama a `obtener_catalogo_ubicaciones(...)`.
        """
        self.tree_gestor.delete(*self.tree_gestor.get_children())
        busq = self.var_busqueda_gestor.get().strip()
        filtro = self.var_filtro_gestor.get()

        catalogo = inventario_service.obtener_catalogo_ubicaciones(busqueda=busq, anaquel_filtro=filtro)
        for i, item in enumerate(catalogo):
            self.tree_gestor.insert(
                "",
                "end",
                tags=("alterna",) if i % 2 else (),
                values=(
                    item["codigo"],
                    item["producto"],
                    item["laboratorio"],
                    item["anaquel"],
                    item.get("fecha_mod", "")[:16],
                ),
            )
        self.lbl_contador_gestor.configure(text=f"{len(catalogo):,} productos registrados")

    def _mover_productos_seleccionados(self) -> None:
        """
        Reasigna la sección de los productos seleccionados en el gestor.

        Se comunica con:
            - `services/inventario_service.py`: Llama a `asignar_lote_anaquel(items_a_mover)`.
        """
        seleccionados = self.tree_gestor.selection()
        if not seleccionados:
            messagebox.showwarning(config.APP_NOMBRE, "Seleccione uno o más productos de la tabla para moverlos.")
            return

        nuevo_anaquel = self.var_nuevo_anaquel.get()
        items_a_mover = []
        for s in seleccionados:
            vals = self.tree_gestor.item(s, "values")
            items_a_mover.append((vals[0], vals[1], vals[2], nuevo_anaquel))

        inventario_service.asignar_lote_anaquel(items_a_mover)
        messagebox.showinfo(
            config.APP_NOMBRE, f"Se movieron {len(items_a_mover)} producto(s) a '{nuevo_anaquel}' correctamente."
        )
        self._cargar_datos_gestor()
        if self.df_stock is not None:
            self._actualizar_vista_conteo()

    def _reasignar_laboratorio_completo(self) -> None:
        """
        Mueve todos los productos pertenecientes al laboratorio del ítem seleccionado a una nueva sección.

        Se comunica con:
            - `services/inventario_service.py`: Consulta `obtener_catalogo_ubicaciones` y ejecuta `asignar_lote_anaquel`.
        """
        seleccionado = self.tree_gestor.selection()
        if not seleccionado:
            messagebox.showwarning(
                config.APP_NOMBRE, "Seleccione un producto para tomar su laboratorio como referencia."
            )
            return

        vals = self.tree_gestor.item(seleccionado[0], "values")
        laboratorio = vals[2].strip()
        if not laboratorio:
            messagebox.showwarning(config.APP_NOMBRE, "El producto seleccionado no tiene laboratorio definido.")
            return

        nuevo_anaquel = self.var_nuevo_anaquel.get()
        if not messagebox.askyesno(
            config.APP_NOMBRE,
            f"¿Desea mover TODOS los productos del laboratorio '{laboratorio}' a:\n'{nuevo_anaquel}'?",
        ):
            return

        # Buscar todos los productos del laboratorio en BD
        prods_lab = inventario_service.obtener_catalogo_ubicaciones(busqueda=laboratorio, anaquel_filtro="Todos")
        items = [
            (p["codigo"], p["producto"], p["laboratorio"], nuevo_anaquel)
            for p in prods_lab
            if p["laboratorio"] == laboratorio
        ]
        total = inventario_service.asignar_lote_anaquel(items)

        messagebox.showinfo(
            config.APP_NOMBRE,
            f"Se actualizaron {total} producto(s) del laboratorio '{laboratorio}' a '{nuevo_anaquel}'.",
        )
        self._cargar_datos_gestor()
        if self.df_stock is not None:
            self._actualizar_vista_conteo()

    # ----------------------------------------------------------------------- #
    # PESTAÑA 3: PRODUCTOS NUEVOS POR ASIGNAR
    # ----------------------------------------------------------------------- #
    def _construir_pestana_nuevos(self) -> None:
        """
        Construye la interfaz de la Pestaña 3 para clasificar productos recién ingresados al stock.
        """
        aviso_frame = tk.Frame(self.tab_nuevos, bg="#fff8e6", bd=1, relief="solid")
        aviso_frame.pack(fill="x", padx=6, pady=6)

        self.lbl_aviso_nuevos = tk.Label(
            aviso_frame,
            text="No hay productos nuevos pendientes. Cargue un reporte de stock en la pestaña 1 para verificar.",
            font=(config.FUENTE, 9, "bold"),
            bg="#fff8e6",
            fg="#8a6100",
            justify="left",
        )
        self.lbl_aviso_nuevos.pack(anchor="w", padx=10, pady=8)

        # Tabla de productos nuevos
        self.tree_nuevos = crear_treeview(self.tab_nuevos, self.COLUMNAS_NUEVOS)
        self.tree_nuevos.tag_configure("alterna", background=config.COLOR_FONDO)

        # Acciones para asignar
        acc_frame = tk.Frame(self.tab_nuevos, bg=config.COLOR_TARJETA, bd=1, relief="solid")
        acc_frame.pack(fill="x", padx=6, pady=6)

        tk.Label(
            acc_frame,
            text="Asignar sección a productos nuevos:",
            font=(config.FUENTE, 9, "bold"),
            bg=config.COLOR_TARJETA,
            fg=config.COLOR_TEXTO,
        ).pack(side="left", padx=(10, 6), pady=8)

        self.var_anaquel_nuevos = tk.StringVar(value=config.SECCION_CAJA)
        cb_anaq_nuevos = ttk.Combobox(
            acc_frame, textvariable=self.var_anaquel_nuevos, values=config.ANAQUELES, state="readonly", width=25
        )
        cb_anaq_nuevos.pack(side="left", padx=4, pady=8)

        ttk.Button(
            acc_frame, text="Asignar Seleccionados", style="Primario.TButton", command=self._asignar_nuevos_seleccionados
        ).pack(side="left", padx=8, pady=8)

        ttk.Button(
            acc_frame, text="Asignar TODOS los Nuevos", command=self._asignar_todos_los_nuevos
        ).pack(side="left", padx=6, pady=8)

    def _actualizar_pestana_nuevos(self) -> None:
        """
        Refresca la lista de productos sin ubicación en la Pestaña 3.
        """
        self.tree_nuevos.delete(*self.tree_nuevos.get_children())
        if self.df_nuevos is None or self.df_nuevos.empty:
            self.lbl_aviso_nuevos.configure(
                text="✅ Todos los productos del reporte cargado tienen un anaquel asignado. ¡Catálogo al día!"
            )
            return

        total = len(self.df_nuevos)
        self.lbl_aviso_nuevos.configure(
            text=f"⚠️ Se detectaron {total} producto(s) nuevos en el reporte sin anaquel asignado.\n"
            "Seleccione los productos y asígneles su anaquel correspondiente para que aparezcan en la hoja de conteo."
        )

        for i, r in enumerate(self.df_nuevos.itertuples(index=False)):
            self.tree_nuevos.insert(
                "",
                "end",
                tags=("alterna",) if i % 2 else (),
                values=(r.codigo, r.producto, r.tipo),
            )

    def _asignar_nuevos_seleccionados(self) -> None:
        """
        Guarda en base de datos la sección elegida para los productos nuevos seleccionados.

        Se comunica con:
            - `services/inventario_service.py`: Llama a `asignar_lote_anaquel(items)`.
        """
        seleccionados = self.tree_nuevos.selection()
        if not seleccionados:
            messagebox.showwarning(config.APP_NOMBRE, "Seleccione uno o más productos nuevos de la tabla.")
            return

        destino = self.var_anaquel_nuevos.get()
        items = []
        codigos_asignados = set()
        for s in seleccionados:
            vals = self.tree_nuevos.item(s, "values")
            cod, prod, lab = vals[0], vals[1], vals[2]
            items.append((cod, prod, lab, destino))
            codigos_asignados.add(cod)

        inventario_service.asignar_lote_anaquel(items)

        # Actualizar lista de nuevos
        if self.df_nuevos is not None:
            self.df_nuevos = self.df_nuevos[~self.df_nuevos["codigo"].isin(codigos_asignados)].copy()

        total_restantes = len(self.df_nuevos) if self.df_nuevos is not None else 0
        if total_restantes > 0:
            self.notebook.tab(self.tab_nuevos, text=f"  ⚠️ Productos Nuevos ({total_restantes})  ")
        else:
            self.notebook.tab(self.tab_nuevos, text="  ✅ Sin Productos Nuevos  ")

        self._actualizar_pestana_nuevos()
        self._cargar_datos_gestor()
        if self.df_stock is not None:
            self._actualizar_vista_conteo()

        messagebox.showinfo(config.APP_NOMBRE, f"Se asignaron {len(items)} producto(s) a '{destino}'.")

    def _asignar_todos_los_nuevos(self) -> None:
        """
        Asigna en bloque todos los productos nuevos pendientes a la sección seleccionada.

        Se comunica con:
            - `services/inventario_service.py`: Llama a `asignar_lote_anaquel(items)`.
        """
        if self.df_nuevos is None or self.df_nuevos.empty:
            messagebox.showinfo(config.APP_NOMBRE, "No hay productos nuevos pendientes de asignación.")
            return

        destino = self.var_anaquel_nuevos.get()
        total = len(self.df_nuevos)
        if not messagebox.askyesno(
            config.APP_NOMBRE,
            f"¿Desea asignar los {total} productos nuevos a:\n'{destino}'?",
        ):
            return

        items = [
            (str(r.codigo), str(r.producto), str(r.tipo), destino)
            for r in self.df_nuevos.itertuples(index=False)
        ]
        inventario_service.asignar_lote_anaquel(items)

        self.df_nuevos = pd.DataFrame(columns=["codigo", "producto", "tipo"])
        self.notebook.tab(self.tab_nuevos, text="  ✅ Sin Productos Nuevos  ")
        self._actualizar_pestana_nuevos()
        self._cargar_datos_gestor()
        if self.df_stock is not None:
            self._actualizar_vista_conteo()

        messagebox.showinfo(config.APP_NOMBRE, f"Se asignaron {total} productos a '{destino}'.")

    def al_mostrar(self) -> None:
        """
        Se ejecuta cada vez que el usuario ingresa a `PantallaInventario`.
        Refresca la insignia de usuario en la barra superior y recarga el catálogo del gestor.

        Se comunica con:
            - `ui/views/base_view.py`: Llama a `super().al_mostrar()`.
        """
        super().al_mostrar()
        self._cargar_datos_gestor()
