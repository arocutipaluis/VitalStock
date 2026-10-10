"""
services/inventario_service.py - Gestión de secciones físicas y exportación de formatos Excel de inventario y Yape.

Permite:
  1. Asignar y clasificar productos en las 4 secciones físicas de la botica (`Sección Vitrina`,
     `Sección Caja`, `Sección Anaquel`, `Sección Almacén`).
  2. Generar formatos de conteo físico estructurados por tablas de laboratorio (estilo Irene),
     con casilleros de conteo y columna `SISTEMA (UNID / FRAC)` en blanco antes de `TOTAL`.
  3. Exportar libros Excel multi-hoja (todas las secciones en pestañas separadas o sección individual).
  4. Exportar reportes estructurados de transacciones de pagos Yape con la fecha/hora real del pago.

Comunicación con otros archivos del proyecto:
  - Importa `config.py` (nombres de secciones, normalizadores y constantes).
  - Importa `database.py` (`inicializar_db` y `obtener_conexion`) para leer/guardar `ubicacion_productos`.
  - Es consumido por `ui/views/inventario_view.py`, `ui/dialogs/yape_history_dialog.py`
    y reexportado en `motor_inventario.py`.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.page import PageMargins

import config
import database

# --------------------------------------------------------------------------- #
# Configuración visual para Inventario
# --------------------------------------------------------------------------- #
COLOR_PRIMARIO = "1F6F5C"
COLOR_ALTERNO = "F4F6F5"
COLOR_SUBENCABEZADO = "DCEBE6"

ORDENES = {
    "laboratorio": ["tipo", "producto"],
    "producto": ["producto"],
    "codigo": ["codigo"],
}

# Anchos de columna para formato de inventario A4 horizontal (12 columnas: A a L)
ANCHOS_COLUMNA_INVENTARIO = {
    "A": 11,   # Código
    "B": 42,   # Producto
    "C": 17,   # Laboratorio
    "D": 11,   # F. Vencimiento
    "E": 7.5,  # Anaquel Unid
    "F": 7.5,  # Anaquel Frac
    "G": 7.5,  # Almacén Unid
    "H": 7.5,  # Almacén Frac
    "I": 7.5,  # Sistema Unid
    "J": 7.5,  # Sistema Frac
    "K": 10,   # Total
    "L": 18,   # Observaciones
}

TOTAL_COLUMNAS_INVENTARIO = 12


# --------------------------------------------------------------------------- #
# Heurística de Clasificación por Secciones de Botica
# --------------------------------------------------------------------------- #
def clasificar_heuristicamente(producto: str, laboratorio: str, codigo: str) -> str:
    """Determina la sección física sugerida para un producto nuevo según su descripción y laboratorio.

    Reglas de negocio:
      - `Sección Vitrina`: Dermocosmética, cuidado facial, protectores solares, perfumería y belleza.
      - `Sección Almacén`: Pañales, paños húmedos, algodones en volumen, sueros grandes y bultos.
      - `Sección Anaquel`: OTC, gasas, apósitos, alcohol, botiquín e higiene bucal.
      - `Sección Caja`: Medicamentos éticos, comprimidos, inyectables y fármacos de laboratorio.

    Comunicación entre módulos:
      - Utiliza las constantes de sección de `config.py`.
      - Invocada internamente por `clasificar_stock_con_anaqueles()` y `preparar_inventario()`.
    """
    cod = str(codigo).strip()
    prod_up = unicodedata.normalize("NFKD", str(producto)).encode("ascii", "ignore").decode("ascii").upper()
    lab_up = unicodedata.normalize("NFKD", str(laboratorio)).encode("ascii", "ignore").decode("ascii").upper()

    # Vitrinas: Dermo, cuidado facial, fotoprotectores, belleza, perfumes
    palabras_vitrina = [
        "CERAVE", "LA ROCHE", "ISDIN", "EUCERIN", "VICHY", "AVENE", "BIODERMA",
        "CETAPHIL", "DERMO", "BLOQUEADOR", "FOTOPROTECTOR", "SOLAR", "SERUM",
        "FACIAL", "ANTIARRUGAS", "HIALURONICO", "MICELAR", "LABIAL", "COLONIA",
        "PERFUME", "DESODORANTE", "TINTURA", "CREMA FACIAL", "BEAUTY", "LOREAL",
        "NEUTROGENA", "NIVEA", "BABARIA", "DOVE", "EXFOLIANTE", "MASCARILLA",
        "MAQUILLAJE", "TALCO", "SHAMPOO ANTICASPA"
    ]
    if any(k in prod_up for k in palabras_vitrina) or any(k in lab_up for k in ["LOREAL", "EUCERIN", "BEIERSDORF"]):
        return config.SECCION_VITRINA

    # Almacén: Pañales, paños, bultos grandes
    palabras_almacen = [
        "PANAL", "BABYSEC", "HUGGIES", "PAMPERS", "PLENITUD", "PANITO",
        "TOALLITAS HUMEDAS", "ALGODON 500", "ALGODON 1000", "ALGODON 250",
        "SUERO 1000", "PAPEL HIGIENICO", "CAJA X 100", "PAQUETE X"
    ]
    if any(k in prod_up for k in palabras_almacen) or "PAMPERS" in lab_up or "HUGGIES" in lab_up:
        return config.SECCION_ALMACEN

    # Anaquel: Insumos de botiquín, curación, gasas, higiene dental, OTC tópico
    palabras_anaquel = [
        "GASA", "ALCOHOL", "APOSITO", "ESPARADRAPO", "MICROPORE", "VENDA",
        "JERINGA", "AGUJA", "PASTA DENTAL", "DENTIFRICO", "CEPILLO DENTAL",
        "COLGATE", "ORAL-B", "KOLYNOS", "SENSODYNE", "ENJUAGUE BUCAL",
        "LISTERINE", "CARAMELO", "PROPOLEO", "MENTOL", "AGUA OXIGENADA",
        "CURITA", "BANDITA", "PRESERVATIVO", "CONDON", "DUREX", "PRUDENCE",
        "POMADA", "GEL", "UNGUENTO", "SHAMPOO", "JABON"
    ]
    if any(k in prod_up for k in palabras_anaquel) or "COLGATE" in lab_up:
        return config.SECCION_ANAQUEL

    # Resto de medicamentos éticos / fármacos de laboratorio van a Sección Caja
    return config.SECCION_CAJA


# --------------------------------------------------------------------------- #
# Gestión de Catálogo y Asignación de Secciones
# --------------------------------------------------------------------------- #
def normalizar_orden(orden: str) -> str:
    """Valida y normaliza el criterio de ordenamiento ('laboratorio', 'producto' o 'codigo').

    Comunicación entre módulos:
      - Invocada por `preparar_inventario()` y desde `ui/views/inventario_view.py`.
    """
    s = unicodedata.normalize("NFKD", str(orden)).encode("ascii", "ignore").decode("ascii").strip().lower()
    if s not in ORDENES:
        raise ValueError(f"Orden no válido: '{orden}'. Use Laboratorio, Producto o Código.")
    return s


def obtener_mapeo_ubicaciones() -> dict[str, str]:
    """Retorna un diccionario `{codigo: seccion}` consultando la tabla `ubicacion_productos`.

    Comunicación entre módulos:
      - Se comunica con `database.py` (`obtener_conexion`) y `config.py` (`normalizar_anaquel`).
      - Invocada por `clasificar_stock_con_anaqueles()` y `preparar_inventario()`.
    """
    database.inicializar_db()
    with database.obtener_conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT codigo, anaquel FROM ubicacion_productos")
        return {str(row[0]).strip(): config.normalizar_anaquel(row[1]) for row in cur.fetchall()}


def obtener_catalogo_ubicaciones(busqueda: str = "", anaquel_filtro: str = "") -> list[dict]:
    """Consulta el catálogo completo de ubicaciones de productos aplicando filtros de sección y búsqueda.

    Comunicación entre módulos:
      - Consulta SQLite a través de `database.obtener_conexion()`.
      - Es invocada por `ui/views/inventario_view.py` en el diálogo de gestión de secciones.
    """
    database.inicializar_db()
    with database.obtener_conexion() as conn:
        conn.row_factory = database.sqlite3.Row
        cur = conn.cursor()
        query = "SELECT codigo, producto, laboratorio, anaquel, fecha_mod FROM ubicacion_productos WHERE 1=1"
        params: list[str] = []

        if anaquel_filtro and not config.es_filtro_todos(anaquel_filtro):
            filtro_canonico = config.normalizar_anaquel(anaquel_filtro)
            query += " AND anaquel = ?"
            params.append(filtro_canonico)

        if busqueda:
            termino = f"%{busqueda.strip()}%"
            query += " AND (codigo LIKE ? OR producto LIKE ? OR laboratorio LIKE ?)"
            params.extend([termino, termino, termino])

        query += " ORDER BY anaquel, laboratorio, producto"
        cur.execute(query, params)
        resultados = []
        for r in cur.fetchall():
            d = dict(r)
            d["anaquel"] = config.normalizar_anaquel(d.get("anaquel", ""))
            resultados.append(d)
        return resultados


def asignar_anaquel(codigo: str, anaquel: str, producto: str = "", laboratorio: str = "") -> None:
    """Asigna o actualiza la sección física de un producto individual en SQLite.

    Comunicación entre módulos:
      - Escribe en `ubicacion_productos` mediante `database.obtener_conexion()`.
      - Es invocada desde `ui/views/inventario_view.py` cuando el usuario reasigna un producto.
    """
    codigo = str(codigo).strip()
    if not codigo:
        return
    anaquel_canonico = config.normalizar_anaquel(anaquel)

    database.inicializar_db()
    with database.obtener_conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ubicacion_productos (codigo, producto, laboratorio, anaquel, fecha_mod)
            VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(codigo) DO UPDATE SET
                anaquel = excluded.anaquel,
                producto = CASE WHEN excluded.producto != '' THEN excluded.producto ELSE ubicacion_productos.producto END,
                laboratorio = CASE WHEN excluded.laboratorio != '' THEN excluded.laboratorio ELSE ubicacion_productos.laboratorio END,
                fecha_mod = datetime('now', 'localtime')
            """,
            (codigo, producto.strip(), laboratorio.strip(), anaquel_canonico),
        )


