from database import get_connection


def crear_notificacion(
    id_usuario: int,
    titulo: str,
    mensaje: str,
    id_servicio: int | None = None,
    clave: str | None = None,
) -> None:
    """
    Crea una notificación evitando duplicados.

    - Si se pasa `clave`, se deduplica por (id_usuario, titulo, mensaje) en una
      ventana de 2 minutos. Útil para mensajes "de estado" que no deben repetirse
      aunque se creen varios servicios seguidos (p. ej. "Buscando conductor").
    - Si no se pasa `clave` pero sí `id_servicio`, se deduplica por
      (id_usuario, id_servicio, mensaje), como antes.
    """
    with get_connection() as conn:
        if clave is not None:
            existe = conn.execute(
                """SELECT 1 FROM NOTIFICACION
                   WHERE id_usuario = ? AND titulo = ? AND mensaje = ?
                     AND fecha_hora >= datetime('now','localtime','-2 minutes')""",
                (id_usuario, titulo, mensaje),
            ).fetchone()
            if existe:
                return
        elif id_servicio is not None:
            existe = conn.execute(
                """SELECT 1 FROM NOTIFICACION
                   WHERE id_usuario = ? AND id_servicio = ? AND mensaje = ?""",
                (id_usuario, id_servicio, mensaje),
            ).fetchone()
            if existe:
                return

        conn.execute(
            """INSERT INTO NOTIFICACION (id_usuario, id_servicio, titulo, mensaje)
               VALUES (?, ?, ?, ?)""",
            (id_usuario, id_servicio, titulo, mensaje),
        )
        conn.commit()


def listar_por_usuario(id_usuario: int, limite: int = 40):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id_notificacion, id_servicio, titulo, mensaje, leida, fecha_hora
            FROM NOTIFICACION
            WHERE id_usuario = ?
            ORDER BY id_notificacion DESC
            LIMIT ?
            """,
            (id_usuario, limite),
        ).fetchall()


def marcar_leida(id_notificacion: int, id_usuario: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE NOTIFICACION SET leida = 1 WHERE id_notificacion = ? AND id_usuario = ?",
            (id_notificacion, id_usuario),
        )
        conn.commit()


def marcar_todas_leidas(id_usuario: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE NOTIFICACION SET leida = 1 WHERE id_usuario = ? AND leida = 0",
            (id_usuario,),
        )
        conn.commit()


# Alias por compatibilidad con nombres anteriores
registrar_notificacion = crear_notificacion
obtener_notificaciones = listar_por_usuario
marcar_como_leida = marcar_leida