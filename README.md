# CUIDAVIA

Plataforma web de mototaxi para menores y courier, hecha con Flask + SQLite3 (arquitectura MVC).
Identidad visual TEKI: azul `#092747`, naranja `#FF8200`, blanco humo `#F5F6F8`.

## Requisitos

- Python 3.10+
- Flask

## Instalación

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install flask
```

## Ejecución

```bash
python seed.py     # opcional: crea usuarios y datos de prueba
python app.py
```

Abre <http://127.0.0.1:5000>. La base `cuidavia.db` se crea sola al iniciar.

## Usuarios de prueba

Después de ejecutar `python seed.py`:

| Rol           | Correo                    | Contraseña     |
|---------------|---------------------------|----------------|
| Cliente       | cliente@cuidavia.com      | cliente123     |
| Conductor     | conductor@cuidavia.com    | conductor123   |
| Administrador | admin@cuidavia.com        | admin123       |

También se puede ingresar con el teléfono (70000003, 70000002, 70000001).

## Estructura

```
cuidavia/
├── app.py              # Flask y registro de Blueprints
├── database.py         # Conexión SQLite y creación de tablas
├── seed.py             # Datos de prueba
├── models/             # Consultas SQL por entidad
├── controllers/        # Rutas (Blueprints) y lógica por rol
├── templates/          # Vistas Jinja2 (auth, cliente, conductor, admin)
└── static/             # CSS, JS e imágenes
```

## Rutas implementadas

| Ruta                          | Rol            | Descripción                         |
|-------------------------------|----------------|-------------------------------------|
| `/login`, `/registro`, `/logout` | Público     | Autenticación                       |
| `/cliente/menu`               | Cliente        | Menú principal                      |
| `/conductor/panel`            | Conductor      | Disponibilidad y solicitudes        |
| `/admin/dashboard`            | Administrador  | Métricas generales                  |

## Reglas de negocio actuales

- Contraseñas guardadas con hash (werkzeug).
- El registro público solo permite crear clientes y conductores.
- Un conductor nuevo queda en estado `pendiente` y no recibe solicitudes hasta ser aprobado.
- Un servicio solo puede ser aceptado por un conductor (sin doble asignación).

## Pendiente

- Vistas de hijos/menores, solicitud de mototaxi y courier, seguimiento y pagos.
- Validación de conductores desde el panel de administración.
- Cambiar `secret_key` en `app.py` antes de publicar.
