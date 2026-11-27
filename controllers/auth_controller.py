import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import usuario_model

auth_bp = Blueprint("auth", __name__)

DESTINOS = {
    "cliente": "cliente.menu",
    "conductor": "conductor.panel",
    "administrador": "admin.dashboard",
}


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identificador = request.form.get("identificador", "").strip()
        contrasena = request.form.get("contrasena", "")
        user = usuario_model.autenticar(identificador, contrasena)

        if not user:
            flash("Credenciales incorrectas.", "error")
        elif user["estado"] != "activo":
            flash("Tu cuenta está bloqueada o inactiva. Contacta a soporte.", "error")
        else:
            session.clear()
            session["id_usuario"] = user["id_usuario"]
            session["nombre"] = user["nombre"]
            session["rol"] = user["rol"]
            return redirect(url_for(DESTINOS.get(user["rol"], "auth.login")))
    return render_template("auth/login.html")


@auth_bp.route("/registro", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        datos = {
            "nombre": f.get("nombre", "").strip(),
            "apellido": f.get("apellido", "").strip(),
            "ci": f.get("ci", "").strip(),
            "telefono": f.get("telefono", "").strip(),
            "correo": f.get("correo", "").strip().lower(),
            "contrasena": f.get("contrasena", ""),
            # Por seguridad el registro público solo permite cliente o conductor.
            "rol": f.get("rol") if f.get("rol") in ("cliente", "conductor") else "cliente",
            "direccion": f.get("direccion", "").strip(),
            "licencia": f.get("licencia", "").strip(),
            "descripcion_vehiculo": f.get("descripcion_vehiculo", "").strip(),
        }
        obligatorios = ["nombre", "apellido", "ci", "correo", "contrasena"]
        if datos["rol"] == "conductor":
            obligatorios.append("licencia")

        if any(not datos[c] for c in obligatorios):
            flash("Completa todos los campos obligatorios.", "error")
        elif len(datos["contrasena"]) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "error")
        elif datos["contrasena"] != f.get("confirmar", ""):
            flash("Las contraseñas no coinciden.", "error")
        else:
            try:
                usuario_model.registrar_usuario(datos)
            except sqlite3.IntegrityError:
                flash("El CI o el correo ya están registrados.", "error")
            else:
                msg = "Cuenta creada. Ya puedes iniciar sesión."
                if datos["rol"] == "conductor":
                    msg = "Cuenta creada. Un administrador validará tus documentos."
                flash(msg, "success")
                return redirect(url_for("auth.login"))
    return render_template("auth/register.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/home")
def home():
    rol = session.get("rol")
    if rol in DESTINOS:
        return redirect(url_for(DESTINOS[rol]))
    return redirect(url_for("auth.login"))
