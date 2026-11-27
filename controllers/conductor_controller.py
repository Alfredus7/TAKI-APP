import re

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)

from controllers.decorators import login_required
from models import conductor_model, servicio_model, usuario_model

conductor_bp = Blueprint("conductor", __name__)


# ---------------------------------------------------------------- Helpers

def _conductor_actual():
    return usuario_model.obtener_conductor_por_usuario(session["id_usuario"])


def _no_validado(conductor) -> bool:
    """Devuelve True (y deja un flash) si el conductor aún no está aprobado."""
    if conductor["estado_validacion"] != "aprobado":
        flash("Tu cuenta no está validada por un administrador.", "error")
        return True
    return False


def _resolver(resultado, id_servicio):
    """Convierte (ok, mensaje) del modelo en flash + redirección al servicio."""
    ok, mensaje = resultado
    flash(mensaje, "success" if ok else "error")
    return redirect(url_for("conductor.servicio", id_servicio=id_servicio))


# ---------------------------------------------------------------- Panel y solicitudes

def _grafico(metricas):
    """Convierte los 7 valores diarios en puntos para el SVG del panel (viewBox 350x130)."""
    valores = metricas["grafico_valores"]
    x0, paso, y_alto, y_bajo = 25, 50, 22, 102
    mayor = max(valores)
    circulos = []
    for i, v in enumerate(valores):
        y = y_bajo - (v / mayor) * (y_bajo - y_alto) if mayor else y_bajo
        circulos.append((x0 + i * paso, round(y, 1)))
    return {
        "puntos": " ".join(f"{x},{y}" for x, y in circulos),
        "circulos": circulos,
        "valores": valores,
        "dias": metricas["grafico_dias"],
        "total": sum(valores),
    }


@conductor_bp.route("/panel")
@login_required("conductor")
def panel():
    conductor = _conductor_actual()
    validado = conductor["estado_validacion"] == "aprobado"
    solicitudes = []
    if validado and conductor["disponibilidad"] == "disponible":
        descartadas = set(session.get("descartadas", []))
        solicitudes = [
            s for s in servicio_model.listar_solicitudes_disponibles(20)
            if s["id_servicio"] not in descartadas
        ]
    proximos = servicio_model.servicios_del_conductor(conductor["id_conductor"], solo_activos=True)
    metricas = conductor_model.metricas_panel(conductor["id_conductor"])
    return render_template(
        "conductor/panel.html",
        conductor=conductor,
        validado=validado,
        solicitudes=solicitudes,
        proximos=proximos,
        resumen=servicio_model.resumen_conductor(conductor["id_conductor"]),
        metricas=metricas,
        grafico=_grafico(metricas),
        # Campana: solicitudes por atender + servicios activos + aviso de cuenta sin validar
        notif_pendientes=len(solicitudes) + len(proximos) + (0 if validado else 1),
    )


@conductor_bp.route("/disponibilidad", methods=["POST"])
@login_required("conductor")
def alternar_disponibilidad():
    conductor = _conductor_actual()
    if conductor["estado_validacion"] != "aprobado":
        flash("Tu cuenta aún no fue validada por un administrador.", "warning")
    else:
        nuevo = "no_disponible" if conductor["disponibilidad"] == "disponible" else "disponible"
        usuario_model.cambiar_disponibilidad(conductor["id_conductor"], nuevo)
    return redirect(url_for("conductor.panel"))


@conductor_bp.route("/aceptar/<int:id_servicio>", methods=["POST"])
@login_required("conductor")
def aceptar(id_servicio):
    conductor = _conductor_actual()
    if conductor["estado_validacion"] != "aprobado":
        flash("No puedes aceptar servicios sin validación.", "error")
        return redirect(url_for("conductor.panel"))

    ok, mensaje = servicio_model.aceptar_servicio(id_servicio, conductor["id_conductor"])
    if ok:
        flash(mensaje, "success")
        return redirect(url_for("conductor.servicio", id_servicio=id_servicio))

    flash(mensaje, "warning")
    return redirect(url_for("conductor.panel"))


@conductor_bp.route("/rechazar/<int:id_servicio>", methods=["POST"])
@login_required("conductor")
def rechazar(id_servicio):
    # El rechazo no cambia el servicio (otro conductor aún puede tomarlo);
    # solo se oculta para este conductor durante su sesión.
    descartadas = session.get("descartadas", [])
    if id_servicio not in descartadas:
        descartadas.append(id_servicio)
    session["descartadas"] = descartadas[-50:]
    flash("Solicitud descartada.", "success")
    return redirect(url_for("conductor.panel"))


# ---------------------------------------------------------------- Servicio activo

@conductor_bp.route("/servicio/<int:id_servicio>")
@login_required("conductor")
def servicio(id_servicio):
    conductor = _conductor_actual()
    detalle = servicio_model.obtener_servicio_conductor(id_servicio, conductor["id_conductor"])
    if detalle is None:
        abort(404)
    return render_template(
        "conductor/servicio.html",
        s=detalle["s"],
        menor=detalle["menor"],
        courier=detalle["courier"],
        recogido=detalle["recogido"],
    )


