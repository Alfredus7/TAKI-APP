"""Consultas del módulo administrador."""
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from database import get_connection
from models import servicio_model

ROLES = ("cliente", "conductor", "administrador")
ESTADOS_USUARIO = ("activo", "inactivo", "suspendido")
ESTADOS_SERVICIO = ("pendiente", "aceptado", "en_curso", "finalizado", "cancelado")
ESTADOS_CONSULTA = ("pendiente", "en_revision", "resuelto")
TIPOS_CONSULTA = ("consulta", "reclamo", "sugerencia")
METODOS_PAGO = ("efectivo", "tarjeta", "transferencia", "qr")
ESTADOS_PAGO = ("pendiente", "pagado")
MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _donde(condiciones):
    return ("WHERE " + " AND ".join(condiciones)) if condiciones else ""


# ---------------------------------------------------------------- Dashboard

def metricas_dashboard() -> dict:
    with get_connection() as conn:
        def q(sql):
            return conn.execute(sql).fetchone()[0]
        return {
            "servicios_total": q("SELECT COUNT(*) FROM SERVICIO"),
            "servicios_activos": q("SELECT COUNT(*) FROM SERVICIO WHERE estado IN ('aceptado','en_curso')"),
            "ingresos": float(q("SELECT COALESCE(SUM(monto),0) FROM PAGO WHERE estado_pago = 'pagado'")),
            "pendientes_validacion": q("SELECT COUNT(*) FROM CONDUCTOR WHERE estado_validacion = 'pendiente'"),
            "reclamos_abiertos": q("SELECT COUNT(*) FROM CONSULTA WHERE estado IN ('pendiente','en_revision')"),
            "sin_conductor": q("SELECT COUNT(*) FROM SERVICIO WHERE estado = 'pendiente' AND id_conductor IS NULL"),
            "conductores_en_linea": q(
                "SELECT COUNT(*) FROM CONDUCTOR WHERE estado_validacion = 'aprobado' AND disponibilidad = 'disponible'"
            ),
            "conductores_aprobados": q("SELECT COUNT(*) FROM CONDUCTOR WHERE estado_validacion = 'aprobado'"),
            "calificacion_promedio": (lambda v: round(v, 1) if v else None)(
                q("SELECT AVG(puntuacion) FROM SERVICIO WHERE estado = 'finalizado' AND puntuacion IS NOT NULL")
            ),
        }


def series_dashboard(dias: int = 7) -> dict:
    """Servicios solicitados e ingresos cobrados por día, de los últimos `dias` días (incluye hoy)."""
    with get_connection() as conn:
        hoy = date.fromisoformat(conn.execute("SELECT date('now','localtime')").fetchone()[0])
        desde = f"-{dias - 1} days"
        servicios = {r["d"]: r["n"] for r in conn.execute(
            """SELECT date(fecha_solicitud) AS d, COUNT(*) AS n FROM SERVICIO
               WHERE estado != 'cancelado' AND date(fecha_solicitud) >= date('now','localtime', ?)
               GROUP BY d""", (desde,)).fetchall()}
        ingresos = {r["d"]: float(r["t"]) for r in conn.execute(
            """SELECT date(fecha_pago) AS d, SUM(monto) AS t FROM PAGO
               WHERE estado_pago = 'pagado' AND date(fecha_pago) >= date('now','localtime', ?)
               GROUP BY d""", (desde,)).fetchall()}
    fechas = [(hoy - timedelta(days=i)).isoformat() for i in range(dias - 1, -1, -1)]
    return {
        "servicios": [servicios.get(f, 0) for f in fechas],
        "ingresos": [ingresos.get(f, 0.0) for f in fechas],
    }


