"""
===============================================================================
MÓDULO: ui/dialogs/login_dialog.py
DESCRIPCIÓN:
    Ventana modal de inicio de sesión para el personal de la botica.
    Solicita usuario y contraseña, valida las credenciales contra la base de datos
    y ejecuta los callbacks de éxito o cancelación.

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Importa de `config.py`: Colores institucionales, fuentes y nombre de la app.
    - Importa de `services/auth_service.py`: `autenticar_usuario` para verificar credenciales.
    - Es instanciado desde: `ui/app.py` (`VitalStockApp.solicitar_login`).
===============================================================================
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import config
from services import auth_service


class VentanaLogin(tk.Toplevel):
    """
    Modal de inicio de sesión para el personal de la botica (Admin / Caja / Soporte).

    Se comunica con:
        - `ui/app.py`: Recibe los callbacks `al_exito` y `al_cancelar` para notificar
          a `VitalStockApp` el resultado de la autenticación.
        - `services/auth_service.py`: Invoca `autenticar_usuario(user, pwd)`.
    """

    def __init__(self, maestro: tk.Tk, al_exito, al_cancelar=None) -> None:
        """
        Construye y centra el formulario modal de inicio de sesión.

        Se comunica con:
            - `config.py`: Aplica estilos y paleta visual.
            - `ui/app.py`: Se asocia como ventana hija (`transient`) de `root`.
        """
        super().__init__(maestro)
        self.maestro = maestro
        self.al_exito = al_exito
        self.al_cancelar = al_cancelar
        self.title(f"{config.APP_NOMBRE} · Iniciar Sesión")
        self.geometry("380x350")
        self.resizable(False, False)
        self.configure(bg=config.COLOR_FONDO)
        self.transient(maestro)
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

        # Centrar ventana respecto al maestro (o pantalla si está recién restaurado)
        self.update_idletasks()
        ancho = 380
        alto = 350
        x = max(10, maestro.winfo_x() + (maestro.winfo_width() - ancho) // 2)
        y = max(10, maestro.winfo_y() + (maestro.winfo_height() - alto) // 2)
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

        # Cabecera institucional
        barra = tk.Frame(self, bg=config.COLOR_PRIMARIO, height=64)
        barra.pack(fill="x")
        barra.pack_propagate(False)

        tk.Label(
            barra,
            text=f"💊  {config.APP_NOMBRE}",
            font=(config.FUENTE, 15, "bold"),
            fg="white",
            bg=config.COLOR_PRIMARIO,
        ).pack(anchor="w", padx=18, pady=(8, 0))
        tk.Label(
            barra,
            text="Sistema de Gestión y Control de Botica",
            font=(config.FUENTE, 9),
            fg="#cfe5de",
            bg=config.COLOR_PRIMARIO,
        ).pack(anchor="w", padx=18)

        # Formulario de credenciales
        cuerpo = tk.Frame(
            self,
            bg=config.COLOR_TARJETA,
            padx=24,
            pady=20,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDE,
        )
        cuerpo.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(
            cuerpo,
            text="Ingreso de Personal",
            font=(config.FUENTE, 12, "bold"),
            fg=config.COLOR_TEXTO,
            bg=config.COLOR_TARJETA,
        ).pack(anchor="w", pady=(0, 14))

        tk.Label(
            cuerpo, text="Usuario:", font=(config.FUENTE, 9, "bold"), fg=config.COLOR_TEXTO, bg=config.COLOR_TARJETA
        ).pack(anchor="w")
        self.ent_usuario = ttk.Entry(cuerpo, font=(config.FUENTE, 10))
        self.ent_usuario.pack(fill="x", pady=(3, 12))

        tk.Label(
            cuerpo, text="Contraseña:", font=(config.FUENTE, 9, "bold"), fg=config.COLOR_TEXTO, bg=config.COLOR_TARJETA
        ).pack(anchor="w")
        self.ent_clave = ttk.Entry(cuerpo, font=(config.FUENTE, 10), show="•")
        self.ent_clave.pack(fill="x", pady=(3, 18))

        self.btn_ingresar = ttk.Button(
            cuerpo, text="Ingresar al Sistema", style="Primario.TButton", command=self._autenticar
        )
        self.btn_ingresar.pack(fill="x", pady=(2, 0))

        self.ent_usuario.bind("<Return>", lambda _e: self.ent_clave.focus_set())
        self.ent_clave.bind("<Return>", lambda _e: self._autenticar())

        self.ent_usuario.focus_set()
        self.grab_set()

    def _autenticar(self) -> None:
        """
        Verifica las credenciales ingresadas contra la base de datos.

        Se comunica con:
            - `services/auth_service.py`: Llama a `autenticar_usuario(user, pwd)`.
            - `ui/app.py`: Si las credenciales son válidas, invoca `self.al_exito(datos_u)`.
        """
        user = self.ent_usuario.get().strip()
        pwd = self.ent_clave.get()
        if not user or not pwd:
            messagebox.showwarning(config.APP_NOMBRE, "Ingrese su usuario y contraseña.", parent=self)
            return

        try:
            datos_u = auth_service.autenticar_usuario(user, pwd)
            if not datos_u:
                messagebox.showerror(config.APP_NOMBRE, "Usuario o contraseña incorrectos.", parent=self)
                self.ent_clave.delete(0, tk.END)
                self.ent_clave.focus_set()
                return
            self.grab_release()
            self.destroy()
            self.al_exito(datos_u)
        except ValueError as exc:
            messagebox.showwarning(config.APP_NOMBRE, str(exc), parent=self)

    def _al_cerrar(self) -> None:
        """
        Maneja el cierre de la ventana de login con el botón 'X'.

        Se comunica con:
            - `ui/app.py`: Ejecuta `self.al_cancelar()` para ocultar nuevamente
              la aplicación en la bandeja del sistema si no hay sesión activa.
        """
        if self.al_cancelar:
            self.al_cancelar()
        else:
            self.grab_release()
            self.destroy()
            self.maestro.destroy()
