"""
ui/dialogs/yape_history_dialog.py - Ventana de Historial, Filtrado y Exportación de Pagos Yape.

Muestra los pagos recibidos desde VitalNotifier con su fecha y hora exacta de operación
(`fecha_hora`), permitiendo filtrarlos por período, buscar por cliente y exportarlos a Excel.

Comunicación con otros archivos del proyecto:
  - Instanciada desde `ui/views/menu_view.py` (`PantallaMenu._ver_pagos_yape`).
  - Registrada en `ui/app.py` (`self.ventana_historial_yape`) para auto-refrescarse en tiempo real
    cuando `ServicioNotificacionesYape` recibe un pago nuevo.
  - Consume `services/yape_service.py` (`listar_pagos_yape` y `eliminar_pago_yape`).
  - Consume `services/inventario_service.py` (`generar_excel_pagos_yape`).
  - Utiliza `config.py` (colores y constantes) y `ui/widgets.py` (`Tarjeta`, `crear_treeview`, `abrir_archivo`).
"""

from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import config
from services import inventario_service, yape_service
from ui.widgets import Tarjeta, abrir_archivo, crear_treeview


class VentanaHistorialYape(tk.Toplevel):
    """Ventana modal/secundaria para consultar, auditar y exportar a Excel los pagos Yape."""

    COLUMNAS = [
        ("num", "#", 45, "center"),
        ("fecha", "Fecha / Hora del Yape", 155, "center"),
        ("cliente", "Remitente / Cliente", 220, "w"),
        ("monto", "Monto (S/)", 95, "e"),
        ("seg", "Cód. Seg", 90, "center"),
        ("detalle", "Mensaje / Detalle Notificación", 320, "w"),
    ]

    def __init__(self, maestro: tk.Tk | tk.Toplevel, app) -> None:
        """Construye la ventana de historial de pagos Yape, sus filtros de período y su tabla.

        Si el usuario en sesión tiene rol de mantenimiento (`app.es_soporte()`), habilita
        controles especiales para depurar o eliminar transacciones de prueba.

        Comunicación entre módulos:
          - Recibe la instancia `app` (`VitalStockApp` de `ui/app.py`) para verificar permisos (`es_soporte`).
          - Utiliza componentes visuales de `ui/widgets.py` (`Tarjeta`, `crear_treeview`).
          - Invoca `self.cargar_datos()` que consulta `services/yape_service.py`.
        """
        super().__init__(maestro)
        self.app = app
        self.title(f"{config.APP_NOMBRE} · Historial y Exportación de Pagos Yape")
        self.geometry("980x620")
        self.minsize(840, 520)
        self.configure(bg=config.COLOR_FONDO)
        self.transient(maestro)

        self.pagos_actuales: list[dict] = []
        self.pagos_filtrados: list[dict] = []
        self.etiqueta_periodo = ""

        # Centrar la ventana respecto al padre
        self._centrar(maestro)

        barra = tk.Frame(self, bg=config.COLOR_PRIMARIO, height=52)
        barra.pack(fill="x")
        barra.pack_propagate(False)

        tk.Label(
            barra,
            text="💰 Control y Exportación de Pagos Yape",
            font=(config.FUENTE, 13, "bold"),
            fg="white",
            bg=config.COLOR_PRIMARIO,
        ).pack(side="left", padx=16)
        tk.Label(
            barra,
            text="Historial sincronizado desde VitalNotifier  ·  Exportación a Excel",
            font=(config.FUENTE, 9),
            fg="#cfe5de",
            bg=config.COLOR_PRIMARIO,
        ).pack(side="left")

        cuerpo = tk.Frame(self, bg=config.COLOR_FONDO, padx=16, pady=12)
        cuerpo.pack(fill="both", expand=True)

        tarjeta_filtros = Tarjeta(cuerpo, "Filtros de Período y Búsqueda")
        tarjeta_filtros.pack(fill="x", pady=(0, 10))

        fila_f = tk.Frame(tarjeta_filtros, bg=config.COLOR_TARJETA, padx=12, pady=6)
        fila_f.pack(fill="x", pady=(0, 6))

        tk.Label(fila_f, text="Período:", font=(config.FUENTE, 9, "bold"), fg=config.COLOR_TEXTO, bg=config.COLOR_TARJETA).grid(
            row=0, column=0, sticky="w", pady=4
        )

        self.var_filtro = tk.StringVar(value="dia")
        opciones_periodo = [
            ("Yapes del día (Hoy)", "dia"),
            ("La semana (Desde el lunes)", "semana"),
            ("Por rango de fechas", "rango"),
            ("Todos los registros", "todos"),
        ]
        for idx, (texto, val) in enumerate(opciones_periodo):
            rb = ttk.Radiobutton(fila_f, text=texto, value=val, variable=self.var_filtro, command=self._al_cambiar_modo_filtro)
            rb.grid(row=0, column=idx + 1, padx=(6, 12), sticky="w")

        self.frame_rango = tk.Frame(fila_f, bg=config.COLOR_TARJETA)
        self.frame_rango.grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

        tk.Label(self.frame_rango, text="Desde (DD/MM/AAAA):", font=(config.FUENTE, 9), fg=config.COLOR_TEXTO, bg=config.COLOR_TARJETA).pack(side="left")
        hoy = date.today()
        primer_dia_mes = date(hoy.year, hoy.month, 1)
        self.var_fecha_desde = tk.StringVar(value=primer_dia_mes.strftime("%d/%m/%Y"))
        self.ent_desde = ttk.Entry(self.frame_rango, textvariable=self.var_fecha_desde, width=12)
        self.ent_desde.pack(side="left", padx=(4, 12))

        tk.Label(self.frame_rango, text="Hasta (DD/MM/AAAA):", font=(config.FUENTE, 9), fg=config.COLOR_TEXTO, bg=config.COLOR_TARJETA).pack(side="left")
        self.var_fecha_hasta = tk.StringVar(value=hoy.strftime("%d/%m/%Y"))
        self.ent_hasta = ttk.Entry(self.frame_rango, textvariable=self.var_fecha_hasta, width=12)
        self.ent_hasta.pack(side="left", padx=(4, 12))

        self.btn_aplicar_rango = ttk.Button(self.frame_rango, text="Filtrar fechas", style="Secundario.TButton", command=self.cargar_datos)
        self.btn_aplicar_rango.pack(side="left", padx=(0, 20))

        tk.Label(self.frame_rango, text="Buscar cliente:", font=(config.FUENTE, 9), fg=config.COLOR_TEXTO, bg=config.COLOR_TARJETA).pack(side="left")
        self.var_buscar = tk.StringVar()
        self.var_buscar.trace_add("write", lambda *_: self._filtrar_tabla_local())
        ttk.Entry(self.frame_rango, textvariable=self.var_buscar, width=20).pack(side="left", padx=(4, 0))

        self._actualizar_visibilidad_rango()

        tarjeta_tabla = Tarjeta(cuerpo, "Detalle de Transacciones Registradas")
        tarjeta_tabla.pack(fill="both", expand=True)

        self.tree = crear_treeview(tarjeta_tabla, self.COLUMNAS)
        self.tree.tag_configure("par", background=config.COLOR_TARJETA)
        self.tree.tag_configure("impar", background="#f9fbfa")

        fila_pie = tk.Frame(cuerpo, bg=config.COLOR_FONDO, pady=8)
        fila_pie.pack(fill="x")

        self.lbl_resumen = tk.Label(
            fila_pie,
            text="Cargando...",
            font=(config.FUENTE, 10, "bold"),
            fg=config.COLOR_PRIMARIO,
            bg=config.COLOR_FONDO,
        )
        self.lbl_resumen.pack(side="left")

        self.lbl_periodo_desc = tk.Label(
            fila_pie,
            text="",
            font=(config.FUENTE, 9, "italic"),
            fg=config.COLOR_TEXTO_SEC,
            bg=config.COLOR_FONDO,
        )
        self.lbl_periodo_desc.pack(side="left", padx=16)

        if hasattr(self.app, "es_soporte") and self.app.es_soporte():
            ttk.Button(
                fila_pie,
                text="🗑️ Eliminar Pago (Mantenimiento)",
                style="Peligro.TButton",
                command=self._eliminar_pago_mantenimiento,
            ).pack(side="left", padx=8)
            self._menu_contextual = tk.Menu(self, tearoff=0)
            self._menu_contextual.add_command(
                label="🗑️ Eliminar Transacción (Mantenimiento)",
                command=self._eliminar_pago_mantenimiento,
            )
            self.tree.bind("<Button-3>", self._mostrar_menu_contextual)

        ttk.Button(fila_pie, text="Exportar a Excel (.xlsx)", style="Primario.TButton", command=self._exportar_excel).pack(side="right")
        ttk.Button(fila_pie, text="Actualizar lista", style="Secundario.TButton", command=self.cargar_datos).pack(side="right", padx=8)

        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.cargar_datos()

    def _mostrar_menu_contextual(self, event) -> None:
        """Despliega el menú contextual de clic derecho sobre una fila (exclusivo para soporte)."""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            if hasattr(self, "_menu_contextual"):
                self._menu_contextual.post(event.x_root, event.y_root)

    def _eliminar_pago_mantenimiento(self) -> None:
        """Elimina de la base de datos la transacción seleccionada tras confirmar con el usuario de soporte.

        Comunicación entre módulos:
          - Invoca `yape_service.eliminar_pago_yape(id_pago)` en `services/yape_service.py`.
        """
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning(config.APP_NOMBRE, "Seleccione un pago de la lista para eliminar.", parent=self)
            return
        # El iid de cada fila en el Treeview almacena el ID real de la base de datos
        pago_id = int(sel[0])
        vals = self.tree.item(sel[0], "values")
        fecha = vals[1]
        remitente = vals[2]
        monto = vals[3]

        if not messagebox.askyesno(
            "Eliminar Transacción (Mantenimiento)",
            f"¿Desea eliminar permanentemente esta transacción de la base de datos?\n\n"
            f"ID en BD: #{pago_id}\n"
            f"Remitente: {remitente}\n"
            f"Monto: {monto}\n"
            f"Fecha / Hora Yape: {fecha}\n\n"
            f"Esta operación no se puede deshacer.",
            parent=self,
        ):
            return

        if yape_service.eliminar_pago_yape(pago_id):
            messagebox.showinfo(config.APP_NOMBRE, f"Transacción #{pago_id} eliminada con éxito.", parent=self)
            self.cargar_datos()
        else:
            messagebox.showerror(config.APP_NOMBRE, "No se pudo eliminar el registro.", parent=self)

    def _centrar(self, maestro) -> None:
        """Centra la ventana respecto a la ventana principal (`maestro`)."""
        self.update_idletasks()
        ancho, alto = 980, 620
        x = max(10, maestro.winfo_x() + (maestro.winfo_width() - ancho) // 2)
        y = max(10, maestro.winfo_y() + (maestro.winfo_height() - alto) // 2)
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

    def _al_cambiar_modo_filtro(self) -> None:
        """Actualiza los controles de fechas cuando cambia el radiobutton de período y recarga la tabla."""
        self._actualizar_visibilidad_rango()
        self.cargar_datos()

    def _actualizar_visibilidad_rango(self) -> None:
        """Habilita o deshabilita las cajas de texto de fecha inicial y final según el modo seleccionado."""
        if self.var_filtro.get() == "rango":
            self.ent_desde.configure(state="normal")
            self.ent_hasta.configure(state="normal")
            self.btn_aplicar_rango.configure(state="normal")
        else:
            self.ent_desde.configure(state="disabled")
            self.ent_hasta.configure(state="disabled")
            self.btn_aplicar_rango.configure(state="disabled")

    def cargar_datos(self) -> None:
        """Consulta en SQLite los pagos del período seleccionado y refresca la vista previa.

        Comunicación entre módulos:
          - Llama a `yape_service.listar_pagos_yape()` en `services/yape_service.py`.
          - También es invocada externamente desde `ui/app.py` (`_procesar_eventos_yape`)
            cuando entra un nuevo pago mientras esta ventana está abierta.
        """
        modo = self.var_filtro.get()
        f_desde_str = self.var_fecha_desde.get().strip()
        f_hasta_str = self.var_fecha_hasta.get().strip()

        f_ini, f_fin = None, None
        if modo == "rango":
            try:
                partes_i = [int(p) for p in f_desde_str.replace("-", "/").split("/")]
                f_ini = date(partes_i[2], partes_i[1], partes_i[0]) if len(partes_i) == 3 else None
            except Exception:
                f_ini = None
            try:
                partes_f = [int(p) for p in f_hasta_str.replace("-", "/").split("/")]
                f_fin = date(partes_f[2], partes_f[1], partes_f[0]) if len(partes_f) == 3 else None
            except Exception:
                f_fin = None

        self.pagos_actuales = yape_service.listar_pagos_yape(
            filtro_modo=modo,
            fecha_desde=f_ini,
            fecha_hasta=f_fin,
            limite=1000,
        )

        hoy = date.today()
        if modo == "dia":
            self.etiqueta_periodo = f"Yapes de Hoy ({hoy:%d/%m/%Y})"
        elif modo == "semana":
            lunes = hoy - date.resolution * hoy.weekday()
            self.etiqueta_periodo = f"Semana ({lunes:%d/%m/%Y} al {hoy:%d/%m/%Y})"
        elif modo == "rango":
            self.etiqueta_periodo = f"Rango: {f_desde_str} al {f_hasta_str}"
        else:
            self.etiqueta_periodo = "Todo el historial registrado"

        self._filtrar_tabla_local()

    def _filtrar_tabla_local(self) -> None:
        """Filtra en memoria por texto de búsqueda y renderiza las filas mostrando `fecha_hora` del Yape."""
        termino = self.var_buscar.get().strip().lower()
        if not termino:
            self.pagos_filtrados = list(self.pagos_actuales)
        else:
            self.pagos_filtrados = [
                p for p in self.pagos_actuales
                if termino in str(p.get("remitente", "")).lower()
                or termino in str(p.get("codigo_seg", "")).lower()
                or termino in str(p.get("mensaje_raw", "")).lower()
            ]

        self.tree.delete(*self.tree.get_children())
        total_monto = sum(float(p.get("monto", 0.0)) for p in self.pagos_filtrados)

        for i, p in enumerate(self.pagos_filtrados, start=1):
            tag = "impar" if i % 2 == 1 else "par"
            # Priorizar siempre fecha_hora (la hora real del Yape enviada por VitalNotifier)
            f_txt = str(p.get("fecha_hora") or p.get("fecha_registro") or "")
            m_txt = f"S/ {float(p.get('monto', 0.0)):,.2f}"
            seg_txt = str(p.get("codigo_seg") or "-")
            msg_txt = str(p.get("mensaje_raw") or "")
            iid_bd = str(p.get("id", i))

            self.tree.insert("", "end", iid=iid_bd, tags=(tag,), values=(
                i, f_txt, p.get("remitente", ""), m_txt, seg_txt, msg_txt
            ))

        self.lbl_resumen.configure(
            text=f"{len(self.pagos_filtrados):,} pago(s) encontrado(s)   ·   Total Recaudado: S/ {total_monto:,.2f}"
        )
        self.lbl_periodo_desc.configure(text=f"Filtro aplicado: {self.etiqueta_periodo}")

    def _exportar_excel(self) -> None:
        """Exporta los pagos Yape filtrados a un archivo Excel `.xlsx` con formato institucional.

        Comunicación entre módulos:
          - Invoca `inventario_service.generar_excel_pagos_yape()` en `services/inventario_service.py`.
          - Abre el archivo generado mediante `abrir_archivo()` de `ui/widgets.py`.
        """
        if not self.pagos_filtrados:
            messagebox.showwarning(config.APP_NOMBRE, "No hay pagos para exportar en el período seleccionado.", parent=self)
            return

        hoy = date.today()
        modo = self.var_filtro.get()
        if modo == "dia":
            sugerido = f"Yapes_Dia_{hoy:%Y%m%d}.xlsx"
        elif modo == "semana":
            sugerido = f"Yapes_Semana_{hoy:%Y%m%d}.xlsx"
        elif modo == "rango":
            sugerido = f"Yapes_Rango_{hoy:%Y%m%d}.xlsx"
        else:
            sugerido = f"Yapes_Historial_{hoy:%Y%m%d}.xlsx"

        ruta = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar Reporte de Pagos Yape",
            defaultextension=".xlsx",
            initialfile=sugerido,
            filetypes=[("Excel (*.xlsx)", "*.xlsx"), ("Todos los archivos", "*.*")],
        )
        if not ruta:
            return

        try:
            pagos_ordenados = sorted(
                self.pagos_filtrados,
                key=lambda p: (str(p.get("fecha_registro", "")), p.get("id", 0)),
            )
            salida = inventario_service.generar_excel_pagos_yape(
                pagos=pagos_ordenados,
                ruta_salida=ruta,
                titulo_periodo=self.etiqueta_periodo,
                nombre_botica=config.APP_NOMBRE,
            )
        except PermissionError:
            messagebox.showerror(
                config.APP_NOMBRE,
                "No se pudo guardar el archivo.\nCierre el documento si está abierto en Excel e intente de nuevo.",
                parent=self,
            )
            return
        except Exception as exc:
            messagebox.showerror(config.APP_NOMBRE, f"Error al generar el archivo Excel:\n\n{exc}", parent=self)
            return

        total = sum(float(p.get("monto", 0.0)) for p in self.pagos_filtrados)
        if messagebox.askyesno(
            config.APP_NOMBRE,
            f"¡Reporte Excel generado con éxito!\n\n"
            f"• Archivo: {Path(salida).name}\n"
            f"• Transacciones: {len(self.pagos_filtrados):,}\n"
            f"• Total recaudado: S/ {total:,.2f}\n\n"
            f"¿Desea abrir el archivo Excel ahora?",
            parent=self,
        ):
            abrir_archivo(salida)

    def _cerrar(self) -> None:
        """Limpia la referencia en `VitalStockApp` y destruye la ventana secundaria."""
        if hasattr(self.app, "ventana_historial_yape"):
            self.app.ventana_historial_yape = None
        self.destroy()
