import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

def generar_excel_inventario(df_stock, ruta_salida, orden="Laboratorio"):
    if orden == "Laboratorio":
        df_stock = df_stock.sort_values(by=["tipo", "producto"])
    elif orden == "Código":
        df_stock = df_stock.sort_values(by=["codigo"])
    else:
        df_stock = df_stock.sort_values(by=["producto"])

    wb = Workbook()
    ws = wb.active
    ws.title = "Inventario Físico"

    # Estilos
    borde_fino = Border(
        left=Side(style='thin'), right=Side(style='thin'), 
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    fill_cabecera = PatternFill(start_color="1F6F5C", end_color="1F6F5C", fill_type="solid")
    font_cabecera = Font(name='Arial', size=9, bold=True, color="FFFFFF")
    fill_par = PatternFill(start_color="F4F6F5", end_color="F4F6F5", fill_type="solid")

    # 1. Definir valores de cabecera (9 columnas en total: A hasta I)
    ws['A1'] = "PRODUCTO"
    ws['B1'] = "LABORATORIO"
    ws['C1'] = "ANAQUEL"
    ws['D1'] = "ANAQUEL"
    ws['E1'] = "ALMACÉN"
    ws['F1'] = "ALMACÉN"
    ws['G1'] = "SISTEMA"
    ws['H1'] = "SISTEMA"
    ws['I1'] = "OBS"

    ws['C2'] = "UNID"
    ws['D2'] = "FRAC"
    ws['E2'] = "UNID"
    ws['F2'] = "FRAC"
    ws['G2'] = "UNID"
    ws['H2'] = "FRAC"

    # 2. Combinar celdas de las cabeceras superiores
    ws.merge_cells("A1:A2") # Producto
    ws.merge_cells("B1:B2") # Laboratorio
    ws.merge_cells("C1:D1") # ANAQUEL (UNID, FRAC)
    ws.merge_cells("E1:F1") # ALMACÉN (UNID, FRAC)
    ws.merge_cells("G1:H1") # SISTEMA (UNID, FRAC)
    ws.merge_cells("I1:I2") # OBS

    # 3. Aplicar formato a la cabecera (filas 1 y 2)
    for r in [1, 2]:
        for c in range(1, 10):
            celda = ws.cell(row=r, column=c)
            celda.font = font_cabecera
            celda.fill = fill_cabecera
            celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            celda.border = borde_fino

    # Escribir datos de stock a partir de la fila 3
    for idx, row in enumerate(df_stock.itertuples(), start=3):
        fila_datos = [
            row.producto, 
            row.tipo, 
            "", "",       # Anaquel U, F (vacíos para conteo)
            "", "",       # Almacén U, F (vacíos para conteo)
            row.cant,     # Sistema U
            row.frac,     # Sistema F
            ""            # Obs (vacío)
        ]
        ws.append(fila_datos)
        
        for col in range(1, 10):
            celda = ws.cell(row=idx, column=col)
            celda.font = Font(name='Arial', size=9)
            celda.border = borde_fino
            if col in [3, 4, 5, 6, 7, 8]: 
                celda.alignment = Alignment(horizontal="center", vertical="center")
            else:
                celda.alignment = Alignment(vertical="center")
                
            if idx % 2 == 0:
                celda.fill = fill_par

    # Anchos de columna optimizados para formato A4 horizontal
    anchos = {'A': 40, 'B': 15, 'C': 7, 'D': 7, 'E': 7, 'F': 7, 'G': 7, 'H': 7, 'I': 16}
    for col_letra, ancho in anchos.items():
        ws.column_dimensions[col_letra].width = ancho

    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.print_title_rows = '1:2'

    ws.oddFooter.left.text = "&11 Contado por: _______________________"
    ws.oddFooter.center.text = "&11 Fecha: ___/___/202_"
    ws.oddFooter.right.text = "&11 Página &P de &N"

    wb.save(ruta_salida)