def servicios_por_mes(meses: int = 6):
    """Solicitados y finalizados por mes, de los últimos `meses` meses (incluye el actual)."""
    with get_connection() as conn:
        hoy = date.fromisoformat(conn.execute("SELECT date('now','localtime')").fetchone()[0])
        claves = []
        anio, mes = hoy.year, hoy.month
        for _ in range(meses):
            claves.append((anio, mes))
            mes -= 1
            if mes == 0:
                anio, mes = anio - 1, 12
        claves.reverse()
        inicio = f"{claves[0][0]:04d}-{claves[0][1]:02d}-01"
        filas = {r["m"]: r for r in conn.execute(
            """SELECT strftime('%Y-%m', fecha_solicitud) AS m, COUNT(*) AS total,
                      SUM(CASE WHEN estado = 'finalizado' THEN 1 ELSE 0 END) AS finalizados
               FROM SERVICIO WHERE date(fecha_solicitud) >= ? GROUP BY m""", (inicio,)).fetchall()}
    resultado = []
    for anio, mes in claves:
        f = filas.get(f"{anio:04d}-{mes:02d}")
        resultado.append({"mes": MESES_CORTOS[mes - 1],
                          "solicitados": f["total"] if f else 0,
                          "finalizados": (f["finalizados"] or 0) if f else 0})
    return resultado


def disponibilidad_conductores() -> dict:
    """Conductores aprobados: ocupados (con servicio aceptado o en curso), libres (en línea) y fuera de línea."""
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT c.disponibilidad,
                      EXISTS(SELECT 1 FROM SERVICIO s
                              WHERE s.id_conductor = c.id_conductor
                                AND s.estado IN ('aceptado','en_curso')) AS ocupado
               FROM CONDUCTOR c WHERE c.estado_validacion = 'aprobado'"""
        ).fetchall()
    ocupados = sum(1 for f in filas if f["ocupado"])
    libres = sum(1 for f in filas if not f["ocupado"] and f["disponibilidad"] == "disponible")
    return {"total": len(filas), "ocupados": ocupados, "libres": libres,
            "fuera": len(filas) - ocupados - libres}


def servicios_activos(limite: int = 30):
    with get_connection() as conn:
        return conn.execute(
            """SELECT s.id_servicio, s.origen, s.destino, s.estado, t.nombre AS tipo,
                      uc.nombre || ' ' || uc.apellido AS cliente,
                      ud.nombre || ' ' || ud.apellido AS conductor
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               JOIN CLIENTE cl ON cl.id_cliente = s.id_cliente
               JOIN USUARIO uc ON uc.id_usuario = cl.id_usuario
               LEFT JOIN CONDUCTOR cd ON cd.id_conductor = s.id_conductor
               LEFT JOIN USUARIO ud ON ud.id_usuario = cd.id_usuario
               WHERE s.estado IN ('pendiente','aceptado','en_curso')
               ORDER BY s.fecha_solicitud DESC LIMIT ?""",
            (limite,),
        ).fetchall()


# ---------------------------------------------------------------- Usuarios

def listar_usuarios(q=None, rol=None, estado=None, limite: int = 200):
    cond, params = [], []
    if q:
        like = f"%{q}%"
        cond.append("(nombre LIKE ? OR apellido LIKE ? OR ci LIKE ? OR correo LIKE ? "
                    "OR (nombre || ' ' || apellido) LIKE ?)")
        params += [like] * 5
    if rol:
        cond.append("rol = ?")
        params.append(rol)
    if estado:
        cond.append("estado = ?")
        params.append(estado)
    with get_connection() as conn:
        return conn.execute(
            f"""SELECT id_usuario, nombre, apellido, ci, telefono, correo, rol, estado
                FROM USUARIO {_donde(cond)} ORDER BY apellido, nombre LIMIT ?""",
            params + [limite],
        ).fetchall()


def obtener_usuario(id_usuario: int):
    """Datos del usuario sin la contraseña, o None."""
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT id_usuario, nombre, apellido, ci, telefono, correo, rol, estado
               FROM USUARIO WHERE id_usuario = ?""",
            (id_usuario,),
        ).fetchone()
    return dict(fila) if fila else None


def _apagar_conductor(conn, id_usuario: int) -> None:
    """Un conductor desactivado/suspendido deja de recibir solicitudes."""
    conn.execute(
        "UPDATE CONDUCTOR SET disponibilidad = 'no_disponible' WHERE id_usuario = ?", (id_usuario,)
    )


def actualizar_usuario(id_usuario: int, datos: dict) -> None:
    """Lanza sqlite3.IntegrityError si el CI o el correo ya existen."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE USUARIO SET nombre = ?, apellido = ?, ci = ?, telefono = ?, correo = ?, estado = ?
               WHERE id_usuario = ?""",
            (datos["nombre"], datos["apellido"], datos["ci"], datos.get("telefono"),
             datos["correo"], datos["estado"], id_usuario),
        )
        if datos.get("contrasena"):
            conn.execute(
                "UPDATE USUARIO SET contrasena = ? WHERE id_usuario = ?",
                (generate_password_hash(datos["contrasena"]), id_usuario),
            )
        if datos["estado"] != "activo":
            _apagar_conductor(conn, id_usuario)


