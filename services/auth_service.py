"""
services/auth_service.py - Servicio de autenticación criptográfica, control de roles y gestión de personal.

Implementa la validación de credenciales en tiempo constante (`PBKDF2-HMAC-SHA256`),
la administración de cuentas de usuario y las reglas de protección del rol oculto `soporte`.

Comunicación con otros archivos del proyecto:
  - Importa `config.py` para validar roles (`ROLES_PERMITIDOS`, `ROL_ADMIN`, `ROL_SOPORTE`).
  - Importa `database.py` (`hash_password` y `obtener_conexion`) para operar sobre la tabla `usuarios`.
  - Es consumido por `ui/dialogs/login_dialog.py` (inicio de sesión), `ui/dialogs/users_dialog.py`
    (gestión de personal), `ui/app.py` (autorización de cierre del sistema) y reexportado en `motor.py`.
"""

from __future__ import annotations

import secrets
import sqlite3

import config
from database import hash_password, obtener_conexion


def _verificar_password(password: str, password_hash: str, salt: str) -> bool:
    """Verifica una contraseña en texto plano contra su hash y salt en tiempo constante.

    Comunicación entre módulos:
      - Invoca `hash_password()` de `database.py` y es usada internamente por `autenticar_usuario()`.
    """
    hashed, _ = hash_password(password, salt)
    return secrets.compare_digest(hashed, password_hash)


def autenticar_usuario(username: str, password: str) -> dict | None:
    """Valida las credenciales ingresadas contra la tabla `usuarios` de SQLite.

    Retorna un diccionario con los datos del usuario si las credenciales son válidas, o `None`.
    Lanza `ValueError` si el usuario existe pero su cuenta fue desactivada.

    Comunicación entre módulos:
      - Consulta SQLite mediante `database.obtener_conexion()`.
      - Invocada por `ui/dialogs/login_dialog.py` (`VentanaLogin._intentar_login`)
        y por `ui/app.py` (`VitalStockApp.solicitar_cierre_seguro`).
    """
    u = username.strip().lower()
    with obtener_conexion() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, salt, rol, nombre, activo FROM usuarios WHERE LOWER(username) = ?",
            (u,),
        ).fetchone()

    if not row:
        return None

    user_id, uname, p_hash, salt, rol, nombre, activo = row
    if not activo:
        raise ValueError(f"El usuario '{uname}' se encuentra inactivo. Contacte al administrador.")

    if _verificar_password(password, p_hash, salt):
        return {
            "id": user_id,
            "username": uname,
            "rol": rol,
            "nombre": nombre,
            "activo": bool(activo),
        }
    return None


def crear_usuario(username: str, password: str, rol: str, nombre: str) -> int:
    """Crea un nuevo usuario con contraseña cifrada (`PBKDF2-HMAC-SHA256`) en la base de datos.

    Comunicación entre módulos:
      - Valida el rol contra `config.ROLES_PERMITIDOS` (`config.py`).
      - Utiliza `hash_password()` y `obtener_conexion()` de `database.py`.
      - Invocada desde `ui/dialogs/users_dialog.py` (`VentanaGestionUsuarios._nuevo_usuario`).
    """
    u = username.strip().lower()
    if not u or len(u) < 3:
        raise ValueError("El nombre de usuario debe tener al menos 3 caracteres.")
    if not password or len(password) < 4:
        raise ValueError("La contraseña debe tener al menos 4 caracteres.")
    if rol not in config.ROLES_PERMITIDOS:
        raise ValueError(f"Rol no válido: '{rol}'. Roles permitidos: {', '.join(config.ROLES_PERMITIDOS)}.")
    nom = nombre.strip() or u.capitalize()

    p_hash, salt = hash_password(password)
    try:
        with obtener_conexion() as conn:
            cur = conn.execute(
                "INSERT INTO usuarios (username, password_hash, salt, rol, nombre, activo) VALUES (?, ?, ?, ?, ?, 1)",
                (u, p_hash, salt, rol, nom),
            )
            return cur.lastrowid or 0
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"El usuario '{u}' ya existe.") from exc


