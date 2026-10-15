"""
ui/app.py - Controlador principal de la interfaz gráfica y ciclo de vida de VitalStock.

Este módulo coordina la ventana raíz de Tkinter, la navegación entre pantallas,
el servicio receptor de pagos Yape en segundo plano, las notificaciones flotantes
apiladas y la integración con la bandeja del sistema (System Tray).

Comunicación con otros archivos del proyecto:
  - Instanciado por `main.py` al iniciar la aplicación.
  - Importa `config.py` (colores, fuentes, roles y rutas) y `database.py` (`inicializar_db`).
  - Importa `services/yape_service.py` (`ServicioNotificacionesYape`) y `services/auth_service.py`.
  - Importa `ui/styles.py`, `ui/toasts.py`, `ui/tray_manager.py` y `ui/widgets.py`.
  - Administra las vistas `ui/views/menu_view.py`, `ui/views/pedido_view.py`, `ui/views/inventario_view.py`
    y los diálogos `ui/dialogs/login_dialog.py` y `ui/dialogs/yape_history_dialog.py`.
"""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import config
import database
from services import auth_service
from services.yape_service import ServicioNotificacionesYape
from ui.dialogs.login_dialog import VentanaLogin
from ui.dialogs.yape_history_dialog import VentanaHistorialYape
from ui.styles import configurar_estilos
from ui.toasts import NotificacionToastYape, emitir_alerta_sonido_pago
from ui.tray_manager import GestorBandejaSistema
from ui.views.inventario_view import PantallaInventario
from ui.views.menu_view import PantallaMenu
from ui.views.pedido_view import PantallaPedido
from ui.widgets import DND_DISPONIBLE, TkinterDnD


