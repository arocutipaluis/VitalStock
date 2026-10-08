"""
services/reportes_service.py - Módulo de parsing y normalización de reportes de stock y ventas.

El sistema de la botica exporta archivos con extensión ".xls" que en realidad
son tablas HTML (o archivos Excel binarios/OOXML). Este módulo detecta el formato
real leyendo la firma de bytes del archivo y extrae la tabla de interés ubicando
la fila de encabezados mediante una columna clave ("codigo" para stock, "codpro" para ventas).

Comunicación con otros archivos del proyecto:
  - Es invocado por `services/pedido_service.py` (`importar_ventas` llama a `leer_ventas`).
  - Es invocado por `ui/views/pedido_view.py` y `ui/views/inventario_view.py` (`leer_stock`).
  - Reexportado en `reportes.py` por compatibilidad.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #
FIRMA_OLE2 = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"  # Excel 97-2003 (.xls binario)
FIRMA_ZIP = b"PK\x03\x04"                          # Excel 2007+ (.xlsx)
BOM_UTF8 = b"\xef\xbb\xbf"
BOM_UTF16 = (b"\xff\xfe", b"\xfe\xff")

FORMATO_HTML = "html"
FORMATO_XLS = "xls"
FORMATO_XLSX = "xlsx"

COLUMNAS_STOCK = ["codigo", "producto", "tipo", "ufrac", "cant", "frac"]
COLUMNAS_VENTAS = ["codigo", "producto", "cant", "frac", "venta", "costo", "util"]

_FECHA = r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})"
_HORA_OPCIONAL = r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?)?"
_PATRON_FECHAS = re.compile(
    rf"\bDel\s*:?\s*{_FECHA}{_HORA_OPCIONAL}\s*\bAl\s*:?\s*{_FECHA}",
    re.IGNORECASE,
)
_PATRON_MILES = re.compile(r"^-?\d{1,3}(,\d{3})+$")
_PATRON_ENTERO_FLOAT = re.compile(r"^(-?\d+)\.0+$")


class ReporteError(Exception):
    """Error de lectura o formato en un reporte exportado por el sistema."""


# --------------------------------------------------------------------------- #
# Utilidades de texto
# --------------------------------------------------------------------------- #
def _normalizar(texto: object) -> str:
    """Minúsculas, sin tildes y sin caracteres no alfanuméricos ('Cód. Pro' -> 'codpro')."""
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _decodificar(datos: bytes) -> str:
    """Decodifica bytes probando las codificaciones habituales en Windows/Perú."""
    if datos.startswith(BOM_UTF16):
        return datos.decode("utf-16", errors="replace")
    if datos.startswith(BOM_UTF8):
        return datos.decode("utf-8-sig", errors="replace")
    for codificacion in ("utf-8", "cp1252"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return datos.decode("latin-1", errors="replace")


def _normalizar_codigo(valor: object) -> str:
    """Convierte el código a texto limpio ('123.0' -> '123')."""
    s = str(valor).strip()
    m = _PATRON_ENTERO_FLOAT.match(s)
    return m.group(1) if m else s


def _limpiar_numero_individual(valor: object) -> float:
    if pd.isna(valor):
        return 0.0
    s = str(valor).replace("\xa0", "").replace(" ", "").strip()
    if not s or s.upper() in ("-", "OK", "W", "NONE", "NAN"):
        return 0.0
    if _PATRON_MILES.match(s):
        s = s.replace(",", "")
    elif "." in s and "," in s:
        s = s.replace(",", "")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        pass
    m = re.search(r"^(-?\d+(?:[.,]\d+)?)", s)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return 0.0


def _a_numero(serie: pd.Series) -> pd.Series:
    """Convierte una serie a numérica soportando miles, comas decimales y sufijos como '10U'."""
    return serie.map(_limpiar_numero_individual).fillna(0.0)


def _parsear_fecha(texto: str) -> date:
    return datetime.strptime(texto.replace("-", "/"), "%d/%m/%Y").date()


# --------------------------------------------------------------------------- #
# Detección de formato y carga de filas
# --------------------------------------------------------------------------- #
def detectar_formato(ruta: str | Path) -> str:
    """Detecta el formato real del archivo leyendo su cabecera."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ReporteError(f"No se encontró el archivo:\n{ruta}")

    with open(ruta, "rb") as f:
        cabecera = f.read(4096)

    if not cabecera:
        raise ReporteError(f"El archivo está vacío:\n{ruta.name}")
    if cabecera.startswith(FIRMA_OLE2):
        return FORMATO_XLS
    if cabecera.startswith(FIRMA_ZIP):
        return FORMATO_XLSX

    texto = _decodificar(cabecera).lstrip().lower()
    if texto.startswith("<") or any(m in texto for m in ("<html", "<table", "<tr", "<br", "<form")):
        return FORMATO_HTML

    raise ReporteError(
        f"Formato no reconocido en '{ruta.name}'.\n"
        "Se esperaba un reporte HTML (.xls del sistema) o un Excel."
    )


