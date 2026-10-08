"""
services/pedido_service.py - Lógica de cálculo de sugerencias de compra e historial de ventas.

Calcula el Consumo Promedio Diario (CPD), los días de cobertura de stock, el punto de pedido
y la cantidad óptima a solicitar a droguerías/laboratorios cruzando el stock actual contra
el historial de ventas almacenado en SQLite.

Comunicación con otros archivos del proyecto:
  - Importa `config.py` (umbrales de días de urgencia, sobrestock y prioridades de estado).
  - Importa `database.py` (`obtener_conexion`) para persistir y consultar `importaciones` y `ventas`.
  - Importa `services/reportes_service.py` (`leer_ventas`, `ReporteError`) para parsear archivos de ventas.
  - Es consumido por `ui/views/pedido_view.py`, `ui/views/menu_view.py` y reexportado en `motor.py`.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import config
from database import obtener_conexion
from services import reportes_service


class ArchivoDuplicadoError(Exception):
    """Excepción lanzada cuando se intenta importar un archivo de ventas ya registrado en SQLite."""


def archivo_ya_importado(nombre_archivo: str) -> bool:
    """Verifica si un archivo de reporte de ventas ya existe en la tabla `importaciones`.

    Comunicación entre módulos:
      - Consulta SQLite mediante `database.obtener_conexion()` y es usada por `importar_ventas()`.
    """
    with obtener_conexion() as conn:
        fila = conn.execute(
            "SELECT 1 FROM importaciones WHERE archivo = ? LIMIT 1", (nombre_archivo,)
        ).fetchone()
    return fila is not None


def importar_ventas(ruta: str | Path) -> dict:
    """Lee un reporte de ventas del sistema de botica y guarda sus registros en SQLite.

    Comunicación entre módulos:
      - Invoca `reportes_service.leer_ventas(ruta)` de `services/reportes_service.py`.
      - Inserta registros en `importaciones` y `ventas` mediante `database.obtener_conexion()`.
      - Es llamada desde `ui/views/pedido_view.py` (`PantallaPedido._importar_ventas`).
    """
    ruta = Path(ruta)
    nombre = ruta.name

    if archivo_ya_importado(nombre):
        raise ArchivoDuplicadoError(f"El archivo '{nombre}' ya fue importado anteriormente.")

    df, fecha_inicio, fecha_fin = reportes_service.leer_ventas(ruta)
    if fecha_inicio is None or fecha_fin is None:
        raise reportes_service.ReporteError(
            f"No se encontró el rango de fechas ('Del : DD/MM/YYYY Al : DD/MM/YYYY') en '{nombre}'."
        )
    if df.empty:
        raise reportes_service.ReporteError(f"El reporte de ventas '{nombre}' no contiene registros.")

    filas = [
        (nombre, str(r.codigo), str(r.producto), float(r.cant), float(r.frac))
        for r in df.itertuples(index=False)
    ]
    try:
        with obtener_conexion() as conn:
            conn.execute(
                "INSERT INTO importaciones (archivo, fecha_inicio, fecha_fin, registros) VALUES (?, ?, ?, ?)",
                (nombre, fecha_inicio.isoformat(), fecha_fin.isoformat(), len(filas)),
            )
            conn.executemany(
                "INSERT INTO ventas (archivo, codigo, producto, cant, frac) VALUES (?, ?, ?, ?, ?)",
                filas,
            )
    except sqlite3.IntegrityError as exc:
        raise ArchivoDuplicadoError(f"El archivo '{nombre}' ya fue importado anteriormente.") from exc

    return {"archivo": nombre, "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin, "registros": len(filas)}


def listar_importaciones() -> pd.DataFrame:
    """Retorna un DataFrame con todos los archivos de ventas importados ordenados por fecha.

    Comunicación entre módulos:
      - Consulta SQLite vía `database.obtener_conexion()` y es usada por `ui/views/pedido_view.py`.
    """
    with obtener_conexion() as conn:
        return pd.read_sql_query(
            "SELECT archivo, fecha_inicio, fecha_fin, registros, fecha_carga "
            "FROM importaciones ORDER BY fecha_inicio",
            conn,
        )


def eliminar_importacion(nombre_archivo: str) -> None:
    """Elimina un archivo específico y sus ventas asociadas de la base de datos.

    Comunicación entre módulos:
      - Opera sobre SQLite vía `database.obtener_conexion()` y es llamada por `ui/views/pedido_view.py`.
    """
    with obtener_conexion() as conn:
        conn.execute("DELETE FROM ventas WHERE archivo = ?", (nombre_archivo,))
        conn.execute("DELETE FROM importaciones WHERE archivo = ?", (nombre_archivo,))


def limpiar_historial() -> None:
    """Borra la totalidad del historial de ventas e importaciones en SQLite (solo Admin).

    Comunicación entre módulos:
      - Opera sobre SQLite vía `database.obtener_conexion()` y es llamada por `ui/views/pedido_view.py`.
    """
    with obtener_conexion() as conn:
        conn.execute("DELETE FROM ventas")
        conn.execute("DELETE FROM importaciones")


def obtener_resumen_historial() -> dict | None:
    """Obtiene el rango total de fechas, cantidad de archivos y registros de ventas en SQLite.

    Comunicación entre módulos:
      - Consulta SQLite vía `database.obtener_conexion()`.
      - Invocada por `ui/views/menu_view.py` y `ui/views/pedido_view.py` para mostrar indicadores.
    """
    with obtener_conexion() as conn:
        inicio, fin, archivos = conn.execute(
            "SELECT MIN(fecha_inicio), MAX(fecha_fin), COUNT(*) FROM importaciones"
        ).fetchone()
        registros = conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
    if not archivos:
        return None
    fecha_inicio, fecha_fin = date.fromisoformat(inicio), date.fromisoformat(fin)
    return {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "dias": (fecha_fin - fecha_inicio).days + 1,
        "archivos": archivos,
        "registros": registros,
    }


def obtener_dias_periodo() -> int | None:
    """Devuelve el número total de días calendario cubiertos por el historial de ventas."""
    resumen = obtener_resumen_historial()
    return resumen["dias"] if resumen else None


def obtener_ventas_acumuladas() -> pd.DataFrame:
    """Agrupa las ventas históricas por código de producto sumando unidades y fracciones.

    Comunicación entre módulos:
      - Consulta SQLite vía `database.obtener_conexion()` y es usada por `calcular_recomendacion()`.
    """
    with obtener_conexion() as conn:
        df = pd.read_sql_query(
            "SELECT codigo, SUM(cant) AS total_cant, SUM(frac) AS total_frac "
            "FROM ventas GROUP BY codigo",
            conn,
        )
    df["codigo"] = df["codigo"].astype(str)
    return df


def calcular_recomendacion(
    df_stock: pd.DataFrame,
    lead_time: int = 3,
    dias_seg: int = 7,
    dias_cob: int = 30,
    *,
    df_ventas: pd.DataFrame | None = None,
    dias_periodo: int | None = None,
) -> pd.DataFrame:
    """Cruza el stock actual con el histórico de ventas y calcula las cantidades sugeridas a pedir.

    Clasifica cada producto en `URGENTE`, `POR PEDIR`, `NORMAL`, `SOBRESTOCK` o `SIN ROTACIÓN`.

    Comunicación entre módulos:
      - Consume parámetros de negocio de `config.py` y datos de `obtener_ventas_acumuladas()`.
      - Invocada por `ui/views/pedido_view.py` (`PantallaPedido._calcular`) y reexportada en `motor.py`.
    """
    if df_stock is None or df_stock.empty:
        raise ValueError("Primero cargue el reporte de stock.")
    for nombre, valor in (("Lead time", lead_time), ("Días de seguridad", dias_seg), ("Días de cobertura", dias_cob)):
        if valor < 0:
            raise ValueError(f"{nombre} no puede ser negativo.")

    if dias_periodo is None:
        dias_periodo = obtener_dias_periodo()
    if not dias_periodo or dias_periodo <= 0:
        raise ValueError("No hay historial de ventas. Importe al menos un reporte de ventas.")

    ventas = obtener_ventas_acumuladas() if df_ventas is None else df_ventas.copy()

    df = df_stock.copy()
    df["codigo"] = df["codigo"].astype(str)
    ventas["codigo"] = ventas["codigo"].astype(str)
    df = df.merge(ventas[["codigo", "total_cant", "total_frac"]], on="codigo", how="left")
    df[["total_cant", "total_frac"]] = df[["total_cant", "total_frac"]].fillna(0.0)

    ufrac = pd.to_numeric(df["ufrac"], errors="coerce").fillna(1.0)
    df["ufrac"] = ufrac.where(ufrac > 0, 1.0)
    df["cant"] = pd.to_numeric(df["cant"], errors="coerce").fillna(0.0)
    df["frac"] = pd.to_numeric(df["frac"], errors="coerce").fillna(0.0)

    df["venta_eq"] = df["total_cant"] + df["total_frac"] / df["ufrac"]
    df["cpd"] = df["venta_eq"] / float(dias_periodo)
    df["stock_eq"] = df["cant"] + df["frac"] / df["ufrac"]

    cpd = df["cpd"].to_numpy(dtype=float)
    stock = df["stock_eq"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        dias_stock = np.where(cpd > 0, stock / cpd, np.inf)
    df["dias_stock"] = dias_stock

    df["punto_pedido"] = cpd * (lead_time + dias_seg)
    stock_objetivo = cpd * (lead_time + dias_seg + dias_cob)
    faltante = np.clip(stock_objetivo - np.maximum(stock, 0.0), 0.0, None)
    a_pedir = np.ceil(np.round(faltante, 6)).astype(int)

    sin_venta = df["venta_eq"].to_numpy() < config.UMBRAL_SIN_ROTACION
    a_pedir[sin_venta] = 0
    df["a_pedir"] = a_pedir

    tiene_cpd = cpd > 0
    condiciones = [
        sin_venta,
        dias_stock > config.DIAS_SOBRESTOCK,
        tiene_cpd & (dias_stock < config.DIAS_URGENTE) & (a_pedir > 0),
        tiene_cpd & (dias_stock >= config.DIAS_URGENTE) & (dias_stock <= config.DIAS_POR_PEDIR) & (a_pedir > 0),
        (stock > df["punto_pedido"].to_numpy()) & (a_pedir == 0),
    ]
    opciones = [
        config.ESTADO_SIN_ROTACION,
        config.ESTADO_SOBRESTOCK,
        config.ESTADO_URGENTE,
        config.ESTADO_POR_PEDIR,
        config.ESTADO_SIN_ROTACION,
    ]
    df["estado"] = np.select(condiciones, opciones, default=config.ESTADO_NORMAL)

    df["_prioridad"] = df["estado"].map(config.PRIORIDAD_ESTADOS)
    df = df.sort_values(["_prioridad", "dias_stock", "producto"], kind="mergesort").drop(columns="_prioridad")

    columnas = [
        "codigo", "producto", "tipo", "ufrac", "cant", "frac", "venta_eq", "cpd",
        "stock_eq", "dias_stock", "punto_pedido", "a_pedir", "estado",
    ]
    return df[columnas].reset_index(drop=True)
