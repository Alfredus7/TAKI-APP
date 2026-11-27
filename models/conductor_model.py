"""Perfil y notificaciones del conductor.
Las notificaciones se derivan de los estados de SERVICIO (no hay tabla propia)."""
import math
from datetime import date, timedelta

from database import get_connection
from models import servicio_model

DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def obtener_perfil(id_usuario: int):
    """Datos de USUARIO + CONDUCTOR para la vista de perfil."""
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT c.id_conductor, u.nombre, u.apellido, u.ci, u.telefono, u.correo,
                      c.licencia, c.descripcion_vehiculo, c.estado_validacion, c.disponibilidad
               FROM CONDUCTOR c
               JOIN USUARIO u ON u.id_usuario = c.id_usuario
               WHERE c.id_usuario = ?""",
            (id_usuario,),
        ).fetchone()
    return dict(fila) if fila else None


def actualizar_perfil(id_usuario: int, telefono: str, descripcion_vehiculo: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE USUARIO SET telefono = ? WHERE id_usuario = ?", (telefono, id_usuario))
        conn.execute(
            "UPDATE CONDUCTOR SET descripcion_vehiculo = ? WHERE id_usuario = ?",
            (descripcion_vehiculo, id_usuario),
        )


_TITULOS_ESTADO = {
    "aceptado": "Servicio aceptado",
    "en_curso": "Viaje en curso",
    "finalizado": "Servicio finalizado",
    "cancelado": "Servicio cancelado",
}


def notificaciones(conductor, con_solicitudes: bool) -> list:
    """Lista de alertas para el conductor.
    con_solicitudes: True solo si está aprobado y en línea (si no, no recibe solicitudes)."""
    lista = []

    if con_solicitudes:
        for s in servicio_model.listar_solicitudes_disponibles(5):
            lista.append({
                "tipo": "solicitud",
                "titulo": f"Nueva solicitud de {s['tipo']}",
                "mensaje": f"{s['origen']} → {s['destino']} · Bs {float(s['precio']):.2f}",
                "fecha": s["fecha_solicitud"],
                "nueva": True,
                "id_servicio": None,
            })

    for s in servicio_model.servicios_del_conductor(conductor["id_conductor"])[:20]:
        mensaje = f"{s['tipo']}: {s['origen']} → {s['destino']}"
        if s["estado"] == "finalizado" and s["puntuacion"]:
            mensaje += f" · El cliente te calificó con {s['puntuacion']} / 5"
        lista.append({
            "tipo": "servicio",
            "titulo": _TITULOS_ESTADO.get(s["estado"], s["estado"]),
            "mensaje": mensaje,
            "fecha": s["fecha_programada"] or s["fecha_solicitud"],
            "nueva": s["estado"] in ("aceptado", "en_curso"),
            "id_servicio": s["id_servicio"],
        })

    if conductor["estado_validacion"] == "aprobado":
        lista.append({"tipo": "sistema", "titulo": "Cuenta validada",
                      "mensaje": "Ya puedes recibir solicitudes cuando estés en línea.",
                      "fecha": "", "nueva": False, "id_servicio": None})
    else:
        lista.append({"tipo": "sistema", "titulo": "Cuenta pendiente de validación",
                      "mensaje": f"Estado actual: {conductor['estado_validacion']}. Un administrador revisará tus documentos.",
                      "fecha": "", "nueva": True, "id_servicio": None})
    return lista


# ---------------------------------------------------------------- Métricas del panel

def _cambio_porcentual(hoy, ayer):
    """% de cambio respecto a ayer; None si ayer no hubo datos con los que comparar."""
    if not ayer:
        return None
    return round((hoy - ayer) / ayer * 100)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def metricas_panel(id_conductor: int) -> dict:
    """Datos reales del panel: variación vs ayer, km de hoy (desde SEGUIMIENTO) y ganancias de 7 días."""
    cond_hoy = "date(fecha_solicitud) = date('now','localtime')"
    cond_ayer = "date(fecha_solicitud) = date('now','localtime','-1 day')"
    with get_connection() as conn:
        f = conn.execute(
            f"""SELECT
                  COALESCE(SUM(CASE WHEN {cond_hoy} THEN 1 END), 0) AS s_hoy,
                  COALESCE(SUM(CASE WHEN {cond_ayer} THEN 1 END), 0) AS s_ayer,
                  COALESCE(SUM(CASE WHEN {cond_hoy} THEN precio END), 0) AS g_hoy,
                  COALESCE(SUM(CASE WHEN {cond_ayer} THEN precio END), 0) AS g_ayer
                FROM SERVICIO WHERE id_conductor = ? AND estado = 'finalizado'""",
            (id_conductor,),
        ).fetchone()
        por_dia = {
            r["d"]: float(r["total"])
            for r in conn.execute(
                """SELECT date(fecha_solicitud) AS d, SUM(precio) AS total
                   FROM SERVICIO
                   WHERE id_conductor = ? AND estado = 'finalizado'
                     AND date(fecha_solicitud) >= date('now','localtime','-6 days')
                   GROUP BY d""",
                (id_conductor,),
            ).fetchall()
        }
        hoy = date.fromisoformat(conn.execute("SELECT date('now','localtime')").fetchone()[0])
        puntos = conn.execute(
            """SELECT g.id_servicio, g.latitud, g.longitud
               FROM SEGUIMIENTO g JOIN SERVICIO s ON s.id_servicio = g.id_servicio
               WHERE s.id_conductor = ? AND date(g.fecha_hora) = date('now','localtime')
               ORDER BY g.id_servicio, g.fecha_hora, g.id_seguimiento""",
            (id_conductor,),
        ).fetchall()

    km, anterior = 0.0, None
    for p in puntos:
        if anterior is not None and anterior["id_servicio"] == p["id_servicio"]:
            tramo = _haversine_km(anterior["latitud"], anterior["longitud"], p["latitud"], p["longitud"])
            if tramo < 5:  # descarta saltos imposibles de GPS
                km += tramo
        anterior = p

    dias = [hoy - timedelta(days=i) for i in range(6, -1, -1)]
    return {
        "variacion_servicios": _cambio_porcentual(f["s_hoy"], f["s_ayer"]),
        "variacion_ganancias": _cambio_porcentual(float(f["g_hoy"]), float(f["g_ayer"])),
        "distancia_km": round(km, 1),
        "grafico_valores": [por_dia.get(d.isoformat(), 0.0) for d in dias],
        "grafico_dias": [DIAS_CORTOS[d.weekday()] for d in dias],
    }