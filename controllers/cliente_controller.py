from datetime import date
import sqlite3

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)

from controllers.decorators import login_required
from models import cliente_model, notificacion_model, servicio_model

cliente_bp = Blueprint("cliente", __name__)

TIPOS_CONSULTA = ("consulta", "reclamo", "sugerencia")
METODOS_PAGO = ("efectivo", "tarjeta", "transferencia", "qr")


# ---------------------------------------------------------------- Helpers

def _cliente_actual():
    cliente = cliente_model.obtener_cliente_por_usuario(session["id_usuario"])
    if cliente is None:
        abort(403)
    return cliente


def _servicio_del_cliente(id_servicio: int, id_cliente: int):
    servicio = servicio_model.obtener_servicio_cliente(id_servicio, id_cliente)
    if servicio is None:
        abort(404)
    return servicio


def _datos_menor(form):
    nombre = form.get("nombres", "").strip()
    apellido = form.get("apellidos", "").strip()
    if not nombre or not apellido:
        return None
    return {
        "nombre": nombre,
        "apellido": apellido,
        "fecha_nacimiento": form.get("fecha_nacimiento") or None,
        "colegio": form.get("institucion", "").strip() or None,
        "contacto_emergencia": form.get("contacto_emergencia", "").strip() or None,
    }


def _puntuacion_desde_form(form):
    if form.get("puntuacion"):
        valores = [form.get("puntuacion")]
    else:
        valores = [v for v in (form.get("atencion"), form.get("transporte")) if v]
    try:
        notas = [int(v) for v in valores]
    except ValueError:
        return None
    if not notas or any(n < 1 or n > 5 for n in notas):
        return None
    return round(sum(notas) / len(notas))


def _url_google_maps(lat, lng):
    if lat is None or lng is None:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


# ---------------------------------------------------------------- Menú

@cliente_bp.route("/menu")
@cliente_bp.route("/cliente/menu")
@login_required("cliente")
def menu():
    cliente = _cliente_actual()
    id_cliente = cliente["id_cliente"]
    recientes = servicio_model.servicios_del_cliente(id_cliente, limite=4)
    activos = servicio_model.servicios_activos_del_cliente(id_cliente)
    notificaciones = notificacion_model.listar_por_usuario(session["id_usuario"], limite=3)
    return render_template(
        "cliente/menu.html",
        recientes=recientes,
        servicio_activo=activos[0] if activos else None,
        notificaciones=notificaciones,
    )


# ---------------------------------------------------------------- Perfil (Mi cuenta)

@cliente_bp.route("/cliente/perfil", methods=["GET", "POST"])
@login_required("cliente")
def perfil():
    _cliente_actual()
    actual = cliente_model.obtener_perfil(session["id_usuario"])

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip()
        ci = request.form.get("documento", "").strip()
        tipo = request.form.get("tipo_cliente", "padre")

        if not nombre or not correo or not ci:
            flash("Nombre, documento y correo son obligatorios.", "error")
        elif tipo not in ("padre", "empresa"):
            flash("Tipo de cliente no válido.", "error")
        else:
            datos = {
                "nombre": nombre,
                "apellido": request.form.get("apellido", "").strip() or actual["apellido"],
                "ci": ci,
                "telefono": request.form.get("telefono", "").strip() or None,
                "correo": correo,
                "direccion": request.form.get("direccion", "").strip() or None,
                "tipo_cliente": tipo,
            }
            try:
                cliente_model.actualizar_perfil(session["id_usuario"], datos)
                flash("Datos actualizados correctamente.", "success")
            except sqlite3.IntegrityError:
                flash("El correo o el documento ya están registrados.", "error")
        return redirect(url_for("cliente.perfil"))

    return render_template("cliente/perfil.html", usuario=cliente_model.obtener_perfil(session["id_usuario"]))


# ---------------------------------------------------------------- Mis hijos

