from functools import wraps

from flask import session, redirect, url_for, flash


def login_required(*roles):
    """Protege una ruta: exige sesión y, opcionalmente, uno de los roles dados."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if "id_usuario" not in session:
                flash("Inicia sesión para continuar.", "warning")
                return redirect(url_for("auth.login"))
            if roles and session.get("rol") not in roles:
                flash("No tienes permiso para acceder a esa sección.", "error")
                return redirect(url_for("auth.home"))
            return vista(*args, **kwargs)
        return envoltura
    return decorador
