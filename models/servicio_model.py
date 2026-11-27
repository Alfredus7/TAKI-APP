import sqlite3

from database import get_connection

# Tarifas base por tipo de servicio.
TARIFAS_BASE = {"Mototaxi": 5.00, "Courier": 8.00}


# ---------------------------------------------------------------- Conductor (existente)

def listar_solicitudes_disponibles(limite: int = 10):
    with get_connection() as conn:
        return conn.execute(
            """SELECT s.*, t.nombre AS tipo
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               WHERE s.id_conductor IS NULL AND s.estado = 'pendiente'
               ORDER BY s.fecha_solicitud ASC, s.id_servicio ASC LIMIT ?""",
            (limite,),
        ).fetchall()


def aceptar_servicio(id_servicio: int, id_conductor: int) -> tuple[bool, str]:
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE SERVICIO SET id_conductor = ?, estado = 'aceptado'
               WHERE id_servicio = ? AND id_conductor IS NULL AND estado = 'pendiente'""",
            (id_conductor, id_servicio),
        )
        if cur.rowcount == 1:
            return True, "Servicio aceptado correctamente."
    return False, "Este servicio ya no está disponible o fue asignado a otro conductor."


def servicios_del_conductor(id_conductor: int, solo_activos: bool = False):
    filtro = "AND s.estado IN ('aceptado','en_curso')" if solo_activos else ""
    with get_connection() as conn:
        return conn.execute(
            f"""SELECT s.*, t.nombre AS tipo
                FROM SERVICIO s
                JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
                WHERE s.id_conductor = ? {filtro}
                ORDER BY COALESCE(s.fecha_programada, s.fecha_solicitud) DESC""",
            (id_conductor,),
        ).fetchall()


def resumen_conductor(id_conductor: int) -> dict:
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT COUNT(*) AS servicios,
                      COALESCE(SUM(precio), 0) AS ganancias,
                      AVG(puntuacion) AS calificacion
               FROM SERVICIO
               WHERE id_conductor = ? AND estado = 'finalizado'
                 AND date(fecha_solicitud) = date('now', 'localtime')""",
            (id_conductor,),
        ).fetchone()
    return {
        "servicios": fila["servicios"],
        "ganancias": fila["ganancias"],
        "calificacion": round(fila["calificacion"], 1) if fila["calificacion"] else None,
    }


# ---------------------------------------------------------------- Helpers internos

def _servicio_propio(conn, id_servicio: int, id_conductor: int, estado: str):
    return conn.execute(
        """SELECT s.id_servicio, s.estado, t.nombre AS tipo
           FROM SERVICIO s
           JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
           WHERE s.id_servicio = ? AND s.id_conductor = ? AND s.estado = ?""",
        (id_servicio, id_conductor, estado),
    ).fetchone()


def _recogido(conn, id_servicio: int, tipo: str) -> bool:
    """Devuelve True si el paquete o pasajero ya fue recogido. False en caso contrario."""
    if tipo == "Courier":
        fila = conn.execute(
            "SELECT estado_entrega FROM COURIER WHERE id_servicio = ?", (id_servicio,)
        ).fetchone()
        return fila is not None and fila["estado_entrega"] in ("recogido", "entregado")
    
    # Para Mototaxi
    fila = conn.execute(
        "SELECT hora_recogida FROM VIAJE_MENOR WHERE id_servicio = ?", (id_servicio,)
    ).fetchone()
    
    # Si no hay fila, es porque no se ha recogido (o no hay menor). Retorna False.
    if fila is None:
        return False
        
    # Si hay fila, retorna True solo si hora_recogida tiene un valor
    return bool(fila["hora_recogida"])


