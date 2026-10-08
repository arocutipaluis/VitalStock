"""
VitalStock - Interfaz gráfica (v0.1, solo pantallas)

Pantallas:
  - Menú principal (2 opciones visibles; Yape corre en segundo plano, sin pantalla)
  - Recomendación de pedido
  - Formato de inventario

Todavía NO hay lógica real: los botones "Calcular" y "Generar" usan datos de
ejemplo para que veas cómo queda la interfaz. Los puntos donde se conectará el
motor están marcados con  # TODO.

Dependencias:  ninguna obligatoria (Tkinter viene con Python).
Opcional para arrastrar archivos:  pip install tkinterdnd2
(sin esa librería, la zona de archivos funciona haciendo clic).
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import reportes
import motor
import pandas as pd
from pathlib import Path
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    BaseTk = TkinterDnD.Tk
    HAY_DND = True
except ImportError:
    BaseTk = tk.Tk
    HAY_DND = False

# ----------------------------------------------------------------- estilo
VERSION = "0.1"
C_PRIMARIO = "#1f6f5c"
C_PRIMARIO_OSC = "#165345"
C_FONDO = "#f4f6f5"
C_TEXTO = "#1c2b27"
C_GRIS = "#5f6b67"
F_BASE = ("Segoe UI", 10)
F_NEGRITA = ("Segoe UI", 10, "bold")
F_TITULO = ("Segoe UI", 20, "bold")
F_SUBTITULO = ("Segoe UI", 12)

FILTROS_ARCHIVO = [
    ("Reportes del sistema", "*.xls *.xlsx *.html *.htm"),
    ("Todos los archivos", "*.*"),
]

COLORES_ESTADO = {
    "URGENTE": "#f8d0d0",
    "POR PEDIR": "#fde3c0",
    "SOBRESTOCK": "#d4e4f7",
    "SIN ROTACIÓN": "#e3e3e3",
    "OK": "#ffffff",
}

# Datos de ejemplo (solo para ver la interfaz)
DEMO_PEDIDO = [
    # código, producto, stock, CPD, días stock, punto pedido, a pedir, estado
    ("000123", "PARACETAMOL 500 MG X 100 TAB", 12, 3.2, 3.8, 31, 107, "URGENTE"),
    ("000456", "AMOXICILINA 500 MG X 100 CAP", 40, 3.1, 12.9, 30, 76, "POR PEDIR"),
    ("000789", "IBUPROFENO 400 MG X 100 TAB", 150, 2.0, 75.0, 20, 0, "SOBRESTOCK"),
    ("001010", "OMEPRAZOL 20 MG X 30 CAP", 90, 2.5, 36.0, 24, 0, "OK"),
    ("001111", "JARABE TOS ADULTO 120 ML", 6, 0.0, None, 0, 0, "SIN ROTACIÓN"),
]
DEMO_INVENTARIO = [
    # N°, código, producto, laboratorio, stock sistema
    (1, "000123", "PARACETAMOL 500 MG X 100 TAB", "LAB. A", 12),
    (2, "000456", "AMOXICILINA 500 MG X 100 CAP", "LAB. A", 40),
    (3, "000789", "IBUPROFENO 400 MG X 100 TAB", "LAB. B", 150),
    (4, "001010", "OMEPRAZOL 20 MG X 30 CAP", "LAB. C", 90),
]


# ----------------------------------------------------------- widgets base
class ZonaArchivos(tk.Frame):
    """Cuadro para arrastrar archivos (si hay tkinterdnd2) o hacer clic."""

    def __init__(self, parent, titulo, ayuda, al_recibir, multiple=False):
        super().__init__(parent, bg="white", highlightbackground=C_PRIMARIO,
                         highlightthickness=2, cursor="hand2", height=105)
        self.pack_propagate(False)
        self.al_recibir = al_recibir
        self.multiple = multiple

        self.lbl_titulo = tk.Label(self, text=titulo, font=("Segoe UI", 11, "bold"),
                                   bg="white", fg=C_PRIMARIO)
        self.lbl_titulo.pack(pady=(14, 2))
        self.lbl_estado = tk.Label(self, text=ayuda, font=F_BASE, bg="white",
                                   fg=C_GRIS, wraplength=360, justify="center")
        self.lbl_estado.pack()

        for w in (self, self.lbl_titulo, self.lbl_estado):
            w.bind("<Button-1>", self._elegir)
            if HAY_DND:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._soltar)

    def _elegir(self, _evento=None):
        if self.multiple:
            rutas = list(filedialog.askopenfilenames(filetypes=FILTROS_ARCHIVO))
        else:
            ruta = filedialog.askopenfilename(filetypes=FILTROS_ARCHIVO)
            rutas = [ruta] if ruta else []
        if rutas:
            self.al_recibir(rutas)

    def _soltar(self, evento):
        rutas = list(self.tk.splitlist(evento.data))
        if not self.multiple:
            rutas = rutas[:1]
        if rutas:
            self.al_recibir(rutas)

    def mostrar(self, texto, ok=True):
        self.lbl_estado.config(text=texto, fg="#1b7a3a" if ok else C_GRIS)


class Pantalla(tk.Frame):
    """Pantalla con barra superior (botón Menú + título)."""

    def __init__(self, app, titulo):
        super().__init__(app.contenedor, bg=C_FONDO)
        self.app = app
        barra = tk.Frame(self, bg=C_PRIMARIO)
        barra.pack(fill="x")
        ttk.Button(barra, text="← Menú", style="Barra.TButton",
                   command=lambda: app.mostrar("menu")).pack(side="left", padx=10, pady=8)
        tk.Label(barra, text=titulo, font=("Segoe UI", 14, "bold"),
                 bg=C_PRIMARIO, fg="white").pack(side="left", padx=8)
        self.cuerpo = tk.Frame(self, bg=C_FONDO)
        self.cuerpo.pack(fill="both", expand=True, padx=18, pady=14)
        self.estado = tk.StringVar(value="Listo.")
        tk.Label(self, textvariable=self.estado, anchor="w", font=("Segoe UI", 9),
                 bg="#e6ebe9", fg=C_GRIS).pack(fill="x", side="bottom", ipady=3)


def crear_tabla(parent, columnas, anchos, altura=14):
    """Treeview con scrollbars. columnas: nombres; anchos: px por columna."""
    marco = tk.Frame(parent, bg=C_FONDO)
    tabla = ttk.Treeview(marco, columns=columnas, show="headings", height=altura)
    for col, ancho in zip(columnas, anchos):
        tabla.heading(col, text=col)
        tabla.column(col, width=ancho, anchor="w" if col == "Producto" else "center")
    sy = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
    sx = ttk.Scrollbar(marco, orient="horizontal", command=tabla.xview)
    tabla.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    tabla.grid(row=0, column=0, sticky="nsew")
    sy.grid(row=0, column=1, sticky="ns")
    sx.grid(row=1, column=0, sticky="ew")
    marco.rowconfigure(0, weight=1)
    marco.columnconfigure(0, weight=1)
    return marco, tabla


# ------------------------------------------------------------- menú principal
class PantallaMenu(tk.Frame):
    def __init__(self, app):
        super().__init__(app.contenedor, bg=C_FONDO)
        centro = tk.Frame(self, bg=C_FONDO)
        centro.place(relx=0.5, rely=0.46, anchor="center")

        tk.Label(centro, text="VitalStock", font=F_TITULO, bg=C_FONDO,
                 fg=C_PRIMARIO).pack()
        tk.Label(centro, text="Gestión de stock para tu botica", font=F_SUBTITULO,
                 bg=C_FONDO, fg=C_GRIS).pack(pady=(0, 30))

        ttk.Button(centro, text="Recomendación de pedido", style="Menu.TButton",
                   command=lambda: app.mostrar("pedido")).pack(pady=8, ipadx=30, ipady=14)
        ttk.Button(centro, text="Formato de inventario", style="Menu.TButton",
                   command=lambda: app.mostrar("inventario")).pack(pady=8, ipadx=30, ipady=14)

        tk.Label(self, text=f"VitalStock v{VERSION}  ·  Modo piloto", font=("Segoe UI", 9),
                 bg=C_FONDO, fg=C_GRIS).pack(side="bottom", pady=10)


# ------------------------------------------------------ recomendación de pedido
class PantallaPedido(Pantalla):
    ESTADOS = ["Todos", "URGENTE", "POR PEDIR", "SOBRESTOCK", "SIN ROTACIÓN", "OK"]

    def __init__(self, app):
        super().__init__(app, "Recomendación de pedido")
        self.archivos_ventas = []
        self.archivo_stock = None
        self.filas = []

        # --- fila superior: zonas de archivos + parámetros
        arriba = tk.Frame(self.cuerpo, bg=C_FONDO)
        arriba.pack(fill="x")
        arriba.columnconfigure(0, weight=1)
        arriba.columnconfigure(1, weight=1)

        self.zona_ventas = ZonaArchivos(
            arriba, "1. Ventas por producto",
            "Arrastra aquí el reporte de ventas del mes\n(o haz clic para elegir; puedes elegir varios)",
            self._recibir_ventas, multiple=True)
        self.zona_ventas.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.zona_stock = ZonaArchivos(
            arriba, "2. Stock actual",
            "Arrastra aquí el reporte de stock\n(o haz clic para elegirlo)",
            self._recibir_stock)
        self.zona_stock.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        # --- parámetros + historial
        medio = tk.Frame(self.cuerpo, bg=C_FONDO)
        medio.pack(fill="x", pady=(12, 6))

        params = ttk.LabelFrame(medio, text=" Parámetros ")
        params.pack(side="left", padx=(0, 12))
        self.var_lead = tk.IntVar(value=3)
        self.var_seg = tk.IntVar(value=7)
        self.var_cob = tk.IntVar(value=30)
        for i, (txt, var, rango) in enumerate([
            ("Lead time (días)", self.var_lead, (1, 60)),
            ("Días de seguridad", self.var_seg, (0, 60)),
            ("Días de cobertura", self.var_cob, (7, 120)),
        ]):
            ttk.Label(params, text=txt).grid(row=i, column=0, sticky="w", padx=8, pady=3)
            ttk.Spinbox(params, from_=rango[0], to=rango[1], width=6,
                        textvariable=var).grid(row=i, column=1, padx=8, pady=3)

        hist = ttk.LabelFrame(medio, text=" Historial de ventas guardado ")
        hist.pack(side="left", fill="both", expand=True)
        self.var_hist = tk.StringVar(value="Aún no hay meses cargados.")
        ttk.Label(hist, textvariable=self.var_hist, wraplength=420,
                  justify="left").pack(anchor="w", padx=8, pady=8)

        # --- acciones
        acciones = tk.Frame(self.cuerpo, bg=C_FONDO)
        acciones.pack(fill="x", pady=(0, 6))
        ttk.Button(acciones, text="Calcular recomendación", style="Accion.TButton",
                   command=self._calcular).pack(side="left")
        self.btn_exportar = ttk.Button(acciones, text="Exportar PEDIDO_RECOMENDADO.xlsx",
                                       command=self._exportar, state="disabled")
        self.btn_exportar.pack(side="left", padx=8)
        ttk.Label(acciones, text="Filtrar:").pack(side="right")
        self.var_filtro = tk.StringVar(value="Todos")
        cb = ttk.Combobox(acciones, textvariable=self.var_filtro, values=self.ESTADOS,
                          state="readonly", width=14)
        cb.pack(side="right", padx=(0, 6))
        cb.bind("<<ComboboxSelected>>", lambda _e: self._refrescar())

        # --- tabla de resultados
        cols = ("Código", "Producto", "Stock U", "Stock F", "CPD", "Días stock",
                        "Punto pedido", "A pedir", "Estado")
        marco, self.tabla = crear_tabla(self.cuerpo, cols,
                                        (80, 260, 65, 65, 70, 85, 90, 75, 110))
        marco.pack(fill="both", expand=True)
        for estado, color in COLORES_ESTADO.items():
            self.tabla.tag_configure(estado, background=color)
        # Cargar historial guardado al iniciar la pantalla
        self._actualizar_historial()
    # --- eventos de archivos
    def _actualizar_historial(self):
        info_hist = motor.obtener_info_historial()
        self.var_hist.set(info_hist)
    def _recibir_ventas(self, rutas):
            self.archivos_ventas = rutas
            nuevos = 0
            for ruta in rutas:
                try:
                    # Recibimos los 3 valores que ahora bota el parser de reportes
                    df, f_inicio, f_fin = reportes.leer_ventas(ruta)
                    
                    # Pasamos las fechas al motor SQLite
                    if motor.registrar_ventas(df, Path(ruta).name, f_inicio, f_fin):
                        nuevos += 1
                except Exception as e:
                    messagebox.showerror("Error", str(e))
                    return
            
            self.zona_ventas.mostrar(f"Ventas registradas: {nuevos} archivos nuevos.")
            
            # Actualizar el texto del historial en la interfaz
            info_hist = motor.obtener_info_historial()
            self.var_hist.set(info_hist)
            
            self.estado.set("Ventas guardadas en BD. Falta el stock actual." if not self.archivo_stock else "Todo listo. Pulsa «Calcular».")
        # TODO: importar a historial.db y actualizar self.var_hist

    def _recibir_stock(self, rutas):
        self.archivo_stock = rutas[0]
        self.zona_stock.mostrar(Path(rutas[0]).name)
        self.estado.set("Stock cargado." if not self.archivos_ventas
                        else "Todo cargado. Pulsa «Calcular recomendación».")

    # --- acciones
    def _calcular(self):
        if not self.archivo_stock:
            messagebox.showwarning("Atención", "Falta cargar el archivo de stock actual.")
            return
            
        try:
            df_stock, _ = reportes.leer_stock(self.archivo_stock)
            df_calculado = motor.calcular_recomendacion(
                df_stock, 
                self.var_lead.get(), 
                self.var_seg.get(), 
                self.var_cob.get()
            )
            
            # Formatear para el Treeview (Código, Producto, Stock, CPD, Días, PP, Pedir, Estado)
            self.filas = df_calculado[[
                            'codigo', 'producto', 'cant', 'frac', 'CPD', 
                            'dias_stock', 'punto_pedido', 'a_pedir', 'estado'
                        ]].values.tolist()
            self._refrescar()
            
            self.btn_exportar.config(state="normal")
            self.df_exportar = df_calculado # Guardamos para exportar
            self.estado.set("Cálculo completado con datos reales.")
        except Exception as e:
            messagebox.showerror("Error de Cálculo", str(e))

    def _refrescar(self):
            self.tabla.delete(*self.tabla.get_children())
            filtro = self.var_filtro.get()
            for f in self.filas:
                # f[8] es la columna 'Estado' en nuestra tupla de datos
                estado_fila = f[8] if len(f) > 8 else "OK"
                if filtro != "Todos" and estado_fila != filtro:
                    continue
                
                # Formatear valores (si es None o 999, mostrar '-')
                valores = []
                for v in f:
                    if v is None:
                        valores.append("-")
                    elif isinstance(v, float):
                        valores.append(f"{v:.1f}" if v != 999.0 else "-")
                    else:
                        valores.append(v)
                        
                self.tabla.insert("", "end", values=valores, tags=(estado_fila,))
    def _exportar(self):
        ruta = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="PEDIDO_RECOMENDADO.xlsx", filetypes=[("Excel", "*.xlsx")])
        if ruta:
            self.df_exportar.to_excel(ruta, index=False)
            messagebox.showinfo("VitalStock", f"Pedido exportado en:\n{ruta}")

# ------------------------------------------------------------ formato inventario
class PantallaInventario(Pantalla):
    def __init__(self, app):
        super().__init__(app, "Formato de inventario")
        self.archivo_stock = None

        self.zona = ZonaArchivos(
            self.cuerpo, "Stock actual",
            "Arrastra aquí el reporte de stock\n(o haz clic para elegirlo)",
            self._recibir_stock)
        self.zona.pack(fill="x")

        opciones = ttk.LabelFrame(self.cuerpo, text=" Opciones de la hoja ")
        opciones.pack(fill="x", pady=12)

        ttk.Label(opciones, text="Local:").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.var_local = tk.StringVar(value="Local principal")
        ttk.Entry(opciones, textvariable=self.var_local, width=24).grid(row=0, column=1, padx=4)

        ttk.Label(opciones, text="Ordenar por:").grid(row=0, column=2, padx=(18, 8), sticky="w")
        self.var_orden = tk.StringVar(value="Laboratorio")
        ttk.Combobox(opciones, textvariable=self.var_orden, state="readonly", width=14,
                     values=["Laboratorio", "Producto", "Código"]).grid(row=0, column=3)

        self.var_solo_stock = tk.BooleanVar(value=False)
        ttk.Checkbutton(opciones, text="Solo productos con stock > 0",
                        variable=self.var_solo_stock).grid(row=0, column=4, padx=18)

        ttk.Label(opciones, text="Formato fijo: A4 horizontal · Arial 11 · filas alternadas",
                  foreground=C_GRIS).grid(row=1, column=0, columnspan=5, padx=8, pady=(0, 6), sticky="w")

        acciones = tk.Frame(self.cuerpo, bg=C_FONDO)
        acciones.pack(fill="x", pady=(0, 6))
        ttk.Button(acciones, text="Vista previa", style="Accion.TButton",
                   command=self._vista_previa).pack(side="left")
        self.btn_excel = ttk.Button(acciones, text="Generar Excel", state="disabled",
                                    command=lambda: self._generar("xlsx"))
        self.btn_excel.pack(side="left", padx=8)
        self.btn_pdf = ttk.Button(acciones, text="Generar PDF", state="disabled",
                                  command=lambda: self._generar("pdf"))
        self.btn_pdf.pack(side="left")

        cols = ("N°", "Código", "Producto", "Laboratorio", "Sist. U", "Sist. F", 
                        "Anaq. U", "Anaq. F", "Almac. U", "Almac. F", "Dif. U", "Dif. F")
        
        # Ajusta los anchos para que quepan en la pantalla
        anchos = (40, 70, 240, 100, 50, 50, 50, 50, 55, 55, 45, 45)
        marco, self.tabla = crear_tabla(self.cuerpo, cols, anchos)
        marco.pack(fill="both", expand=True)
        self.tabla.tag_configure("par", background="#eef3f1")

    def _recibir_stock(self, rutas):
        self.archivo_stock = rutas[0]
        self.zona.mostrar(Path(rutas[0]).name)
        self.estado.set("Stock cargado. Pulsa «Vista previa».")

    def _vista_previa(self):
        if not self.archivo_stock:
            messagebox.showwarning("Atención", "Carga el archivo de stock actual primero.")
            return
            
        try:
            # Asumiendo que importaste reportes.py al inicio
            df_stock, _ = reportes.leer_stock(self.archivo_stock)
            
            if self.var_solo_stock.get():
                df_stock = df_stock[(df_stock['cant'] > 0) | (df_stock['frac'] > 0)]
                
            col_orden = "tipo" if self.var_orden.get() == "Laboratorio" else "producto"
            if self.var_orden.get() == "Código": col_orden = "codigo"
            df_stock = df_stock.sort_values(by=col_orden)

            self.tabla.delete(*self.tabla.get_children())
            
            for i, row in enumerate(df_stock.itertuples(), 1):
                # row.cant es Unidad, row.frac es Fracción
                valores = (i, row.codigo, row.producto, row.tipo, row.cant, row.frac, "", "", "", "", "", "")
                self.tabla.insert("", "end", values=valores, tags=("par",) if i % 2 else ())

            self.btn_excel.config(state="normal")
            self.df_actual = df_stock # Lo guardamos para pasarlo al Excel luego
            self.estado.set(f"Vista previa generada con {len(df_stock)} productos.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _generar(self, formato):
        if formato != "xlsx":
            messagebox.showinfo("Aviso", "El módulo actual solo exporta directamente a Excel (listo para imprimir en PDF desde ahí).")
            return
            
        ruta = filedialog.asksaveasfilename(
            defaultextension=".xlsx", 
            initialfile="INVENTARIO_FISICO.xlsx", 
            filetypes=[("Excel", "*.xlsx")]
        )
        
        if ruta:
            try:
                # Aquí llamas a la función que creamos en el paso 1
                # Asumiendo que la guardaste en motor_inventario.py
                import motor_inventario 
                motor_inventario.generar_excel_inventario(self.df_actual, ruta, self.var_orden.get())
                self.estado.set(f"Inventario guardado en {ruta}")
                messagebox.showinfo("Éxito", "Excel generado correctamente. Está listo para imprimir en A4.")
            except Exception as e:
                messagebox.showerror("Error al generar Excel", str(e))


# ---------------------------------------------------------------- aplicación
class App(BaseTk):
    def __init__(self):
        super().__init__()
        self.title("VitalStock")
        self.configure(bg=C_FONDO)
        self._centrar(1020, 700)
        self.minsize(900, 600)
        self._estilos()

        self.contenedor = tk.Frame(self, bg=C_FONDO)
        self.contenedor.pack(fill="both", expand=True)
        self.contenedor.rowconfigure(0, weight=1)
        self.contenedor.columnconfigure(0, weight=1)

        self.pantallas = {
            "menu": PantallaMenu(self),
            "pedido": PantallaPedido(self),
            "inventario": PantallaInventario(self),
        }
        for p in self.pantallas.values():
            p.grid(row=0, column=0, sticky="nsew")
        self.mostrar("menu")

        self.iniciar_yape_en_segundo_plano()

    def mostrar(self, nombre):
        self.pantallas[nombre].tkraise()

    def iniciar_yape_en_segundo_plano(self):
        """Yape no tiene pantalla en el menú: corre aquí, en un hilo aparte."""
        # TODO: arrancar el servidor local que recibe las notificaciones del celular
        #       (threading.Thread(daemon=True)) y abrir la alerta en una ventana
        #       propia cuando llegue un pago.
        pass

    def _centrar(self, ancho, alto):
        x = (self.winfo_screenwidth() - ancho) // 2
        y = (self.winfo_screenheight() - alto) // 3
        self.geometry(f"{ancho}x{alto}+{x}+{max(y, 0)}")

    def _estilos(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", font=F_BASE)
        s.configure("TLabelframe", background=C_FONDO)
        s.configure("TLabelframe.Label", background=C_FONDO, foreground=C_PRIMARIO,
                    font=F_NEGRITA)
        s.configure("TLabel", background=C_FONDO, foreground=C_TEXTO)
        s.configure("TCheckbutton", background=C_FONDO)
        s.configure("Treeview", rowheight=26, font=F_BASE)
        s.configure("Treeview.Heading", font=F_NEGRITA)
        s.configure("Menu.TButton", font=("Segoe UI", 13, "bold"), background=C_PRIMARIO,
                    foreground="white", borderwidth=0)
        s.map("Menu.TButton", background=[("active", C_PRIMARIO_OSC)])
        s.configure("Accion.TButton", font=F_NEGRITA, background=C_PRIMARIO,
                    foreground="white", padding=(14, 6), borderwidth=0)
        s.map("Accion.TButton", background=[("active", C_PRIMARIO_OSC)])
        s.configure("Barra.TButton", background="white", foreground=C_PRIMARIO,
                    font=F_NEGRITA, borderwidth=0)


if __name__ == "__main__":
    App().mainloop()