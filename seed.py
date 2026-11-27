"""Crea datos de prueba: usuarios de cada rol, tipos de servicio y solicitudes de ejemplo.
Uso:  python seed.py   (es seguro ejecutarlo varias veces)"""
import sqlite3

from database import get_connection, init_db
from models import usuario_model

USUARIOS = [
    dict(
        rol="administrador",
        nombre="Rodrigo",
        apellido="Salazar",
        ci="6482910",
        telefono="71245890",
        correo="rodrigo.salazar@teki.bo",
        contrasena="Admin#2026",
        cargo="Coordinador General de Operaciones",
    ),
    dict(
        rol="conductor",
        nombre="Marco Antonio",
        apellido="Quispe Mamani",
        ci="5893412",
        telefono="72581430",
        correo="marco.quispe@teki.bo",
        contrasena="Conductor#2026",
        licencia="LP-884120-C",
        descripcion_vehiculo="Honda XR 150L blanca - Placa 4521-KTR",
    ),
    dict(
        rol="conductor",
        nombre="Daniela",
        apellido="Vargas Torrico",
        ci="7319045",
        telefono="76903214",
        correo="daniela.vargas@teki.bo",
        contrasena="Conductor#2026",
        licencia="CB-309412-B",
        descripcion_vehiculo="Yamaha FZ 25 negra - Placa 3890-PTL",
    ),
    dict(
        rol="cliente",
        nombre="Valeria",
        apellido="Gutiérrez Roca",
        ci="6104823",
        telefono="73419082",
        correo="valeria.gutierrez@correo.bo",
        contrasena="Cliente#2026",
        tipo_cliente="padre",
        direccion="Av. Ballivián #450, Zona Norte",
    ),
    dict(
        rol="cliente",
        nombre="Jorge Luis",
        apellido="Paz Céspedes",
        ci="4928176",
        telefono="78901245",
        correo="jorge.paz@correo.bo",
        contrasena="Cliente#2026",
        tipo_cliente="empresa",
        direccion="Calle Suárez #215, Centro",
    ),
]


def main():
    init_db()
    for u in USUARIOS:
        try:
            usuario_model.registrar_usuario(u)
            print(f"Creado: {u['correo']}")
        except sqlite3.IntegrityError:
            print(f"Ya existe: {u['correo']}")

    with get_connection() as conn:
        # Conductores aprobados y disponibles para pruebas
        for correo in ("marco.quispe@teki.bo", "daniela.vargas@teki.bo"):
            conn.execute(
                "UPDATE CONDUCTOR SET estado_validacion='aprobado', disponibilidad='disponible' "
                "WHERE id_usuario = (SELECT id_usuario FROM USUARIO WHERE correo=?)",
                (correo,),
            )

        if conn.execute("SELECT COUNT(*) FROM TIPO_SERVICIO").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO TIPO_SERVICIO (nombre, descripcion) VALUES (?, ?)",
                [
                    ("Mototaxi", "Traslado seguro de estudiantes y menores en ruta"),
                    ("Courier", "Envío express de documentos y paquetes urbanos"),
                ],
            )

        valeria = conn.execute(
            "SELECT id_cliente FROM CLIENTE c JOIN USUARIO u ON u.id_usuario=c.id_usuario "
            "WHERE u.correo='valeria.gutierrez@correo.bo'"
        ).fetchone()
        jorge = conn.execute(
            "SELECT id_cliente FROM CLIENTE c JOIN USUARIO u ON u.id_usuario=c.id_usuario "
            "WHERE u.correo='jorge.paz@correo.bo'"
        ).fetchone()

        if valeria and jorge and conn.execute("SELECT COUNT(*) FROM SERVICIO").fetchone()[0] == 0:
            conn.executemany(
                """INSERT INTO SERVICIO (id_cliente, id_tipo_servicio, fecha_solicitud,
                   origen, destino, precio, estado) VALUES (?, ?, datetime('now','localtime'), ?, ?, ?, 'pendiente')""",
                [
                    (valeria["id_cliente"], 1, "Av. Ballivián #450", "Colegio La Salle", 12),
                    (valeria["id_cliente"], 1, "Colegio La Salle", "Av. Ballivián #450", 12),
                    (jorge["id_cliente"], 2, "Calle Suárez #215", "Sucursal Mercado Central", 18),
                ],
            )

        conn.commit()
    print("Listo. Ver usuarios_prueba.txt para las credenciales.")


if __name__ == "__main__":
    main()