def cambiar_estado_usuario(id_usuario: int, estado: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE USUARIO SET estado = ? WHERE id_usuario = ?", (estado, id_usuario)
        )
        if cur.rowcount == 1 and estado != "activo":
            _apagar_conductor(conn, id_usuario)
        return cur.rowcount == 1


# ---------------------------------------------------------------- Conductores y vehículos

def listar_conductores(validacion=None):
    cond, params = [], []
    if validacion:
        cond.append("c.estado_validacion = ?")
        params.append(validacion)
    with get_connection() as conn:
        return conn.execute(
            f"""SELECT c.id_conductor, u.id_usuario, u.nombre, u.apellido, u.ci, u.telefono,
                       u.correo, u.estado, c.licencia, c.descripcion_vehiculo,
                       c.estado_validacion, c.disponibilidad,
                       (SELECT COUNT(*) FROM SERVICIO s
                         WHERE s.id_conductor = c.id_conductor AND s.estado = 'finalizado') AS servicios,
                       (SELECT AVG(s.puntuacion) FROM SERVICIO s
                         WHERE s.id_conductor = c.id_conductor AND s.puntuacion IS NOT NULL) AS calificacion
                FROM CONDUCTOR c
                JOIN USUARIO u ON u.id_usuario = c.id_usuario
                {_donde(cond)}
                ORDER BY u.apellido, u.nombre""",
            params,
        ).fetchall()


def obtener_conductor(id_conductor: int):
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT c.id_conductor, u.id_usuario, u.nombre, u.apellido, u.ci, u.telefono,
                      u.correo, u.estado, c.licencia, c.descripcion_vehiculo,
                      c.estado_validacion, c.disponibilidad
               FROM CONDUCTOR c JOIN USUARIO u ON u.id_usuario = c.id_usuario
               WHERE c.id_conductor = ?""",
            (id_conductor,),
        ).fetchone()
    return dict(fila) if fila else None


def resumen_conductor_total(id_conductor: int) -> dict:
    """Totales históricos del conductor (servicios finalizados)."""
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT COUNT(*) AS servicios, COALESCE(SUM(precio), 0) AS ganancias,
                      AVG(puntuacion) AS calificacion
               FROM SERVICIO WHERE id_conductor = ? AND estado = 'finalizado'""",
            (id_conductor,),
        ).fetchone()
    return {
        "servicios": fila["servicios"],
        "ganancias": float(fila["ganancias"]),
        "calificacion": round(fila["calificacion"], 1) if fila["calificacion"] else None,
    }


def validar_conductor(id_conductor: int, aprobar: bool) -> bool:
    nuevo = "aprobado" if aprobar else "rechazado"
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE CONDUCTOR SET estado_validacion = ? WHERE id_conductor = ?", (nuevo, id_conductor)
        )
        if cur.rowcount == 1 and not aprobar:
            conn.execute(
                "UPDATE CONDUCTOR SET disponibilidad = 'no_disponible' WHERE id_conductor = ?",
                (id_conductor,),
            )
        return cur.rowcount == 1


def actualizar_vehiculo(id_conductor: int, descripcion: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE CONDUCTOR SET descripcion_vehiculo = ? WHERE id_conductor = ?",
            (descripcion, id_conductor),
        )
        return cur.rowcount == 1


# ---------------------------------------------------------------- Servicios (viajes y courier)

