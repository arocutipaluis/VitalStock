"""
services/yape_service.py - Servicio de recepción HTTP, parseo y persistencia de pagos Yape.

Este módulo escucha en segundo plano las peticiones HTTP POST enviadas por la aplicación
móvil VitalNotifier (`http://<IP_PC>:5005/yape`) y almacena las transacciones en SQLite
respetando la fecha y hora exacta en que se efectuó el Yape (`fecha_hora`).

Comunicación con otros archivos del proyecto:
  - Importa `config.py` para obtener el puerto de escucha (`PUERTO_YAPE_DEFECTO`).
  - Importa `database.py` (`obtener_conexion` y `convertir_fecha_hora_yape`) para persistir y consultar pagos.
  - Es instanciado y monitoreado por `ui/app.py` (`VitalStockApp`) mediante una cola segura entre hilos (`queue.Queue`).
  - Es invocado por `ui/dialogs/yape_history_dialog.py`, `ui/dialogs/network_dialog.py`, `ui/views/menu_view.py` y `main.py`.
"""

from __future__ import annotations

import json
import queue
import re
import socket
import threading
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import config
from database import convertir_fecha_hora_yape, obtener_conexion


def obtener_ip_local() -> str:
    """Obtiene la dirección IPv4 local de la computadora en la red Wi-Fi / LAN de la botica.

    Comunicación entre módulos:
      - Invocada internamente por `ServicioNotificacionesYape.iniciar()`.
      - Invocada por `ui/dialogs/network_dialog.py` y `ui/views/menu_view.py` para mostrar
        al usuario la dirección IP que debe configurar en la app móvil VitalNotifier.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def parsear_texto_notificacion_yape(texto: str) -> tuple[str, float, str]:
    """Extrae remitente, monto y código de seguridad desde el texto plano de una notificación Yape.

    Actúa como respaldo inteligente en caso de que algún campo individual del JSON venga vacío.
    Formatos soportados:
      - "Confirmación de Pago Nombre Ape* te envió un pago por S/ 1. El cód. de seguridad es: 796"
      - "Juan Perez te envió un pago por S/ 15.50. El cód. de seguridad es: 123"
      - "¡Te transfirieron S/ 25.50 de JUAN PEREZ! Cód: 1234"

    Comunicación entre módulos:
      - Invocada por `YapeRequestHandler.do_POST` dentro de `ServicioNotificacionesYape`
        y reexportada en `motor.py`.
    """
    raw = (texto or "").strip()
    remitente = ""
    monto = 0.0
    cod_seg = ""

    # 1. Código de seguridad (soporta "cód. de seguridad es: 1234" y "Cód: 1234")
    m_cod = re.search(
        r"c[oó]d(?:igo|\.)?(?:\s*de\s*seguridad\s*es)?\s*:?\s*([A-Za-z0-9]+)",
        raw,
        re.IGNORECASE,
    )
    if m_cod:
        cod_seg = m_cod.group(1).strip()

    # 2. Nombre y monto
    m1 = re.search(
        r"(?:Confirmaci[oó]n\s+de\s+Pago\s+)?([A-Za-zÀ-ÿ0-9\s*.'-]+?)\s+te\s+(?:envi[oó]|transfiri[oó])\s+(?:un\s+pago\s+por\s+)?S/\s*([\d,]+(?:\.\d{1,2})?)",
        raw,
        re.IGNORECASE,
    )
    if m1:
        nom = m1.group(1).strip()
        nom = re.sub(r"^Confirmaci[oó]n\s+de\s+Pago\s*", "", nom, flags=re.IGNORECASE).strip()
        if nom:
            remitente = nom
        try:
            monto = float(m1.group(2).replace(",", ""))
        except ValueError:
            pass
    else:
        m2 = re.search(
            r"transfirieron\s+S/\s*([\d,]+(?:\.\d{1,2})?)\s+de\s+([A-Za-zÀ-ÿ0-9\s*.'-]+?)(?:\s*[!.]|\s+C[oó]d|$)",
            raw,
            re.IGNORECASE,
        )
        if m2:
            try:
                monto = float(m2.group(1).replace(",", ""))
            except ValueError:
                pass
            remitente = m2.group(2).strip()

    return remitente, monto, cod_seg


def registrar_pago_yape(
    remitente: str,
    monto: float,
    fecha_hora: str = "",
    codigo_seg: str = "",
    mensaje_raw: str = "",
) -> int:
    """Guarda un pago Yape en la tabla `pagos_yape` preservando la fecha y hora real del Yape.

    Importante:
      Tanto `fecha_hora` (formato legible `DD/MM/YYYY HH:MM:SS`) como `fecha_registro`
      (formato ISO `YYYY-MM-DD HH:MM:SS` para filtros de fechas SQL) se calculan a partir
      de la hora enviada por VitalNotifier (`fecha_hora`), y NO de la hora en que la PC
      recibió la notificación. Así, si el celular estuvo fuera de red y sincroniza después,
      cada pago se registra con su hora real.

    Comunicación entre módulos:
      - Invoca `convertir_fecha_hora_yape()` y `obtener_conexion()` de `database.py`.
      - Es llamada por `ServicioNotificacionesYape` al recibir un POST en `/yape`,
        y por `ui/dialogs/network_dialog.py` en pruebas locales.
    """
    fecha_visual, fecha_iso = convertir_fecha_hora_yape(fecha_hora)

    with obtener_conexion() as conn:
        cur = conn.execute(
            """
            INSERT INTO pagos_yape (remitente, monto, fecha_hora, codigo_seg, mensaje_raw, fecha_registro)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                remitente.strip(),
                float(monto),
                fecha_visual,
                codigo_seg.strip(),
                mensaje_raw.strip(),
                fecha_iso,
            ),
        )
        return cur.lastrowid or 0


