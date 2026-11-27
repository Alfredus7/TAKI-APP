from database import get_connection


# ---------------------------------------------------------------- Cliente / perfil

def obtener_cliente_por_usuario(id_usuario: int):
    with get_connection() as conn:
        return conn.execute(
            """SELECT c.id_cliente, c.id_usuario, c.tipo_cliente, c.direccion,
                      u.nombre, u.apellido, u.correo
               FROM CLIENTE c
               JOIN USUARIO u ON u.id_usuario = c.id_usuario
               WHERE c.id_usuario = ?""",
            (id_usuario,),
        ).fetchone()


def obtener_perfil(id_usuario: int):
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT u.nombre, u.apellido, u.ci AS documento, u.telefono, u.correo,
                      c.direccion, c.tipo_cliente
               FROM USUARIO u
               JOIN CLIENTE c ON c.id_usuario = u.id_usuario
               WHERE u.id_usuario = ?""",
            (id_usuario,),
        ).fetchone()
    return dict(fila) if fila else None


def actualizar_perfil(id_usuario: int, datos: dict) -> None:
    """Puede lanzar sqlite3.IntegrityError si el correo o la CI ya existen."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE USUARIO
               SET nombre = ?, apellido = ?, ci = ?, telefono = ?, correo = ?
               WHERE id_usuario = ?""",
            (datos["nombre"], datos["apellido"], datos["ci"],
             datos.get("telefono"), datos["correo"], id_usuario),
        )
        conn.execute(
            "UPDATE CLIENTE SET tipo_cliente = ?, direccion = ? WHERE id_usuario = ?",
            (datos["tipo_cliente"], datos.get("direccion"), id_usuario),
        )


def obtener_empresa_id(id_cliente: int):
    """id_empresa si el cliente es una empresa, None si es padre de familia."""
    with get_connection() as conn:
        fila = conn.execute(
            "SELECT id_empresa FROM EMPRESA WHERE id_cliente = ?", (id_cliente,)
        ).fetchone()
    return fila["id_empresa"] if fila else None





# ---------------------------------------------------------------- Menores

def listar_menores(id_cliente: int):
    with get_connection() as conn:
        return conn.execute(
            """SELECT id_menor AS id, nombre AS nombres, apellido AS apellidos,
                      fecha_nacimiento, colegio AS institucion, contacto_emergencia
               FROM MENOR
               WHERE id_cliente = ?
               ORDER BY nombre""",
            (id_cliente,),
        ).fetchall()


def obtener_menor(id_menor: int, id_cliente: int):
    """Devuelve el menor solo si pertenece al cliente indicado."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM MENOR WHERE id_menor = ? AND id_cliente = ?",
            (id_menor, id_cliente),
        ).fetchone()


def crear_menor(id_cliente: int, datos: dict) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO MENOR (id_cliente, nombre, apellido, fecha_nacimiento,
                                  colegio, contacto_emergencia)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (id_cliente, datos["nombre"], datos["apellido"], datos.get("fecha_nacimiento"),
             datos.get("colegio"), datos.get("contacto_emergencia")),
        )
        return cur.lastrowid


def actualizar_menor(id_menor: int, id_cliente: int, datos: dict) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE MENOR
               SET nombre = ?, apellido = ?, fecha_nacimiento = ?,
                   colegio = ?, contacto_emergencia = ?
               WHERE id_menor = ? AND id_cliente = ?""",
            (datos["nombre"], datos["apellido"], datos.get("fecha_nacimiento"),
             datos.get("colegio"), datos.get("contacto_emergencia"),
             id_menor, id_cliente),
        )
        return cur.rowcount == 1


def colegios_frecuentes(id_cliente: int) -> list:
    """Colegios de los menores del cliente; sirven como destinos sugeridos."""
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT DISTINCT colegio FROM MENOR
               WHERE id_cliente = ? AND colegio IS NOT NULL AND colegio <> ''""",
            (id_cliente,),
        ).fetchall()
    return [f["colegio"] for f in filas]