def listar_servicios(tipo: str, estado=None, desde=None, hasta=None, limite: int = 200):
    cond, params = ["t.nombre = ?"], [tipo]
    if estado:
        cond.append("s.estado = ?")
        params.append(estado)
    if desde:
        cond.append("date(s.fecha_solicitud) >= ?")
        params.append(desde)
    if hasta:
        cond.append("date(s.fecha_solicitud) <= ?")
        params.append(hasta)
    with get_connection() as conn:
        return conn.execute(
            f"""SELECT s.id_servicio, s.fecha_solicitud, s.fecha_programada, s.origen, s.destino,
                       s.precio, s.estado, t.nombre AS tipo,
                       uc.nombre || ' ' || uc.apellido AS cliente,
                       ud.nombre || ' ' || ud.apellido AS conductor,
                       m.nombre || ' ' || m.apellido AS menor,
                       co.descripcion_paquete AS paquete,
                       co.nombre_destinatario AS destinatario
                FROM SERVICIO s
                JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
                JOIN CLIENTE cl ON cl.id_cliente = s.id_cliente
                JOIN USUARIO uc ON uc.id_usuario = cl.id_usuario
                LEFT JOIN CONDUCTOR cd ON cd.id_conductor = s.id_conductor
                LEFT JOIN USUARIO ud ON ud.id_usuario = cd.id_usuario
                LEFT JOIN VIAJE_MENOR vm ON vm.id_servicio = s.id_servicio
                LEFT JOIN MENOR m ON m.id_menor = vm.id_menor
                LEFT JOIN COURIER co ON co.id_servicio = s.id_servicio
                {_donde(cond)}
                ORDER BY s.fecha_solicitud DESC, s.id_servicio DESC LIMIT ?""",
            params + [limite],
        ).fetchall()


def obtener_servicio(id_servicio: int):
    """Detalle completo para el administrador, o None.
    Devuelve {'s','menor','courier','pagos','ubicacion'}."""
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT s.*, t.nombre AS tipo,
                      uc.nombre || ' ' || uc.apellido AS cliente, uc.telefono AS cliente_telefono,
                      ud.nombre || ' ' || ud.apellido AS conductor, ud.telefono AS conductor_telefono,
                      cd.descripcion_vehiculo AS vehiculo
               FROM SERVICIO s
               JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               JOIN CLIENTE cl ON cl.id_cliente = s.id_cliente
               JOIN USUARIO uc ON uc.id_usuario = cl.id_usuario
               LEFT JOIN CONDUCTOR cd ON cd.id_conductor = s.id_conductor
               LEFT JOIN USUARIO ud ON ud.id_usuario = cd.id_usuario
               WHERE s.id_servicio = ?""",
            (id_servicio,),
        ).fetchone()
        if fila is None:
            return None
        menor = conn.execute(
            """SELECT m.nombre, m.apellido, m.colegio, v.hora_recogida, v.hora_llegada, v.estado_entrega
               FROM VIAJE_MENOR v JOIN MENOR m ON m.id_menor = v.id_menor
               WHERE v.id_servicio = ?""",
            (id_servicio,),
        ).fetchone()
        courier = conn.execute("SELECT * FROM COURIER WHERE id_servicio = ?", (id_servicio,)).fetchone()
        pagos = conn.execute(
            "SELECT * FROM PAGO WHERE id_servicio = ? ORDER BY id_pago", (id_servicio,)
        ).fetchall()
    return {
        "s": dict(fila),
        "menor": dict(menor) if menor else None,
        "courier": dict(courier) if courier else None,
        "pagos": pagos,
        "ubicacion": servicio_model.ultima_ubicacion(id_servicio),
    }


def cancelar_servicio(id_servicio: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE SERVICIO SET estado = 'cancelado'
               WHERE id_servicio = ? AND estado IN ('pendiente','aceptado','en_curso')""",
            (id_servicio,),
        )
        return cur.rowcount == 1


# ---------------------------------------------------------------- Pagos

def _filtros_pago(estado, metodo, desde, hasta):
    cond, params = [], []
    if estado:
        cond.append("p.estado_pago = ?")
        params.append(estado)
    if metodo:
        cond.append("p.metodo_pago = ?")
        params.append(metodo)
    if desde:
        cond.append("date(p.fecha_pago) >= ?")
        params.append(desde)
    if hasta:
        cond.append("date(p.fecha_pago) <= ?")
        params.append(hasta)
    return _donde(cond), params


_FROM_PAGO = """FROM PAGO p
                JOIN SERVICIO s ON s.id_servicio = p.id_servicio
                JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
                JOIN CLIENTE cl ON cl.id_cliente = s.id_cliente
                JOIN USUARIO uc ON uc.id_usuario = cl.id_usuario"""


