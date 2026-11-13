"""Portal del cliente: solo ve lo suyo (servicios, consumo, facturas, soporte, datos fiscales)."""
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from dashboard.forms import MensajeForm, PerfilFiscalForm, TicketClienteForm
from dashboard.models import ClienteProfile, Contratacion, FacturaCliente, PlanServicio, Servicio, Ticket, TicketMensaje
from dashboard.permisos import cliente_required
from dashboard.servicios import finanzas, metricas
from dashboard.views import _crear_contratacion

DIAS_OPCIONES = (7, 30, 90)


def _perfil(request):
    perfil, _ = ClienteProfile.objects.get_or_create(
        user=request.user,
        defaults={'nombre': request.user.get_full_name() or request.user.username, 'email': request.user.email},
    )
    return perfil


def _ctx(request, seccion, **extra):
    perfil = _perfil(request)
    return {
        'perfil': perfil,
        'seccion': seccion,
        'tickets_abiertos_count': perfil.tickets.filter(tipo='soporte', estado__in=['abierto', 'en_proceso']).count(),
        'facturas_pendientes_count': perfil.facturas.filter(estado__in=['pendiente', 'vencido']).count(),
        **extra,
    }


def _tenant(contratacion):
    return getattr(contratacion, 'tenant', None)


@cliente_required
def inicio(request):
    perfil = _perfil(request)
    contrataciones = list(perfil.contrataciones.select_related('plan__servicio', 'tenant')
                          .exclude(estado='historico'))
    tarjetas = []
    for c in contrataciones:
        t = _tenant(c)
        cons = metricas.consumo(t, solo_cliente=True) if t else []
        tarjetas.append({'c': c, 'tenant': t, 'consumo': cons[:3],
                         'alerta': any(m['nivel_alerta'] != 'ok' for m in cons)})

    activas = [c for c in contrataciones if c.estado == 'activo']
    proximo = min(activas, key=lambda c: c.fecha_vencimiento) if activas else None
    cobranza = finanzas.resumen_cobranza(perfil.facturas.all())
    return render(request, 'portal/inicio.html', _ctx(
        request, 'inicio',
        tarjetas=tarjetas,
        kpis={
            'servicios_activos': len(activas),
            'proximo_vencimiento': proximo,
            'pendiente_monto': cobranza['pendiente_monto'],
            'pendiente_count': cobranza['pendiente_count'],
            'vencido_count': cobranza['vencido_count'],
            'gasto_mensual': sum((c.valor_mensual for c in activas), 0),
        },
        chart_pagos=finanzas.serie_facturacion(perfil.facturas.all(), meses=12),
        ultimas_facturas=perfil.facturas.all()[:4],
        pendientes_pago=[c for c in contrataciones if c.estado == 'pendiente'],
    ))


@cliente_required
def servicios(request):
    perfil = _perfil(request)
    contrataciones = perfil.contrataciones.select_related('plan__servicio', 'tenant')
    return render(request, 'portal/servicios.html', _ctx(request, 'servicios', contrataciones=contrataciones))


@cliente_required
def servicio_detalle(request, contratacion_id):
    perfil = _perfil(request)
    c = get_object_or_404(Contratacion.objects.select_related('plan__servicio'), pk=contratacion_id, cliente=perfil)
    t = _tenant(c)
    try:
        dias = int(request.GET.get('dias', 30))
    except ValueError:
        dias = 30
    dias = dias if dias in DIAS_OPCIONES else 30

    graficos, consumo, ultimo = [], [], None
    if t:
        consumo = metricas.consumo(t, solo_cliente=True)
        defs = metricas.definiciones(t.servicio, solo_cliente=True)
        serie = metricas.serie_diaria(t, [d.clave for d in defs], dias=dias)
        graficos = [{'clave': d.clave, 'nombre': d.nombre, 'unidad': d.unidad, 'tipo': d.tipo,
                     'datos': serie['series'][d.clave]} for d in defs]
        ultimo = metricas.ultimo_snapshot(t)
        labels = serie['labels']
    else:
        labels = []
    return render(request, 'portal/servicio_detalle.html', _ctx(
        request, 'servicios', c=c, tenant=t, consumo=consumo, dias=dias, dias_opciones=DIAS_OPCIONES,
        chart={'labels': labels, 'graficos': graficos}, ultimo=ultimo,
        facturas=c.facturas.all()[:12],
        tickets=c.tickets.filter(tipo='soporte')[:5],
        planes_superiores=PlanServicio.objects.filter(servicio=c.plan.servicio, activo=True,
                                                      precio_mensual__gt=c.plan.precio_mensual) if c.plan else [],
    ))