@cliente_bp.route("/cliente/menores", methods=["GET", "POST"])
@login_required("cliente")
def menores():
    cliente = _cliente_actual()
    id_cliente = cliente["id_cliente"]

    if request.method == "POST":
        datos = _datos_menor(request.form)
        if datos is None:
            flash("Nombres y apellidos son obligatorios.", "error")
        else:
            cliente_model.crear_menor(id_cliente, datos)
            flash("Menor registrado.", "success")
        return redirect(url_for("cliente.menores"))

    return render_template("cliente/menores.html",
                           menores=cliente_model.listar_menores(id_cliente))


@cliente_bp.route("/cliente/menores/<int:id_menor>/editar", methods=["POST"])
@login_required("cliente")
def menor_editar(id_menor):
    cliente = _cliente_actual()
    datos = _datos_menor(request.form)
    if datos is None:
        flash("Nombres y apellidos son obligatorios.", "error")
    elif cliente_model.actualizar_menor(id_menor, cliente["id_cliente"], datos):
        flash("Datos del menor actualizados.", "success")
    else:
        flash("No se encontró el menor.", "error")
    return redirect(url_for("cliente.menores"))


# ---------------------------------------------------------------- Mototaxi

@cliente_bp.route("/cliente/mototaxi", methods=["GET", "POST"])
@login_required("cliente")
def solicitar_mototaxi():
    cliente = _cliente_actual()
    id_cliente = cliente["id_cliente"]

    if request.method == "POST":
        texto = request.form.get("origen", "").strip()
        destino_form = request.form.get("destino", "").strip()

        # --- NUEVO: Capturar coordenadas del formulario ---
        origen_lat = request.form.get("origen_lat") or None
        origen_lng = request.form.get("origen_lng") or None
        destino_lat = request.form.get("destino_lat") or None
        destino_lng = request.form.get("destino_lng") or None
        # ---------------------------------------------------

        lugar = request.form.get("lugar_id", "").strip()
        sentido = request.form.get("sentido", "ida")
        if sentido not in ("ida", "vuelta"):
            sentido = "ida"
        menor_raw = request.form.get("menor_id", "").strip()

        if not texto:
            flash("Indica la dirección.", "error")
            return redirect(url_for("cliente.solicitar_mototaxi"))

        fecha_programada = None
        if request.form.get("programado") == "si":
            fecha = request.form.get("fecha")
            hora = request.form.get("hora")
            if not fecha or not hora:
                flash("Para programar el viaje indica fecha y hora.", "error")
                return redirect(url_for("cliente.solicitar_mototaxi"))
            fecha_programada = f"{fecha} {hora}"

        id_menor = None
        if menor_raw:
            try:
                menor = cliente_model.obtener_menor(int(menor_raw), id_cliente)
            except ValueError:
                abort(400)
            if menor is None:
                abort(403)
            id_menor = menor["id_menor"]

            if not lugar:
                flash("Selecciona el colegio.", "error")
                return redirect(url_for("cliente.solicitar_mototaxi"))

            if sentido == "vuelta":
                origen, destino = lugar, texto
                # Intercambiamos coordenadas si es "vuelta" (colegio -> casa)
                origen_lat, origen_lng, destino_lat, destino_lng = destino_lat, destino_lng, origen_lat, origen_lng
            else:
                origen, destino = texto, lugar
        else:
            origen, destino = texto, (destino_form or "Por confirmar")

        tarifa = servicio_model.calcular_tarifa("Mototaxi")
        try:
            # --- NUEVO: Pasar coordenadas al modelo ---
            id_servicio = servicio_model.crear_servicio(
                id_cliente, "Mototaxi", origen, destino, tarifa, fecha_programada,
                origen_lat, origen_lng, destino_lat, destino_lng
            )
            # ------------------------------------------
            if id_menor:
                servicio_model.crear_viaje_menor(id_servicio, id_menor)
        except sqlite3.IntegrityError:
            flash("No se pudo registrar la solicitud. Verifica los datos ingresados.", "error")
            return redirect(url_for("cliente.solicitar_mototaxi"))

        if destino and destino != "Por confirmar":
            mensaje = (f"Solicitud de mototaxi registrada: {origen} → {destino}. "
                       f"Buscando conductor.")
        else:
            mensaje = f"Solicitud de mototaxi registrada en {origen}. Buscando conductor."

        notificacion_model.crear_notificacion(
            id_usuario=session["id_usuario"],
            id_servicio=id_servicio,
            titulo="Solicitud de mototaxi",
            mensaje=mensaje,
        )

        flash(f"Solicitud registrada. Tarifa: S/ {tarifa:.2f}", "success")
        return redirect(url_for("cliente.seguimiento_detalle", id_servicio=id_servicio))

    lugares = [{"id": c, "nombre": c, "tipo": "Colegio"}
               for c in cliente_model.colegios_frecuentes(id_cliente)]

    return render_template(
        "cliente/solicitar_mototaxi.html",
        menores=cliente_model.listar_menores(id_cliente),
        lugares=lugares,
        disponibles=servicio_model.conductores_disponibles(),
        tarifa=None,
        fecha_min=date.today().isoformat(),
    )