def obtener_servicio_conductor(id_servicio: int, id_conductor: int):
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT s.*, t.nombre AS tipo,
                      u.nombre || ' ' || u.apellido AS cliente,
                      u.telefono AS cliente_telefono
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               JOIN CLIENTE c ON c.id_cliente = s.id_cliente
               JOIN USUARIO u ON u.id_usuario = c.id_usuario
               WHERE s.id_servicio = ? AND s.id_conductor = ?""",
            (id_servicio, id_conductor),
        ).fetchone()
        if fila is None:
            return None
        menor = conn.execute(
            """SELECT m.nombre, m.apellido, m.colegio, m.contacto_emergencia,
                      v.hora_recogida, v.hora_llegada, v.estado_entrega
               FROM VIAJE_MENOR v
               JOIN MENOR m ON m.id_menor = v.id_menor
               WHERE v.id_servicio = ?""",
            (id_servicio,),
        ).fetchone()
        courier = conn.execute(
            "SELECT * FROM COURIER WHERE id_servicio = ?", (id_servicio,)
        ).fetchone()
        recogido = _recogido(conn, id_servicio, fila["tipo"])
    return {
        "s": dict(fila),
        "menor": dict(menor) if menor else None,
        "courier": dict(courier) if courier else None,
        "recogido": recogido,
    }


def iniciar_servicio(id_servicio: int, id_conductor: int):
    with get_connection() as conn:
        otro = conn.execute(
            """SELECT 1 FROM SERVICIO
               WHERE id_conductor = ? AND estado = 'en_curso' AND id_servicio != ?""",
            (id_conductor, id_servicio),
        ).fetchone()
        if otro:
            return False, "Ya tienes un viaje en curso. Finalízalo antes de iniciar otro."
        cur = conn.execute(
            """UPDATE SERVICIO SET estado = 'en_curso'
               WHERE id_servicio = ? AND id_conductor = ? AND estado = 'aceptado'""",
            (id_servicio, id_conductor),
        )
        if cur.rowcount == 1:
            return True, "Viaje iniciado."
    return False, "Este servicio no se puede iniciar."


def confirmar_recogida(id_servicio: int, id_conductor: int):
    with get_connection() as conn:
        s = _servicio_propio(conn, id_servicio, id_conductor, "en_curso")
        if s is None:
            return False, "El viaje debe estar en curso para confirmar la recogida."
        if s["tipo"] == "Courier":
            cur = conn.execute(
                """UPDATE COURIER SET estado_entrega = 'recogido'
                   WHERE id_servicio = ? AND estado_entrega = 'pendiente'""",
                (id_servicio,),
            )
            mensaje = "Paquete recogido."
        else:
            cur = conn.execute(
                """UPDATE VIAJE_MENOR
                   SET hora_recogida = datetime('now','localtime'), estado_entrega = 'recogido'
                   WHERE id_servicio = ? AND hora_recogida IS NULL""",
                (id_servicio,),
            )
            mensaje = "Pasajero recogido."
        if cur.rowcount == 1:
            return True, mensaje
    return False, "La recogida ya estaba registrada o no aplica a este servicio."


def finalizar_servicio(id_servicio: int, id_conductor: int, tipo_esperado: str):
    with get_connection() as conn:
        s = _servicio_propio(conn, id_servicio, id_conductor, "en_curso")
        if s is None:
            return False, "El servicio debe estar en curso para finalizarlo."
        if s["tipo"] != tipo_esperado:
            return False, "Esta acción no corresponde al tipo de servicio."
        if not _recogido(conn, id_servicio, s["tipo"]):
            return False, "Primero confirma la recogida."
        conn.execute(
            """UPDATE SERVICIO SET estado = 'finalizado'
               WHERE id_servicio = ? AND id_conductor = ? AND estado = 'en_curso'""",
            (id_servicio, id_conductor),
        )
        if s["tipo"] == "Courier":
            conn.execute(
                "UPDATE COURIER SET estado_entrega = 'entregado' WHERE id_servicio = ?",
                (id_servicio,),
            )
            return True, "Entrega confirmada."
        conn.execute(
            """UPDATE VIAJE_MENOR
               SET hora_llegada = datetime('now','localtime'), estado_entrega = 'entregado'
               WHERE id_servicio = ?""",
            (id_servicio,),
        )
        return True, "Viaje finalizado."


def registrar_ubicacion(id_servicio: int, id_conductor: int, latitud: float, longitud: float) -> bool:
    with get_connection() as conn:
        if _servicio_propio(conn, id_servicio, id_conductor, "en_curso") is None:
            return False
        conn.execute(
            """INSERT INTO SEGUIMIENTO (id_servicio, latitud, longitud, fecha_hora, estado)
               VALUES (?, ?, ?, datetime('now','localtime'), 'en_curso')""",
            (id_servicio, latitud, longitud),
        )
        return True


def historial_conductor(id_conductor: int, tipo=None, limite: int = 100):
    filtro = "AND t.nombre = ?" if tipo else ""
    params = [id_conductor] + ([tipo] if tipo else []) + [limite]
    with get_connection() as conn:
        return conn.execute(
            f"""SELECT s.*, t.nombre AS tipo
                FROM SERVICIO s
                JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
                WHERE s.id_conductor = ? {filtro}
                ORDER BY COALESCE(s.fecha_programada, s.fecha_solicitud) DESC
                LIMIT ?""",
            params,
        ).fetchall()


def ganancias_conductor(id_conductor: int) -> dict:
    periodos = {
        "hoy": "date(fecha_solicitud) = date('now','localtime')",
        "semana": "date(fecha_solicitud) >= date('now','localtime','-6 days')",
        "mes": "strftime('%Y-%m', fecha_solicitud) = strftime('%Y-%m','now','localtime')",
    }
    columnas = ", ".join(
        f"COALESCE(SUM(CASE WHEN {cond} THEN 1 END), 0) AS {k}_n, "
        f"COALESCE(SUM(CASE WHEN {cond} THEN precio END), 0) AS {k}_t"
        for k, cond in periodos.items()
    )
    with get_connection() as conn:
        fila = conn.execute(
            f"SELECT {columnas} FROM SERVICIO WHERE id_conductor = ? AND estado = 'finalizado'",
            (id_conductor,),
        ).fetchone()
    return {
        k: {"servicios": fila[f"{k}_n"], "total": float(fila[f"{k}_t"])} for k in periodos
    }


def detalle_ganancias(id_conductor: int, limite: int = 50):
    with get_connection() as conn:
        return conn.execute(
            """SELECT s.*, t.nombre AS tipo
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               WHERE s.id_conductor = ? AND s.estado = 'finalizado'
               ORDER BY COALESCE(s.fecha_programada, s.fecha_solicitud) DESC
               LIMIT ?""",
            (id_conductor, limite),
        ).fetchall()


# ---------------------------------------------------------------- Cliente

def servicios_del_cliente(id_cliente: int, limite: int = 5):
    with get_connection() as conn:
        return conn.execute(
            """SELECT s.*, s.id_servicio AS id, t.nombre AS tipo
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               WHERE s.id_cliente = ?
               ORDER BY s.fecha_solicitud DESC LIMIT ?""",
            (id_cliente, limite),
        ).fetchall()


def calcular_tarifa(tipo_nombre: str) -> float:
    try:
        with get_connection() as conn:
            fila = conn.execute(
                """SELECT f.precio FROM TARIFA f
                   JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = f.id_tipo_servicio
                   WHERE t.nombre = ?""",
                (tipo_nombre,),
            ).fetchone()
    except sqlite3.OperationalError:
        fila = None
    if fila is not None:
        return float(fila["precio"])
    return TARIFAS_BASE.get(tipo_nombre, 0.0)


def conductores_disponibles() -> int:
    with get_connection() as conn:
        return conn.execute(
            """SELECT COUNT(*) FROM CONDUCTOR
               WHERE estado_validacion = 'aprobado' AND disponibilidad = 'disponible'"""
        ).fetchone()[0]


def crear_servicio(id_cliente: int, tipo_nombre: str, origen: str, destino: str,
                   precio: float, fecha_programada=None, 
                   origen_lat=None, origen_lng=None, destino_lat=None, destino_lng=None) -> int:
    """MODIFICADO: Acepta y guarda las coordenadas de origen y destino."""
    with get_connection() as conn:
        tipo = conn.execute(
            "SELECT id_tipo_servicio FROM TIPO_SERVICIO WHERE nombre = ?", (tipo_nombre,)
        ).fetchone()
        if tipo is None:
            raise ValueError(f"El tipo de servicio '{tipo_nombre}' no existe en TIPO_SERVICIO")
        cur = conn.execute(
            """INSERT INTO SERVICIO (id_cliente, id_tipo_servicio, fecha_solicitud,
                                     fecha_programada, origen, destino, precio, estado,
                                     origen_lat, origen_lng, destino_lat, destino_lng)
               VALUES (?, ?, datetime('now','localtime'), ?, ?, ?, ?, 'pendiente', ?, ?, ?, ?)""",
            (id_cliente, tipo["id_tipo_servicio"], fecha_programada, origen, destino, precio,
             origen_lat, origen_lng, destino_lat, destino_lng),
        )
        return cur.lastrowid


def crear_viaje_menor(id_servicio: int, id_menor: int) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO VIAJE_MENOR (id_servicio, id_menor, estado_entrega)
               VALUES (?, ?, 'pendiente')""",
            (id_servicio, id_menor),
        )
        return cur.lastrowid