class _TablaHTMLParser(HTMLParser):
    """Parser tolerante que convierte todas las filas <tr> en listas de texto."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.filas: list[list[str]] = []
        self.textos: list[str] = []
        self._fila: list[str] | None = None
        self._celda: list[str] | None = None
        self._colspan = 1

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._cerrar_fila()
            self._fila = []
        elif tag in ("td", "th"):
            self._cerrar_celda()
            if self._fila is None:
                self._fila = []
            self._celda = []
            try:
                self._colspan = max(1, int(dict(attrs).get("colspan") or 1))
            except ValueError:
                self._colspan = 1
        elif tag == "br":
            self.textos.append(" ")
            if self._celda is not None:
                self._celda.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._cerrar_celda()
        elif tag in ("tr", "table"):
            self._cerrar_fila()

    def handle_data(self, data):
        self.textos.append(data)
        if self._celda is not None:
            self._celda.append(data)

    def close(self):
        super().close()
        self._cerrar_fila()

    def _cerrar_celda(self):
        if self._celda is not None and self._fila is not None:
            texto = " ".join("".join(self._celda).split())
            self._fila.append(texto)
            self._fila.extend([""] * (self._colspan - 1))
        self._celda = None
        self._colspan = 1

    def _cerrar_fila(self):
        self._cerrar_celda()
        if self._fila:
            self.filas.append(self._fila)
        self._fila = None


def _cargar_html(ruta: Path) -> tuple[list[list[str]], str]:
    with open(ruta, "rb") as f:
        contenido = _decodificar(f.read())
    parser = _TablaHTMLParser()
    parser.feed(contenido)
    parser.close()
    texto_plano = " ".join(" ".join(parser.textos).split())
    return parser.filas, texto_plano


def _cargar_excel(ruta: Path, formato: str) -> tuple[list[list[str]], str]:
    motor_excel = "xlrd" if formato == FORMATO_XLS else "openpyxl"
    try:
        hojas = pd.read_excel(ruta, header=None, sheet_name=None, dtype=str, engine=motor_excel)
    except ImportError as exc:
        raise ReporteError(
            "Para leer archivos Excel binarios (.xls reales) instale 'xlrd':\n"
            "    pip install xlrd"
        ) from exc
    except Exception as exc:
        raise ReporteError(f"No se pudo leer el Excel '{ruta.name}':\n{exc}") from exc

    filas: list[list[str]] = []
    for df in hojas.values():
        filas.extend(df.fillna("").astype(str).values.tolist())
    texto_plano = " ".join(" ".join(c for c in fila if c) for fila in filas)
    return filas, texto_plano


def _cargar(ruta: str | Path) -> tuple[list[list[str]], str]:
    ruta = Path(ruta)
    formato = detectar_formato(ruta)
    if formato == FORMATO_HTML:
        return _cargar_html(ruta)
    return _cargar_excel(ruta, formato)


# --------------------------------------------------------------------------- #
# Extracción y limpieza de tablas
# --------------------------------------------------------------------------- #
MAPEO_SINONIMOS = {
    "codigo": ["codigo", "cod", "codpro", "cod_pro", "item", "código"],
    "producto": ["producto", "prod", "descripcion", "nombre", "articulo", "detalle"],
    "tipo": ["tipo", "laborat", "laboratorio", "lab", "marca"],
    "cant": ["cant", "cantidad", "sistema", "stock", "stock_u", "unidades", "sist_u", "caja"],
    "frac": ["frac", "fraccion", "fracciones", "stock_f", "sist_f", "unidad", "und"],
    "ufrac": ["ufrac", "u_frac", "fraccionamiento", "unid_frac"],
}


def _normalizar_nombre_columna(columna: str) -> str:
    norm = _normalizar(columna)
    for canonico, sinonimos in MAPEO_SINONIMOS.items():
        if norm in sinonimos or any(norm.startswith(s) for s in sinonimos if len(s) >= 4):
            return canonico
    return norm


def _extraer_tabla(filas: list[list[str]], claves: list[str] | str, nombre_archivo: str) -> pd.DataFrame:
    if isinstance(claves, str):
        claves = [claves]
    claves_norm = [_normalizar(k) for k in claves]

    idx_encabezado = None
    for i, fila in enumerate(filas):
        celdas_norm = [_normalizar(c) for c in fila]
        if any(k in celdas_norm for k in claves_norm):
            idx_encabezado = i
            break

    if idx_encabezado is None:
        raise ReporteError(
            f"No se encontró la columna de identificación ('{', '.join(claves)}') en '{nombre_archivo}'.\n"
            "Verifique que sea un reporte válido del sistema o formato de inventario."
        )

    encabezado: list[str] = []
    for i, celda in enumerate(filas[idx_encabezado]):
        canonico = _normalizar_nombre_columna(celda) or f"col_{i}"
        encabezado.append(canonico)

    ancho = len(encabezado)
    datos = []
    for fila in filas[idx_encabezado + 1:]:
        fila = list(fila[:ancho]) + [""] * max(0, ancho - len(fila))
        datos.append(fila)

    df = pd.DataFrame(datos, columns=encabezado, dtype=object)
    return df.loc[:, ~df.columns.duplicated()]


def _limpiar_filas(df: pd.DataFrame, encabezados_repetidos: set[str]) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df = df.replace("", pd.NA)

    df = df[df["codigo"].notna()].copy()
    df["codigo"] = df["codigo"].map(_normalizar_codigo)
    codigo_n = df["codigo"].map(_normalizar)
    descartar = codigo_n.isin(encabezados_repetidos) | codigo_n.str.startswith("total") | (codigo_n == "")
    return df[~descartar].copy()


def _asegurar_columnas(df: pd.DataFrame, obligatorias: list[str], opcionales: dict, archivo: str) -> pd.DataFrame:
    faltantes = [c for c in obligatorias if c not in df.columns]
    if faltantes:
        raise ReporteError(
            f"Faltan columnas necesarias en '{archivo}': {', '.join(faltantes)}.\n"
            f"Columnas detectadas: {', '.join(df.columns)}"
        )
    for col, defecto in opcionales.items():
        if col not in df.columns:
            df[col] = defecto
    return df


# --------------------------------------------------------------------------- #
# API pública de Parsing
# --------------------------------------------------------------------------- #
def leer_stock(ruta: str | Path) -> pd.DataFrame:
    """Lee el reporte de stock actual (compatible con exportaciones de rol Admin o Caja).

    Retorna:
      `pd.DataFrame` con columnas: `codigo`, `producto`, `tipo`, `ufrac`, `cant`, `frac`.

    Comunicación entre módulos:
      - Invocada por `ui/views/pedido_view.py` (`PantallaPedido._cargar_stock`) y
        `ui/views/inventario_view.py` (`PantallaInventario._cargar_stock`).
    """
    ruta = Path(ruta)
    filas, _ = _cargar(ruta)
    df = _extraer_tabla(filas, ["codigo", "cod", "codpro", "item"], ruta.name)
    df = _asegurar_columnas(
        df,
        obligatorias=["codigo", "producto"],
        opcionales={"tipo": "", "ufrac": "1", "cant": "0", "frac": "0"},
        archivo=ruta.name,
    )
    df = _limpiar_filas(df, {"codigo", "cod", "codpro", "item"})

    if df.empty:
        raise ReporteError(f"El reporte de stock '{ruta.name}' no contiene productos válidos.")

    for col in ("producto", "tipo"):
        df[col] = df[col].fillna("").astype(str)
    for col in ("cant", "frac", "ufrac"):
        df[col] = _a_numero(df[col])

    df = (
        df.groupby("codigo", as_index=False, sort=False)
        .agg(producto=("producto", "first"), tipo=("tipo", "first"), ufrac=("ufrac", "first"),
             cant=("cant", "sum"), frac=("frac", "sum"))
    )
    return df[COLUMNAS_STOCK].reset_index(drop=True)


def extraer_rango_fechas(texto: str) -> tuple[date | None, date | None]:
    """Busca el patrón `'Del : DD/MM/YYYY Al : DD/MM/YYYY'` en la cabecera del reporte de ventas.

    Comunicación entre módulos:
      - Invocada internamente por `leer_ventas()` y reexportada en `reportes.py`.
    """
    m = _PATRON_FECHAS.search(texto or "")
    if not m:
        return None, None
    try:
        return _parsear_fecha(m.group(1)), _parsear_fecha(m.group(2))
    except ValueError:
        return None, None


def leer_ventas(ruta: str | Path) -> tuple[pd.DataFrame, date | None, date | None]:
    """Lee el reporte de ventas por producto y extrae su rango de fechas.

    Retorna:
      `(df_ventas, fecha_inicio, fecha_fin)`

    Comunicación entre módulos:
      - Invocada por `services/pedido_service.py` (`importar_ventas`) al registrar ventas en SQLite.
    """
    ruta = Path(ruta)
    filas, texto_plano = _cargar(ruta)
    df = _extraer_tabla(filas, ["codpro", "codigo", "cod"], ruta.name)

    if "codigo" not in df.columns:
        for c in ("codpro", "cod"):
            if c in df.columns:
                df = df.rename(columns={c: "codigo"})
                break
    if "producto" not in df.columns:
        for p in ("prod", "descripcion"):
            if p in df.columns:
                df = df.rename(columns={p: "producto"})
                break

    df = _asegurar_columnas(
        df,
        obligatorias=["codigo", "producto"],
        opcionales={"cant": "0", "frac": "0", "venta": "0", "costo": "0", "util": "0"},
        archivo=ruta.name,
    )
    df = _limpiar_filas(df, {"codigo", "codpro", "cod"})

    if df.empty:
        raise ReporteError(f"El reporte de ventas '{ruta.name}' no contiene transacciones válidas.")

    df["producto"] = df["producto"].fillna("").astype(str)
    for col in ("cant", "frac", "venta", "costo", "util"):
        df[col] = _a_numero(df[col])

    df = (
        df.groupby("codigo", as_index=False, sort=False)
        .agg(producto=("producto", "first"),
             cant=("cant", "sum"), frac=("frac", "sum"),
             venta=("venta", "sum"), costo=("costo", "sum"), util=("util", "sum"))
    )
    fecha_i, fecha_f = extraer_rango_fechas(texto_plano)
    return df[COLUMNAS_VENTAS].reset_index(drop=True), fecha_i, fecha_f