def listar_pagos_yape(
    filtro_modo: str = "todos",
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    limite: int = 500,
) -> list[dict]:
    """Consulta los pagos Yape registrados según el filtro temporal ('dia', 'semana', 'rango', 'todos').

    Filtra y ordena utilizando la fecha/hora real del Yape almacenada en `fecha_registro` / `fecha_hora`.

    Comunicación entre módulos:
      - Se conecta a SQLite mediante `obtener_conexion()` de `database.py`.
      - Es invocada por `ui/dialogs/yape_history_dialog.py` (`VentanaHistorialYape.cargar_datos`)
        para poblar la tabla del historial y preparar la exportación a Excel.
    """
    hoy = date.today()
    condiciones = []
    parametros: list[object] = []

    if filtro_modo == "dia":
        condiciones.append("date(fecha_registro) = date('now', 'localtime')")
    elif filtro_modo == "semana":
        lunes = hoy - timedelta(days=hoy.weekday())
        condiciones.append("date(fecha_registro) >= date(?) AND date(fecha_registro) <= date(?)")
        parametros.extend([lunes.isoformat(), hoy.isoformat()])
    elif filtro_modo == "rango":
        if fecha_desde:
            condiciones.append("date(fecha_registro) >= date(?)")
            parametros.append(fecha_desde.isoformat())
        if fecha_hasta:
            condiciones.append("date(fecha_registro) <= date(?)")
            parametros.append(fecha_hasta.isoformat())

    where_sql = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    sql = f"""
        SELECT id, remitente, monto, fecha_hora, codigo_seg, mensaje_raw, fecha_registro
        FROM pagos_yape
        {where_sql}
        ORDER BY fecha_registro DESC, id DESC
        LIMIT ?
    """
    parametros.append(limite)

    with obtener_conexion() as conn:
        cur = conn.execute(sql, parametros)
        filas = cur.fetchall()

    return [
        {
            "id": r[0],
            "remitente": r[1],
            "monto": r[2],
            "fecha_hora": r[3],
            "codigo_seg": r[4],
            "mensaje_raw": r[5],
            "fecha_registro": r[6],
        }
        for r in filas
    ]


