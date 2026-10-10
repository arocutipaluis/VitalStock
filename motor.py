"""
===============================================================================
MÓDULO: motor.py (Fachada de Compatibilidad)
DESCRIPCIÓN:
    Mantiene compatibilidad retroactiva reexportando constantes, funciones de
    base de datos y servicios que anteriormente residían en un único archivo monolítico.

COMUNICACIÓN CON OTROS ARCHIVOS:
    - Reexporta desde `config.py`: Constantes de negocio y estados de inventario.
    - Reexporta desde `database.py`: `inicializar_db`, `obtener_conexion`, `ruta_db`.
    - Reexporta desde `services/auth_service.py`: Funciones de gestión de usuarios.
    - Reexporta desde `services/pedido_service.py`: Funciones de historial y cálculo de pedidos.
    - Reexporta desde `services/yape_service.py`: Funciones de registro y consulta de Yape.
===============================================================================
"""

from __future__ import annotations

import config
import database
from database import inicializar_db, obtener_conexion, ruta_db
from services import auth_service, pedido_service, yape_service
from services.auth_service import (
    alternar_estado_usuario,
    autenticar_usuario,
    cambiar_password,
    crear_usuario,
    eliminar_usuario,
    listar_usuarios,
)
from services.pedido_service import (
    ArchivoDuplicadoError,
    archivo_ya_importado,
    calcular_recomendacion,
    eliminar_importacion,
    importar_ventas,
    limpiar_historial,
    listar_importaciones,
    obtener_dias_periodo,
    obtener_resumen_historial,
    obtener_ventas_acumuladas,
)
from services.yape_service import (
    listar_pagos_yape,
    obtener_fechas_periodo_yape,
    obtener_resumen_yape_hoy,
    parsear_texto_notificacion_yape,
    registrar_pago_yape,
)

# Constantes de negocio
NOMBRE_DB = config.NOMBRE_DB
ROL_ADMIN = config.ROL_ADMIN
ROL_CAJA = config.ROL_CAJA
ROLES_PERMITIDOS = config.ROLES_PERMITIDOS

# Alias de compatibilidad previa
ROL_DUENA = config.ROL_ADMIN
ROL_CAJERA = config.ROL_CAJA

ESTADO_URGENTE = config.ESTADO_URGENTE
ESTADO_POR_PEDIR = config.ESTADO_POR_PEDIR
ESTADO_NORMAL = config.ESTADO_NORMAL
ESTADO_SOBRESTOCK = config.ESTADO_SOBRESTOCK
ESTADO_SIN_ROTACION = config.ESTADO_SIN_ROTACION
ESTADOS = config.ESTADOS
PRIORIDAD_ESTADOS = config.PRIORIDAD_ESTADOS

UMBRAL_SIN_ROTACION = config.UMBRAL_SIN_ROTACION
DIAS_URGENTE = config.DIAS_URGENTE
DIAS_POR_PEDIR = config.DIAS_POR_PEDIR
DIAS_SOBRESTOCK = config.DIAS_SOBRESTOCK

ruta_base = config.ruta_base
_conexion = database.obtener_conexion
