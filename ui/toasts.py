"""
ui/toasts.py - Notificaciones visuales flotantes apiladas (Stacked Toast) y alertas de audio.

Este módulo proporciona alertas sonoras y tarjetas flotantes en la esquina inferior
derecha de Windows cada vez que se recibe un pago de Yape, incluso cuando la ventana
principal de VitalStock se encuentra oculta en segundo plano.

Comunicación con otros archivos del proyecto:
  - Importa `config.py` para los colores institucionales y tipografía.
  - Es consumido por `ui/app.py` (`VitalStockApp._procesar_eventos_yape`), el cual recibe
    los datos de pago desde `services/yape_service.py` y dispara `emitir_alerta_sonido_pago()`
    y `NotificacionToastYape`.
"""

from __future__ import annotations

import tkinter as tk

import config


def emitir_alerta_sonido_pago() -> None:
    """Reproduce un sonido del sistema de Windows en modo asíncrono para alertar un nuevo pago.

    Comunicación entre módulos:
      - Invocada por `VitalStockApp._procesar_eventos_yape()` en `ui/app.py` al recibir un evento `"pago"`.
    """
    try:
        import winsound
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass


class GestorToasts:
    """Administra la cola activa de notificaciones Toast para apilarlas verticalmente sin solaparse.

    Cuando entran pagos simultáneos, cada nueva tarjeta se posiciona encima de la anterior.
    Cuando una tarjeta inferior se cierra o agota su tiempo, las tarjetas superiores bajan
    automáticamente con una animación suave.
    """

    def __init__(self) -> None:
        """Inicializa la lista en memoria de instancias `NotificacionToastYape` visibles."""
        self.toasts_activas: list[NotificacionToastYape] = []

    def registrar(self, toast: NotificacionToastYape) -> int:
        """Añade una nueva notificación a la pila y devuelve su índice vertical (`slot`)."""
        self.toasts_activas.append(toast)
        return len(self.toasts_activas) - 1

    def desregistrar(self, toast: NotificacionToastYape) -> None:
        """Elimina una notificación cerrada de la pila y ordena reacomodar las restantes."""
        if toast in self.toasts_activas:
            self.toasts_activas.remove(toast)
            self.reacomodar()

    def reacomodar(self) -> None:
        """Recalcula el índice de cada notificación activa y le indica deslizarse a su nueva posición."""
        for idx, t in enumerate(self.toasts_activas):
            t.actualizar_slot(idx)


_gestor_toasts = GestorToasts()