# ---------------------------------------------------------------- Courier

@cliente_bp.route("/cliente/courier", methods=["GET", "POST"])
@login_required("cliente")
def courier():
    cliente = _cliente_actual()
    id_cliente = cliente["id_cliente"]

    if request.method == "POST":
        f = request.form
        origen = f.get("origen", "").strip()
        destino = f.get("destino", "").strip()
        
        # --- NUEVO: Capturar coordenadas ---
        origen_lat = f.get("origen_lat") or None
        origen_lng = f.get("origen_lng") or None
        destino_lat = f.get("destino_lat") or None
        destino_lng = f.get("destino_lng") or None
        # -----------------------------------

        nombre_dest = f.get("dest_nombre", "").strip()
        tel_dest = f.get("dest_telefono", "").strip()
        descripcion = f.get("descripcion", "").strip()
        if not all([origen, destino, nombre_dest, tel_dest, descripcion]):
            flash("Completa los datos del envío y del destinatario.", "error")
            return redirect(url_for("cliente.courier"))

        tipo_envio = f.get("tipo_envio", "paquete")
        peso = f.get("peso", "").strip()
        referencia = f.get("dest_referencia", "").strip()
        detalle = f"[{tipo_envio}] {descripcion}"
        if peso:
            detalle += f" ({peso} kg)"
        if referencia:
            destino = f"{destino} - {referencia}"

        tarifa = servicio_model.calcular_tarifa("Courier")
        
        # --- NUEVO: Pasar coordenadas al modelo ---
        id_servicio = servicio_model.crear_servicio(
            id_cliente, "Courier", origen, destino, tarifa, 
            None, origen_lat, origen_lng, destino_lat, destino_lng
        )
        # ------------------------------------------
        
        servicio_model.crear_courier(
            id_servicio, cliente_model.obtener_empresa_id(id_cliente),
            detalle, nombre_dest, tel_dest)

        notificacion_model.crear_notificacion(
            id_usuario=session["id_usuario"],
            id_servicio=id_servicio,
            titulo="Solicitud de courier",
            mensaje=f"Envío registrado desde {origen} hasta {destino}. Buscando conductor.",
        )

        flash(f"Envío registrado. Tarifa: S/ {tarifa:.2f}", "success")
        return redirect(url_for("cliente.seguimiento_detalle", id_servicio=id_servicio))

    return render_template(
        "cliente/courier.html",
        envios=servicio_model.historial_envios(id_cliente, limite=5),
        tarifa=None,
    )


# ---------------------------------------------------------------- Seguimiento

