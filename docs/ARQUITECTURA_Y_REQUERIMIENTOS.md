# Documento de Requerimientos y Arquitectura de Software — VitalStock Suite

**Curso:** Ingeniería de Software  
**Docente:** Dr. Alexander Morales Gonzales  
**Proyecto:** Ecosistema VitalStock Suite (Desktop + Android)  
**Repositorios del Sistema:**
- **Servidor y Gestión Desktop:** [`VitalStock`](https://github.com/arocutipaluis/VitalStock) *(Este repositorio)*
- **Agente Capturador Móvil Android:** [`VitalNotifier`](https://github.com/arocutipaluis/VitalNotifier) *(Repositorio complementario)*
**Versión:** 1.4.1  

---

## 1. Contexto, Problemática Real y Conexión Funcional entre Repositorios

En la operación diaria de la botica se identificaron tres cuellos de botella críticos que generaban pérdidas económicas y de tiempo operativo:
1. **Quiebres de stock y compras empíricas**: Los pedidos a droguerías se realizaban de memoria o revisando listados extensos sin cruzar la velocidad real de rotación (`Consumo Promedio Diario`) frente al stock actual.
2. **Desorden en el conteo físico de inventario**: El personal realizaba inventarios manuales sin dividir las hojas por las secciones reales de la botica (`Sección Vitrina`, `Sección Caja`, `Sección Anaquel`, `Sección Almacén`) ni agrupar por laboratorio, y al ver el stock del sistema en la hoja se sesgaba el conteo.
3. **Verificación de pagos Yape en caja**: El teléfono con la cuenta de Yape pertenece a la administración; el personal de caja necesitaba confirmar al instante si un cliente realmente realizó el pago (monto, remitente, código de seguridad y hora exacta del Yape) sin depender de capturas de pantalla falsificables.

### Integración Arquitectónica (`VitalNotifier` → `VitalStock`)
El ecosistema se divide en dos aplicaciones desacopladas que se comunican mediante HTTP sobre la red local (LAN) de la botica:
- **[VitalNotifier (Android)](https://github.com/arocutipaluis/VitalNotifier)**: Ejecuta un servicio `NotificationListenerService` en el teléfono de administración, intercepta las notificaciones de `com.bcp.innovacxion.yapeapp`, extrae los 5 campos canónicos (`remitente`, `monto`, `fecha_hora`, `codigo_seg`, `mensaje_raw`), los persiste en su base de datos local `Room` (actuando como cola de respaldo ante caídas de Wi-Fi) y los despacha mediante `HTTP POST http://<IP_PC>:5005/yape` a todas las PCs registradas en la botica.
- **[VitalStock (Windows Desktop)](https://github.com/arocutipaluis/VitalStock)**: Corre en segundo plano en la bandeja del sistema (`System Tray`) de las computadoras de la botica, recibe el JSON en `services/yape_service.py`, almacena el pago respetando la `fecha_hora` real de emisión del Yape en `%APPDATA%\VitalStock\historial.db` y despliega notificaciones *Toast* apiladas con alerta sonora para el personal de caja.

---

## 2. Requerimientos Funcionales (RF) e Historias de Usuario

| Código | Historia de Usuario / Requerimiento Funcional | Rol | Módulo que lo implementa | Estado |
| :--- | :--- | :--- | :--- | :--- |
| **RF-01** | **Autenticación y Control de Roles (RBAC)**: El sistema debe autenticar al personal diferenciando permisos entre `Admin` y `Caja`, impidiendo que un Administrador modifique la contraseña de otro Administrador. | Admin / Caja | `services/auth_service.py`, `ui/dialogs/login_dialog.py`, `ui/dialogs/users_dialog.py` | ✅ Cumplido |
| **RF-02** | **Importación Polimórfica de Reportes**: El sistema debe leer reportes de ventas y stock exportados por el sistema comercial de la botica tanto en formato Excel (`.xls`, `.xlsx`) como en tablas HTML con extensión `.xls`. | Admin / Caja | `services/reportes_service.py` | ✅ Cumplido |
| **RF-03** | **Cálculo de Recomendación de Pedido**: Cruzar el historial acumulado de ventas con el stock actual parametrizando *Lead Time*, *Stock de Seguridad* y *Días de Cobertura*, clasificando cada ítem en `URGENTE`, `POR PEDIR`, `NORMAL`, `SOBRESTOCK` o `SIN ROTACIÓN`. | Admin | `services/pedido_service.py`, `ui/views/pedido_view.py` | ✅ Cumplido |
| **RF-04** | **Gestión de Secciones y Formato de Inventario A4**: Clasificar productos en 4 secciones de la botica, detectar productos nuevos sin ubicación y exportar el formato Excel A4 horizontal dividido en sub-tablas por laboratorio con la columna `SISTEMA (UNID / FRAC)` en blanco antes de `TOTAL`. | Admin / Caja | `services/inventario_service.py`, `ui/views/inventario_view.py` | ✅ Cumplido |
| **RF-05** | **Recepción de Pagos Yape en Tiempo Real y Cola de Toasts**: Escuchar en el puerto `5005` los pagos enviados por `VitalNotifier`, mostrar notificaciones emergentes apiladas con sonido y registrar la **fecha y hora exacta en que se realizó el Yape** (`fecha_hora`). | Admin / Caja | `services/yape_service.py`, `ui/toasts.py`, `ui/dialogs/yape_history_dialog.py` | ✅ Cumplido |
| **RF-06** | **Ejecución Silenciosa en Segundo Plano y Cierre Protegido**: Iniciar minimizado en la bandeja del sistema (`System Tray`) al encender Windows, permitir abrir la ventana desde la bandeja o el acceso directo (`GET /mostrar`) y exigir contraseña de Administrador para cerrar definitivamente el proceso. | Sistema | `main.py`, `ui/app.py`, `ui/tray_manager.py` | ✅ Cumplido |

---

## 3. Requerimientos No Funcionales (RNF) y Atributos de Calidad

1. **RNF-01 Seguridad Criptográfica**: Las contraseñas nunca se almacenan en texto plano; se utiliza `PBKDF2-HMAC-SHA256` con `100,000` iteraciones y un `salt` aleatorio de 16 bytes por usuario (`database.hash_password`). Las consultas SQL emplean exclusivamente parámetros enlazados (`?`) previniendo inyección SQL.
2. **RNF-02 Persistencia Desacoplada y Migraciones Automáticas**: La base de datos `historial.db` se almacena en `%APPDATA%\VitalStock\historial.db` y cuenta con un motor de migración automática basado en `PRAGMA user_version` (`database._migrar_esquema_versiones`), permitiendo actualizar el ejecutable sin perder datos históricos.
3. **RNF-03 Integridad Temporal Ante Desconexiones**: Si el celular con `VitalNotifier` pierde conexión Wi-Fi y sincroniza los pagos horas después, `VitalStock` persiste el timestamp real de la operación (`fecha_hora`) tanto en la vista como en el índice ISO SQLite (`fecha_registro`).
4. **RNF-04 Concurrencia No Bloqueante**: El servidor HTTP receptor (`HTTPServer`) y el ícono de bandeja (`pystray`) corren en hilos `daemon` independientes, comunicándose con el hilo principal de Tkinter mediante una cola segura para hilos (`queue.Queue`).

---

## 4. Principios de Diseño Aplicados (SOLID, DRY, KISS)

- **S — Single Responsibility Principle (Responsabilidad Única)**:
  - `config.py` solo gestiona constantes y variables de entorno.
  - `database.py` solo administra conexiones SQLite y migraciones de esquema.
  - Cada servicio en `services/` encapsula un único dominio de negocio (`auth`, `yape`, `pedido`, `inventario`, `reportes`).
  - Cada vista en `ui/views/` y diálogo en `ui/dialogs/` gestiona únicamente su interfaz gráfica.
- **O — Open/Closed Principle (Abierto/Cerrado)**:
  - `PantallaBase` (`ui/views/base_view.py`) define la estructura institucional extensible por `PantallaMenu`, `PantallaPedido` y `PantallaInventario` sin modificar la clase base.
  - El motor de migraciones en `database.py` permite añadir nuevas versiones de esquema (`version_actual < N`) sin alterar las migraciones previas.
- **D — Dependency Inversion / Separación de Capas**:
  - La capa `ui/` nunca ejecuta sentencias SQL directas de negocio; consume la capa `services/`, la cual a su vez se apoya en `database.py`.
- **DRY (Don't Repeat Yourself)**:
  - Componentes visuales como `ZonaDrop`, `Tarjeta` y `crear_treeview` están centralizados en `ui/widgets.py` y reutilizados en todas las pantallas.
  - La normalización de fechas Yape (`convertir_fecha_hora_yape`) se reutiliza tanto en el registro en vivo como en las migraciones retroactivas.