def _parsear_fecha_flexible(texto: str) -> date | None:
    """Convierte una cadena de fecha (`DD/MM/YYYY` o `YYYY-MM-DD`) en un objeto `datetime.date`.

    Comunicación entre módulos:
      - Función auxiliar interna usada por `obtener_fechas_periodo_yape()` y `consultar_pagos_yape()`.
    """
    if not texto:
        return None
    s = texto.strip().replace("-", "/")
    partes = s.split("/")
    if len(partes) == 3:
        try:
            if len(partes[0]) == 4:
                return date(int(partes[0]), int(partes[1]), int(partes[2]))
            else:
                return date(int(partes[2]), int(partes[1]), int(partes[0]))
        except (ValueError, TypeError):
            return None
    return None


def obtener_fechas_periodo_yape(
    filtro: str,
    desde_str: str = "",
    hasta_str: str = "",
) -> tuple[date | None, date | None, str]:
    """Calcula las fechas de inicio y fin junto con una etiqueta descriptiva para el filtro elegido.

    Comunicación entre módulos:
      - Reexportada en `motor.py` para consultas de períodos de pagos Yape.
    """
    hoy = date.today()
    if filtro == "dia":
        return hoy, hoy, f"Yapes del día ({hoy:%d/%m/%Y})"
    elif filtro == "semana":
        lunes = hoy - timedelta(days=hoy.weekday())
        return lunes, hoy, f"Semana en curso ({lunes:%d/%m/%Y} al {hoy:%d/%m/%Y})"
    elif filtro == "todos":
        return None, None, "Todos los pagos registrados"
    elif filtro == "rango":
        f_ini = _parsear_fecha_flexible(desde_str) if desde_str else hoy
        f_fin = _parsear_fecha_flexible(hasta_str) if hasta_str else hoy
        if f_ini and f_fin and f_ini > f_fin:
            f_ini, f_fin = f_fin, f_ini
        txt_ini = f_ini.strftime("%d/%m/%Y") if f_ini else "?"
        txt_fin = f_fin.strftime("%d/%m/%Y") if f_fin else "?"
        return f_ini, f_fin, f"Del {txt_ini} al {txt_fin}"
    return None, None, "Filtro no reconocido"


def consultar_pagos_yape(
    fecha_inicio: date | str | None = None,
    fecha_fin: date | str | None = None,
    orden_asc: bool = False,
) -> list[dict]:
    """Consulta pagos Yape en un rango de fechas específico ordenados cronológicamente.

    Comunicación entre módulos:
      - Se comunica con `database.py` (`obtener_conexion`) y es reexportada por `motor.py`.
    """
    if isinstance(fecha_inicio, str):
        fecha_inicio = _parsear_fecha_flexible(fecha_inicio)
    if isinstance(fecha_fin, str):
        fecha_fin = _parsear_fecha_flexible(fecha_fin)

    clausulas = []
    params: list[str] = []
    if fecha_inicio:
        clausulas.append("date(fecha_registro) >= ?")
        params.append(fecha_inicio.isoformat())
    if fecha_fin:
        clausulas.append("date(fecha_registro) <= ?")
        params.append(fecha_fin.isoformat())

    where_sql = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
    order_sql = "ORDER BY fecha_registro ASC, id ASC" if orden_asc else "ORDER BY fecha_registro DESC, id DESC"

    query = f"""
        SELECT id, remitente, monto, fecha_hora, codigo_seg, mensaje_raw, fecha_registro
        FROM pagos_yape
        {where_sql}
        {order_sql}
    """
    with obtener_conexion() as conn:
        cur = conn.execute(query, params)
        filas = cur.fetchall()
        return [
            {
                "id": f[0],
                "remitente": f[1],
                "monto": float(f[2]),
                "fecha_hora": f[3],
                "codigo_seg": f[4],
                "mensaje_raw": f[5],
                "fecha_registro": f[6],
            }
            for f in filas
        ]