def asignar_lote_anaquel(items: list[tuple[str, str, str, str]]) -> int:
    """Guarda en bloque una lista de tuplas `(codigo, producto, laboratorio, seccion)` en SQLite.

    Comunicación entre módulos:
      - Escribe transaccionalmente usando `database.obtener_conexion()`.
      - Es invocada por `ui/views/inventario_view.py` al clasificar productos nuevos en lote.
    """
    if not items:
        return 0
    database.inicializar_db()
    actualizados = 0
    with database.obtener_conexion() as conn:
        cur = conn.cursor()
        for item in items:
            cod, prod, lab, anaq = item
            cod = str(cod).strip()
            if not cod:
                continue
            anaq_canonico = config.normalizar_anaquel(anaq)
            cur.execute(
                """
                INSERT INTO ubicacion_productos (codigo, producto, laboratorio, anaquel, fecha_mod)
                VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
                ON CONFLICT(codigo) DO UPDATE SET
                    anaquel = excluded.anaquel,
                    producto = CASE WHEN excluded.producto != '' THEN excluded.producto ELSE ubicacion_productos.producto END,
                    laboratorio = CASE WHEN excluded.laboratorio != '' THEN excluded.laboratorio ELSE ubicacion_productos.laboratorio END,
                    fecha_mod = datetime('now', 'localtime')
                """,
                (cod, str(prod).strip(), str(lab).strip(), anaq_canonico),
            )
            actualizados += 1
    return actualizados