def cambiar_password(username: str, nuevo_password: str) -> bool:
    """Actualiza el hash y salt de la contraseña de un usuario existente.

    Comunicación entre módulos:
      - Utiliza `hash_password()` y `obtener_conexion()` de `database.py`.
      - Invocada desde `ui/dialogs/users_dialog.py` (`VentanaGestionUsuarios._cambiar_password`).
    """
    if not nuevo_password or len(nuevo_password) < 4:
        raise ValueError("La nueva contraseña debe tener al menos 4 caracteres.")
    u = username.strip().lower()
    p_hash, salt = hash_password(nuevo_password)
    with obtener_conexion() as conn:
        cur = conn.execute(
            "UPDATE usuarios SET password_hash = ?, salt = ? WHERE LOWER(username) = ?",
            (p_hash, salt, u),
        )
        return cur.rowcount > 0


def listar_usuarios(incluir_soporte: bool = False) -> list[dict]:
    """Lista los usuarios registrados en el sistema (sin exponer hashes ni salts).

    Por seguridad, oculta la cuenta de mantenimiento (`bowly` / rol `soporte`) a menos
    que quien realice la consulta tenga sesión iniciada como soporte técnico.

    Comunicación entre módulos:
      - Consulta SQLite mediante `database.obtener_conexion()` y usa `config.ROL_SOPORTE`.
      - Invocada por `ui/dialogs/users_dialog.py` (`VentanaGestionUsuarios.cargar_usuarios`).
    """
    with obtener_conexion() as conn:
        if incluir_soporte:
            cur = conn.execute(
                "SELECT id, username, rol, nombre, activo, fecha_creacion FROM usuarios ORDER BY id ASC"
            )
        else:
            cur = conn.execute(
                "SELECT id, username, rol, nombre, activo, fecha_creacion FROM usuarios "
                "WHERE rol != ? AND LOWER(username) != 'bowly' ORDER BY id ASC",
                (config.ROL_SOPORTE,),
            )
        return [
            {
                "id": r[0],
                "username": r[1],
                "rol": r[2],
                "nombre": r[3],
                "activo": bool(r[4]),
                "fecha_creacion": r[5],
            }
            for r in cur.fetchall()
        ]


def eliminar_usuario(id_usuario: int) -> bool:
    """Elimina un usuario por su ID, impidiendo borrar al último Administrador o a Soporte.

    Comunicación entre módulos:
      - Opera sobre SQLite mediante `database.obtener_conexion()` y lee `config.py`.
      - Invocada por `ui/dialogs/users_dialog.py` (`VentanaGestionUsuarios._eliminar_usuario`).
    """
    with obtener_conexion() as conn:
        usuario = conn.execute("SELECT username, rol FROM usuarios WHERE id = ?", (id_usuario,)).fetchone()
        if not usuario:
            return False
        uname, rol = usuario
        if rol == config.ROL_SOPORTE or str(uname).lower() == "bowly":
            raise ValueError("No se puede eliminar la cuenta de mantenimiento del sistema.")
        if rol == config.ROL_ADMIN:
            admins = conn.execute(
                "SELECT COUNT(*) FROM usuarios WHERE rol = ? AND activo = 1", (config.ROL_ADMIN,)
            ).fetchone()[0]
            if admins <= 1:
                raise ValueError("No se puede eliminar la única cuenta de Administrador activa.")
        cur = conn.execute("DELETE FROM usuarios WHERE id = ?", (id_usuario,))
        return cur.rowcount > 0


def alternar_estado_usuario(id_usuario: int) -> bool:
    """Activa o desactiva un usuario, protegiendo al último Administrador activo y a Soporte.

    Comunicación entre módulos:
      - Opera sobre SQLite mediante `database.obtener_conexion()` y lee `config.py`.
      - Invocada por `ui/dialogs/users_dialog.py` (`VentanaGestionUsuarios._alternar_estado`).
    """
    with obtener_conexion() as conn:
        usuario = conn.execute("SELECT username, rol, activo FROM usuarios WHERE id = ?", (id_usuario,)).fetchone()
        if not usuario:
            return False
        uname, rol, activo = usuario
        if rol == config.ROL_SOPORTE or str(uname).lower() == "bowly":
            raise ValueError("No se puede alterar el estado de la cuenta de mantenimiento.")
        nuevo_estado = 0 if activo else 1
        if rol == config.ROL_ADMIN and nuevo_estado == 0:
            admins = conn.execute(
                "SELECT COUNT(*) FROM usuarios WHERE rol = ? AND activo = 1", (config.ROL_ADMIN,)
            ).fetchone()[0]
            if admins <= 1:
                raise ValueError("No se puede desactivar la única cuenta de Administrador activa.")
        conn.execute("UPDATE usuarios SET activo = ? WHERE id = ?", (nuevo_estado, id_usuario))
        return True
