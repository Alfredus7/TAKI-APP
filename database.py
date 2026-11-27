import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "db" / "TEKI.db"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS USUARIO (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    apellido TEXT NOT NULL,
    ci TEXT NOT NULL UNIQUE,
    telefono TEXT,
    correo TEXT NOT NULL UNIQUE,
    contrasena TEXT NOT NULL,
    rol TEXT NOT NULL,
    estado TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS CLIENTE (
    id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL,
    tipo_cliente TEXT NOT NULL,
    direccion TEXT,
    FOREIGN KEY (id_usuario) REFERENCES USUARIO(id_usuario)
);

CREATE TABLE IF NOT EXISTS CONDUCTOR (
    id_conductor INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL,
    licencia TEXT NOT NULL,
    descripcion_vehiculo TEXT,
    estado_validacion TEXT NOT NULL,
    disponibilidad TEXT NOT NULL,
    FOREIGN KEY (id_usuario) REFERENCES USUARIO(id_usuario)
);

CREATE TABLE IF NOT EXISTS ADMINISTRADOR (
    id_administrador INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL,
    cargo TEXT NOT NULL,
    FOREIGN KEY (id_usuario) REFERENCES USUARIO(id_usuario)
);

CREATE TABLE IF NOT EXISTS TIPO_SERVICIO (
    id_tipo_servicio INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    descripcion TEXT
);

CREATE TABLE IF NOT EXISTS MENOR (
    id_menor INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    apellido TEXT NOT NULL,
    fecha_nacimiento TEXT,
    colegio TEXT,
    contacto_emergencia TEXT,
    FOREIGN KEY (id_cliente) REFERENCES CLIENTE(id_cliente)
);

CREATE TABLE IF NOT EXISTS EMPRESA (
    id_empresa INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente INTEGER NOT NULL,
    razon_social TEXT NOT NULL,
    nit TEXT NOT NULL,
    direccion TEXT,
    FOREIGN KEY (id_cliente) REFERENCES CLIENTE(id_cliente)
);

CREATE TABLE IF NOT EXISTS SERVICIO (
    id_servicio INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente INTEGER NOT NULL,
    id_conductor INTEGER,
    id_tipo_servicio INTEGER NOT NULL,
    fecha_solicitud TEXT NOT NULL,
    fecha_programada TEXT,
    origen TEXT NOT NULL,
    destino TEXT NOT NULL,
    precio NUMERIC NOT NULL,
    puntuacion INTEGER,
    estado TEXT NOT NULL,
    origen_lat REAL,
    origen_lng REAL,
    destino_lat REAL,
    destino_lng REAL,
    FOREIGN KEY (id_cliente) REFERENCES CLIENTE(id_cliente),
    FOREIGN KEY (id_conductor) REFERENCES CONDUCTOR(id_conductor),
    FOREIGN KEY (id_tipo_servicio) REFERENCES TIPO_SERVICIO(id_tipo_servicio)
);

CREATE TABLE IF NOT EXISTS VIAJE_MENOR (
    id_viaje INTEGER PRIMARY KEY AUTOINCREMENT,
    id_servicio INTEGER NOT NULL,
    id_menor INTEGER NOT NULL,
    hora_recogida TEXT,
    hora_llegada TEXT,
    estado_entrega TEXT NOT NULL,
    FOREIGN KEY (id_servicio) REFERENCES SERVICIO(id_servicio),
    FOREIGN KEY (id_menor) REFERENCES MENOR(id_menor)
);

CREATE TABLE IF NOT EXISTS COURIER (
    id_courier INTEGER PRIMARY KEY AUTOINCREMENT,
    id_servicio INTEGER NOT NULL,
    id_empresa INTEGER,
    descripcion_paquete TEXT NOT NULL,
    nombre_destinatario TEXT NOT NULL,
    telefono_destinatario TEXT NOT NULL,
    estado_entrega TEXT NOT NULL,
    FOREIGN KEY (id_servicio) REFERENCES SERVICIO(id_servicio),
    FOREIGN KEY (id_empresa) REFERENCES EMPRESA(id_empresa)
);

CREATE TABLE IF NOT EXISTS PAGO (
    id_pago INTEGER PRIMARY KEY AUTOINCREMENT,
    id_servicio INTEGER NOT NULL,
    monto NUMERIC NOT NULL,
    metodo_pago TEXT NOT NULL,
    fecha_pago TEXT,
    estado_pago TEXT NOT NULL,
    FOREIGN KEY (id_servicio) REFERENCES SERVICIO(id_servicio)
);

CREATE TABLE IF NOT EXISTS SEGUIMIENTO (
    id_seguimiento INTEGER PRIMARY KEY AUTOINCREMENT,
    id_servicio INTEGER NOT NULL,
    latitud NUMERIC NOT NULL,
    longitud NUMERIC NOT NULL,
    fecha_hora TEXT NOT NULL,
    estado TEXT NOT NULL,
    FOREIGN KEY (id_servicio) REFERENCES SERVICIO(id_servicio)
);

CREATE TABLE IF NOT EXISTS CONSULTA (
    id_consulta INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL,
    id_servicio INTEGER,
    tipo TEXT NOT NULL,
    mensaje TEXT NOT NULL,
    estado TEXT NOT NULL,
    fecha TEXT NOT NULL,
    FOREIGN KEY (id_usuario) REFERENCES USUARIO(id_usuario),
    FOREIGN KEY (id_servicio) REFERENCES SERVICIO(id_servicio)
);

CREATE TABLE IF NOT EXISTS TARIFA (
    id_tarifa INTEGER PRIMARY KEY AUTOINCREMENT,
    id_tipo_servicio INTEGER NOT NULL UNIQUE,
    precio NUMERIC NOT NULL,
    fecha_actualizacion TEXT,
    FOREIGN KEY (id_tipo_servicio) REFERENCES TIPO_SERVICIO(id_tipo_servicio)
);

CREATE TABLE IF NOT EXISTS PROMOCION (
    id_promocion INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    descripcion TEXT,
    descuento NUMERIC NOT NULL,
    id_tipo_servicio INTEGER,
    fecha_inicio TEXT NOT NULL,
    fecha_fin TEXT NOT NULL,
    activa INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (id_tipo_servicio) REFERENCES TIPO_SERVICIO(id_tipo_servicio)
);

CREATE TABLE IF NOT EXISTS NOTIFICACION (
    id_notificacion INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL,
    id_servicio INTEGER,
    titulo TEXT NOT NULL,
    mensaje TEXT NOT NULL,
    leida INTEGER NOT NULL DEFAULT 0,
    fecha_hora TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (id_usuario) REFERENCES USUARIO(id_usuario),
    FOREIGN KEY (id_servicio) REFERENCES SERVICIO(id_servicio)
);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def autopoblar() -> None:
    """Llena la base de datos con datos de prueba si está vacía."""
    with get_connection() as conn:
        # Verificamos si ya hay usuarios. Si hay, no hacemos nada.
        existe = conn.execute("SELECT COUNT(*) FROM USUARIO").fetchone()[0]
        if existe > 0:
            return

        print("Base de datos vacía. Insertando datos de prueba...")
        
        # 1. Insertar Tipos de Servicio
        conn.execute("INSERT INTO TIPO_SERVICIO (nombre, descripcion) VALUES ('Mototaxi', 'Viajes en mototaxi')")
        conn.execute("INSERT INTO TIPO_SERVICIO (nombre, descripcion) VALUES ('Courier', 'Envíos y paquetería')")
        
        # 2. Insertar Tarifas
        conn.execute("INSERT INTO TARIFA (id_tipo_servicio, precio, fecha_actualizacion) VALUES (1, 5.00, datetime('now'))")
        conn.execute("INSERT INTO TARIFA (id_tipo_servicio, precio, fecha_actualizacion) VALUES (2, 8.00, datetime('now'))")

        # 3. Insertar Usuarios (Contraseñas en texto plano para pruebas)
        # Admin
        conn.execute("""INSERT INTO USUARIO (nombre, apellido, ci, telefono, correo, contrasena, rol, estado) 
                        VALUES ('Admin', 'Sistema', '1111111', '70000000', 'admin@teki.com', '123456', 'administrador', 'activo')""")
        id_admin_user = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO ADMINISTRADOR (id_usuario, cargo) VALUES (?, 'Gerente')", (id_admin_user,))

        # Cliente
        conn.execute("""INSERT INTO USUARIO (nombre, apellido, ci, telefono, correo, contrasena, rol, estado) 
                        VALUES ('Valeria', 'Gutiérrez', '2222222', '71111111', 'valeria@correo.com', '123456', 'cliente', 'activo')""")
        id_cliente_user = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO CLIENTE (id_usuario, tipo_cliente, direccion) VALUES (?, 'padre', 'Av. Ballivián #450')", (id_cliente_user,))
        id_cliente = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Conductor
        conn.execute("""INSERT INTO USUARIO (nombre, apellido, ci, telefono, correo, contrasena, rol, estado) 
                        VALUES ('Marco', 'Antonio', '3333333', '72222222', 'marco@correo.com', '123456', 'conductor', 'activo')""")
        id_conductor_user = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("""INSERT INTO CONDUCTOR (id_usuario, licencia, descripcion_vehiculo, estado_validacion, disponibilidad) 
                        VALUES (?, 'LIC-123', 'Moto Honda Roja', 'aprobado', 'disponible')""", (id_conductor_user,))
        
        # 4. Insertar un Menor (Hijo de Valeria)
        conn.execute("""INSERT INTO MENOR (id_cliente, nombre, apellido, fecha_nacimiento, colegio, contacto_emergencia) 
                        VALUES (?, 'Diego', 'Gutiérrez', '2015-05-10', 'Colegio La Salle', '71111111')""", (id_cliente,))

        # 5. Insertar una Notificación de bienvenida
        conn.execute("""INSERT INTO NOTIFICACION (id_usuario, titulo, mensaje) 
                        VALUES (?, 'Bienvenido a TEKI', 'Tu cuenta ha sido creada exitosamente.')""", (id_cliente_user,))

        conn.commit()
        print("¡Datos de prueba insertados con éxito!")


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    # Llamamos a la función de autopoblar justo después de crear las tablas
    autopoblar()