@conductor_bp.route("/servicio/<int:id_servicio>/iniciar", methods=["POST"])
@login_required("conductor")
def iniciar(id_servicio):
    conductor = _conductor_actual()
    if _no_validado(conductor):
        return redirect(url_for("conductor.panel"))
    return _resolver(servicio_model.iniciar_servicio(id_servicio, conductor["id_conductor"]), id_servicio)


@conductor_bp.route("/servicio/<int:id_servicio>/recoger", methods=["POST"])
@login_required("conductor")
def recoger(id_servicio):
    conductor = _conductor_actual()
    if _no_validado(conductor):
        return redirect(url_for("conductor.panel"))
    return _resolver(servicio_model.confirmar_recogida(id_servicio, conductor["id_conductor"]), id_servicio)


@conductor_bp.route("/servicio/<int:id_servicio>/finalizar", methods=["POST"])
@login_required("conductor")
def finalizar(id_servicio):
    """Finaliza un viaje de mototaxi."""
    conductor = _conductor_actual()
    if _no_validado(conductor):
        return redirect(url_for("conductor.panel"))
    return _resolver(
        servicio_model.finalizar_servicio(id_servicio, conductor["id_conductor"], "Mototaxi"), id_servicio
    )


@conductor_bp.route("/servicio/<int:id_servicio>/entregar", methods=["POST"])
@login_required("conductor")
def entregar(id_servicio):
    """Confirma la entrega de un courier."""
    conductor = _conductor_actual()
    if _no_validado(conductor):
        return redirect(url_for("conductor.panel"))
    return _resolver(
        servicio_model.finalizar_servicio(id_servicio, conductor["id_conductor"], "Courier"), id_servicio
    )


@conductor_bp.route("/servicio/<int:id_servicio>/ubicacion", methods=["POST"])
@login_required("conductor")
def registrar_ubicacion(id_servicio):
    """Recibe {latitud, longitud} del navegador del conductor y la guarda en SEGUIMIENTO."""
    conductor = _conductor_actual()
    datos = request.get_json(silent=True) or {}
    try:
        latitud = float(datos.get("latitud"))
        longitud = float(datos.get("longitud"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Coordenadas inválidas"), 400
    if not (-90 <= latitud <= 90 and -180 <= longitud <= 180):
        return jsonify(ok=False, error="Coordenadas fuera de rango"), 400
    if not servicio_model.registrar_ubicacion(id_servicio, conductor["id_conductor"], latitud, longitud):
        return jsonify(ok=False, error="El servicio no está en curso"), 409
    return jsonify(ok=True)


# ---------------------------------------------------------------- Historial y ganancias

@conductor_bp.route("/historial")
@login_required("conductor")
def historial():
    conductor = _conductor_actual()
    tipo = request.args.get("tipo")
    if tipo not in ("Mototaxi", "Courier"):
        tipo = None
    return render_template(
        "conductor/historial.html",
        servicios=servicio_model.historial_conductor(conductor["id_conductor"], tipo),
        filtro=tipo,
    )


@conductor_bp.route("/ganancias")
@login_required("conductor")
def ganancias():
    conductor = _conductor_actual()
    id_conductor = conductor["id_conductor"]
    detalle = servicio_model.detalle_ganancias(id_conductor)
    return render_template(
        "conductor/ganancias.html",
        ganancias=servicio_model.ganancias_conductor(id_conductor),
        detalle=detalle,
        total_detalle=sum(float(s["precio"]) for s in detalle),
    )


# ---------------------------------------------------------------- Notificaciones y perfil

@conductor_bp.route("/notificaciones")
@login_required("conductor")
def notificaciones():
    conductor = _conductor_actual()
    recibe_solicitudes = (
        conductor["estado_validacion"] == "aprobado" and conductor["disponibilidad"] == "disponible"
    )
    return render_template(
        "conductor/notificaciones.html",
        notificaciones=conductor_model.notificaciones(conductor, recibe_solicitudes),
    )


@conductor_bp.route("/perfil")
@login_required("conductor")
def perfil():
    return render_template(
        "conductor/perfil.html",
        conductor=conductor_model.obtener_perfil(session["id_usuario"]),
    )


@conductor_bp.route("/perfil/actualizar", methods=["POST"])
@login_required("conductor")
def actualizar_perfil():
    telefono = request.form.get("telefono", "").strip()
    vehiculo = request.form.get("descripcion_vehiculo", "").strip()
    if not re.fullmatch(r"[0-9+\-\s]{0,20}", telefono):
        flash("El teléfono solo admite números, +, - y espacios (máx. 20).", "error")
    elif len(vehiculo) > 200:
        flash("La descripción del vehículo no puede superar 200 caracteres.", "error")
    else:
        conductor_model.actualizar_perfil(session["id_usuario"], telefono, vehiculo)
        flash("Perfil actualizado.", "success")
    return redirect(url_for("conductor.perfil"))