def crear_courier(id_servicio: int, id_empresa, descripcion: str,
                  nombre_destinatario: str, telefono_destinatario: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO COURIER (id_servicio, id_empresa, descripcion_paquete,
                                    nombre_destinatario, telefono_destinatario, estado_entrega)
               VALUES (?, ?, ?, ?, ?, 'pendiente')""",
            (id_servicio, id_empresa, descripcion, nombre_destinatario, telefono_destinatario),
        )
        return cur.lastrowid


def obtener_servicio_cliente(id_servicio: int, id_cliente: int):
    """Devuelve el servicio y calcula el estado de 'recogida' para mototaxi y courier."""
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT s.*, s.id_servicio AS id, t.nombre AS tipo,
                      c.descripcion_vehiculo AS vehiculo,
                      u.nombre || ' ' || u.apellido AS conductor_nombre
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               LEFT JOIN CONDUCTOR c ON c.id_conductor = s.id_conductor
               LEFT JOIN USUARIO u ON u.id_usuario = c.id_usuario
               WHERE s.id_servicio = ? AND s.id_cliente = ?""",
            (id_servicio, id_cliente),
        ).fetchone()
        if fila is None:
            return None
            
        # Verificamos la recogida según el tipo
        tipo = fila["tipo"]
        recogida = False
        if tipo == "Courier":
            courier = conn.execute(
                "SELECT estado_entrega FROM COURIER WHERE id_servicio = ?", (id_servicio,)
            ).fetchone()
            recogida = courier is not None and courier["estado_entrega"] in ("recogido", "entregado")
        else:
            viaje = conn.execute(
                "SELECT hora_recogida FROM VIAJE_MENOR WHERE id_servicio = ?", (id_servicio,)
            ).fetchone()
            recogida = bool(viaje and viaje["hora_recogida"])

    servicio = dict(fila)
    estado = servicio["estado"]
    inicio = estado in ("en_curso", "finalizado")
    servicio.update(inicio=inicio, recogida=recogida, fin=estado == "finalizado")
    return servicio


