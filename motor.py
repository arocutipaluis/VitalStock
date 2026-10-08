import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

DB_PATH = "historial.db"

def inicializar_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ventas'")
        tabla_existe = cursor.fetchone()
        
        if tabla_existe:
            cursor.execute("PRAGMA table_info(ventas)")
            columnas = [info[1] for info in cursor.fetchall()]
            if 'cant' not in columnas:
                cursor.execute("DROP TABLE ventas")
                cursor.execute("DROP TABLE IF EXISTS importaciones")
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ventas (
                archivo TEXT, 
                codigo TEXT, 
                producto TEXT, 
                cant REAL, 
                frac REAL
            )
        """)
        # Agregamos columnas para guardar el rango de fechas real del Excel
        conn.execute("""
            CREATE TABLE IF NOT EXISTS importaciones (
                archivo TEXT PRIMARY KEY, 
                fecha_inicio TEXT,
                fecha_fin TEXT
            )
        """)

def registrar_ventas(df_ventas, nombre_archivo, f_inicio=None, f_fin=None):
    inicializar_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM importaciones WHERE archivo = ?", (nombre_archivo,))
        if cursor.fetchone():
            return False  
        
        df_ventas['archivo'] = nombre_archivo
        cols_guardar = ['archivo', 'codigo', 'producto', 'cant', 'frac']
        for c in cols_guardar:
            if c not in df_ventas.columns:
                df_ventas[c] = 0.0
                
        df_ventas[cols_guardar].to_sql('ventas', conn, if_exists='append', index=False)
        cursor.execute("INSERT INTO importaciones (archivo, fecha_inicio, fecha_fin) VALUES (?, ?, ?)", 
                       (nombre_archivo, f_inicio, f_fin))
        return True

def obtener_info_historial():
    inicializar_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT archivo), MIN(fecha_inicio), MAX(fecha_fin) FROM importaciones")
        res = cursor.fetchone()
        archivos_count = res[0] if res else 0
        f_min = res[1] if res else None
        f_max = res[2] if res else None
        
        if archivos_count == 0 or not f_min or not f_max:
            return "Aún no hay meses cargados."
            
        return f"Archivos cargados: {archivos_count} | Rango: {f_min} al {f_max} | Último registro: {f_max}"

def calcular_recomendacion(df_stock, lead_time, dias_seg, dias_cob):
    inicializar_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(fecha_inicio), MAX(fecha_fin) FROM importaciones")
        r = cursor.fetchone()
        
        dias_periodo = 180.0
        if r and r[0] and r[1]:
            try:
                dt1 = datetime.strptime(r[0], "%d/%m/%Y")
                dt2 = datetime.strptime(r[1], "%d/%m/%Y")
                diff = (dt2 - dt1).days + 1
                if diff > 0:
                    dias_periodo = float(diff)
            except Exception:
                pass

        query = "SELECT codigo, SUM(cant) as total_cant, SUM(frac) as total_frac FROM ventas GROUP BY codigo"
        df_ventas = pd.read_sql(query, conn)
    
    df = pd.merge(df_stock, df_ventas, on="codigo", how="left").fillna(0)
    
    df['ufrac_val'] = pd.to_numeric(df['ufrac'], errors='coerce').fillna(1)
    df.loc[df['ufrac_val'] <= 0, 'ufrac_val'] = 1.0

    df['venta_eq'] = df['total_cant'] + (df['total_frac'] / df['ufrac_val'])
    df['CPD'] = df['venta_eq'] / dias_periodo
    df['stock_eq'] = df['cant'] + (df['frac'] / df['ufrac_val'])
    
    df['dias_stock'] = np.where(df['CPD'] > 0, df['stock_eq'] / df['CPD'], None)
    
    df['punto_pedido'] = (df['CPD'] * lead_time) + (df['CPD'] * dias_seg)
    
    # Usamos ceil (redondear hacia arriba) para asegurar que si hay déficit, se pida al menos 1 unidad lógica
    df['a_pedir_eq'] = np.where(
        (df['CPD'] > 0) & (df['stock_eq'] <= df['punto_pedido']), 
        (((df['CPD'] * dias_cob) + (df['CPD'] * dias_seg)) - df['stock_eq']), 
        0
    )
    df['a_pedir'] = np.where(df['a_pedir_eq'] > 0, np.ceil(df['a_pedir_eq']), 0)

    # Clasificación lógica estricta (Exige que a_pedir > 0 para urgencias)
    condiciones = [
        (df['venta_eq'] < 0.1) | (df['a_pedir'] == 0) & (df['stock_eq'] > df['punto_pedido']),                                     
        (df['CPD'] > 0) & (df['dias_stock'] < 7) & (df['a_pedir'] > 0),                     
        (df['CPD'] > 0) & (df['dias_stock'] >= 7) & (df['dias_stock'] <= 15) & (df['a_pedir'] > 0), 
        (df['dias_stock'].notnull()) & (df['dias_stock'] > 60)                                       
    ]
    etiquetas = ['SIN ROTACIÓN', 'URGENTE', 'POR PEDIR', 'SOBRESTOCK']
    df['estado'] = np.select(condiciones, etiquetas, default='OK')

    return df