class VitalStockApp:
    """Controlador central de la aplicación de escritorio VitalStock.

    Gestiona el estado de la sesión actual, el intercambio de vistas, la cola de eventos
    del servidor HTTP de Yape y la permanencia en segundo plano en la bandeja de Windows.
    """

    PANTALLAS = (PantallaMenu, PantallaPedido, PantallaInventario)

    def __init__(self, iniciar_minimizada: bool = True) -> None:
        """Inicializa la aplicación, la base de datos, el receptor Yape y el icono de bandeja.

        Por defecto (`iniciar_minimizada=True`), oculta la ventana principal de inmediato para
        arrancar silenciosamente en la bandeja del sistema sin interrumpir el inicio de Windows.

        Comunicación entre módulos:
          - Llamado desde `main.py`.
          - Invoca `database.inicializar_db()` (`database.py`).
          - Inicia `ServicioNotificacionesYape` (`services/yape_service.py`).
          - Inicia `GestorBandejaSistema` (`ui/tray_manager.py`).
          - Construye las vistas definidas en `ui/views/*`.
        """
        self.iniciar_minimizada = iniciar_minimizada
        self.root = TkinterDnD.Tk() if DND_DISPONIBLE else tk.Tk()

        # Si arranca en segundo plano, ocultar de inmediato antes de dibujar para evitar parpadeos
        if self.iniciar_minimizada:
            self.root.withdraw()

        self.root.title(f"{config.APP_NOMBRE} · Botica")
        self.root.geometry("1220x740")
        self.root.minsize(1000, 620)
        self.root.configure(bg=config.COLOR_FONDO)
        self.root.report_callback_exception = self._error_no_controlado
        self.root.protocol("WM_DELETE_WINDOW", self.ocultar_a_bandeja)

        configurar_estilos(self.root)
        self._configurar_icono()

        # 1. Inicializar base de datos y migraciones automáticas en %APPDATA%
        try:
            database.inicializar_db()
        except Exception as exc:
            messagebox.showerror(config.APP_NOMBRE, f"No se pudo inicializar la base de datos:\n\n{exc}")

        self.usuario_actual: dict | None = None
        self.ventana_login: VentanaLogin | None = None
        self.ventana_historial_yape: VentanaHistorialYape | None = None

        # 2. Receptor Yape en segundo plano:
        # Se activa de inmediato e independientemente del inicio de sesión
        # para asegurar que NUNCA se pierda ningún pago mientras la PC esté encendida.
        self.servicio_yape = ServicioNotificacionesYape()
        self.servicio_yape.iniciar()

        # 3. Contenedor de pantallas principales
        contenedor = tk.Frame(self.root, bg=config.COLOR_FONDO)
        contenedor.pack(fill="both", expand=True)
        contenedor.rowconfigure(0, weight=1)
        contenedor.columnconfigure(0, weight=1)

        self.pantallas: dict[str, tk.Frame] = {}
        for clase in self.PANTALLAS:
            pantalla = clase(contenedor, self)
            pantalla.grid(row=0, column=0, sticky="nsew")
            self.pantallas[clase.__name__] = pantalla

        self.mostrar("PantallaMenu")

        # 4. Iniciar bucle de escucha de eventos Yape y señales de apertura
        self.root.after(100, self._auto_iniciar_receptor_yape)
        self.root.after(250, self._procesar_eventos_yape)

        # 5. Bandeja del sistema (System Tray) para operación continua en segundo plano
        self.bandeja = GestorBandejaSistema(self)
        self.bandeja.iniciar()

        if not self.iniciar_minimizada:
            self.root.after(150, self.solicitar_login)

    def es_admin(self) -> bool:
        """Indica si el usuario en sesión posee privilegios administrativos (`admin` o `soporte`).

        Comunicación entre módulos:
          - Consultada por `ui/views/menu_view.py`, `ui/views/pedido_view.py` y `ui/views/inventario_view.py`
            para habilitar o restringir acciones protegidas.
        """
        if not self.usuario_actual:
            return False
        return self.usuario_actual.get("rol") in (config.ROL_ADMIN, config.ROL_SOPORTE)

    def es_soporte(self) -> bool:
        """Indica si el usuario actual tiene el rol oculto de mantenimiento técnico (`soporte`).

        Comunicación entre módulos:
          - Consultada por `ui/dialogs/users_dialog.py` (para mostrar cuentas ocultas y permitir
            cambio de claves a cualquier admin) y por `ui/dialogs/yape_history_dialog.py`
            (para habilitar la eliminación de transacciones Yape de prueba).
        """
        if not self.usuario_actual:
            return False
        return self.usuario_actual.get("rol") == config.ROL_SOPORTE

    def solicitar_login(self) -> None:
        """Abre el diálogo modal de inicio de sesión o le da foco si ya se encuentra abierto.

        Comunicación entre módulos:
          - Instancia `VentanaLogin` desde `ui/dialogs/login_dialog.py`.
          - Invocada por `mostrar_desde_bandeja()` y por `ui/views/menu_view.py` al cambiar de usuario.
        """
        if self.ventana_login is not None and self.ventana_login.winfo_exists():
            try:
                self.ventana_login.deiconify()
                self.ventana_login.lift()
                self.ventana_login.focus_force()
            except Exception:
                pass
            return

        self.ventana_login = VentanaLogin(
            self.root,
            al_exito=self.al_iniciar_sesion,
            al_cancelar=self._al_cancelar_login,
        )

    def _al_cancelar_login(self) -> None:
        """Manejador ejecutado cuando se cierra el diálogo de login sin haber iniciado sesión.

        Si no hay sesión activa, oculta la ventana nuevamente en la bandeja del sistema
        para que el receptor de pagos Yape siga funcionando en segundo plano.

        Comunicación entre módulos:
          - Pasado como callback `al_cancelar` hacia `VentanaLogin` (`ui/dialogs/login_dialog.py`).
        """
        self.ventana_login = None
        if self.usuario_actual is None:
            self.ocultar_a_bandeja()

    def al_iniciar_sesion(self, usuario: dict) -> None:
        """Recibe los datos del usuario autenticado y actualiza todas las vistas de la aplicación.

        Comunicación entre módulos:
          - Invocado como callback `al_exito` desde `VentanaLogin` (`ui/dialogs/login_dialog.py`).
          - Llama a `refrescar_usuario()` en las vistas de `ui/views/*`.
        """
        self.ventana_login = None
        self.usuario_actual = usuario
        for p in self.pantallas.values():
            if hasattr(p, "refrescar_usuario"):
                p.refrescar_usuario()
        self.mostrar("PantallaMenu")

    def _auto_iniciar_receptor_yape(self) -> None:
        """Garantiza que el servidor HTTP de Yape esté activo y actualiza el indicador del menú.

        Comunicación entre módulos:
          - Se comunica con `self.servicio_yape` (`services/yape_service.py`) y `PantallaMenu` (`ui/views/menu_view.py`).
        """
        try:
            self.servicio_yape.iniciar()
            menu = self.pantallas.get("PantallaMenu")
            if isinstance(menu, PantallaMenu):
                menu.actualizar_estado_yape()
        except Exception as exc:
            print(f"Error iniciando receptor Yape: {exc}")

    def mostrar(self, nombre: str) -> None:
        """Eleva al frente la pantalla solicitada (`PantallaMenu`, `PantallaPedido` o `PantallaInventario`).

        Comunicación entre módulos:
          - Invocado por los botones de navegación en `ui/views/menu_view.py`, `ui/views/pedido_view.py`
            y `ui/views/inventario_view.py`.
        """
        pantalla = self.pantallas[nombre]
        pantalla.tkraise()
        if hasattr(pantalla, "al_mostrar"):
            pantalla.al_mostrar()

    def _procesar_eventos_yape(self) -> None:
        """Bucle periódico en el hilo principal que consume los eventos de `ServicioNotificacionesYape`.

        Procesa tres tipos de eventos desde la cola:
          - `"pago"`: Reproduce alerta sonora (`ui/toasts.py`), despliega notificación flotante
            apilada (`NotificacionToastYape`) y refresca `VentanaHistorialYape` si está abierta.
          - `"mostrar"`: Señal recibida cuando el usuario abre el acceso directo de `VitalStock.exe`;
            restaura la ventana principal desde el segundo plano (`mostrar_desde_bandeja()`).
          - `"error"` / `"info"`: Actualiza el texto de estado en `PantallaMenu`.

        Comunicación entre módulos:
          - Lee `self.servicio_yape.cola` (`services/yape_service.py`).
          - Invoca `emitir_alerta_sonido_pago()` y `NotificacionToastYape` (`ui/toasts.py`).
          - Actualiza `PantallaMenu` (`ui/views/menu_view.py`) y `VentanaHistorialYape` (`ui/dialogs/yape_history_dialog.py`).
        """
        menu = self.pantallas.get("PantallaMenu")
        try:
            while True:
                tipo, dato = self.servicio_yape.cola.get_nowait()
                if tipo == "pago" and isinstance(dato, dict):
                    monto_txt = f"S/ {dato.get('monto', 0):.2f}"
                    texto = f"Pago Yape: {monto_txt} de {dato.get('remitente', '?')}"
                    if isinstance(menu, PantallaMenu):
                        menu.actualizar_estado_yape(texto)

                    # 1. Alerta de sonido en la PC
                    emitir_alerta_sonido_pago()

                    # 2. Notificación visual flotante apilada (Toast)
                    try:
                        NotificacionToastYape(self.root, dato)
                    except Exception as e_toast:
                        print(f"Error mostrando toast: {e_toast}")

                    # 3. Refrescar historial e indicadores si están abiertos
                    if self.ventana_historial_yape and self.ventana_historial_yape.winfo_exists():
                        try:
                            self.ventana_historial_yape.cargar_datos()
                        except Exception:
                            pass

                elif tipo == "mostrar":
                    # El usuario ejecutó el acceso directo de VitalStock para abrir la interfaz
                    self.mostrar_desde_bandeja()

                elif tipo == "error":
                    if isinstance(menu, PantallaMenu):
                        menu.actualizar_estado_yape(f"Error: {dato}")
                else:
                    if isinstance(menu, PantallaMenu):
                        menu.actualizar_estado_yape(str(dato))
        except queue.Empty:
            pass

        self.root.after(250, self._procesar_eventos_yape)

    def _configurar_icono(self) -> None:
        """Carga el icono institucional (`vitalstock.ico` / `vitalstock.png`) en la ventana de Windows.

        Comunicación entre módulos:
          - Utiliza `config.ruta_base()` de `config.py` para ubicar los archivos gráficos.
        """
        posibles_rutas = [
            config.ruta_base() / "vitalstock.ico",
            Path(getattr(sys, "_MEIPASS", "")) / "vitalstock.ico",
            Path(__file__).resolve().parent.parent / "vitalstock.ico",
        ]
        for ruta in posibles_rutas:
            if ruta.is_file():
                try:
                    self.root.iconbitmap(str(ruta))
                    return
                except Exception:
                    pass

        for ruta_png in [
            config.ruta_base() / "vitalstock.png",
            Path(getattr(sys, "_MEIPASS", "")) / "vitalstock.png",
            Path(__file__).resolve().parent.parent / "vitalstock.png",
        ]:
            if ruta_png.is_file():
                try:
                    img = tk.PhotoImage(file=str(ruta_png))
                    self.root.iconphoto(True, img)
                    return
                except Exception:
                    pass

    def _error_no_controlado(self, tipo, valor, _traza) -> None:
        """Captura excepciones no controladas en callbacks de Tkinter y las informa en un cuadro modal."""
        messagebox.showerror(config.APP_NOMBRE, f"Ocurrió un error inesperado:\n\n{tipo.__name__}: {valor}")

    def ocultar_a_bandeja(self) -> None:
        """Oculta la ventana principal enviándola a la bandeja del sistema sin detener el receptor Yape.

        Comunicación entre módulos:
          - Invocada al pulsar la `X` de la ventana (`WM_DELETE_WINDOW`), al cancelar el login
            o desde el menú contextual de `ui/tray_manager.py`.
          - Envía una notificación informativa mediante `self.bandeja.notificar()` (`ui/tray_manager.py`).
        """
        self.root.withdraw()
        if not hasattr(self, "_aviso_bandeja_mostrado"):
            self._aviso_bandeja_mostrado = True
            self.bandeja.notificar(
                config.APP_NOMBRE,
                "VitalStock continúa en segundo plano escuchando pagos Yape.\n"
                "Ábralo desde el icono junto al reloj o desde su acceso directo.",
            )

    def mostrar_desde_bandeja(self) -> None:
        """Restaura y trae al frente la ventana principal desde el segundo plano.

        Si ningún usuario ha iniciado sesión aún, despliega automáticamente la ventana de Login.

        Comunicación entre módulos:
          - Invocada desde `ui/tray_manager.py` (al hacer clic en el icono de la bandeja)
            y desde `_procesar_eventos_yape()` cuando `main.py` envía la señal `/mostrar`
            al abrir el acceso directo de VitalStock.
        """
        self.root.deiconify()
        try:
            self.root.state("normal")
        except Exception:
            pass
        self.root.lift()
        self.root.focus_force()
        if self.usuario_actual is None:
            self.solicitar_login()

    def solicitar_cierre_seguro(self) -> None:
        """Muestra un diálogo modal que exige credenciales de Administrador o Soporte para apagar la app.

        Impide que el personal de caja cierre accidental o intencionalmente el receptor de pagos.

        Comunicación entre módulos:
          - Invocado desde el menú "Cerrar Sistema..." de `ui/tray_manager.py`.
          - Valida credenciales contra `services/auth_service.py` (`autenticar_usuario`).
        """
        dlg = tk.Toplevel(self.root)
        dlg.title("Autorización de Cierre")
        dlg.geometry("380x250")
        dlg.resizable(False, False)
        dlg.configure(bg=config.COLOR_FONDO)
        dlg.attributes("-topmost", True)
        dlg.deiconify()
        dlg.lift()
        dlg.grab_set()

        ancho, alto = 380, 250
        x = max(10, (dlg.winfo_screenwidth() - ancho) // 2)
        y = max(10, (dlg.winfo_screenheight() - alto) // 2)
        dlg.geometry(f"{ancho}x{alto}+{x}+{y}")

        f = tk.Frame(dlg, bg=config.COLOR_TARJETA, padx=20, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(
            f,
            text="🔒  Cerrar VitalStock",
            font=(config.FUENTE, 11, "bold"),
            fg=config.COLOR_ERROR,
            bg=config.COLOR_TARJETA,
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            f,
            text="Para apagar el receptor de pagos y salir se requiere autorización de Administrador o Soporte:",
            font=(config.FUENTE, 8),
            fg=config.COLOR_TEXTO_SEC,
            bg=config.COLOR_TARJETA,
            wraplength=330,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(f, text="Usuario Administrador / Soporte:", font=(config.FUENTE, 8, "bold"), bg=config.COLOR_TARJETA).pack(anchor="w")
        u_defecto = "admin"
        if self.usuario_actual and self.usuario_actual.get("rol") in (config.ROL_ADMIN, config.ROL_SOPORTE):
            u_defecto = self.usuario_actual.get("username", "admin")
        ent_u = ttk.Entry(f)
        ent_u.insert(0, u_defecto)
        ent_u.pack(fill="x", pady=(2, 6))

        tk.Label(f, text="Contraseña:", font=(config.FUENTE, 8, "bold"), bg=config.COLOR_TARJETA).pack(anchor="w")
        ent_p = ttk.Entry(f, show="•")
        ent_p.pack(fill="x", pady=(2, 14))
        ent_p.focus_set()

        def _validar_y_salir():
            u = ent_u.get().strip()
            p = ent_p.get()
            try:
                user = auth_service.autenticar_usuario(u, p)
            except Exception:
                user = None

            if user and user.get("rol") in (config.ROL_ADMIN, config.ROL_SOPORTE):
                dlg.destroy()
                self.cerrar_definitivo()
            else:
                messagebox.showerror(
                    "Acceso Denegado",
                    "Credenciales incorrectas o usuario sin privilegios para cerrar el sistema.\n\n"
                    "VitalStock continuará activo en segundo plano.",
                    parent=dlg,
                )

        f_btn = tk.Frame(f, bg=config.COLOR_TARJETA)
        f_btn.pack(fill="x")
        ttk.Button(f_btn, text="Cancelar", style="Secundario.TButton", command=dlg.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(f_btn, text="Cerrar Sistema", style="Peligro.TButton", command=_validar_y_salir).pack(side="right")
        dlg.bind("<Return>", lambda _e: _validar_y_salir())

    def cerrar_definitivo(self) -> None:
        """Detiene el icono de bandeja, apaga el servidor HTTP Yape y destruye la ventana raíz.

        Comunicación entre módulos:
          - Invoca `self.bandeja.detener()` (`ui/tray_manager.py`) y `self.servicio_yape.detener()`
            (`services/yape_service.py`).
        """
        self.bandeja.detener()
        self.servicio_yape.detener()
        self.root.destroy()

    def ejecutar(self) -> None:
        """Inicia el bucle principal de eventos de Tkinter (`mainloop`).

        Comunicación entre módulos:
          - Llamado por `main()` en `main.py`.
        """
        self.root.mainloop()
