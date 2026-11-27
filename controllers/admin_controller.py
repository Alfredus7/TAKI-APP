import csv
import io
import math
import re
import sqlite3
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from flask import (Blueprint, Response, abort, flash, redirect, render_template,
                   request, session, url_for)

from controllers.decorators import login_required
from models import admin_model, servicio_model, usuario_model

admin_bp = Blueprint("admin", __name__)

_RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RE_TELEFONO = re.compile(r"^[0-9+\-\s]{0,20}$")
_RE_CODIGO = re.compile(r"^[A-Z0-9_\-]{3,20}$")


# ---------------------------------------------------------------- Helpers

def _fecha(valor):
    """'YYYY-MM-DD' válido o None."""
    try:
        return datetime.strptime(valor or "", "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _opcion(valor, permitidos):
    return valor if valor in permitidos else None


def _volver(por_defecto):
    """Vuelve a la página anterior si es del mismo sitio; si no, a `por_defecto`."""
    ref = request.referrer
    if ref and urlparse(ref).netloc == request.host:
        return redirect(ref)
    return redirect(por_defecto)


def _error_form(mensaje, destino):
    flash(mensaje, "error")
    return redirect(destino)


# ---------------------------------------------------------------- Dashboard

def _sparkline(valores, ancho=120, alto=36, margen=4):
    """Puntos del SVG (línea y área) para un minigráfico. Serie plana -> línea al medio."""
    n = len(valores)
    mayor, menor = max(valores), min(valores)
    puntos = []
    for i, v in enumerate(valores):
        x = margen + i * (ancho - 2 * margen) / (n - 1)
        y = (alto - margen - (v - menor) / (mayor - menor) * (alto - 2 * margen)) if mayor > menor else alto / 2
        puntos.append(f"{x:.1f},{y:.1f}")
    linea = " ".join(puntos)
    return {"linea": linea, "area": f"{linea} {ancho - margen},{alto} {margen},{alto}"}


def _barras(meses):
    """Altura (%) de cada barra respecto al mayor valor del periodo."""
    mayor = max([m["solicitados"] for m in meses] + [0])
    for m in meses:
        for clave in ("solicitados", "finalizados"):
            m["h_" + clave] = max(4, round(m[clave] / mayor * 100)) if m[clave] else 0
    return meses


def _donut(d, radio=40):
    """Arcos del anillo de disponibilidad (stroke-dasharray sobre un círculo de radio 40)."""
    perimetro = 2 * 3.14159265 * radio
    total = d["total"]
    segmentos, acumulado = [], 0.0
    for clave, clase in (("libres", "libres"), ("ocupados", "ocupados"), ("fuera", "fuera")):
        largo = d[clave] / total * perimetro if total else 0
        segmentos.append({"clase": clase, "dash": f"{largo:.2f} {perimetro - largo:.2f}",
                          "offset": f"{-acumulado:.2f}"})
        acumulado += largo
    activos = d["libres"] + d["ocupados"]
    return {**d, "segmentos": segmentos, "activos": activos,
            "pct_activos": round(activos / total * 100) if total else 0,
            "pct_libres": round(d["libres"] / total * 100) if total else 0,
            "pct_ocupados": round(d["ocupados"] / total * 100) if total else 0,
            "pct_fuera": round(d["fuera"] / total * 100) if total else 0}


@admin_bp.route("/dashboard")
@login_required("administrador")
def dashboard():
    series = admin_model.series_dashboard()
    pendientes = admin_model.listar_conductores("pendiente")
    return render_template(
        "admin/dashboard.html",
        m=admin_model.metricas_dashboard(),
        activos=admin_model.servicios_activos(),
        spark_servicios=_sparkline(series["servicios"]),
        spark_ingresos=_sparkline(series["ingresos"]),
        servicios_7d=sum(series["servicios"]),
        ingresos_7d=sum(series["ingresos"]),
        barras=_barras(admin_model.servicios_por_mes()),
        donut=_donut(admin_model.disponibilidad_conductores()),
        proximo=pendientes[0] if pendientes else None,
    )


# ---------------------------------------------------------------- Usuarios

@admin_bp.route("/usuarios")
@login_required("administrador")
def usuarios():
    filtros = {
        "q": request.args.get("q", "").strip() or None,
        "rol": _opcion(request.args.get("rol"), admin_model.ROLES),
        "estado": _opcion(request.args.get("estado"), admin_model.ESTADOS_USUARIO),
    }
    return render_template(
        "admin/usuarios.html",
        usuarios=admin_model.listar_usuarios(**filtros),
        filtros=filtros,
        roles=admin_model.ROLES,
        estados=admin_model.ESTADOS_USUARIO,
    )


def _leer_usuario(editando: bool):
    """Devuelve (datos, error)."""
    f = request.form
    datos = {k: f.get(k, "").strip() for k in
             ("nombre", "apellido", "ci", "telefono", "correo", "licencia",
              "descripcion_vehiculo", "direccion", "cargo")}
    datos["contrasena"] = f.get("contrasena", "")
    datos["telefono"] = datos["telefono"] or None
    datos["direccion"] = datos["direccion"] or None
    datos["descripcion_vehiculo"] = datos["descripcion_vehiculo"] or None
    datos["cargo"] = datos["cargo"] or "Administrador"
    datos["tipo_cliente"] = _opcion(f.get("tipo_cliente"), ("padre", "empresa")) or "padre"

    for campo, nombre in (("nombre", "El nombre"), ("apellido", "El apellido"),
                          ("ci", "El CI"), ("correo", "El correo")):
        if not datos[campo]:
            return datos, f"{nombre} es obligatorio."
    if not _RE_CORREO.match(datos["correo"]):
        return datos, "El correo no es válido."
    if datos["telefono"] and not _RE_TELEFONO.match(datos["telefono"]):
        return datos, "El teléfono solo admite números, +, - y espacios (máx. 20)."

    if datos["contrasena"] and len(datos["contrasena"]) < 6:
        return datos, "La contraseña debe tener al menos 6 caracteres."

    if editando:
        datos["estado"] = _opcion(f.get("estado"), admin_model.ESTADOS_USUARIO)
        if datos["estado"] is None:
            return datos, "Estado no válido."
    else:
        if not datos["contrasena"]:
            return datos, "La contraseña es obligatoria."
        datos["rol"] = _opcion(f.get("rol"), admin_model.ROLES)
        if datos["rol"] is None:
            return datos, "Rol no válido."
        if datos["rol"] == "conductor" and not datos["licencia"]:
            return datos, "La licencia es obligatoria para un conductor."
    return datos, None


@admin_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required("administrador")
def usuario_nuevo():
    if request.method == "POST":
        datos, error = _leer_usuario(editando=False)
        if error:
            return _error_form(error, url_for("admin.usuario_nuevo"))
        try:
            usuario_model.registrar_usuario(datos)
        except sqlite3.IntegrityError:
            return _error_form("El CI o el correo ya están registrados.", url_for("admin.usuario_nuevo"))
        if datos["rol"] == "conductor":
            flash("Conductor creado. Queda pendiente en Validación hasta que lo apruebes.", "success")
        else:
            flash("Usuario creado.", "success")
        return redirect(url_for("admin.usuarios"))
    return render_template("admin/usuario_form.html", u=None,
                           roles=admin_model.ROLES, estados=admin_model.ESTADOS_USUARIO)


@admin_bp.route("/usuarios/<int:id_usuario>/editar", methods=["GET", "POST"])
@login_required("administrador")
def usuario_editar(id_usuario):
    usuario = admin_model.obtener_usuario(id_usuario)
    if usuario is None:
        abort(404)
    if request.method == "POST":
        datos, error = _leer_usuario(editando=True)
        destino = url_for("admin.usuario_editar", id_usuario=id_usuario)
        if error:
            return _error_form(error, destino)
        if id_usuario == session["id_usuario"] and datos["estado"] != "activo":
            return _error_form("No puedes desactivar ni suspender tu propia cuenta.", destino)
        try:
            admin_model.actualizar_usuario(id_usuario, datos)
        except sqlite3.IntegrityError:
            return _error_form("El CI o el correo ya pertenecen a otro usuario.", destino)
        flash("Usuario actualizado.", "success")
        return redirect(url_for("admin.usuarios"))
    return render_template("admin/usuario_form.html", u=usuario,
                           roles=admin_model.ROLES, estados=admin_model.ESTADOS_USUARIO)


@admin_bp.route("/usuarios/<int:id_usuario>/estado", methods=["POST"])
@login_required("administrador")
def usuario_estado(id_usuario):
    estado = _opcion(request.form.get("estado"), admin_model.ESTADOS_USUARIO)
    if estado is None:
        flash("Estado no válido.", "error")
    elif id_usuario == session["id_usuario"]:
        flash("No puedes cambiar el estado de tu propia cuenta.", "error")
    elif admin_model.cambiar_estado_usuario(id_usuario, estado):
        flash(f"Cuenta {estado}.", "success")
    else:
        flash("Usuario no encontrado.", "error")
    return _volver(url_for("admin.usuarios"))


# ---------------------------------------------------------------- Conductores y validación

@admin_bp.route("/validacion")
@login_required("administrador")
def validacion():
    return render_template(
        "admin/validacion.html",
        pendientes=admin_model.listar_conductores("pendiente"),
        rechazados=admin_model.listar_conductores("rechazado"),
    )


@admin_bp.route("/conductores/<int:id_conductor>/validar", methods=["POST"])
@login_required("administrador")
def validar_conductor(id_conductor):
    accion = request.form.get("accion")
    if accion not in ("aprobar", "rechazar"):
        flash("Acción no válida.", "error")
    elif admin_model.validar_conductor(id_conductor, accion == "aprobar"):
        flash("Conductor aprobado." if accion == "aprobar" else "Conductor rechazado.", "success")
    else:
        flash("Conductor no encontrado.", "error")
    return _volver(url_for("admin.validacion"))


@admin_bp.route("/conductores")
@login_required("administrador")
def conductores():
    filtro = _opcion(request.args.get("validacion"), ("aprobado", "pendiente", "rechazado"))
    return render_template(
        "admin/conductores.html",
        conductores=admin_model.listar_conductores(filtro),
        filtro=filtro,
    )


@admin_bp.route("/conductores/<int:id_conductor>")
@login_required("administrador")
def conductor_detalle(id_conductor):
    conductor = admin_model.obtener_conductor(id_conductor)
    if conductor is None:
        abort(404)
    return render_template(
        "admin/conductor_detalle.html",
        c=conductor,
        resumen=admin_model.resumen_conductor_total(id_conductor),
        servicios=servicio_model.servicios_del_conductor(id_conductor)[:10],
    )


@admin_bp.route("/vehiculos")
@login_required("administrador")
def vehiculos():
    return render_template("admin/vehiculos.html", vehiculos=admin_model.listar_conductores())


@admin_bp.route("/vehiculos/<int:id_conductor>", methods=["POST"])
@login_required("administrador")
def vehiculo_actualizar(id_conductor):
    descripcion = request.form.get("descripcion_vehiculo", "").strip()
    if len(descripcion) > 200:
        flash("La descripción no puede superar 200 caracteres.", "error")
    elif admin_model.actualizar_vehiculo(id_conductor, descripcion or None):
        flash("Vehículo actualizado.", "success")
    else:
        flash("Conductor no encontrado.", "error")
    return redirect(url_for("admin.vehiculos"))


# ---------------------------------------------------------------- Viajes, courier y detalle

def _listado_servicios(tipo):
    filtros = {
        "estado": _opcion(request.args.get("estado"), admin_model.ESTADOS_SERVICIO),
        "desde": _fecha(request.args.get("desde")),
        "hasta": _fecha(request.args.get("hasta")),
    }
    return render_template(
        "admin/servicios.html",
        tipo=tipo,
        servicios=admin_model.listar_servicios(tipo, **filtros),
        filtros=filtros,
        estados=admin_model.ESTADOS_SERVICIO,
    )


@admin_bp.route("/viajes")
@login_required("administrador")
def viajes():
    return _listado_servicios("Mototaxi")


@admin_bp.route("/courier")
@login_required("administrador")
def courier():
    return _listado_servicios("Courier")


@admin_bp.route("/servicios/<int:id_servicio>")
@login_required("administrador")
def servicio_detalle(id_servicio):
    detalle = admin_model.obtener_servicio(id_servicio)
    if detalle is None:
        abort(404)
    return render_template("admin/servicio_detalle.html", **detalle)


@admin_bp.route("/servicios/<int:id_servicio>/cancelar", methods=["POST"])
@login_required("administrador")
def servicio_cancelar(id_servicio):
    if admin_model.cancelar_servicio(id_servicio):
        flash("Servicio cancelado.", "success")
    else:
        flash("El servicio ya no se puede cancelar.", "error")
    return redirect(url_for("admin.servicio_detalle", id_servicio=id_servicio))


# ---------------------------------------------------------------- Pagos

@admin_bp.route("/pagos")
@login_required("administrador")
def pagos():
    filtros = {
        "estado": _opcion(request.args.get("estado"), admin_model.ESTADOS_PAGO),
        "metodo": _opcion(request.args.get("metodo"), admin_model.METODOS_PAGO),
        "desde": _fecha(request.args.get("desde")),
        "hasta": _fecha(request.args.get("hasta")),
    }
    return render_template(
        "admin/pagos.html",
        pagos=admin_model.listar_pagos(**filtros),
        totales=admin_model.totales_pagos(**filtros),
        filtros=filtros,
        estados=admin_model.ESTADOS_PAGO,
        metodos=admin_model.METODOS_PAGO,
    )


# ---------------------------------------------------------------- Reclamos

@admin_bp.route("/reclamos")
@login_required("administrador")
def reclamos():
    filtros = {
        "tipo": _opcion(request.args.get("tipo"), admin_model.TIPOS_CONSULTA),
        "estado": _opcion(request.args.get("estado"), admin_model.ESTADOS_CONSULTA),
    }
    return render_template(
        "admin/reclamos.html",
        consultas=admin_model.listar_consultas(**filtros),
        filtros=filtros,
        tipos=admin_model.TIPOS_CONSULTA,
        estados=admin_model.ESTADOS_CONSULTA,
    )


@admin_bp.route("/reclamos/<int:id_consulta>/estado", methods=["POST"])
@login_required("administrador")
def reclamo_estado(id_consulta):
    estado = _opcion(request.form.get("estado"), admin_model.ESTADOS_CONSULTA)
    if estado is None:
        flash("Estado no válido.", "error")
    elif admin_model.cambiar_estado_consulta(id_consulta, estado):
        flash("Estado actualizado.", "success")
    else:
        flash("Consulta no encontrada.", "error")
    return _volver(url_for("admin.reclamos"))


# ---------------------------------------------------------------- Tarifas

@admin_bp.route("/tarifas")
@login_required("administrador")
def tarifas():
    return render_template("admin/tarifas.html", tarifas=admin_model.listar_tarifas())


@admin_bp.route("/tarifas/actualizar", methods=["POST"])
@login_required("administrador")
def tarifa_actualizar():
    tipo = request.form.get("tipo", "").strip()
    try:
        precio = float(request.form.get("precio", "").replace(",", "."))
    except ValueError:
        precio = None
    if precio is None or not math.isfinite(precio) or precio < 0 or precio > 10000:
        flash("Ingresa un precio válido (entre 0 y 10000).", "error")
    elif admin_model.actualizar_tarifa(tipo, round(precio, 2)):
        flash(f"Tarifa de {tipo} actualizada a Bs {precio:.2f}.", "success")
    else:
        flash("Tipo de servicio no encontrado.", "error")
    return redirect(url_for("admin.tarifas"))


# ---------------------------------------------------------------- Promociones

@admin_bp.route("/promociones")
@login_required("administrador")
def promociones():
    return render_template(
        "admin/promociones.html",
        promociones=admin_model.listar_promociones(),
        tipos=admin_model.nombres_tipos_servicio(),
    )


@admin_bp.route("/promociones/crear", methods=["POST"])
@login_required("administrador")
def promocion_crear():
    f = request.form
    codigo = f.get("codigo", "").strip().upper()
    inicio, fin = _fecha(f.get("fecha_inicio")), _fecha(f.get("fecha_fin"))
    tipo = _opcion(f.get("tipo_servicio") or None, admin_model.nombres_tipos_servicio())
    try:
        descuento = float(f.get("descuento", ""))
    except ValueError:
        descuento = None
    destino = url_for("admin.promociones")

    if not _RE_CODIGO.match(codigo):
        return _error_form("El código debe tener de 3 a 20 letras, números, - o _.", destino)
    if descuento is None or not math.isfinite(descuento) or not 1 <= descuento <= 100:
        return _error_form("El descuento debe estar entre 1 y 100.", destino)
    if not inicio or not fin or fin < inicio:
        return _error_form("Revisa las fechas: la fecha final no puede ser anterior a la inicial.", destino)
    try:
        admin_model.crear_promocion(codigo, f.get("descripcion", "").strip()[:120], descuento,
                                    inicio, fin, tipo)
    except sqlite3.IntegrityError:
        return _error_form("Ya existe una promoción con ese código.", destino)
    flash("Promoción creada.", "success")
    return redirect(destino)


@admin_bp.route("/promociones/<int:id_promocion>/estado", methods=["POST"])
@login_required("administrador")
def promocion_estado(id_promocion):
    activa = request.form.get("activa") == "1"
    if admin_model.cambiar_estado_promocion(id_promocion, activa):
        flash("Promoción activada." if activa else "Promoción desactivada.", "success")
    else:
        flash("Promoción no encontrada.", "error")
    return redirect(url_for("admin.promociones"))


# ---------------------------------------------------------------- Reportes

def _rango():
    hoy = date.today()
    hasta = _fecha(request.args.get("hasta")) or hoy.isoformat()
    desde = _fecha(request.args.get("desde")) or (hoy - timedelta(days=29)).isoformat()
    if desde > hasta:
        desde, hasta = hasta, desde
    return desde, hasta


@admin_bp.route("/reportes")
@login_required("administrador")
def reportes():
    desde, hasta = _rango()
    return render_template(
        "admin/reportes.html",
        desde=desde,
        hasta=hasta,
        resumen=admin_model.resumen_reporte(desde, hasta),
        por_dia=admin_model.reporte_por_dia(desde, hasta),
        top_conductores=admin_model.reporte_top_conductores(desde, hasta),
    )


@admin_bp.route("/reportes/csv")
@login_required("administrador")
def reportes_csv():
    desde, hasta = _rango()
    resumen = admin_model.resumen_reporte(desde, hasta)
    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(["Fecha", "Viajes", "Entregas", "Ingresos (Bs)"])
    for d in admin_model.reporte_por_dia(desde, hasta):
        escritor.writerow([d["fecha"], d["viajes"], d["entregas"], f"{d['ingresos']:.2f}"])
    escritor.writerow(["TOTAL", resumen["viajes"], resumen["entregas"], f"{resumen['ingresos']:.2f}"])
    return Response(
        "\ufeff" + buffer.getvalue(),  # BOM para que Excel respete los acentos
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="reporte_cuidavia_{desde}_{hasta}.csv"'},
    )