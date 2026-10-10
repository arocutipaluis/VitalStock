"""
===============================================================================
MÓDULO: ui/dialogs/users_dialog.py
DESCRIPCIÓN:
    Ventana de gestión de usuarios, roles y credenciales del sistema (Solo Admin/Soporte).
    Aplica las reglas de negocio de seguridad:
    - Oculta la cuenta de mantenimiento (`bowly`) para usuarios que no sean Soporte.
    - Impide que un Administrador modifique la contraseña, desactive o elimine la
      cuenta de otro Administrador distinto a sí mismo.

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Importa de `config.py`: Roles (`ROL_ADMIN`, `ROL_CAJA`, `ROL_SOPORTE`), colores y fuentes.
    - Importa de `services/auth_service.py`: Funciones CRUD de usuarios (`listar_usuarios`,
      `crear_usuario`, `cambiar_password`, `alternar_estado_usuario`, `eliminar_usuario`).
    - Importa de `ui/widgets.py`: `crear_treeview` para la tabla de usuarios.
    - Es instanciado desde: `ui/views/menu_view.py` (`PantallaMenu._abrir_gestion_usuarios`).
===============================================================================
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import config
from services import auth_service
from ui.widgets import crear_treeview


class VentanaGestionUsuarios(tk.Toplevel):
    """
    Ventana modal de administración de personal y control de roles.

    Se comunica con:
        - `services/auth_service.py`: Ejecuta todas las operaciones de persistencia de usuarios.
        - `ui/app.py`: Consulta `self.app.usuario_actual` y `self.app.es_soporte()` para aplicar
          restricciones de jerarquía entre administradores.
    """

    def __init__(self, maestro: tk.Tk | tk.Toplevel, app) -> None:
        """
        Inicializa la interfaz gráfica de gestión de usuarios.

        Se comunica con:
            - `ui/widgets.py`: Crea la tabla `Treeview` con `crear_treeview`.
            - `cargar_usuarios()`: Pobla la tabla al abrir la ventana.
        """
        super().__init__(maestro)
        self.app = app
        self.title(f"{config.APP_NOMBRE} · Gestión de Usuarios y Accesos")
        self.geometry("740x480")
        self.minsize(680, 420)
        self.configure(bg=config.COLOR_FONDO)
        self.transient(maestro)

        ancho, alto = 740, 480
        x = max(10, maestro.winfo_x() + (maestro.winfo_width() - ancho) // 2)
        y = max(10, maestro.winfo_y() + (maestro.winfo_height() - alto) // 2)
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

        barra = tk.Frame(self, bg=config.COLOR_PRIMARIO, height=52)
        barra.pack(fill="x")
        barra.pack_propagate(False)
        tk.Label(
            barra,
            text="👥  Gestión de Personal y Roles",
            font=(config.FUENTE, 12, "bold"),
            fg="white",
            bg=config.COLOR_PRIMARIO,
        ).pack(side="left", padx=16)
        tk.Label(
            barra,
            text="Control de accesos y credenciales protegidas",
            font=(config.FUENTE, 9),
            fg="#cfe5de",
            bg=config.COLOR_PRIMARIO,
        ).pack(side="left")

        cuerpo = tk.Frame(self, bg=config.COLOR_FONDO, padx=16, pady=12)
        cuerpo.pack(fill="both", expand=True)

        barra_acc = tk.Frame(cuerpo, bg=config.COLOR_FONDO)
        barra_acc.pack(fill="x", pady=(0, 8))

        ttk.Button(barra_acc, text="➕ Nuevo Usuario", style="Primario.TButton", command=self._nuevo_usuario).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(
            barra_acc, text="🔑 Cambiar Contraseña", style="Secundario.TButton", command=self._cambiar_password
        ).pack(side="left", padx=6)
        ttk.Button(
            barra_acc, text="🔄 Activar / Desactivar", style="Secundario.TButton", command=self._alternar_estado
        ).pack(side="left", padx=6)
        ttk.Button(barra_acc, text="🗑️ Eliminar Usuario", style="Peligro.TButton", command=self._eliminar_usuario).pack(
            side="left", padx=6
        )

        columnas = [
            ("id", "ID", 40, "center"),
            ("username", "Usuario", 110, "w"),
            ("nombre", "Nombre Completo", 200, "w"),
            ("rol", "Rol de Acceso", 110, "center"),
            ("activo", "Estado", 90, "center"),
            ("fecha", "Fecha Registro", 130, "center"),
        ]
        self.tree = crear_treeview(cuerpo, columnas)
        self.tree.tag_configure("inactivo", foreground="#888888")

        self.cargar_usuarios()

    def cargar_usuarios(self) -> None:
        """
        Consulta los usuarios registrados y los muestra en la tabla.
        Oculta la cuenta de soporte (`bowly`) si el usuario actual no tiene rol Soporte.

        Se comunica con:
            - `ui/app.py`: Consulta `self.app.es_soporte()`.
            - `services/auth_service.py`: Llama a `listar_usuarios(incluir_soporte=...)`.
        """
        self.tree.delete(*self.tree.get_children())
        es_soporte = hasattr(self.app, "es_soporte") and self.app.es_soporte()
        usuarios = auth_service.listar_usuarios(incluir_soporte=es_soporte)
        for u in usuarios:
            u_id = u["id"]
            u_name = u["username"]
            nom = u["nombre"]
            rol_txt = config.NOMBRES_ROLES.get(u["rol"], u["rol"].capitalize())
            est = "Activo" if u["activo"] else "Inactivo"
            fec = u["fecha_creacion"]
            tag = "activo" if u["activo"] else "inactivo"
            self.tree.insert("", "end", iid=str(u_id), tags=(tag,), values=(u_id, u_name, nom, rol_txt, est, fec))

    def _obtener_seleccionado(self) -> int | None:
        """
        Retorna el ID numérico del usuario seleccionado en el Treeview o `None`.
        """
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning(config.APP_NOMBRE, "Seleccione un usuario de la lista.", parent=self)
            return None
        return int(sel[0])

    def _nuevo_usuario(self) -> None:
        """
        Abre un sub-diálogo modal para registrar un nuevo usuario (Caja o Admin).

        Se comunica con:
            - `services/auth_service.py`: Llama a `crear_usuario(...)`.
        """
        dlg = tk.Toplevel(self)
        dlg.title("Nuevo Usuario")
        dlg.geometry("340x350")
        dlg.resizable(False, False)
        dlg.configure(bg=config.COLOR_FONDO)
        dlg.transient(self)
        dlg.grab_set()

        f = tk.Frame(dlg, bg=config.COLOR_TARJETA, padx=16, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(
            f, text="Crear Personal", font=(config.FUENTE, 11, "bold"), fg=config.COLOR_PRIMARIO, bg=config.COLOR_TARJETA
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(f, text="Usuario (login):", font=(config.FUENTE, 9), bg=config.COLOR_TARJETA).pack(anchor="w")
        ent_u = ttk.Entry(f)
        ent_u.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Nombre completo:", font=(config.FUENTE, 9), bg=config.COLOR_TARJETA).pack(anchor="w")
        ent_n = ttk.Entry(f)
        ent_n.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Rol:", font=(config.FUENTE, 9), bg=config.COLOR_TARJETA).pack(anchor="w")
        cb_rol = ttk.Combobox(f, values=[config.ROL_CAJA, config.ROL_ADMIN], state="readonly")
        cb_rol.set(config.ROL_CAJA)
        cb_rol.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Contraseña:", font=(config.FUENTE, 9), bg=config.COLOR_TARJETA).pack(anchor="w")
        ent_p = ttk.Entry(f, show="•")
        ent_p.pack(fill="x", pady=(2, 14))

        def _guardar():
            u = ent_u.get().strip()
            n = ent_n.get().strip()
            r = cb_rol.get()
            p = ent_p.get()
            try:
                auth_service.crear_usuario(username=u, password=p, rol=r, nombre=n)
                messagebox.showinfo(config.APP_NOMBRE, f"Usuario '{u}' creado con éxito.", parent=dlg)
                dlg.destroy()
                self.cargar_usuarios()
            except ValueError as ex:
                messagebox.showerror(config.APP_NOMBRE, str(ex), parent=dlg)

        ttk.Button(f, text="Guardar Usuario", style="Primario.TButton", command=_guardar).pack(fill="x")

    def _cambiar_password(self) -> None:
        """
        Abre un sub-diálogo para cambiar la contraseña del usuario seleccionado.
        Valida que un Administrador no pueda cambiar la contraseña de otro Administrador.

        Se comunica con:
            - `services/auth_service.py`: Consulta el rol objetivo y llama a `cambiar_password(...)`.
        """
        user_id = self._obtener_seleccionado()
        if not user_id:
            return
        vals = self.tree.item(str(user_id), "values")
        username = vals[1]

        usuario_actual = getattr(self.app, "usuario_actual", {}) or {}
        mi_rol = usuario_actual.get("rol", "")
        mi_username = usuario_actual.get("username", "").lower()

        # REGLA: Un Administrador no puede cambiar la contraseña de otro Administrador
        if mi_rol != config.ROL_SOPORTE and username.lower() != mi_username:
            with auth_service.obtener_conexion() as conn:
                row = conn.execute("SELECT rol FROM usuarios WHERE LOWER(username) = ?", (username.lower(),)).fetchone()
                if row and row[0] == config.ROL_ADMIN:
                    messagebox.showwarning(
                        config.APP_NOMBRE,
                        f"Por seguridad, un Administrador no puede cambiar la contraseña de otro Administrador.\n\n"
                        f"El usuario '{username}' debe ingresar a su propia cuenta para modificar su contraseña, "
                        f"o solicitarlo a Soporte Técnico.",
                        parent=self,
                    )
                    return

        dlg = tk.Toplevel(self)
        dlg.title(f"Cambiar Contraseña: {username}")
        dlg.geometry("320x200")
        dlg.resizable(False, False)
        dlg.configure(bg=config.COLOR_FONDO)
        dlg.transient(self)
        dlg.grab_set()

        f = tk.Frame(dlg, bg=config.COLOR_TARJETA, padx=16, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(
            f, text=f"Nueva contraseña para '{username}':", font=(config.FUENTE, 9, "bold"), bg=config.COLOR_TARJETA
        ).pack(anchor="w", pady=(0, 6))
        ent_p = ttk.Entry(f, show="•")
        ent_p.pack(fill="x", pady=(0, 14))

        def _guardar_pass():
            p = ent_p.get()
            try:
                auth_service.cambiar_password(username, p)
                messagebox.showinfo(config.APP_NOMBRE, f"Contraseña actualizada para '{username}'.", parent=dlg)
                dlg.destroy()
            except ValueError as ex:
                messagebox.showerror(config.APP_NOMBRE, str(ex), parent=dlg)

        ttk.Button(f, text="Actualizar Contraseña", style="Primario.TButton", command=_guardar_pass).pack(fill="x")

    def _alternar_estado(self) -> None:
        """
        Activa o desactiva la cuenta seleccionada, respetando la protección entre Administradores.

        Se comunica con:
            - `services/auth_service.py`: Llama a `alternar_estado_usuario(user_id)`.
        """
        user_id = self._obtener_seleccionado()
        if not user_id:
            return
        vals = self.tree.item(str(user_id), "values")
        username = vals[1]

        usuario_actual = getattr(self.app, "usuario_actual", {}) or {}
        mi_rol = usuario_actual.get("rol", "")
        mi_username = usuario_actual.get("username", "").lower()

        if mi_rol != config.ROL_SOPORTE and username.lower() != mi_username:
            with auth_service.obtener_conexion() as conn:
                row = conn.execute("SELECT rol FROM usuarios WHERE LOWER(username) = ?", (username.lower(),)).fetchone()
                if row and row[0] == config.ROL_ADMIN:
                    messagebox.showwarning(
                        config.APP_NOMBRE,
                        "No tiene permisos para desactivar la cuenta de otro Administrador.",
                        parent=self,
                    )
                    return

        try:
            auth_service.alternar_estado_usuario(user_id)
            self.cargar_usuarios()
        except ValueError as ex:
            messagebox.showerror(config.APP_NOMBRE, str(ex), parent=self)

    def _eliminar_usuario(self) -> None:
        """
        Elimina permanentemente la cuenta seleccionada tras confirmación,
        respetando la protección entre Administradores y el usuario Soporte.

        Se comunica con:
            - `services/auth_service.py`: Llama a `eliminar_usuario(user_id)`.
        """
        user_id = self._obtener_seleccionado()
        if not user_id:
            return
        vals = self.tree.item(str(user_id), "values")
        username = vals[1]

        usuario_actual = getattr(self.app, "usuario_actual", {}) or {}
        mi_rol = usuario_actual.get("rol", "")
        mi_username = usuario_actual.get("username", "").lower()

        if mi_rol != config.ROL_SOPORTE and username.lower() != mi_username:
            with auth_service.obtener_conexion() as conn:
                row = conn.execute("SELECT rol FROM usuarios WHERE LOWER(username) = ?", (username.lower(),)).fetchone()
                if row and row[0] == config.ROL_ADMIN:
                    messagebox.showwarning(
                        config.APP_NOMBRE,
                        "No tiene permisos para eliminar la cuenta de otro Administrador.",
                        parent=self,
                    )
                    return

        if not messagebox.askyesno(
            config.APP_NOMBRE, f"¿Está seguro de eliminar al usuario '{username}'?", parent=self
        ):
            return
        try:
            auth_service.eliminar_usuario(user_id)
            self.cargar_usuarios()
        except ValueError as ex:
            messagebox.showerror(config.APP_NOMBRE, str(ex), parent=self)
