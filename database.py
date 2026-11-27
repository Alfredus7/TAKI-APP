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

-- TABLA MODIFICADA: Se agregaron las columnas de coordenadas (origen_lat, etc.)
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


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()