def clasificar_stock_con_anaqueles(df_stock: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cruza el DataFrame de stock cargado contra las ubicaciones registradas en la base de datos.

    Retorna:
      - `df_clasificado`: Productos que ya cuentan con sección asignada en SQLite.
      - `df_nuevos`: Productos sin sección asignada (incluye columna `anaquel_sugerido`).

    Comunicación entre módulos:
      - Consume `obtener_mapeo_ubicaciones()` y `clasificar_heuristicamente()`.
      - Es invocada por `ui/views/inventario_view.py` tras leer un reporte de stock con `services/reportes_service.py`.
    """
    if df_stock is None or df_stock.empty:
        vacio = pd.DataFrame(columns=["codigo", "producto", "tipo", "anaquel"])
        return vacio, vacio

    df = df_stock.copy()
    df["codigo"] = df["codigo"].fillna("").astype(str).str.strip()
    df["producto"] = df["producto"].fillna("").astype(str).str.strip()
    if "tipo" not in df.columns:
        df["tipo"] = ""
    df["tipo"] = df["tipo"].fillna("").astype(str).str.strip()

    mapeo = obtener_mapeo_ubicaciones()
    df["anaquel"] = df["codigo"].map(mapeo).fillna("")

    # Separar clasificados vs nuevos sin asignar
    df_clasificado = df[df["anaquel"] != ""].copy()
    df_nuevos = df[df["anaquel"] == ""].copy()

    # Si hay nuevos, sugerir su sección mediante la heurística
    if not df_nuevos.empty:
        df_nuevos["anaquel_sugerido"] = [
            clasificar_heuristicamente(r.producto, r.tipo, r.codigo)
            for r in df_nuevos.itertuples(index=False)
        ]

    return df_clasificado.reset_index(drop=True), df_nuevos.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Preparación de datos para la vista y exportación
# --------------------------------------------------------------------------- #
def preparar_inventario(
    df_stock: pd.DataFrame,
    orden: str = "laboratorio",
    solo_con_stock: bool = False,
    filtro_anaquel: str = "Todos",
) -> pd.DataFrame:
    """Filtra por stock/sección, asigna ubicaciones y ordena el DataFrame para vista previa o Excel.

    Comunicación entre módulos:
      - Utiliza `config.es_filtro_todos()` y `config.normalizar_anaquel()`.
      - Es invocada por `generar_excel_inventario()` y por `ui/views/inventario_view.py`.
    """
    if df_stock is None or df_stock.empty:
        raise ValueError("No hay datos de stock para generar el inventario.")

    df = df_stock.copy()
    for col, defecto in (("producto", ""), ("tipo", ""), ("cant", 0), ("frac", 0)):
        if col not in df.columns:
            df[col] = defecto
    df["cant"] = pd.to_numeric(df["cant"], errors="coerce").fillna(0)
    df["frac"] = pd.to_numeric(df["frac"], errors="coerce").fillna(0)
    df[["codigo", "producto", "tipo"]] = df[["codigo", "producto", "tipo"]].fillna("").astype(str)
    df["codigo"] = df["codigo"].str.strip()

    if solo_con_stock:
        df = df[(df["cant"] > 0) | (df["frac"] > 0)]

    # Cruzar con secciones
    mapeo = obtener_mapeo_ubicaciones()

    def obtener_seccion_fila(row):
        cod = row.codigo
        if cod in mapeo:
            return mapeo[cod]
        return clasificar_heuristicamente(row.producto, row.tipo, cod)

    df["anaquel"] = [obtener_seccion_fila(r) for r in df.itertuples(index=False)]

    if filtro_anaquel and not config.es_filtro_todos(filtro_anaquel):
        filtro_canonico = config.normalizar_anaquel(filtro_anaquel)
        df = df[df["anaquel"] == filtro_canonico]

    columnas_orden = ORDENES[normalizar_orden(orden)]
    df = df.sort_values(columnas_orden, key=lambda s: s.str.upper().str.strip(), kind="mergesort")
    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Generación del Excel de Inventario Dividido por Tablas de Laboratorio
# --------------------------------------------------------------------------- #
def _limpiar_nombre_hoja(nombre: str) -> str:
    """Limpia los nombres de sección para cumplir con la restricción de 31 caracteres de hojas Excel.

    Comunicación entre módulos:
      - Invoca `config.normalizar_anaquel()` de `config.py` y es usada por `generar_excel_inventario()`.
    """
    nombre_canonico = config.normalizar_anaquel(nombre)
    limpio = nombre_canonico
    for c in [":", "\\", "/", "?", "*", "[", "]"]:
        limpio = limpio.replace(c, "")
    return limpio[:31]


def generar_excel_inventario(
    df_stock: pd.DataFrame,
    ruta_salida: str | Path,
    orden: str = "laboratorio",
    local: str = "",
    solo_con_stock: bool = False,
    anaquel_seleccionado: str = "Todas las Secciones",
) -> Path:
    """Genera el formato físico de inventario en Excel (A4 horizontal).

    - Divide cada sección en tablas independientes por laboratorio (estilo Irene).
    - Incluye CÓDIGO, PRODUCTO, LABORATORIO, F. VENC., ANAQUEL (U/F), ALMACÉN (U/F), SISTEMA (U/F), TOTAL y OBSERVACIONES.
    - Deja las columnas de conteo y SISTEMA en blanco para garantizar un inventario físico puro.
    - Si se exporta 'Todas las Secciones', genera un único libro de Excel con 4 hojas separadas por sección.

    Comunicación entre módulos:
      - Utiliza `config.es_filtro_todos()`, `config.normalizar_anaquel()` y `config.ANAQUELES` de `config.py`.
      - Es invocada desde `ui/views/inventario_view.py` (`PantallaInventario._exportar`).
    """
    ruta_salida = Path(ruta_salida)
    df_preparado = preparar_inventario(df_stock, orden, solo_con_stock, filtro_anaquel="Todas las Secciones")

    wb = Workbook()
    hoja_inicial = wb.active

    if anaquel_seleccionado and not config.es_filtro_todos(anaquel_seleccionado):
        anaqueles_a_procesar = [config.normalizar_anaquel(anaquel_seleccionado)]
    else:
        anaqueles_a_procesar = list(config.ANAQUELES)

    for idx, anaq in enumerate(anaqueles_a_procesar):
        df_sub = df_preparado[df_preparado["anaquel"] == anaq].copy()
        titulo_hoja = _limpiar_nombre_hoja(anaq)
        if idx == 0:
            ws = hoja_inicial
            ws.title = titulo_hoja
        else:
            ws = wb.create_sheet(title=titulo_hoja)

        _llenar_hoja_conteo_laboratorios(ws, df_sub, anaq, local, orden)

    try:
        wb.save(ruta_salida)
    except PermissionError as exc:
        raise PermissionError(
            f"No se pudo guardar '{ruta_salida.name}'.\n"
            "Cierre el archivo si está abierto en Excel e intente de nuevo."
        ) from exc

    return ruta_salida


def _llenar_hoja_conteo_laboratorios(
    ws,
    df_sub: pd.DataFrame,
    nombre_seccion: str,
    local: str,
    orden: str = "laboratorio",
) -> None:
    """Llena y da formato a una hoja de Excel dividida en múltiples sub-tablas por laboratorio.

    Comunicación entre módulos:
      - Función auxiliar interna invocada por `generar_excel_inventario()`.
    """
    lado = Side(style="thin", color="8A9A95")
    borde = Border(left=lado, right=lado, top=lado, bottom=lado)
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)
    izquierda = Alignment(horizontal="left", vertical="center")

    relleno_encabezado = PatternFill("solid", fgColor=COLOR_PRIMARIO)
    relleno_sub = PatternFill("solid", fgColor=COLOR_SUBENCABEZADO)
    relleno_alterno = PatternFill("solid", fgColor=COLOR_ALTERNO)

    fuente_encabezado = Font(name="Calibri", size=9, bold=True, color="FFFFFF")
    fuente_sub = Font(name="Calibri", size=8, bold=True, color=COLOR_PRIMARIO)
    fuente_datos = Font(name="Calibri", size=9)
    fuente_codigo = Font(name="Calibri", size=9, bold=True)

    # 1) Título superior de la sección
    local_txt = f" - {local.strip()}" if local.strip() else ""
    ws.cell(row=1, column=1, value=f"INVENTARIO · {nombre_seccion.upper()}{local_txt.upper()}")
    ws.cell(row=1, column=1).font = Font(name="Calibri", size=11, bold=True, color=COLOR_PRIMARIO)
    ws.row_dimensions[1].height = 20

    fila_cursor = 3

    # Agrupar por Laboratorio
    if df_sub.empty:
        ws.cell(row=fila_cursor, column=1, value="No hay productos registrados en esta sección.")
        fila_cursor += 1
    else:
        labs_unicos = sorted(
            df_sub["tipo"].fillna("").astype(str).str.strip().unique(),
            key=lambda x: (x == "", x.upper()),
        )

        for lab_nombre in labs_unicos:
            df_lab = df_sub[df_sub["tipo"].fillna("").astype(str).str.strip() == lab_nombre].copy()
            if df_lab.empty:
                continue

            if orden == "codigo":
                df_lab = df_lab.sort_values("codigo", key=lambda s: s.str.strip())
            else:
                df_lab = df_lab.sort_values("producto", key=lambda s: s.str.upper().str.strip())

            # Encabezado Nivel 1 (Fila r1) y Nivel 2 (Fila r2)
            r1 = fila_cursor
            r2 = fila_cursor + 1

            ws.cell(row=r1, column=1, value="CÓDIGO")
            ws.cell(row=r1, column=2, value="PRODUCTO")
            ws.cell(row=r1, column=3, value="LABORATORIO")
            ws.cell(row=r1, column=4, value="F. VENC.")
            ws.cell(row=r1, column=5, value="ANAQUEL")
            ws.cell(row=r1, column=7, value="ALMACÉN")
            ws.cell(row=r1, column=9, value="SISTEMA")
            ws.cell(row=r1, column=11, value="TOTAL")
            ws.cell(row=r1, column=12, value="OBSERVACIONES")

            ws.cell(row=r2, column=5, value="UNID")
            ws.cell(row=r2, column=6, value="FRAC")
            ws.cell(row=r2, column=7, value="UNID")
            ws.cell(row=r2, column=8, value="FRAC")
            ws.cell(row=r2, column=9, value="UNID")
            ws.cell(row=r2, column=10, value="FRAC")

            # Combinar celdas verticales y horizontales
            for col in (1, 2, 3, 4, 11, 12):
                ws.merge_cells(start_row=r1, start_column=col, end_row=r2, end_column=col)
            ws.merge_cells(start_row=r1, start_column=5, end_row=r1, end_column=6)   # ANAQUEL
            ws.merge_cells(start_row=r1, start_column=7, end_row=r1, end_column=8)   # ALMACÉN
            ws.merge_cells(start_row=r1, start_column=9, end_row=r1, end_column=10)  # SISTEMA

            # Aplicar estilos a encabezados
            for fila_h in (r1, r2):
                for col_h in range(1, TOTAL_COLUMNAS_INVENTARIO + 1):
                    celda = ws.cell(row=fila_h, column=col_h)
                    celda.border = borde
                    es_sub = fila_h == r2 and col_h in (5, 6, 7, 8, 9, 10)
                    celda.fill = relleno_sub if es_sub else relleno_encabezado
                    celda.font = fuente_sub if es_sub else fuente_encabezado
                    celda.alignment = centro

            ws.row_dimensions[r1].height = 19
            ws.row_dimensions[r2].height = 15

            # Filas de datos del laboratorio
            fila_cursor = r2 + 1
            for idx_p, row_p in enumerate(df_lab.itertuples(index=False)):
                fila_actual = fila_cursor + idx_p
                ws.cell(row=fila_actual, column=1, value=str(row_p.codigo)).font = fuente_codigo
                ws.cell(row=fila_actual, column=1).alignment = centro

                ws.cell(row=fila_actual, column=2, value=str(row_p.producto)).font = fuente_datos
                ws.cell(row=fila_actual, column=2).alignment = izquierda

                ws.cell(row=fila_actual, column=3, value=str(row_p.tipo)).font = fuente_datos
                ws.cell(row=fila_actual, column=3).alignment = izquierda

                # Columnas 4 (F.Venc), 5-6 (Anaquel U/F), 7-8 (Almacén U/F), 9-10 (Sistema U/F en blanco), 11 (Total), 12 (Obs)
                alterna = idx_p % 2 == 1
                for c in range(1, TOTAL_COLUMNAS_INVENTARIO + 1):
                    celda_d = ws.cell(row=fila_actual, column=c)
                    celda_d.border = borde
                    if alterna:
                        celda_d.fill = relleno_alterno
                    if c in (4, 5, 6, 7, 8, 9, 10, 11):
                        celda_d.alignment = centro
                    elif c == 12:
                        celda_d.alignment = izquierda

                ws.row_dimensions[fila_actual].height = 18

            fila_cursor += len(df_lab)
            # 2 filas en blanco entre tablas de laboratorios (tal como Irene)
            fila_cursor += 2

    # Ajustar anchos de columnas
    for letra, ancho in ANCHOS_COLUMNA_INVENTARIO.items():
        ws.column_dimensions[letra].width = ancho

    # Configuración de impresión A4 Horizontal
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_options.horizontalCentered = True
    ws.print_options.gridLines = True
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.6, bottom=0.6, header=0.3, footer=0.3)

    local_limpio = (local or "").strip().replace("&", "&&")
    titulo_impresion = f"INVENTARIO · {nombre_seccion.upper()}" + (f" ({local_limpio})" if local_limpio else "")
    ws.oddHeader.left.text = "VitalStock · Botica"
    ws.oddHeader.center.text = titulo_impresion
    ws.oddHeader.center.size = 10
    ws.oddHeader.center.font = "Calibri,Bold"
    ws.oddHeader.right.text = f"Fecha: {datetime.now():%d/%m/%Y} | {len(df_sub)} ítems"
    ws.oddFooter.left.text = "Contado por: ____________________"
    ws.oddFooter.center.text = "Página &P de &N"
    ws.oddFooter.right.text = "Firma Encargado: ____________________"


# --------------------------------------------------------------------------- #
# Exportación de Pagos Yape a Excel Estructurado
# --------------------------------------------------------------------------- #
def generar_excel_pagos_yape(
    pagos: list[dict],
    ruta_salida: str | Path,
    titulo_periodo: str = "",
    nombre_botica: str = "VitalStock",
) -> Path:
    """Genera un archivo Excel estructurado y profesional con el historial de pagos Yape.

    Exporta la fecha y hora exacta en que se efectuó el Yape (`fecha_hora`) enviada por VitalNotifier.

    Comunicación entre módulos:
      - Invocada por `ui/dialogs/yape_history_dialog.py` (`VentanaHistorialYape._exportar_excel`)
        y reexportada en `motor_inventario.py`.
    """
    ruta_salida = Path(ruta_salida)
    wb = Workbook()
    ws = wb.active
    ws.title = "Pagos Yape"

    total_monto = sum(float(p.get("monto", 0.0)) for p in pagos)
    periodo_txt = titulo_periodo.strip() or "Historial de Pagos Yape"
    ahora_txt = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    ws["A1"] = f"{nombre_botica.upper()}  ·  REPORTE DE PAGOS YAPE"
    ws["A2"] = f"Período: {periodo_txt}"
    ws["E2"] = f"Emisión: {ahora_txt}"

    ws["A3"] = f"Total Transacciones: {len(pagos)} pago(s)"
    ws["D3"] = f"Total Recaudado: S/ {total_monto:,.2f}"

    encabezados_tabla = [
        ("A5", "#"),
        ("B5", "FECHA / HORA DEL YAPE"),
        ("C5", "CLIENTE / REMITENTE"),
        ("D5", "MONTO (S/)"),
        ("E5", "CÓD. SEGURIDAD"),
        ("F5", "DETALLE / NOTIFICACIÓN"),
    ]
    for celda, txt in encabezados_tabla:
        ws[celda] = txt

    fila_inicio_datos = 6
    ultima_fila_datos = fila_inicio_datos - 1

    for i, p in enumerate(pagos, start=1):
        fila_actual = fila_inicio_datos + i - 1
        ws.cell(row=fila_actual, column=1, value=i)
        ws.cell(row=fila_actual, column=2, value=str(p.get("fecha_hora") or p.get("fecha_registro") or ""))
        ws.cell(row=fila_actual, column=3, value=str(p.get("remitente", "")).strip())
        ws.cell(row=fila_actual, column=4, value=float(p.get("monto", 0.0)))
        ws.cell(row=fila_actual, column=5, value=str(p.get("codigo_seg", "") or "-").strip())
        ws.cell(row=fila_actual, column=6, value=str(p.get("mensaje_raw", "") or "").strip())
        ultima_fila_datos = fila_actual

    # Estilos
    lado = Side(style="thin", color="8A9A95")
    borde = Border(left=lado, right=lado, top=lado, bottom=lado)
    centro = Alignment(horizontal="center", vertical="center")
    izquierda = Alignment(horizontal="left", vertical="center")
    derecha = Alignment(horizontal="right", vertical="center")

    relleno_enc = PatternFill("solid", fgColor=COLOR_PRIMARIO)
    fuente_enc = Font(name="Calibri", size=9, bold=True, color="FFFFFF")
    fuente_titulo = Font(name="Calibri", size=12, bold=True, color=COLOR_PRIMARIO)
    fuente_meta = Font(name="Calibri", size=9, bold=True, color="40504B")
    fuente_datos = Font(name="Calibri", size=9)
    fuente_monto = Font(name="Calibri", size=9, bold=True)
    relleno_alt = PatternFill("solid", fgColor=COLOR_ALTERNO)

    ws["A1"].font = fuente_titulo
    ws["A2"].font = fuente_meta
    ws["E2"].font = fuente_meta
    ws["A3"].font = fuente_meta
    ws["D3"].font = fuente_meta

    for col in range(1, 7):
        c = ws.cell(row=5, column=col)
        c.fill = relleno_enc
        c.font = fuente_enc
        c.alignment = centro
        c.border = borde
    ws.row_dimensions[5].height = 20

    for f in range(fila_inicio_datos, max(ultima_fila_datos + 1, fila_inicio_datos)):
        alt = (f - fila_inicio_datos) % 2 == 1
        for col in range(1, 7):
            c = ws.cell(row=f, column=col)
            c.border = borde
            c.font = fuente_monto if col == 4 else fuente_datos
            if col in (1, 2, 5):
                c.alignment = centro
            elif col == 4:
                c.alignment = derecha
                c.number_format = '"S/" #,##0.00'
            else:
                c.alignment = izquierda
            if alt:
                c.fill = relleno_alt
        ws.row_dimensions[f].height = 19

    anchos = {"A": 6, "B": 20, "C": 28, "D": 14, "E": 14, "F": 45}
    for col_letra, ancho in anchos.items():
        ws.column_dimensions[col_letra].width = ancho

    try:
        wb.save(ruta_salida)
    except PermissionError as exc:
        raise PermissionError(
            f"No se pudo guardar '{ruta_salida.name}'.\n"
            "Cierre el archivo si está abierto en Excel e intente de nuevo."
        ) from exc

    return ruta_salida