def obtener_resumen_yape_hoy() -> tuple[int, float]:
    """Retorna `(cantidad_pagos_hoy, total_monto_hoy)` correspondientes a la fecha actual.

    Comunicación entre módulos:
      - Consulta SQLite mediante `database.obtener_conexion()`.
      - Es invocada por `ui/views/menu_view.py` para mostrar el resumen diario en el panel principal.
    """
    with obtener_conexion() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(monto), 0)
            FROM pagos_yape
            WHERE date(fecha_registro) = date('now', 'localtime')
            """
        ).fetchone()
    return (row[0], float(row[1])) if row else (0, 0.0)


def eliminar_pago_yape(id_pago: int) -> bool:
    """Elimina permanentemente una transacción de pago por su ID (exclusivo para rol soporte/mantenimiento).

    Comunicación entre módulos:
      - Ejecuta `DELETE` en SQLite mediante `database.obtener_conexion()`.
      - Es invocada por `ui/dialogs/yape_history_dialog.py` (`_eliminar_pago_mantenimiento`).
    """
    with obtener_conexion() as conn:
        cur = conn.execute("DELETE FROM pagos_yape WHERE id = ?", (id_pago,))
        return cur.rowcount > 0


class ServicioNotificacionesYape:
    """Servidor HTTP en segundo plano para recepción de pagos desde VitalNotifier y control de ventana.

    Endpoints soportados:
      - `POST /yape` (o `/notificacion`, `/`): Recibe el JSON de VitalNotifier con los 5 campos
        (`remitente`, `monto`, `fecha_hora`, `codigo_seg`, `mensaje_raw`), lo guarda en SQLite
        con la hora real del Yape y encola el evento `"pago"` para la interfaz gráfica.
      - `GET /ping` (o `/`): Verificación de estado del servidor receptor.
      - `GET /mostrar`: Recibe la señal local desde `main.py` cuando el usuario ejecuta el acceso
        directo para despertar y mostrar la ventana principal que estaba en la bandeja del sistema.

    Comunicación entre módulos:
      - Instanciada e iniciada por `ui/app.py` (`VitalStockApp`).
      - Se comunica hacia `ui/app.py` depositando tuplas `(tipo, dato)` en `self.cola`, que son
        leídas periódicamente por `VitalStockApp._procesar_eventos_yape()`.
      - Recibe peticiones locales desde `main.py` (`_intentar_despertar_instancia_existente`).
    """

    def __init__(self, puerto: int = config.PUERTO_YAPE_DEFECTO) -> None:
        """Inicializa la cola de eventos y parámetros de red usando `config.PUERTO_YAPE_DEFECTO`."""
        self.puerto = puerto
        self.cola: queue.Queue[tuple[str, object]] = queue.Queue()
        self._servidor: HTTPServer | None = None
        self._hilo: threading.Thread | None = None

    @property
    def activo(self) -> bool:
        """Indica si el servidor HTTP está activo y su hilo demonio sigue en ejecución."""
        return self._servidor is not None and self._hilo is not None and self._hilo.is_alive()

    def iniciar(self) -> None:
        """Levanta el servidor HTTP en un hilo secundario (`daemon=True`) sin bloquear Tkinter.

        Comunicación entre módulos:
          - Llamado por `ui/app.py` al arrancar la aplicación y por `ui/dialogs/network_dialog.py`.
          - Invoca `registrar_pago_yape()` al recibir cada transacción entrante.
        """
        if self.activo:
            return
        servicio_self = self

        class YapeRequestHandler(BaseHTTPRequestHandler):
            """Manejador de peticiones HTTP entrantes de VitalNotifier y señales locales."""

            def log_message(self, format, *args):
                """Silencia la salida estándar de logs HTTP para evitar bloqueo sin consola."""
                pass

            def do_GET(self):
                """Atiende consultas de estado (`/ping`) y la orden de mostrar ventana (`/mostrar`)."""
                if self.path in ("/ping", "/"):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b'{"status": "ok", "app": "VitalStock Receiver"}')
                elif self.path == "/mostrar":
                    # Señal enviada por `main.py` al abrir el acceso directo de VitalStock
                    servicio_self.cola.put(("mostrar", None))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b'{"status": "mostrando", "app": "VitalStock Receiver"}')
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                """Procesa el JSON de pago enviado por VitalNotifier en `http://<IP_PC>:5005/yape`."""
                if self.path in ("/yape", "/notificacion", "/"):
                    try:
                        longitud = int(self.headers.get("Content-Length", 0))
                        cuerpo = self.rfile.read(longitud).decode("utf-8")
                        try:
                            datos = json.loads(cuerpo)
                        except Exception:
                            datos = {"mensaje_raw": cuerpo}

                        remitente = str(datos.get("remitente", "")).strip()
                        monto = float(datos.get("monto", 0.0) or 0.0)
                        fecha_hora = str(datos.get("fecha_hora", "")).strip()
                        codigo_seg = str(datos.get("codigo_seg", "")).strip()
                        mensaje_raw = str(datos.get("mensaje_raw", "")).strip()

                        # Respaldo por expresión regular si algún campo vino incompleto
                        texto_analizar = mensaje_raw or cuerpo
                        p_nom, p_monto, p_cod = parsear_texto_notificacion_yape(texto_analizar)
                        if (not remitente or remitente.lower() in ("desconocido", "cliente yape")) and p_nom:
                            remitente = p_nom
                        if monto <= 0.0 and p_monto > 0.0:
                            monto = p_monto
                        if not codigo_seg and p_cod:
                            codigo_seg = p_cod

                        if not remitente:
                            remitente = "Cliente Yape"

                        # Normalizar la hora real del Yape (o usar hora actual solo si vino vacía)
                        fecha_hora_visual, _ = convertir_fecha_hora_yape(fecha_hora)

                        # Persistir de inmediato en SQLite con la fecha/hora exacta del Yape
                        pago_id = registrar_pago_yape(
                            remitente=remitente,
                            monto=monto,
                            fecha_hora=fecha_hora_visual,
                            codigo_seg=codigo_seg,
                            mensaje_raw=mensaje_raw or cuerpo,
                        )

                        pago_dict = {
                            "id": pago_id,
                            "remitente": remitente,
                            "monto": monto,
                            "fecha_hora": fecha_hora_visual,
                            "codigo_seg": codigo_seg,
                        }

                        # Enviar evento a `ui/app.py` para emitir sonido, mostrar Toast y refrescar tabla
                        servicio_self.cola.put(("pago", pago_dict))

                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "recibido", "id": pago_id}).encode("utf-8"))
                    except Exception as exc:
                        servicio_self.cola.put(("error", f"Error procesando pago: {exc}"))
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "error", "detalle": str(exc)}).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

        try:
            self._servidor = HTTPServer(("0.0.0.0", self.puerto), YapeRequestHandler)
            self._hilo = threading.Thread(target=self._servidor.serve_forever, name="VitalYapeServer", daemon=True)
            self._hilo.start()
            ip = obtener_ip_local()
            self.cola.put(("info", f"Servidor escuchando en http://{ip}:{self.puerto}/yape"))
        except Exception as exc:
            self._servidor = None
            self._hilo = None
            self.cola.put(("error", f"No se pudo iniciar el servidor en el puerto {self.puerto}: {exc}"))

    def detener(self) -> None:
        """Apaga ordenadamente el servidor HTTP receptor al cerrar definitivamente la aplicación.

        Comunicación entre módulos:
          - Invocado por `ui/app.py` (`VitalStockApp.cerrar_definitivo`) tras validar clave de Admin/Soporte.
        """
        if self._servidor:
            srv = self._servidor
            self._servidor = None
            threading.Thread(target=srv.shutdown, daemon=True).start()
        self.cola.put(("info", "Servicio receptor de pagos detenido."))