def ultima_ubicacion(id_servicio: int):
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT latitud, longitud, fecha_hora, estado
               FROM SEGUIMIENTO
               WHERE id_servicio = ?
               ORDER BY fecha_hora DESC, id_seguimiento DESC
               LIMIT 1""",
            (id_servicio,),
        ).fetchone()
    return dict(fila) if fila else None


def servicios_activos_del_cliente(id_cliente: int):
    with get_connection() as conn:
        return conn.execute(
            """SELECT s.id_servicio AS id, s.origen, s.destino, s.estado, t.nombre AS tipo
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               WHERE s.id_cliente = ? AND s.estado IN ('pendiente','aceptado','en_curso')
               ORDER BY 
                   CASE s.estado 
                       WHEN 'en_curso' THEN 1 
                       WHEN 'aceptado' THEN 2 
                       WHEN 'pendiente' THEN 3 
                       ELSE 4 
                   END,
                   s.fecha_solicitud DESC""",
            (id_cliente,),
        ).fetchall()


def historial_viajes(id_cliente: int, limite: int = 50):
    with get_connection() as conn:
        return conn.execute(
            """SELECT s.id_servicio AS id, s.fecha_solicitud, s.origen, s.destino,
                      s.precio AS tarifa, s.estado, s.puntuacion AS calificacion,
                      t.nombre AS tipo
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               WHERE s.id_cliente = ? AND t.nombre = 'Mototaxi'
               ORDER BY s.fecha_solicitud DESC
               LIMIT ?""",
            (id_cliente, limite),
        ).fetchall()


def historial_envios(id_cliente: int, limite: int = 50):
    with get_connection() as conn:
        return conn.execute(
            """SELECT s.id_servicio AS id, s.fecha_solicitud, s.origen, s.destino,
                      s.precio AS tarifa, s.estado,
                      c.nombre_destinatario AS dest_nombre,
                      c.descripcion_paquete AS tipo_envio
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               LEFT JOIN COURIER c ON c.id_servicio = s.id_servicio
               WHERE s.id_cliente = ? AND t.nombre = 'Courier'
               ORDER BY s.fecha_solicitud DESC
               LIMIT ?""",
            (id_cliente, limite),
        ).fetchall()


def calificar_servicio(id_servicio: int, id_cliente: int, puntuacion: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE SERVICIO SET puntuacion = ?
               WHERE id_servicio = ? AND id_cliente = ?
                 AND estado = 'finalizado' AND puntuacion IS NULL""",
            (puntuacion, id_servicio, id_cliente),
        )
        return cur.rowcount == 1


# ---------------------------------------------------------------- Administrador

def metricas_generales() -> dict:
    with get_connection() as conn:
        def q(sql):
            return conn.execute(sql).fetchone()[0]
        return {
            "servicios_total": q("SELECT COUNT(*) FROM SERVICIO"),
            "servicios_activos": q("SELECT COUNT(*) FROM SERVICIO WHERE estado IN ('aceptado','en_curso')"),
            "ingresos": q("SELECT COALESCE(SUM(monto),0) FROM PAGO WHERE estado_pago = 'pagado'"),
        }