@cliente_required
def contratar(request):
    perfil = _perfil(request)
    if request.method == 'POST':
        plan = get_object_or_404(PlanServicio, pk=request.POST.get('plan'), activo=True)
        frecuencia = request.POST.get('frecuencia') if request.POST.get('frecuencia') in ('mensual', 'anual') else 'mensual'
        c = _crear_contratacion(perfil, plan, frecuencia)
        return redirect('portal:checkout', contratacion_id=c.id)
    servicios_qs = (Servicio.objects.filter(activo=True, planes__activo=True).distinct()
                    .prefetch_related('planes__limites__metrica'))
    contratados = set(perfil.contrataciones.filter(estado__in=['activo', 'pendiente'])
                      .values_list('plan_id', flat=True))
    return render(request, 'portal/contratar.html', _ctx(request, 'contratar', servicios=servicios_qs,
                                                         contratados=contratados))


@cliente_required
def checkout(request, contratacion_id):
    perfil = _perfil(request)
    c = get_object_or_404(Contratacion, id=contratacion_id, cliente=perfil, estado__in=['pendiente', 'suspendido'])
    if request.method == 'POST':
        if c.link_pago:
            return redirect(c.link_pago)
        messages.error(request, 'Este plan todavía no tiene link de pago. Te contactamos a la brevedad.')
        return redirect('portal:servicios')
    return render(request, 'portal/checkout.html', {
        'contratacion': c, 'plan': c.plan, 'link_pago': c.link_pago, 'precio': c.precio,
    })


@cliente_required
def cancelar_solicitud(request, contratacion_id):
    perfil = _perfil(request)
    c = get_object_or_404(Contratacion, id=contratacion_id, cliente=perfil, estado='pendiente')
    if request.method == 'POST':
        c.delete()
        messages.success(request, 'Solicitud cancelada.')
    return redirect('portal:servicios')


@cliente_required
def facturas(request):
    perfil = _perfil(request)
    qs = perfil.facturas.select_related('contratacion__plan__servicio')
    filtro = request.GET.get('estado', '')
    if filtro == 'pendiente':
        qs = qs.filter(estado__in=['pendiente', 'vencido'])
    elif filtro == 'pagado':
        qs = qs.filter(estado='pagado')
    return render(request, 'portal/facturas.html', _ctx(
        request, 'facturas', facturas=qs, filtro=filtro,
        cobranza=finanzas.resumen_cobranza(perfil.facturas.all()),
        chart_pagos=finanzas.serie_facturacion(perfil.facturas.all(), meses=12),
    ))


@cliente_required
def factura_pdf(request, factura_id):
    f = get_object_or_404(FacturaCliente, pk=factura_id, cliente__user=request.user)
    if not f.archivo_pdf:
        raise Http404
    return FileResponse(f.archivo_pdf.open('rb'), as_attachment=False,
                        filename=f'factura-{f.tipo_comprobante}-{f.numero_comprobante}.pdf')


@cliente_required
def soporte(request):
    perfil = _perfil(request)
    form = TicketClienteForm(request.POST or None, cliente=perfil,
                             initial={'contratacion': request.GET.get('servicio')})
    if request.method == 'POST' and form.is_valid():
        t = form.save(commit=False)
        t.cliente = perfil
        t.tipo = 'soporte'
        if t.contratacion:
            t.tenant = _tenant(t.contratacion)
        t.save()
        messages.success(request, f'Ticket #{t.id} creado. Te respondemos por acá.')
        return redirect('portal:ticket', ticket_id=t.id)
    tickets = (perfil.tickets.filter(tipo='soporte').select_related('contratacion__plan__servicio')
               .annotate(n_mensajes=Count('mensajes', filter=Q(mensajes__interno=False))))
    return render(request, 'portal/soporte.html', _ctx(request, 'soporte', form=form, tickets=tickets))


@cliente_required
def ticket(request, ticket_id):
    perfil = _perfil(request)
    t = get_object_or_404(Ticket, pk=ticket_id, cliente=perfil, tipo='soporte')
    form = MensajeForm(request.POST or None)
    if request.method == 'POST':
        if request.POST.get('accion') == 'cerrar':
            t.estado = 'cerrado'
            t.save(update_fields=['estado', 'updated_at'])
            messages.success(request, 'Ticket cerrado. ¡Gracias!')
            return redirect('portal:ticket', ticket_id=t.id)
        if form.is_valid():
            TicketMensaje.objects.create(ticket=t, autor=request.user, mensaje=form.cleaned_data['mensaje'])
            if t.estado in ('resuelto', 'cerrado'):
                t.estado = 'abierto'  # el cliente reabre al responder
            t.save()
            return redirect('portal:ticket', ticket_id=t.id)
    return render(request, 'portal/ticket.html', _ctx(
        request, 'soporte', ticket=t, form=form,
        mensajes=t.mensajes.filter(interno=False).select_related('autor'),
    ))


@cliente_required
def perfil(request):
    p = _perfil(request)
    form = PerfilFiscalForm(request.POST or None, instance=p)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if form.cleaned_data.get('email') and request.user.email != form.cleaned_data['email']:
            request.user.email = form.cleaned_data['email']
            request.user.save(update_fields=['email'])
        messages.success(request, 'Datos actualizados.')
        return redirect('portal:perfil')
    return render(request, 'portal/perfil.html', _ctx(request, 'perfil', form=form))
