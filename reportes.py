"""
VitalStock - Lectura de los reportes que exporta el sistema de la botica.

El sistema guarda como ".xls" un archivo que en realidad es HTML (una tabla).
Este módulo reconoce el tipo real del archivo (HTML, .xlsx o .xls binario) y
devuelve un DataFrame limpio.

Dependencias:  pandas, lxml   (y xlrd solo si algún día llega un .xls binario)
"""
import re
from io import StringIO
from pathlib import Path

import pandas as pd


class ErrorReporte(Exception):
    """Archivo ilegible o con un formato distinto al esperado.
    El mensaje está pensado para mostrarse tal cual al usuario."""


# "Reporte Generado el: ... 3/10/2026 11:06:04"
_RE_FECHA = re.compile(
    r"Generado\s+el\s*:.*?(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
    re.S | re.I,
)
_RE_RANGO_FECHAS = re.compile(
    r"Del\s*:\s*(\d{1,2}/\d{1,2}/\d{4}).*?Al\s*:\s*(\d{1,2}/\d{1,2}/\d{4})",
    re.S | re.I
)

def _tipo_real(ruta):
    with open(ruta, "rb") as f:
        cabecera = f.read(8)
    if cabecera[:2] == b"PK":
        return "xlsx"
    if cabecera[:4] == b"\xd0\xcf\x11\xe0":
        return "xls"
    return "html"


def _leer_texto(ruta):
    datos = Path(ruta).read_bytes()
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return datos.decode("latin-1", errors="replace")


def leer_tabla(ruta, columna_clave, columnas_texto=()):
    """Devuelve (DataFrame, fecha_de_generacion | None).

    columna_clave : nombre de una columna que identifica la tabla correcta.
    columnas_texto: columnas que deben leerse como texto (para no perder los
                    ceros a la izquierda de los códigos, p. ej. 000123).
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorReporte(f"No se encontró el archivo: {ruta.name}")

    fecha = None
    try:
        tipo = _tipo_real(ruta)
        if tipo == "html":
            texto = _leer_texto(ruta)
            m = _RE_FECHA.search(texto)
            fecha = m.group(1).strip() if m else None
            tablas = pd.read_html(
                StringIO(texto), match=columna_clave, header=0, thousands=",",
                converters={c: str for c in columnas_texto},
            )
            df = tablas[0]
        else:
            df = pd.read_excel(ruta, dtype={c: str for c in columnas_texto})
    except ValueError as e:
        raise ErrorReporte(
            f"No se encontró la tabla esperada en «{ruta.name}». "
            "Verifica que sea el reporte correcto exportado del sistema."
        ) from e
    except ImportError as e:
        raise ErrorReporte(f"Falta una librería para leer «{ruta.name}»: {e}") from e
    except Exception as e:  # archivo corrupto, permisos, etc.
        raise ErrorReporte(f"No se pudo leer «{ruta.name}»: {e}") from e

    df.columns = [str(c).strip().lower() for c in df.columns]
    return df, fecha


def _texto_limpio(serie):
    s = serie.fillna("").astype(str).str.strip()
    return s.mask(s.str.lower() == "nan", "")


def leer_stock(ruta):
    """Reporte de stock -> (DataFrame, fecha_reporte).

    Columnas devueltas: codigo, producto, tipo (= laboratorio), ufrac, cant, frac
    """
    df, fecha = leer_tabla(ruta, "codigo", ("codigo", "producto", "tipo"))
    requeridas = ["codigo", "producto", "tipo", "ufrac", "cant", "frac"]
    faltan = [c for c in requeridas if c not in df.columns]
    if faltan:
        raise ErrorReporte(
            "El archivo no parece un reporte de stock. "
            f"Faltan las columnas: {', '.join(faltan)}."
        )
    df = df[requeridas].copy()
    for c in ("codigo", "producto", "tipo"):
        df[c] = _texto_limpio(df[c])
    # descarta filas vacías o de totales
    df = df[(df["codigo"] != "") & (df["producto"] != "")]
    for c in ("ufrac", "cant", "frac"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    if df.empty:
        raise ErrorReporte("El reporte de stock no tiene productos.")
    return df.reset_index(drop=True), fecha
def leer_ventas(ruta):
    """Reporte de ventas -> (DataFrame, fecha_inicio, fecha_fin)."""
    ruta = Path(ruta)
    texto = _leer_texto(ruta)
    
    # Extraer fechas del reporte HTML
    m = _RE_RANGO_FECHAS.search(texto)
    f_inicio = m.group(1) if m else None
    f_fin = m.group(2) if m else None

    df, _ = leer_tabla(ruta, "codpro", ("codpro", "prod"))
    
    requeridas = ["codpro", "prod", "cant", "frac"]
    faltan = [c for c in requeridas if c not in df.columns]
    
    if faltan:
        raise ErrorReporte(f"El reporte de ventas no tiene las columnas esperadas. Faltan: {', '.join(faltan)}.")

    df = df[["codpro", "prod", "cant", "frac"]].copy()
    df.rename(columns={"codpro": "codigo", "prod": "producto"}, inplace=True)
    
    for c in ("codigo", "producto"):
        df[c] = _texto_limpio(df[c])
        
    df = df[(df["codigo"] != "") & (df["producto"] != "")]
    df["cant"] = pd.to_numeric(df["cant"], errors="coerce").fillna(0)
    df["frac"] = pd.to_numeric(df["frac"], errors="coerce").fillna(0)
    
    df["cantidad"] = df["cant"] + df["frac"]

    return df.reset_index(drop=True), f_inicio, f_fin