# ---------------------------------------------------------------- Pagos

def servicio_pagado(id_servicio: int) -> bool:
    with get_connection() as conn:
        fila = conn.execute(
            "SELECT 1 FROM PAGO WHERE id_servicio = ? AND estado_pago = 'pagado'",
            (id_servicio,),
        ).fetchone()
    return fila is not None


def pagos_pendientes(id_cliente: int):
    """Servicios finalizados que todavía no tienen un pago registrado."""
    with get_connection() as conn:
        return conn.execute(
            """SELECT s.id_servicio AS id, s.fecha_solicitud, s.precio AS tarifa,
                      t.nombre AS tipo
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               WHERE s.id_cliente = ? AND s.estado = 'finalizado'
                 AND NOT EXISTS (
                     SELECT 1 FROM PAGO p
                     WHERE p.id_servicio = s.id_servicio AND p.estado_pago = 'pagado')
               ORDER BY s.fecha_solicitud DESC""",
            (id_cliente,),
        ).fetchall()


def historial_pagos(id_cliente: int, limite: int = 50):
    with get_connection() as conn:
        return conn.execute(
            """SELECT p.fecha_pago AS fecha,
                      t.nombre || ' #' || s.id_servicio AS descripcion,
                      p.monto, p.metodo_pago AS metodo
               FROM PAGO p
               JOIN SERVICIO s ON s.id_servicio = p.id_servicio
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               WHERE s.id_cliente = ?
               ORDER BY p.fecha_pago DESC
               LIMIT ?""",
            (id_cliente, limite),
        ).fetchall()


def registrar_pago(id_servicio: int, monto: float, metodo: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO PAGO (id_servicio, monto, metodo_pago, fecha_pago, estado_pago)
               VALUES (?, ?, ?, datetime('now','localtime'), 'pagado')""",
            (id_servicio, monto, metodo),
        )
        return cur.lastrowid


# ---------------------------------------------------------------- Atención al cliente

def crear_consulta(id_usuario: int, tipo: str, mensaje: str, id_servicio=None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO CONSULTA (id_usuario, id_servicio, tipo, mensaje, estado, fecha)
               VALUES (?, ?, ?, ?, 'pendiente', datetime('now','localtime'))""",
            (id_usuario, id_servicio, tipo, mensaje),
        )
        return cur.lastrowid


def listar_consultas(id_usuario: int, limite: int = 20):
    with get_connection() as conn:
        return conn.execute(
            """SELECT id_consulta AS id, tipo, mensaje, estado, fecha
               FROM CONSULTA
               WHERE id_usuario = ?
               ORDER BY fecha DESC
               LIMIT ?""",
            (id_usuario, limite),
        ).fetchall()


# ---------------------------------------------------------------- Notificaciones

MENSAJES_ESTADO = {
    "pendiente": "Tu solicitud fue registrada y está buscando conductor.",
    "aceptado": "Un conductor aceptó tu servicio.",
    "en_curso": "Tu servicio está en curso.",
    "finalizado": "Tu servicio finalizó. Ya puedes pagar y calificar.",
    "cancelado": "Tu servicio fue cancelado.",
}


def notificaciones_cliente(id_cliente: int, limite: int = 20) -> list:
    """
    El esquema no guarda notificaciones; se derivan de los servicios del cliente.
    Si más adelante agregas una tabla NOTIFICACION, reemplaza esta función.
    """
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT s.estado, s.fecha_solicitud, t.nombre AS tipo
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               WHERE s.id_cliente = ?
               ORDER BY s.fecha_solicitud DESC
               LIMIT ?""",
            (id_cliente, limite),
        ).fetchall()
    return [
        {
            "tipo": f["tipo"],
            "mensaje": MENSAJES_ESTADO.get(f["estado"], f["estado"]),
            "fecha": f["fecha_solicitud"],
            "leida": True,
        }
        for f in filas
    ]
