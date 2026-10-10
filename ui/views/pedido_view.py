"""
===============================================================================
MÓDULO: ui/views/pedido_view.py
DESCRIPCIÓN:
    Pantalla de recomendación de pedidos (`PantallaPedido` - Solo Admin/Soporte).
    Permite arrastrar o seleccionar reportes de ventas e inventario, almacenar el
    historial acumulado en SQLite, parametrizar días de lead time / seguridad /
    cobertura, visualizar sugerencias de compra por urgencia y exportar a Excel.

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Importa de `config.py`: Estados de inventario, colores de semáforo y fuentes.
    - Importa de `services/pedido_service.py`: Lógica de importación de ventas,
      resumen de historial y cálculo de recomendación (`calcular_recomendacion`).
    - Importa de `services/reportes_service.py`: `leer_stock` para parsear el stock actual.
    - Importa de `ui/views/base_view.py`: Hereda de `PantallaBase`.
    - Importa de `ui/widgets.py`: `Tarjeta`, `ZonaDrop`, `crear_treeview`, `fmt_num`, `abrir_archivo`.
    - Es instanciada y gestionada por: `ui/app.py` (`VitalStockApp`).
===============================================================================
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
import pandas as pd

import config
from services import pedido_service, reportes_service
from ui.views.base_view import PantallaBase
from ui.widgets import Tarjeta, ZonaDrop, abrir_archivo, crear_treeview, fmt_num


class PantallaPedido(PantallaBase):
    """
    Vista de análisis de rotación y cálculo de sugerencias de compra.

    Se comunica con:
        - `services/pedido_service.py`: Importa ventas, consulta historial y calcula pedidos.
        - `services/reportes_service.py`: Lee archivos de stock `.xls`/`.xlsx`/`.html`.
        - `ui/app.py`: Verifica permisos de administrador en `al_mostrar()`.
    """

    titulo = "Recomendación de pedido"
    subtitulo = "Ventas históricas × stock actual"

    COLUMNAS = [
        ("codigo", "Código", 90, "w"),
        ("producto", "Producto", 320, "w"),
        ("stock_u", "Stock U", 70, "e"),
        ("stock_f", "Stock F", 70, "e"),
        ("cpd", "CPD", 70, "e"),
        ("dias_stock", "Días stock", 85, "e"),
        ("punto_pedido", "Punto pedido", 95, "e"),
        ("a_pedir", "A pedir", 70, "e"),
        ("estado", "Estado", 110, "center"),
    ]

    MAPA_ORDEN = {
        "codigo": "codigo",
        "producto": "producto",
        "stock_u": "cant",
        "stock_f": "frac",
        "cpd": "cpd",
        "dias_stock": "dias_stock",
        "punto_pedido": "punto_pedido",
        "a_pedir": "a_pedir",
        "estado": "estado",
    }

    def __init__(self, padre, app):
        """
        Inicializa las zonas de carga de archivos, controles de parámetros, filtros y tabla.
        """
        super().__init__(padre, app)
        self.df_stock: pd.DataFrame | None = None
        self.df_resultado: pd.DataFrame | None = None
        self._orden_actual: tuple[str, bool] | None = None

        # --- Fila superior: zonas drop + parámetros ---
        superior = tk.Frame(self.cuerpo, bg=config.COLOR_FONDO)
        superior.pack(fill="x")
        superior.columnconfigure((0, 1), weight=1, uniform="drop")

        self.zona_ventas = ZonaDrop(superior, "1. Reporte(s) de VENTAS", self._recibir_ventas, multiple=True)
        self.zona_ventas.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.zona_stock = ZonaDrop(superior, "2. Reporte de STOCK actual", self._recibir_stock)
        self.zona_stock.grid(row=0, column=1, sticky="nsew", padx=8)

        params = Tarjeta(superior, "Parámetros (días)")
        params.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        self.var_lead = tk.IntVar(value=3)
        self.var_seg = tk.IntVar(value=7)
        self.var_cob = tk.IntVar(value=30)
        grid_p = tk.Frame(params, bg=config.COLOR_TARJETA)
        grid_p.pack(padx=12, pady=(0, 10))
        for i, (texto, var) in enumerate((
            ("Lead time", self.var_lead),
            ("Seguridad", self.var_seg),
            ("Cobertura", self.var_cob),
        )):
            tk.Label(grid_p, text=texto, font=(config.FUENTE, 9), fg=config.COLOR_TEXTO, bg=config.COLOR_TARJETA).grid(
                row=i, column=0, sticky="w", pady=2
            )
            ttk.Spinbox(grid_p, from_=0, to=365, textvariable=var, width=6).grid(row=i, column=1, padx=(8, 0), pady=2)

        # --- Historial ---
        fila_hist = tk.Frame(self.cuerpo, bg=config.COLOR_FONDO)
        fila_hist.pack(fill="x", pady=(10, 4))
        self.lbl_historial = tk.Label(
            fila_hist, text="", font=(config.FUENTE, 10), fg=config.COLOR_TEXTO, bg=config.COLOR_FONDO
        )
        self.lbl_historial.pack(side="left")
        ttk.Button(
            fila_hist, text="Borrar historial", style="Peligro.TButton", command=self._borrar_historial
        ).pack(side="right")
        ttk.Button(
            fila_hist, text="Ver importaciones", style="Secundario.TButton", command=self._ver_importaciones
        ).pack(side="right", padx=6)

        # --- Acciones y filtros ---
        acciones = tk.Frame(self.cuerpo, bg=config.COLOR_FONDO)
        acciones.pack(fill="x", pady=(4, 8))
        ttk.Button(
            acciones, text="Calcular recomendación", style="Primario.TButton", command=self._calcular
        ).pack(side="left")
        ttk.Button(
            acciones, text="Exportar a Excel", style="Secundario.TButton", command=self._exportar
        ).pack(side="left", padx=8)

        tk.Label(
            acciones, text="Estado:", font=(config.FUENTE, 9), fg=config.COLOR_TEXTO, bg=config.COLOR_FONDO
        ).pack(side="left", padx=(16, 4))
        self.var_filtro_estado = tk.StringVar(value="Todos")
        cb = ttk.Combobox(
            acciones,
            textvariable=self.var_filtro_estado,
            state="readonly",
            width=14,
            values=["Todos", "Con pedido"] + config.ESTADOS,
        )
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda _e: self._poblar_tabla())

        tk.Label(
            acciones, text="Buscar:", font=(config.FUENTE, 9), fg=config.COLOR_TEXTO, bg=config.COLOR_FONDO
        ).pack(side="left", padx=(12, 4))
        self.var_buscar = tk.StringVar()
        self.var_buscar.trace_add("write", lambda *_: self._poblar_tabla())
        ttk.Entry(acciones, textvariable=self.var_buscar, width=24).pack(side="left")

        self.lbl_resumen = tk.Label(
            acciones, text="", font=(config.FUENTE, 9), fg=config.COLOR_TEXTO_SEC, bg=config.COLOR_FONDO
        )
        self.lbl_resumen.pack(side="right")

        # --- Tabla ---
        self.tree = crear_treeview(self.cuerpo, self.COLUMNAS)
        for col_id, titulo, _a, _b in self.COLUMNAS:
            self.tree.heading(col_id, text=titulo, command=lambda c=col_id: self._ordenar_por(c))
        for estado, tag in config.TAGS_ESTADO.items():
            if estado in config.COLORES_ESTADO:
                self.tree.tag_configure(tag, background=config.COLORES_ESTADO[estado])

    def al_mostrar(self) -> None:
        """
        Verifica que el usuario activo tenga rol Admin/Soporte y actualiza el resumen de historial.

        Se comunica con:
            - `ui/views/base_view.py`: Llama a `super().al_mostrar()`.
            - `ui/app.py`: Consulta `self.app.es_admin()` y redirige a `PantallaMenu` si no tiene permiso.
        """
        super().al_mostrar()
        if not self.app.es_admin():
            messagebox.showwarning(
                config.APP_NOMBRE,
                "Acceso Restringido\n\n"
                "La sección 'Recomendación de pedido' está reservada para Administración.",
                parent=self,
            )
            self.app.mostrar("PantallaMenu")
            return
        self.actualizar_historial()

    def actualizar_historial(self) -> None:
        """
        Muestra el rango de fechas, total de días y cantidad de archivos de ventas importados.

        Se comunica con:
            - `services/pedido_service.py`: Llama a `obtener_resumen_historial()`.
        """
        try:
            resumen = pedido_service.obtener_resumen_historial()
        except Exception as exc:
            self.lbl_historial.configure(text=f"Historial de ventas guardado: error ({exc})", fg=config.COLOR_ERROR)
            return
        if not resumen:
            self.lbl_historial.configure(
                text="Historial de ventas guardado: (vacío) — importe reportes de ventas",
                fg=config.COLOR_TEXTO_SEC,
            )
            return
        self.lbl_historial.configure(
            fg=config.COLOR_TEXTO,
            text=(
                f"Historial de ventas guardado: del {resumen['fecha_inicio']:%d/%m/%Y} "
                f"al {resumen['fecha_fin']:%d/%m/%Y}  ·  {resumen['dias']} días  ·  "
                f"{resumen['archivos']} archivo(s)  ·  {resumen['registros']:,} registros"
            ),
        )

    def _recibir_ventas(self, rutas: list[str]) -> None:
        """
        Callback ejecutado cuando el usuario suelta o selecciona archivos de ventas.

        Se comunica con:
            - `services/pedido_service.py`: Llama a `importar_ventas(ruta)` por cada archivo.
        """
        importados, duplicados, errores = [], [], []
        for ruta in rutas:
            try:
                info = pedido_service.importar_ventas(ruta)
                importados.append(
                    f"• {info['archivo']}: {info['fecha_inicio']:%d/%m/%Y} – "
                    f"{info['fecha_fin']:%d/%m/%Y} ({info['registros']} registros)"
                )
            except pedido_service.ArchivoDuplicadoError:
                duplicados.append(f"• {Path(ruta).name}")
            except Exception as exc:
                errores.append(f"• {Path(ruta).name}: {exc}")

        self.actualizar_historial()
        partes = []
        if importados:
            partes.append("Importados:\n" + "\n".join(importados))
        if duplicados:
            partes.append("Ya existían en el historial (omitidos):\n" + "\n".join(duplicados))
        if errores:
            partes.append("Con errores:\n" + "\n".join(errores))
        mensaje = "\n\n".join(partes)

        if errores and not importados:
            self.zona_ventas.set_estado("Error al importar", ok=False)
            messagebox.showerror(config.APP_NOMBRE, mensaje)
        elif duplicados and not importados and not errores:
            self.zona_ventas.set_estado("Archivo(s) ya importado(s)", ok=False)
            messagebox.showwarning(config.APP_NOMBRE, mensaje)
        else:
            self.zona_ventas.set_estado(f"{len(importados)} archivo(s) importado(s)")
            (messagebox.showwarning if (errores or duplicados) else messagebox.showinfo)(config.APP_NOMBRE, mensaje)

        if importados and self.df_stock is not None:
            self._calcular(silencioso=True)

    def _recibir_stock(self, rutas: list[str]) -> None:
        """
        Callback ejecutado cuando el usuario carga el reporte de stock actual.

        Se comunica con:
            - `services/reportes_service.py`: Llama a `leer_stock(ruta)`.
            - `services/pedido_service.py`: Verifica `obtener_dias_periodo()` para autocalcular.
        """
        ruta = rutas[0]
        try:
            self.df_stock = reportes_service.leer_stock(ruta)
        except Exception as exc:
            self.zona_stock.set_estado("Error al leer el archivo", ok=False)
            messagebox.showerror(config.APP_NOMBRE, f"No se pudo leer el stock:\n\n{exc}")
            return
        self.zona_stock.set_estado(f"{Path(ruta).name} · {len(self.df_stock):,} productos")
        if pedido_service.obtener_dias_periodo():
            self._calcular(silencioso=True)

    def _leer_parametros(self) -> tuple[int, int, int]:
        """
        Extrae y valida los parámetros numéricos de Lead time, Seguridad y Cobertura.
        """
        try:
            valores = (self.var_lead.get(), self.var_seg.get(), self.var_cob.get())
        except tk.TclError as exc:
            raise ValueError("Los parámetros deben ser números enteros.") from exc
        if any(v < 0 for v in valores):
            raise ValueError("Los parámetros no pueden ser negativos.")
        return valores

    def _calcular(self, silencioso: bool = False) -> None:
        """
        Ejecuta el cruce entre el stock cargado y el historial de ventas para generar sugerencias.

        Se comunica con:
            - `services/pedido_service.py`: Llama a `calcular_recomendacion(...)`.
        """
        try:
            lead, seg, cob = self._leer_parametros()
            self.df_resultado = pedido_service.calcular_recomendacion(self.df_stock, lead, seg, cob)
        except ValueError as exc:
            if not silencioso:
                messagebox.showwarning(config.APP_NOMBRE, str(exc))
            return
        except Exception as exc:
            messagebox.showerror(config.APP_NOMBRE, f"Error al calcular la recomendación:\n\n{exc}")
            return
        self._orden_actual = None
        self._poblar_tabla()

    def _filtrar(self) -> pd.DataFrame:
        """
        Aplica los filtros de estado y búsqueda de texto sobre `self.df_resultado`.
        """
        df = self.df_resultado
        filtro = self.var_filtro_estado.get()
        if filtro == "Con pedido":
            df = df[df["a_pedir"] > 0]
        elif filtro != "Todos":
            df = df[df["estado"] == filtro]
        texto = self.var_buscar.get().strip().upper()
        if texto:
            mascara = (
                df["producto"].str.upper().str.contains(texto, regex=False)
                | df["codigo"].str.upper().str.contains(texto, regex=False)
            )
            df = df[mascara]
        return df

    def _poblar_tabla(self) -> None:
        """
        Renderiza las filas filtradas en el Treeview aplicando colores por estado.

        Se comunica con:
            - `ui/widgets.py`: Usa `fmt_num` para formatear cantidades y decimales.
        """
        self.tree.delete(*self.tree.get_children())
        if self.df_resultado is None:
            return
        df = self._filtrar()
        for r in df.itertuples(index=False):
            self.tree.insert(
                "",
                "end",
                tags=(config.TAGS_ESTADO.get(r.estado, "normal"),),
                values=(
                    r.codigo,
                    r.producto,
                    fmt_num(r.cant),
                    fmt_num(r.frac),
                    fmt_num(r.cpd, 2),
                    fmt_num(r.dias_stock, 1),
                    fmt_num(r.punto_pedido, 1),
                    fmt_num(r.a_pedir),
                    r.estado,
                ),
            )
        conteo = self.df_resultado["estado"].value_counts()
        detalle = "  ·  ".join(f"{e}: {conteo.get(e, 0)}" for e in config.ESTADOS if conteo.get(e, 0))
        self.lbl_resumen.configure(text=f"Mostrando {len(df):,} de {len(self.df_resultado):,}   |   {detalle}")

    def _ordenar_por(self, col_id: str) -> None:
        """
        Ordena ascendente o descendentemente la tabla al hacer clic en un encabezado.
        """
        if self.df_resultado is None:
            return
        ascendente = not (self._orden_actual == (col_id, True))
        columna = self.MAPA_ORDEN[col_id]
        if columna == "estado":
            clave = lambda s: s.map(config.PRIORIDAD_ESTADOS)
        elif self.df_resultado[columna].dtype == object:
            clave = lambda s: s.str.upper()
        else:
            clave = None
        self.df_resultado = self.df_resultado.sort_values(columna, ascending=ascendente, key=clave, kind="mergesort")
        self._orden_actual = (col_id, ascendente)
        self._poblar_tabla()

    def _exportar(self) -> None:
        """
        Exporta la tabla filtrada de recomendación de pedido a un archivo Excel `.xlsx`.

        Se comunica con:
            - `ui/widgets.py`: Llama a `abrir_archivo(Path(ruta))` si el usuario desea abrir el Excel.
        """
        if self.df_resultado is None or self.df_resultado.empty:
            messagebox.showwarning(config.APP_NOMBRE, "Primero calcule la recomendación.")
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar recomendación",
            defaultextension=".xlsx",
            initialfile=f"Pedido_{datetime.now():%Y%m%d_%H%M}.xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not ruta:
            return
        df = self._filtrar().copy()
        df["dias_stock"] = df["dias_stock"].replace([np.inf, -np.inf], np.nan)
        df = df.rename(
            columns={
                "codigo": "Código",
                "producto": "Producto",
                "tipo": "Laboratorio",
                "ufrac": "U. Frac",
                "cant": "Stock U",
                "frac": "Stock F",
                "venta_eq": "Venta eq.",
                "cpd": "CPD",
                "stock_eq": "Stock eq.",
                "dias_stock": "Días stock",
                "punto_pedido": "Punto pedido",
                "a_pedir": "A pedir",
                "estado": "Estado",
            }
        )
        try:
            df.round(2).to_excel(ruta, index=False, sheet_name="Pedido")
        except PermissionError:
            messagebox.showerror(config.APP_NOMBRE, "No se pudo guardar. Cierre el archivo si está abierto en Excel.")
            return
        except Exception as exc:
            messagebox.showerror(config.APP_NOMBRE, f"Error al exportar:\n\n{exc}")
            return
        if messagebox.askyesno(config.APP_NOMBRE, "Archivo exportado correctamente.\n¿Desea abrirlo?"):
            abrir_archivo(Path(ruta))

    def _ver_importaciones(self) -> None:
        """
        Muestra un cuadro de diálogo con la lista de reportes de ventas importados.

        Se comunica con:
            - `services/pedido_service.py`: Llama a `listar_importaciones()`.
        """
        try:
            df = pedido_service.listar_importaciones()
        except Exception as exc:
            messagebox.showerror(config.APP_NOMBRE, f"No se pudo leer el historial:\n\n{exc}")
            return
        if df.empty:
            messagebox.showinfo(config.APP_NOMBRE, "No hay importaciones registradas.")
            return
        lineas = [f"• {r.archivo}  ({r.fecha_inicio} → {r.fecha_fin}, {r.registros} reg.)" for r in df.itertuples()]
        messagebox.showinfo(config.APP_NOMBRE, "Archivos importados:\n\n" + "\n".join(lineas[-40:]))

    def _borrar_historial(self) -> None:
        """
        Solicita confirmación y vacía el historial de ventas acumulado en la base de datos.

        Se comunica con:
            - `services/pedido_service.py`: Llama a `limpiar_historial()`.
        """
        if not messagebox.askyesno(
            config.APP_NOMBRE,
            "¿Eliminar TODO el historial de ventas guardado?\nEsta acción no se puede deshacer.",
            icon="warning",
        ):
            return
        try:
            pedido_service.limpiar_historial()
        except Exception as exc:
            messagebox.showerror(config.APP_NOMBRE, f"No se pudo borrar el historial:\n\n{exc}")
            return
        self.df_resultado = None
        self._poblar_tabla()
        self.lbl_resumen.configure(text="")
        self.zona_ventas.set_estado("Sin archivo", ok=True)
        self.actualizar_historial()