class NotificacionToastYape:
    """Ventana flotante (`Toplevel` con `-topmost`) en la esquina inferior derecha para mostrar un pago Yape.

    Muestra el monto recibido, el nombre del remitente, la hora exacta del Yape (`fecha_hora`)
    y el código de seguridad.

    Comunicación entre módulos:
      - Instanciada desde `ui/app.py` (`VitalStockApp._procesar_eventos_yape`).
      - Se coordina con `_gestor_toasts` (`GestorToasts`) en este mismo módulo para su posicionamiento.
    """

    ANCHO = 340
    ALTO = 140
    ESPACIADO = 12
    MARGEN_INFERIOR = 55
    MARGEN_DERECHO = 25

    def __init__(self, maestro: tk.Tk, datos_pago: dict, duracion_ms: int = 5500) -> None:
        """Crea y posiciona la tarjeta flotante encima de cualquier aplicación abierta en Windows."""
        self.maestro = maestro
        self.datos = datos_pago
        self.duracion_ms = duracion_ms
        self._cerrada = False

        self.ventana = tk.Toplevel(maestro)
        self.ventana.overrideredirect(True)
        self.ventana.attributes("-topmost", True)
        self.ventana.configure(bg="#113e33")  # Borde verde institucional oscuro

        ancho_pantalla = self.ventana.winfo_screenwidth()
        self.alto_pantalla = self.ventana.winfo_screenheight()
        self.pos_x = max(10, ancho_pantalla - self.ANCHO - self.MARGEN_DERECHO)

        self.slot = _gestor_toasts.registrar(self)
        pos_y = self._calcular_y(self.slot)
        self.ventana.geometry(f"{self.ANCHO}x{self.ALTO}+{self.pos_x}+{pos_y}")

        marco = tk.Frame(self.ventana, bg=config.COLOR_TARJETA, bd=0)
        marco.pack(fill="both", expand=True, padx=2, pady=2)

        barra = tk.Frame(marco, bg=config.COLOR_PRIMARIO, height=32)
        barra.pack(fill="x")
        barra.pack_propagate(False)

        lbl_icono = tk.Label(
            barra,
            text="💰  ¡Nuevo Pago Yape Recibido!",
            font=(config.FUENTE, 9, "bold"),
            fg="white",
            bg=config.COLOR_PRIMARIO,
        )
        lbl_icono.pack(side="left", padx=10)

        lbl_cerrar = tk.Label(
            barra,
            text="✕",
            font=(config.FUENTE, 9, "bold"),
            fg="white",
            bg=config.COLOR_PRIMARIO,
            cursor="hand2",
        )
        lbl_cerrar.pack(side="right", padx=10)
        lbl_cerrar.bind("<Button-1>", lambda _e: self.cerrar())

        cuerpo = tk.Frame(marco, bg=config.COLOR_TARJETA, padx=12, pady=8)
        cuerpo.pack(fill="both", expand=True)

        monto_val = float(datos_pago.get("monto", 0.0))
        lbl_monto = tk.Label(
            cuerpo,
            text=f"S/ {monto_val:.2f}",
            font=(config.FUENTE, 18, "bold"),
            fg="#0f765e",
            bg=config.COLOR_TARJETA,
        )
        lbl_monto.pack(anchor="w")

        remitente = datos_pago.get("remitente", "Cliente Yape")
        lbl_remitente = tk.Label(
            cuerpo,
            text=f"De: {remitente}",
            font=(config.FUENTE, 10, "bold"),
            fg=config.COLOR_TEXTO,
            bg=config.COLOR_TARJETA,
            wraplength=310,
            justify="left",
        )
        lbl_remitente.pack(anchor="w", pady=(1, 0))

        info_extra = []
        fecha_hora = datos_pago.get("fecha_hora", "")
        if fecha_hora:
            info_extra.append(f"🕒 {fecha_hora.split()[-1] if ' ' in fecha_hora else fecha_hora}")
        cod_seg = datos_pago.get("codigo_seg", "")
        if cod_seg:
            info_extra.append(f"Seg: {cod_seg}")

        texto_pie = "  ·  ".join(info_extra) if info_extra else "Guardado en historial"
        lbl_pie = tk.Label(cuerpo, text=texto_pie, font=(config.FUENTE, 8), fg=config.COLOR_TEXTO_SEC, bg=config.COLOR_TARJETA)
        lbl_pie.pack(anchor="w", pady=(2, 0))

        # Al hacer clic sobre cualquier parte de la tarjeta, se cierra
        for w in (self.ventana, marco, barra, lbl_icono, cuerpo, lbl_monto, lbl_remitente, lbl_pie):
            w.bind("<Button-1>", lambda _e: self.cerrar())

        self.ventana.lift()
        self._timer_id = self.ventana.after(self.duracion_ms, self.cerrar)

    def _calcular_y(self, slot: int) -> int:
        """Calcula la coordenada Y en pantalla según la posición (`slot`) en la pila de notificaciones."""
        y = self.alto_pantalla - self.ALTO - self.MARGEN_INFERIOR - slot * (self.ALTO + self.ESPACIADO)
        return max(10, y)

    def actualizar_slot(self, nuevo_slot: int) -> None:
        """Actualiza el nivel de apilamiento e inicia el deslizamiento cuando una alerta inferior se cierra."""
        if self._cerrada:
            return
        self.slot = nuevo_slot
        target_y = self._calcular_y(nuevo_slot)
        self._deslizar_hacia(target_y, pasos=4)

    def _deslizar_hacia(self, target_y: int, pasos: int = 4) -> None:
        """Anima suavemente el desplazamiento vertical de la ventana hacia `target_y`."""
        if self._cerrada:
            return
        try:
            curr_y = self.ventana.winfo_y()
        except Exception:
            curr_y = target_y

        diff = target_y - curr_y
        if abs(diff) <= 2 or pasos <= 1:
            try:
                self.ventana.geometry(f"{self.ANCHO}x{self.ALTO}+{self.pos_x}+{target_y}")
            except Exception:
                pass
            return

        paso_y = curr_y + diff // pasos
        try:
            self.ventana.geometry(f"{self.ANCHO}x{self.ALTO}+{self.pos_x}+{paso_y}")
            self.ventana.after(20, lambda: self._deslizar_hacia(target_y, pasos - 1))
        except Exception:
            pass

    def cerrar(self) -> None:
        """Cancela el temporizador pendiente, notifica a `_gestor_toasts` y destruye la ventana flotante."""
        if self._cerrada:
            return
        self._cerrada = True
        try:
            if hasattr(self, "_timer_id") and self._timer_id:
                self.ventana.after_cancel(self._timer_id)
                self._timer_id = None
            _gestor_toasts.desregistrar(self)
            self.ventana.destroy()
        except Exception:
            pass
