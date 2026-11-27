from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection


def registrar_usuario(datos: dict) -> int:
    """Crea el USUARIO y su registro hijo (CLIENTE / CONDUCTOR / ADMINISTRADOR).
    Lanza sqlite3.IntegrityError si el CI o el correo ya existen."""
    rol = datos["rol"]
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO USUARIO
               (nombre, apellido, ci, telefono, correo, contrasena, rol, estado)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'activo')""",
            (
                datos["nombre"],
                datos["apellido"],
                datos["ci"],
                datos.get("telefono"),
                datos["correo"],
                generate_password_hash(datos["contrasena"]),
                rol,
            ),
        )
        id_usuario = cur.lastrowid

        if rol == "cliente":
            conn.execute(
                "INSERT INTO CLIENTE (id_usuario, tipo_cliente, direccion) VALUES (?, ?, ?)",
                (id_usuario, datos.get("tipo_cliente", "padre"), datos.get("direccion")),
            )
        elif rol == "conductor":
            conn.execute(
                """INSERT INTO CONDUCTOR
                   (id_usuario, licencia, descripcion_vehiculo, estado_validacion, disponibilidad)
                   VALUES (?, ?, ?, 'pendiente', 'no_disponible')""",
                (id_usuario, datos["licencia"], datos.get("descripcion_vehiculo")),
            )
        elif rol == "administrador":
            conn.execute(
                "INSERT INTO ADMINISTRADOR (id_usuario, cargo) VALUES (?, ?)",
                (id_usuario, datos.get("cargo", "Administrador")),
            )
        return id_usuario


def autenticar(identificador: str, contrasena: str):
    """Login por correo o teléfono. Devuelve la fila de USUARIO o None.
    Las cuentas inactivas o suspendidas no pueden iniciar sesión."""
    with get_connection() as conn:
        user = conn.execute(
            "SELECT * FROM USUARIO WHERE correo = ? OR telefono = ?",
            (identificador, identificador),
        ).fetchone()
    if user and check_password_hash(user["contrasena"], contrasena) and user["estado"] == "activo":
        return user
    return None


def obtener_usuario(id_usuario: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM USUARIO WHERE id_usuario = ?", (id_usuario,)
        ).fetchone()


def obtener_conductor_por_usuario(id_usuario: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM CONDUCTOR WHERE id_usuario = ?", (id_usuario,)
        ).fetchone()


def cambiar_disponibilidad(id_conductor: int, disponibilidad: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE CONDUCTOR SET disponibilidad = ? WHERE id_conductor = ?",
            (disponibilidad, id_conductor),
        )


def contar_por_rol() -> dict:
    with get_connection() as conn:
        filas = conn.execute(
            "SELECT rol, COUNT(*) AS total FROM USUARIO GROUP BY rol"
        ).fetchall()
        pendientes = conn.execute(
            "SELECT COUNT(*) FROM CONDUCTOR WHERE estado_validacion = 'pendiente'"
        ).fetchone()[0]
    datos = {f["rol"]: f["total"] for f in filas}
    datos["conductores_pendientes"] = pendientes
    return datos