def listar_pagos(estado=None, metodo=None, desde=None, hasta=None, limite: int = 200):
    donde, params = _filtros_pago(estado, metodo, desde, hasta)
    with get_connection() as conn:
        return conn.execute(
            f"""SELECT p.id_pago, p.id_servicio, p.monto, p.metodo_pago, p.fecha_pago, p.estado_pago,
                       t.nombre AS tipo, uc.nombre || ' ' || uc.apellido AS cliente
                {_FROM_PAGO} {donde}
                ORDER BY COALESCE(p.fecha_pago, '') DESC, p.id_pago DESC LIMIT ?""",
            params + [limite],
        ).fetchall()


def totales_pagos(estado=None, metodo=None, desde=None, hasta=None) -> dict:
    donde, params = _filtros_pago(estado, metodo, desde, hasta)
    with get_connection() as conn:
        fila = conn.execute(
            f"""SELECT COALESCE(SUM(CASE WHEN p.estado_pago = 'pagado' THEN p.monto END), 0) AS pagado,
                       COALESCE(SUM(CASE WHEN p.estado_pago != 'pagado' THEN p.monto END), 0) AS pendiente,
                       COUNT(*) AS cantidad
                {_FROM_PAGO} {donde}""",
            params,
        ).fetchone()
    return {"pagado": float(fila["pagado"]), "pendiente": float(fila["pendiente"]),
            "cantidad": fila["cantidad"]}


# ---------------------------------------------------------------- Reclamos

def listar_consultas(tipo=None, estado=None, limite: int = 200):
    cond, params = [], []
    if tipo:
        cond.append("c.tipo = ?")
        params.append(tipo)
    if estado:
        cond.append("c.estado = ?")
        params.append(estado)
    with get_connection() as conn:
        return conn.execute(
            f"""SELECT c.id_consulta, c.id_servicio, c.tipo, c.mensaje, c.estado, c.fecha,
                       u.nombre || ' ' || u.apellido AS usuario, u.rol
                FROM CONSULTA c JOIN USUARIO u ON u.id_usuario = c.id_usuario
                {_donde(cond)}
                ORDER BY CASE c.estado WHEN 'resuelto' THEN 1 ELSE 0 END, c.fecha DESC LIMIT ?""",
            params + [limite],
        ).fetchall()


def cambiar_estado_consulta(id_consulta: int, estado: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE CONSULTA SET estado = ? WHERE id_consulta = ?", (estado, id_consulta)
        )
        return cur.rowcount == 1


# ---------------------------------------------------------------- Tarifas

def listar_tarifas():
    """Precio vigente por tipo de servicio (TARIFA; si no hay fila, usa TARIFAS_BASE)."""
    with get_connection() as conn:
        try:
            filas = conn.execute(
                """SELECT t.nombre AS tipo, f.precio
                   FROM TIPO_SERVICIO t
                   LEFT JOIN TARIFA f ON f.id_tipo_servicio = t.id_tipo_servicio
                   ORDER BY t.id_tipo_servicio"""
            ).fetchall()
        except sqlite3.OperationalError:  # TARIFA aún no existe (falta init_db)
            filas = conn.execute(
                "SELECT nombre AS tipo, NULL AS precio FROM TIPO_SERVICIO ORDER BY id_tipo_servicio"
            ).fetchall()
    return [
        {"tipo": f["tipo"],
         "precio": float(f["precio"]) if f["precio"] is not None
         else servicio_model.TARIFAS_BASE.get(f["tipo"], 0.0)}
        for f in filas
    ]


def actualizar_tarifa(tipo: str, precio: float) -> bool:
    with get_connection() as conn:
        t = conn.execute("SELECT id_tipo_servicio FROM TIPO_SERVICIO WHERE nombre = ?", (tipo,)).fetchone()
        if t is None:
            return False
        conn.execute(
            """INSERT INTO TARIFA (id_tipo_servicio, precio, fecha_actualizacion)
               VALUES (?, ?, datetime('now','localtime'))
               ON CONFLICT(id_tipo_servicio) DO UPDATE
               SET precio = excluded.precio, fecha_actualizacion = excluded.fecha_actualizacion""",
            (t["id_tipo_servicio"], precio),
        )
        return True


# ---------------------------------------------------------------- Promociones

def nombres_tipos_servicio():
    with get_connection() as conn:
        return [f["nombre"] for f in conn.execute(
            "SELECT nombre FROM TIPO_SERVICIO ORDER BY id_tipo_servicio").fetchall()]


