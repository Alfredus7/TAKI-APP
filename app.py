from flask import Flask, redirect, url_for

from database import init_db
from controllers.auth_controller import auth_bp
from controllers.cliente_controller import cliente_bp
from controllers.conductor_controller import conductor_bp
from controllers.admin_controller import admin_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "9eafd5072e5c11995fccfe29c6e87f4b"

    init_db()

    app.register_blueprint(auth_bp)
    app.register_blueprint(cliente_bp, url_prefix="/cliente")
    app.register_blueprint(conductor_bp, url_prefix="/conductor")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Permite al menú lateral comprobar si un endpoint existe
    @app.context_processor
    def utilidades_nav():
        def existe(endpoint):
            return endpoint in app.view_functions
        return dict(existe=existe)

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    return app


# --- LÍNEA CLAVE PARA RENDER ---
# Creamos la app a nivel global para que Gunicorn la encuentre con 'app:app'
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)