@cliente_bp.route("/cliente/seguimiento")
@login_required("cliente")
def seguimiento():
    cliente = _cliente_actual()
    activos = servicio_model.servicios_activos_del_cliente(cliente["id_cliente"])
    if activos:
        return redirect(url_for("cliente.seguimiento_detalle", id_servicio=activos[0]["id"]))
    return render_template("cliente/seguimiento.html", servicio=None, activos=[])


@cliente_bp.route("/cliente/seguimiento/<int:id_servicio>")
@login_required("cliente")
def seguimiento_detalle(id_servicio):
    cliente = _cliente_actual()
    servicio = _servicio_del_cliente(id_servicio, cliente["id_cliente"])
    
    activos = servicio_model.servicios_activos_del_cliente(cliente["id_cliente"])
    
    return render_template(
        "cliente/seguimiento.html",
        servicio=servicio,
        activos=activos,
        ubicacion=servicio_model.ultima_ubicacion(id_servicio),
    )


@cliente_bp.route("/cliente/seguimiento/<int:id_servicio>/ubicacion")
@login_required("cliente")
def ubicacion_json(id_servicio):
    cliente = _cliente_actual()
    servicio = _servicio_del_cliente(id_servicio, cliente["id_cliente"])
    ubicacion = servicio_model.ultima_ubicacion(id_servicio)
    # MODIFICADO: Añadimos 'recogida' para que el frontend sepa en qué fase está
    return jsonify({
        "estado": servicio["estado"], 
        "recogida": servicio.get("recogida", False),
        "ubicacion": ubicacion
    })


# ---------------------------------------------------------------- Historial

@cliente_bp.route("/cliente/historial")
@login_required("cliente")
def historial():
    cliente = _cliente_actual()
    id_cliente = cliente["id_cliente"]
    return render_template(
        "cliente/historial.html",
        viajes=servicio_model.historial_viajes(id_cliente),
        envios=servicio_model.historial_envios(id_cliente),
    )


# ---------------------------------------------------------------- Calificar

@cliente_bp.route("/cliente/calificar/<int:id_servicio>", methods=["GET", "POST"])
@login_required("cliente")
def calificar(id_servicio):
    cliente = _cliente_actual()
    id_cliente = cliente["id_cliente"]
    servicio = _servicio_del_cliente(id_servicio, id_cliente)

    if servicio["estado"] != "finalizado":
        flash("Solo puedes calificar servicios finalizados.", "error")
        return redirect(url_for("cliente.seguimiento_detalle", id_servicio=id_servicio))

    if request.method == "POST":
        puntuacion = _puntuacion_desde_form(request.form)
        if puntuacion is None:
            flash("Selecciona una calificación entre 1 y 5.", "error")
        elif servicio_model.calificar_servicio(id_servicio, id_cliente, puntuacion):
            notificacion_model.crear_notificacion(
                id_usuario=session["id_usuario"],
                id_servicio=id_servicio,
                titulo="Calificación",
                mensaje=f"Registraste una calificación de {puntuacion}/5 para el servicio #{id_servicio}.",
            )
            flash("¡Gracias por tu calificación!", "success")
            return redirect(url_for("cliente.historial"))
        else:
            flash("Este servicio ya fue calificado.", "error")
        return redirect(url_for("cliente.calificar", id_servicio=id_servicio))

    return render_template("cliente/calificar.html", servicio=servicio)


# ---------------------------------------------------------------- Pagos

@cliente_bp.route("/cliente/pagos")
@login_required("cliente")
def pagos():
    cliente = _cliente_actual()
    id_cliente = cliente["id_cliente"]
    return render_template(
        "cliente/pagos.html",
        pendientes=cliente_model.pagos_pendientes(id_cliente),
        transacciones=cliente_model.historial_pagos(id_cliente),
    )