def listar_promociones():
    with get_connection() as conn:
        return conn.execute(
            """SELECT p.id_promocion, p.codigo, p.descripcion, p.descuento, p.fecha_inicio,
                      p.fecha_fin, p.activa, t.nombre AS tipo_servicio
               FROM PROMOCION p
               LEFT JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = p.id_tipo_servicio
               ORDER BY p.activa DESC, p.fecha_fin DESC"""
        ).fetchall()


def crear_promocion(codigo, descripcion, descuento, fecha_inicio, fecha_fin, tipo_servicio=None) -> int:
    """Lanza sqlite3.IntegrityError si el código ya existe."""
    with get_connection() as conn:
        id_tipo = None
        if tipo_servicio:
            t = conn.execute(
                "SELECT id_tipo_servicio FROM TIPO_SERVICIO WHERE nombre = ?", (tipo_servicio,)
            ).fetchone()
            id_tipo = t["id_tipo_servicio"] if t else None
        cur = conn.execute(
            """INSERT INTO PROMOCION (codigo, descripcion, descuento, id_tipo_servicio,
                                      fecha_inicio, fecha_fin, activa)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (codigo, descripcion or None, descuento, id_tipo, fecha_inicio, fecha_fin),
        )
        return cur.lastrowid


def cambiar_estado_promocion(id_promocion: int, activa: bool) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE PROMOCION SET activa = ? WHERE id_promocion = ?", (1 if activa else 0, id_promocion)
        )
        return cur.rowcount == 1


# ---------------------------------------------------------------- Reportes

def resumen_reporte(desde: str, hasta: str) -> dict:
    with get_connection() as conn:
        f = conn.execute(
            """SELECT
                 SUM(CASE WHEN t.nombre = 'Mototaxi' AND s.estado = 'finalizado' THEN 1 ELSE 0 END) AS viajes,
                 SUM(CASE WHEN t.nombre = 'Courier' AND s.estado = 'finalizado' THEN 1 ELSE 0 END) AS entregas,
                 SUM(CASE WHEN s.estado = 'finalizado' THEN s.precio ELSE 0 END) AS ingresos,
                 SUM(CASE WHEN s.estado = 'cancelado' THEN 1 ELSE 0 END) AS cancelados
               FROM SERVICIO s JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               WHERE date(s.fecha_solicitud) BETWEEN ? AND ?""",
            (desde, hasta),
        ).fetchone()
    return {"viajes": f["viajes"] or 0, "entregas": f["entregas"] or 0,
            "ingresos": float(f["ingresos"] or 0), "cancelados": f["cancelados"] or 0}


def reporte_por_dia(desde: str, hasta: str):
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT date(s.fecha_solicitud) AS fecha,
                      SUM(CASE WHEN t.nombre = 'Mototaxi' THEN 1 ELSE 0 END) AS viajes,
                      SUM(CASE WHEN t.nombre = 'Courier' THEN 1 ELSE 0 END) AS entregas,
                      SUM(s.precio) AS ingresos
               FROM SERVICIO s JOIN TIPO_SERVICIO t ON t.id_tipo_servicio = s.id_tipo_servicio
               WHERE s.estado = 'finalizado' AND date(s.fecha_solicitud) BETWEEN ? AND ?
               GROUP BY date(s.fecha_solicitud) ORDER BY fecha DESC""",
            (desde, hasta),
        ).fetchall()
    return [{"fecha": f["fecha"], "viajes": f["viajes"], "entregas": f["entregas"],
             "ingresos": float(f["ingresos"])} for f in filas]


def reporte_top_conductores(desde: str, hasta: str, limite: int = 10):
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT u.nombre || ' ' || u.apellido AS nombre, COUNT(*) AS servicios,
                      SUM(s.precio) AS ingresos, AVG(s.puntuacion) AS calificacion
               FROM SERVICIO s
               JOIN CONDUCTOR c ON c.id_conductor = s.id_conductor
               JOIN USUARIO u ON u.id_usuario = c.id_usuario
               WHERE s.estado = 'finalizado' AND date(s.fecha_solicitud) BETWEEN ? AND ?
               GROUP BY c.id_conductor ORDER BY servicios DESC, ingresos DESC LIMIT ?""",
            (desde, hasta, limite),
        ).fetchall()
    return [{"nombre": f["nombre"], "servicios": f["servicios"], "ingresos": float(f["ingresos"]),
             "calificacion": f["calificacion"]} for f in filas]