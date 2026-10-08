"""
database.py - Gestión de conexiones transaccionales, esquema SQLite y migraciones automáticas.

Este módulo administra la persistencia de datos en SQLite para VitalStock.
Comunicación con otros archivos del proyecto:
  - Importa `config.py` para obtener la ruta de la base de datos (`ruta_db`) y constantes de roles/secciones.
  - Importa bajo demanda `services/seed_data.py` para poblar el catálogo inicial de ubicaciones.
  - Es consumido por todos los servicios en `services/` (`auth_service.py`, `yape_service.py`,
    `inventario_service.py`, `reportes_service.py`) y por el controlador `ui/app.py`.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import config

ruta_db = config.ruta_db
ruta_base = config.ruta_base

# =========================================================================== #
# Definición del Esquema Base SQLite
# =========================================================================== #
_ESQUEMA = """
CREATE TABLE IF NOT EXISTS importaciones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    archivo       TEXT NOT NULL UNIQUE,
    fecha_inicio  TEXT NOT NULL,          -- ISO YYYY-MM-DD
    fecha_fin     TEXT NOT NULL,          -- ISO YYYY-MM-DD
    registros     INTEGER NOT NULL DEFAULT 0,
    fecha_carga   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS ventas (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    archivo   TEXT NOT NULL REFERENCES importaciones(archivo) ON DELETE CASCADE,
    codigo    TEXT NOT NULL,
    producto  TEXT,
    cant      REAL NOT NULL DEFAULT 0,
    frac      REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pagos_yape (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    remitente      TEXT NOT NULL,
    monto          REAL NOT NULL,
    fecha_hora     TEXT NOT NULL,          -- Fecha y hora real del Yape (ej. DD/MM/YYYY HH:MM:SS)
    codigo_seg     TEXT,                   -- Código de seguridad enviado por VitalNotifier
    mensaje_raw    TEXT,                   -- Texto original de la notificación
    fecha_registro TEXT NOT NULL DEFAULT (datetime('now', 'localtime')) -- Fecha/hora ISO del Yape para filtros SQL
);

CREATE TABLE IF NOT EXISTS usuarios (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    salt           TEXT NOT NULL,
    rol            TEXT NOT NULL CHECK(rol IN ('admin', 'caja', 'soporte')),
    nombre         TEXT NOT NULL,
    activo         INTEGER NOT NULL DEFAULT 1,
    fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS ubicacion_productos (
    codigo        TEXT PRIMARY KEY,
    producto      TEXT NOT NULL,
    laboratorio   TEXT,
    anaquel       TEXT NOT NULL,
    fecha_mod     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_ventas_codigo      ON ventas(codigo);
CREATE INDEX IF NOT EXISTS idx_ventas_archivo     ON ventas(archivo);
CREATE INDEX IF NOT EXISTS idx_yape_fecha         ON pagos_yape(fecha_registro);
CREATE INDEX IF NOT EXISTS idx_usuarios_user      ON usuarios(username);
CREATE INDEX IF NOT EXISTS idx_ubicacion_anaquel  ON ubicacion_productos(anaquel);
CREATE INDEX IF NOT EXISTS idx_ubicacion_prod     ON ubicacion_productos(producto);
"""

_db_inicializada: set[str] = set()


@contextmanager
def obtener_conexion():
    """Abre una conexión transaccional con SQLite (hace commit al salir o rollback si ocurre un error).

    En la primera conexión al archivo de base de datos, verifica el esquema y ejecuta
    las migraciones automáticas pendientes.

    Comunicación entre módulos:
      - Consulta `config.ruta_db()` para determinar la ubicación del archivo `.db` en `%APPDATA%`.
      - Es utilizada mediante bloques `with obtener_conexion() as conn:` por `services/auth_service.py`,
        `services/yape_service.py`, `services/inventario_service.py` y `services/reportes_service.py`.
    """
    ruta = config.ruta_db()
    conn = sqlite3.connect(ruta)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        if str(ruta) not in _db_inicializada:
            conn.executescript(_ESQUEMA)
            _migrar_esquema_versiones(conn)
            _migrar_anaqueles_a_secciones(conn)
            _db_inicializada.add(str(ruta))
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Genera un hash criptográfico seguro PBKDF2-HMAC-SHA256 con 100,000 iteraciones y salt aleatorio.

    Comunicación entre módulos:
      - Invocada internamente en `inicializar_db()` para crear las cuentas iniciales.
      - Importada y utilizada por `services/auth_service.py` para autenticar usuarios,
        crear personal nuevo y actualizar contraseñas.
    """
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return hashed, salt


def convertir_fecha_hora_yape(fecha_hora_str: str) -> tuple[str, str]:
    """Interpreta la fecha y hora enviada por VitalNotifier y devuelve su formato visual e ISO.

    VitalNotifier envía el campo `fecha_hora` en formato `"DD/MM/YYYY HH:MM:SS"` (ej. `"15/10/2026 10:35:12"`).
    Esta función garantiza que tanto la columna visual (`fecha_hora`) como la columna de indexación SQL
    (`fecha_registro`) almacenen la hora exacta en que se realizó el Yape y NO la hora en que llegó a la PC.

    Retorna:
      `tuple[str, str]`: `(fecha_hora_visual, fecha_iso_sqlite)`
        - `fecha_hora_visual`: `"DD/MM/YYYY HH:MM:SS"` para mostrar en tablas y reportes Excel.
        - `fecha_iso_sqlite`: `"YYYY-MM-DD HH:MM:SS"` para filtros `date(...)` y ordenamiento en SQLite.

    Comunicación entre módulos:
      - Invocada en `_migrar_esquema_versiones()` dentro de este archivo para corregir registros previos.
      - Importada y utilizada por `services/yape_service.py` al registrar cada pago entrante de VitalNotifier.
    """
    formatos = (
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d",
    )
    texto = (fecha_hora_str or "").strip()
    if texto:
        for fmt in formatos:
            try:
                dt = datetime.strptime(texto, fmt)
                return dt.strftime("%d/%m/%Y %H:%M:%S"), dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

    ahora = datetime.now()
    if texto:
        # Si vino un formato no estándar, conservar el texto original para visualización
        return texto, ahora.strftime("%Y-%m-%d %H:%M:%S")
    return ahora.strftime("%d/%m/%Y %H:%M:%S"), ahora.strftime("%Y-%m-%d %H:%M:%S")


def _migrar_esquema_versiones(conn: sqlite3.Connection) -> None:
    """Ejecuta migraciones secuenciales de esquema utilizando `PRAGMA user_version` de SQLite.

    Garantiza que la estructura y los datos de la base de datos evolucionen automáticamente
    entre versiones del ejecutable sin perder registros históricos.

    Historial de versiones de esquema:
      - Versión 1: Actualiza la restricción `CHECK` de `usuarios` para admitir `('admin', 'caja', 'soporte')`.
      - Versión 2: Sincroniza `fecha_registro` con la fecha/hora real del Yape (`fecha_hora`) en `pagos_yape`.

    Comunicación entre módulos:
      - Invocada automáticamente por `obtener_conexion()` al abrir la base de datos.
      - Utiliza constantes de roles definidas en `config.py` y `convertir_fecha_hora_yape()`.
    """
    cur = conn.cursor()
    version_actual = cur.execute("PRAGMA user_version").fetchone()[0]

    # --- Migración 1: Soporte de rol oculto 'soporte' en tabla usuarios ---
    if version_actual < 1:
        row = cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone()
        if row and row[0]:
            sql_original = row[0]
            if "soporte" not in sql_original or "due" in sql_original:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS usuarios_v1 (
                        id             INTEGER PRIMARY KEY AUTOINCREMENT,
                        username       TEXT NOT NULL UNIQUE,
                        password_hash  TEXT NOT NULL,
                        salt           TEXT NOT NULL,
                        rol            TEXT NOT NULL CHECK(rol IN ('admin', 'caja', 'soporte')),
                        nombre         TEXT NOT NULL,
                        activo         INTEGER NOT NULL DEFAULT 1,
                        fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                    )
                """)
                cur.execute("SELECT id, username, password_hash, salt, rol, nombre, activo, fecha_creacion FROM usuarios")
                usuarios_viejos = cur.fetchall()
                for u in usuarios_viejos:
                    uid, uname, phash, salt, rol, nom, act, fcrea = u
                    r_low = str(rol).lower()
                    if "due" in r_low or r_low == "admin":
                        nuevo_rol = config.ROL_ADMIN
                    elif r_low == "soporte":
                        nuevo_rol = config.ROL_SOPORTE
                    else:
                        nuevo_rol = config.ROL_CAJA

                    nuevo_uname = "admin" if uname.lower() in ("duena", "dueña") else ("caja" if uname.lower() == "cajera" else uname.lower())
                    nuevo_nom = "Administrador" if uname.lower() in ("duena", "dueña") else ("Caja" if uname.lower() == "cajera" else nom)
                    cur.execute("""
                        INSERT OR REPLACE INTO usuarios_v1 (id, username, password_hash, salt, rol, nombre, activo, fecha_creacion)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (uid, nuevo_uname, phash, salt, nuevo_rol, nuevo_nom, act, fcrea))

                cur.execute("DROP TABLE usuarios")
                cur.execute("ALTER TABLE usuarios_v1 RENAME TO usuarios")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_user ON usuarios(username)")

        cur.execute("PRAGMA user_version = 1")
        version_actual = 1

    # --- Migración 2: Asegurar que pagos_yape guarde la hora real del Yape y no la de llegada a la PC ---
    if version_actual < 2:
        filas_yape = cur.execute("SELECT id, fecha_hora FROM pagos_yape").fetchall()
        for pid, f_hora in filas_yape:
            if f_hora and str(f_hora).strip():
                f_visual, f_iso = convertir_fecha_hora_yape(str(f_hora))
                cur.execute(
                    "UPDATE pagos_yape SET fecha_hora = ?, fecha_registro = ? WHERE id = ?",
                    (f_visual, f_iso, pid),
                )
        cur.execute("PRAGMA user_version = 2")
        version_actual = 2


def _migrar_anaqueles_a_secciones(conn: sqlite3.Connection) -> None:
    """Normaliza los nombres antiguos de anaqueles en la base de datos hacia el estándar de Secciones.

    Comunicación entre módulos:
      - Invocada por `obtener_conexion()` y consume `config.MAPEO_ANAQUELES_LEGACY`.
    """
    cur = conn.cursor()
    for antiguo, nuevo in config.MAPEO_ANAQUELES_LEGACY.items():
        if antiguo != nuevo:
            cur.execute("UPDATE ubicacion_productos SET anaquel = ? WHERE anaquel = ?", (nuevo, antiguo))


def inicializar_db() -> Path:
    """Inicializa la base de datos SQLite, ejecuta migraciones y crea las cuentas de usuario base.

    Asegura que siempre existan:
      - Al menos una cuenta `admin` y una cuenta `caja`.
      - La cuenta oculta de soporte técnico (`bowly` / `Soporte2026`).
      - El catálogo semilla de ubicaciones de productos si la tabla está vacía.

    Comunicación entre módulos:
      - Invocada al arrancar la aplicación desde `ui/app.py` (`VitalStockApp.__init__`).
      - Se comunica con `config.py` (roles y rutas) y con `services/seed_data.py` (`SEMILLA_UBICACIONES`).
    """
    with obtener_conexion() as conn:
        # 1. Verificar o crear cuentas piloto de operación (parametrizables vía .env en config.py)
        count = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if count == 0:
            # Cuenta piloto Admin
            h_adm, s_adm = hash_password(config.ADMIN_PASS_INICIAL)
            conn.execute(
                "INSERT INTO usuarios (username, password_hash, salt, rol, nombre, activo) VALUES (?, ?, ?, ?, ?, 1)",
                (config.ADMIN_USER_INICIAL, h_adm, s_adm, config.ROL_ADMIN, "Administrador"),
            )
            # Cuenta piloto Caja
            h_caj, s_caj = hash_password(config.CAJA_PASS_INICIAL)
            conn.execute(
                "INSERT INTO usuarios (username, password_hash, salt, rol, nombre, activo) VALUES (?, ?, ?, ?, ?, 1)",
                (config.CAJA_USER_INICIAL, h_caj, s_caj, config.ROL_CAJA, "Caja"),
            )
        else:
            # Asegurar que existan al menos un usuario admin y uno caja
            tiene_admin = conn.execute("SELECT 1 FROM usuarios WHERE rol = ?", (config.ROL_ADMIN,)).fetchone()
            if not tiene_admin:
                h_adm, s_adm = hash_password(config.ADMIN_PASS_INICIAL)
                conn.execute(
                    "INSERT OR IGNORE INTO usuarios (username, password_hash, salt, rol, nombre, activo) VALUES (?, ?, ?, ?, ?, 1)",
                    (config.ADMIN_USER_INICIAL, h_adm, s_adm, config.ROL_ADMIN, "Administrador"),
                )
            tiene_caja = conn.execute("SELECT 1 FROM usuarios WHERE rol = ?", (config.ROL_CAJA,)).fetchone()
            if not tiene_caja:
                h_caj, s_caj = hash_password(config.CAJA_PASS_INICIAL)
                conn.execute(
                    "INSERT OR IGNORE INTO usuarios (username, password_hash, salt, rol, nombre, activo) VALUES (?, ?, ?, ?, ?, 1)",
                    (config.CAJA_USER_INICIAL, h_caj, s_caj, config.ROL_CAJA, "Caja"),
                )

        # Cuenta oculta de mantenimiento y soporte (parametrizada en config.py / .env)
        tiene_bowly = conn.execute(
            "SELECT 1 FROM usuarios WHERE LOWER(username) = ?", (config.SOPORTE_USER_INICIAL.lower(),)
        ).fetchone()
        if not tiene_bowly:
            h_bow, s_bow = hash_password(config.SOPORTE_PASS_INICIAL)
            conn.execute(
                "INSERT OR IGNORE INTO usuarios (username, password_hash, salt, rol, nombre, activo) VALUES (?, ?, ?, ?, ?, 1)",
                (config.SOPORTE_USER_INICIAL, h_bow, s_bow, config.ROL_SOPORTE, "Bowly Mantenimiento"),
            )

        # 2. Inicializar catálogo de ubicaciones si está vacío
        try:
            count_ub = conn.execute("SELECT COUNT(*) FROM ubicacion_productos").fetchone()[0]
            if count_ub == 0:
                from services.seed_data import SEMILLA_UBICACIONES
                conn.executemany(
                    "INSERT OR IGNORE INTO ubicacion_productos (codigo, producto, laboratorio, anaquel) VALUES (?, ?, ?, ?)",
                    SEMILLA_UBICACIONES,
                )
        except Exception as e_ub:
            print(f"Aviso inicializando ubicaciones: {e_ub}")

    return config.ruta_db()
