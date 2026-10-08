"""
config.py - Configuración global, constantes de negocio y rutas del sistema VitalStock.

Este módulo actúa como fuente única de verdad (Single Source of Truth) para toda la aplicación.
No importa ningún otro archivo del proyecto para evitar dependencias circulares, y es consumido por:
  - `main.py` (puerto del receptor Yape para control de instancia única).
  - `database.py` (rutas de la base de datos SQLite, credenciales semilla y roles permitidos).
  - `services/*` (`auth_service.py`, `yape_service.py`, `inventario_service.py`, `pedido_service.py`, `reportes_service.py`).
  - `ui/*` (`app.py`, `styles.py`, `toasts.py`, `tray_manager.py`, `widgets.py`, vistas y diálogos).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# =========================================================================== #
# 1. Carga de Variables de Entorno (.env) y Metadatos de la Aplicación
# =========================================================================== #
def _cargar_dotenv() -> None:
    """Carga variables clave=valor desde un archivo `.env` local si existe,
    sin requerir dependencias externas y respetando variables ya definidas en el SO.
    """
    posibles = [Path(__file__).resolve().parent / ".env"]
    if getattr(sys, "frozen", False):
        posibles.insert(0, Path(sys.executable).resolve().parent / ".env")
    for ruta_env in posibles:
        if ruta_env.is_file():
            try:
                for linea in ruta_env.read_text(encoding="utf-8").splitlines():
                    limpia = linea.strip()
                    if not limpia or limpia.startswith("#") or "=" not in limpia:
                        continue
                    clave, valor = limpia.split("=", 1)
                    os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))
            except Exception:
                pass


_cargar_dotenv()

APP_NOMBRE = "VitalStock"
APP_SUBTITULO = "Gestión de Stock, Compras y Caja para Botica"
APP_VERSION = "1.4.1"

# =========================================================================== #
# 2. Roles de Usuario, Credenciales Semilla (.env) y Control de Acceso (RBAC)
# Consumido por: `database.py`, `services/auth_service.py`, `ui/app.py` y `ui/dialogs/users_dialog.py`
# =========================================================================== #
ROL_ADMIN = "admin"
ROL_CAJA = "caja"
ROL_SOPORTE = "soporte"
ROLES_PERMITIDOS = [ROL_ADMIN, ROL_CAJA, ROL_SOPORTE]
ROLES_GESTIONABLES = [ROL_CAJA, ROL_ADMIN]

NOMBRES_ROLES = {
    ROL_ADMIN: "Admin",
    ROL_CAJA: "Caja",
    ROL_SOPORTE: "Soporte Técnico",
}

# Credenciales iniciales parametrizables por entorno (.env) para instalaciones nuevas
ADMIN_USER_INICIAL = os.environ.get("VITALSTOCK_ADMIN_USER", "admin")
ADMIN_PASS_INICIAL = os.environ.get("VITALSTOCK_ADMIN_PASS", "admin123")
CAJA_USER_INICIAL = os.environ.get("VITALSTOCK_CAJA_USER", "caja")
CAJA_PASS_INICIAL = os.environ.get("VITALSTOCK_CAJA_PASS", "caja123")
SOPORTE_USER_INICIAL = os.environ.get("VITALSTOCK_SOPORTE_USER", "bowly")
SOPORTE_PASS_INICIAL = os.environ.get("VITALSTOCK_SOPORTE_PASS", "Soporte2026")

# =========================================================================== #
# 3. Zonas Físicas / Secciones de Inventario de la Botica
# Consumido por: `database.py`, `services/inventario_service.py` y `ui/views/inventario_view.py`
# =========================================================================== #
SECCION_VITRINA = "Sección Vitrina"
SECCION_CAJA = "Sección Caja"
SECCION_ANAQUEL = "Sección Anaquel"
SECCION_ALMACEN = "Sección Almacén"

# Alias de compatibilidad hacia atrás
ANAQUEL_1 = SECCION_VITRINA
ANAQUEL_2 = SECCION_CAJA
ANAQUEL_3 = SECCION_ANAQUEL
ANAQUEL_4 = SECCION_ALMACEN

ANAQUELES = [
    SECCION_VITRINA,
    SECCION_CAJA,
    SECCION_ANAQUEL,
    SECCION_ALMACEN,
]
ANAQUEL_DEFAULT = SECCION_CAJA

MAPEO_ANAQUELES_LEGACY = {
    "Vitrinas (Anaquel 1)": SECCION_VITRINA,
    "Detrás de caja (Anaquel 2)": SECCION_CAJA,
    "Lateral por dentro (Anaquel 3)": SECCION_ANAQUEL,
    "Almacén": SECCION_ALMACEN,
    "Anaquel 1": SECCION_VITRINA,
    "Anaquel 2": SECCION_CAJA,
    "Anaquel 3": SECCION_ANAQUEL,
    "Anaquel 4": SECCION_ALMACEN,
    "Vitrinas": SECCION_VITRINA,
    "Detrás de caja": SECCION_CAJA,
    "Lateral": SECCION_ANAQUEL,
}


def normalizar_anaquel(nombre: str) -> str:
    """Convierte cualquier formato o nombre antiguo de anaquel al nombre canónico de sección.

    Comunicación entre módulos:
      - Invocada por `services/inventario_service.py` al cargar o clasificar productos,
        y por `ui/views/inventario_view.py` al mostrar u ordenar ubicaciones en pantalla.
    """
    if not nombre:
        return ANAQUEL_DEFAULT
    limpio = str(nombre).strip()
    return MAPEO_ANAQUELES_LEGACY.get(limpio, limpio)


def es_filtro_todos(nombre: str) -> bool:
    """Determina si el texto seleccionado corresponde a filtrar o exportar todas las secciones.

    Comunicación entre módulos:
      - Invocada por `services/inventario_service.py` (para decidir si exportar múltiples hojas
        en Excel o una sola) y por `ui/views/inventario_view.py` al filtrar la tabla de vista previa.
    """
    if not nombre:
        return True
    s = str(nombre).strip().lower()
    return "tod" in s


# =========================================================================== #
# 4. Estados y Prioridades de Pedido de Reposición
# Consumido por: `services/pedido_service.py` y `ui/views/pedido_view.py`
# =========================================================================== #
ESTADO_URGENTE = "URGENTE"
ESTADO_POR_PEDIR = "POR PEDIR"
ESTADO_NORMAL = "NORMAL"
ESTADO_SOBRESTOCK = "SOBRESTOCK"
ESTADO_SIN_ROTACION = "SIN ROTACIÓN"

ESTADOS = [ESTADO_URGENTE, ESTADO_POR_PEDIR, ESTADO_NORMAL, ESTADO_SOBRESTOCK, ESTADO_SIN_ROTACION]
PRIORIDAD_ESTADOS = {estado: i for i, estado in enumerate(ESTADOS)}

UMBRAL_SIN_ROTACION = 0.1   # Venta equivalente mínima en el período analizado
DIAS_URGENTE = 7
DIAS_POR_PEDIR = 15
DIAS_SOBRESTOCK = 60

# =========================================================================== #
# 5. Red y Servicio Receptor Yape (VitalNotifier)
# Consumido por: `main.py`, `services/yape_service.py` y `ui/dialogs/network_dialog.py`
# =========================================================================== #
PUERTO_YAPE_DEFECTO = int(os.environ.get("VITALSTOCK_PORT", "5005"))

# =========================================================================== #
# 6. Paleta de Colores y Tipografía (Diseño Institucional Botica)
# Consumido por: `ui/styles.py`, `ui/widgets.py`, `ui/toasts.py` y vistas Tkinter
# =========================================================================== #
COLOR_PRIMARIO = "#1f6f5c"
COLOR_PRIMARIO_HOVER = "#185a4b"
COLOR_FONDO = "#f4f6f5"
COLOR_TARJETA = "#ffffff"
COLOR_TEXTO = "#1d2b27"
COLOR_TEXTO_SEC = "#5f6f6a"
COLOR_BORDE = "#d5ddda"
COLOR_DROP_ACTIVO = "#e3f1ec"
COLOR_OK = "#1f6f5c"
COLOR_ERROR = "#b42318"

COLORES_ESTADO = {
    ESTADO_URGENTE: "#f8d7da",       # Rojo suave
    ESTADO_POR_PEDIR: "#ffe5c2",     # Naranja suave
    ESTADO_SOBRESTOCK: "#d6e9f8",    # Azul suave
    ESTADO_SIN_ROTACION: "#e2e3e5",  # Gris
}

TAGS_ESTADO = {
    ESTADO_URGENTE: "urgente",
    ESTADO_POR_PEDIR: "por_pedir",
    ESTADO_SOBRESTOCK: "sobrestock",
    ESTADO_SIN_ROTACION: "sin_rotacion",
    ESTADO_NORMAL: "normal",
}

FUENTE = "Segoe UI"
TIPOS_REPORTE = [("Reportes del sistema", "*.xls *.xlsx *.html *.htm"), ("Todos los archivos", "*.*")]

# =========================================================================== #
# 7. Rutas de Archivos y Base de Datos en %APPDATA%
# Consumido por: `database.py`, `ui/app.py` y `ui/tray_manager.py`
# =========================================================================== #
NOMBRE_DB = "historial.db"


def ruta_base() -> Path:
    """Retorna la carpeta raíz de la aplicación (junto al `.exe` si está compilada con PyInstaller).

    Comunicación entre módulos:
      - Invocada por `ruta_db()` en este mismo archivo, `ui/app.py` y `ui/tray_manager.py`
        para localizar recursos gráficos (`vitalstock.ico`, `vitalstock.png`).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def ruta_appdata() -> Path:
    """Retorna la carpeta de datos persistentes del sistema en `%APPDATA%/VitalStock`.

    Crea el directorio automáticamente si no existe para desacoplar los datos del
    ejecutable y permitir actualizaciones limpias sin pérdida de información.

    Comunicación entre módulos:
      - Invocada internamente por `ruta_db()` y disponible para `database.py`.
    """
    base_appdata = os.environ.get("APPDATA")
    if base_appdata:
        carpeta = Path(base_appdata) / APP_NOMBRE
    else:
        carpeta = Path.home() / f".{APP_NOMBRE.lower()}"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def ruta_db() -> Path:
    """Retorna la ruta absoluta hacia la base de datos SQLite (`historial.db`) en `%APPDATA%/VitalStock`.

    Si la base de datos aún no existe en `%APPDATA%/VitalStock` pero existe una base de datos
    previa en la carpeta local del programa (`ruta_base()`), la copia automáticamente para
    preservar el 100% de los datos históricos de la botica.

    Comunicación entre módulos:
      - Invocada directamente por `database.py` en `obtener_conexion()` e `inicializar_db()`.
    """
    personalizada = os.environ.get("VITALSTOCK_DB")
    if personalizada:
        return Path(personalizada)

    destino = ruta_appdata() / NOMBRE_DB
    if not destino.exists():
        origen_local = ruta_base() / NOMBRE_DB
        if origen_local.is_file():
            try:
                import shutil
                shutil.copy2(origen_local, destino)
                print(f"[VitalStock] Base de datos migrada exitosamente desde {origen_local} hacia {destino}")
            except Exception as e_mig:
                print(f"[VitalStock] Aviso: no se pudo migrar la base local a AppData: {e_mig}")
                return origen_local
    return destino