@cliente_bp.route("/cliente/pagos/<int:id_servicio>", methods=["POST"])
@login_required("cliente")
def pagar(id_servicio):
    cliente = _cliente_actual()
    servicio = _servicio_del_cliente(id_servicio, cliente["id_cliente"])

    if servicio["estado"] != "finalizado" or cliente_model.servicio_pagado(id_servicio):
        flash("Este servicio no está disponible para pago.", "error")
    else:
        metodo = request.form.get("metodo_pago", "efectivo")
        if metodo not in METODOS_PAGO:
            flash("Método de pago no válido.", "error")
            return redirect(url_for("cliente.pagos"))
        cliente_model.registrar_pago(id_servicio, servicio["precio"], metodo)
        notificacion_model.crear_notificacion(
            id_usuario=session["id_usuario"],
            id_servicio=id_servicio,
            titulo="Pago",
            mensaje=f"Pago de S/ {servicio['precio']} registrado mediante {metodo}.",
        )
        flash("Pago registrado.", "success")
    return redirect(url_for("cliente.pagos"))


# ---------------------------------------------------------------- Notificaciones

@cliente_bp.route("/cliente/notificaciones")
@login_required("cliente")
def notificaciones():
    _cliente_actual()
    return render_template(
        "cliente/notificaciones.html",
        notificaciones=notificacion_model.listar_por_usuario(session["id_usuario"]),
    )

@cliente_bp.route("/cliente/notificaciones/json")
@login_required("cliente")
def notificaciones_json():
    _cliente_actual()
    notifs = notificacion_model.listar_por_usuario(session["id_usuario"], limite=20)
    resultado = []
    for n in notifs:
        d = dict(n) if not isinstance(n, dict) else n
        resultado.append(d)
    return jsonify(resultado)


@cliente_bp.route("/cliente/notificaciones/<int:id_notificacion>/leer", methods=["POST"])
@login_required("cliente")
def marcar_notificacion_leida(id_notificacion):
    _cliente_actual()
    notificacion_model.marcar_leida(id_notificacion, session["id_usuario"])
    return redirect(url_for("cliente.notificaciones"))


@cliente_bp.route("/cliente/notificaciones/leer-todas", methods=["POST"])
@login_required("cliente")
def marcar_todas_notificaciones_leidas():
    _cliente_actual()
    notificacion_model.marcar_todas_leidas(session["id_usuario"])
    flash("Todas las notificaciones fueron marcadas como leídas.", "success")
    return redirect(url_for("cliente.notificaciones"))


# ---------------------------------------------------------------- Atención al cliente

@cliente_bp.route("/cliente/atencion", methods=["GET", "POST"])
@login_required("cliente")
def atencion():
    cliente = _cliente_actual()
    id_cliente = cliente["id_cliente"]

    if request.method == "POST":
        tipo = request.form.get("tipo", "")
        mensaje = request.form.get("mensaje", "").strip()
        id_servicio_raw = request.form.get("servicio_id") or None

        if tipo not in TIPOS_CONSULTA or not mensaje:
            flash("Selecciona un tipo y escribe un mensaje.", "error")
            return redirect(url_for("cliente.atencion"))

        id_servicio = None
        if id_servicio_raw:
            try:
                id_servicio = int(id_servicio_raw)
            except ValueError:
                abort(400)
            _servicio_del_cliente(id_servicio, id_cliente)

        cliente_model.crear_consulta(session["id_usuario"], tipo, mensaje, id_servicio)
        notificacion_model.crear_notificacion(
            id_usuario=session["id_usuario"],
            id_servicio=id_servicio,
            titulo=f"Atención ({tipo})",
            mensaje="Tu mensaje fue registrado y está en revisión.",
        )
        flash("Recibimos tu mensaje. Te responderemos pronto.", "success")
        return redirect(url_for("cliente.atencion"))

    return render_template(
        "cliente/atencion.html",
        servicios=servicio_model.servicios_del_cliente(id_cliente, limite=20),
        casos=cliente_model.listar_consultas(session["id_usuario"]),
    )