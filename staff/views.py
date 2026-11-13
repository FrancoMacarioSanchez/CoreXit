"""Backoffice del equipo CoreX: clientes, contrataciones, facturación, soporte y tareas."""
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from dashboard.forms import FacturaForm, MensajeForm, NotasInternasForm, TareaForm, TicketStaffForm
from dashboard.models import ClienteProfile, Contratacion, FacturaCliente, Tenant, Ticket, TicketMensaje
from dashboard.permisos import staff_required
from dashboard.servicios import aprovisionamiento, finanzas, metricas


def _ctx(seccion, **extra):
    return {
        'seccion': seccion,
        'tickets_abiertos_count': Ticket.objects.filter(tipo='soporte', estado='abierto').count(),
        'tareas_abiertas_count': Ticket.objects.filter(tipo='desarrollo', estado__in=['abierto', 'en_proceso']).count(),
        **extra,
    }


@staff_required
def inicio(request):
    hoy = timezone.localdate()
    contrataciones = Contratacion.objects.select_related('plan__servicio', 'cliente')
    mrr = finanzas.mrr(contrataciones)
    cobranza = finanzas.resumen_cobranza()
    return render(request, 'staff/inicio.html', _ctx(
        'inicio',
        kpis={
            'mrr': mrr, 'arr': mrr * 12,
            'clientes': ClienteProfile.objects.count(),
            'clientes_activos': ClienteProfile.objects.filter(contrataciones__estado='activo').distinct().count(),
            'contrataciones_activas': contrataciones.filter(estado='activo').count(),
            'pendientes_pago': contrataciones.filter(estado='pendiente').count(),
            **cobranza,
        },
        chart_ingresos=finanzas.serie_facturacion(FacturaCliente.objects.all(), meses=12),
        chart_servicios=finanzas.suscripciones_por_servicio(),
        chart_planes=finanzas.suscripciones_por_plan(),
        por_vencer=contrataciones.filter(estado='activo', fecha_vencimiento__lte=hoy + timedelta(days=15))
                                 .order_by('fecha_vencimiento')[:8],
        pendientes=contrataciones.filter(estado='pendiente').order_by('-fecha_inicio')[:8],
        ultimos_tickets=Ticket.objects.filter(tipo='soporte', estado__in=['abierto', 'en_proceso'])
                                      .select_related('cliente')[:6],
        tenants_problema=Tenant.objects.filter(estado__in=['error', 'pendiente', 'aprovisionando'])
                                       .select_related('servicio', 'cliente')[:6],
    ))


@staff_required
def clientes(request):
    q = request.GET.get('q', '').strip()
    filtro = request.GET.get('filtro', '')
    hoy = timezone.localdate()
    qs = (ClienteProfile.objects.select_related('user')
          .annotate(n_activos=Count('contrataciones', filter=Q(contrataciones__estado='activo'), distinct=True),
                    n_vencidas=Count('facturas', filter=Q(facturas__estado__in=['pendiente', 'vencido'],
                                                          facturas__fecha_vencimiento__lt=hoy), distinct=True),
                    n_tickets=Count('tickets', filter=Q(tickets__estado__in=['abierto', 'en_proceso'],
                                                        tickets__tipo='soporte'), distinct=True)))
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(empresa__icontains=q) | Q(cuit_cuil__icontains=q) |
                       Q(email__icontains=q) | Q(user__username__icontains=q))
    if filtro == 'mora':
        qs = qs.filter(n_vencidas__gt=0)
    elif filtro == 'activos':
        qs = qs.filter(n_activos__gt=0)
    elif filtro == 'sin_servicio':
        qs = qs.filter(n_activos=0)
    return render(request, 'staff/clientes.html', _ctx('clientes', clientes=qs.prefetch_related('contrataciones__plan__servicio'),
                                                       q=q, filtro=filtro))


@staff_required
def cliente_detalle(request, cliente_id):
    cliente = get_object_or_404(ClienteProfile.objects.select_related('user'), pk=cliente_id)
    notas_form = NotasInternasForm(instance=cliente)

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'notas':
            notas_form = NotasInternasForm(request.POST, instance=cliente)
            if notas_form.is_valid():
                notas_form.save()
                messages.success(request, 'Notas guardadas.')
        elif accion in ('activar', 'suspender', 'finalizar', 'renovar'):
            c = get_object_or_404(Contratacion, pk=request.POST.get('contratacion_id'), cliente=cliente)
            if accion == 'activar':
                aprovisionamiento.activar_contratacion(c)
                messages.success(request, f'{c} activada. Se pidió el alta del sistema.')
            elif accion == 'suspender':
                c.estado = 'suspendido'
                c.save()
                messages.warning(request, f'{c} suspendida.')
            elif accion == 'finalizar':
                c.estado = 'historico'
                c.save()
                messages.info(request, f'{c} finalizada.')
            elif accion == 'renovar':
                dias = 365 if c.frecuencia_pago == 'anual' else 30
                c.fecha_vencimiento = max(c.fecha_vencimiento, timezone.localdate()) + timedelta(days=dias)
                c.save(update_fields=['fecha_vencimiento'])
                messages.success(request, f'Renovada hasta {c.fecha_vencimiento:%d/%m/%Y}.')
        return redirect('staff:cliente', cliente_id=cliente.id)

    contrataciones = list(cliente.contrataciones.select_related('plan__servicio', 'tenant'))
    sistemas = []
    for c in contrataciones:
        t = getattr(c, 'tenant', None)
        sistemas.append({'c': c, 'tenant': t, 'consumo': metricas.consumo(t) if t else []})
    facturas = cliente.facturas.select_related('contratacion__plan__servicio')
    return render(request, 'staff/cliente_detalle.html', _ctx(
        'clientes', cliente=cliente, sistemas=sistemas, facturas=facturas,
        cobranza=finanzas.resumen_cobranza(facturas),
        tickets=cliente.tickets.select_related('contratacion__plan__servicio')[:15],
        notas_form=notas_form,
        mrr_cliente=sum((c.valor_mensual for c in contrataciones if c.estado == 'activo'), 0),
    ))


@staff_required
def facturacion(request):
    form = FacturaForm(request.POST or None, request.FILES or None,
                       initial={'cliente': request.GET.get('cliente'), 'fecha_emision': timezone.localdate()})
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'crear':
            if form.is_valid():
                f = form.save()
                messages.success(request, f'Factura {f.numero_comprobante} publicada en el portal de {f.cliente.nombre_visible}.')
                return redirect('staff:facturacion')
        elif accion in ('pagada', 'anular'):
            f = get_object_or_404(FacturaCliente, pk=request.POST.get('factura_id'))
            if accion == 'pagada':
                f.estado = 'pagado'
                f.fecha_pago = timezone.now()
                f.metodo_pago = request.POST.get('metodo_pago') or f.metodo_pago or 'transferencia'
                f.save()
                messages.success(request, f'Factura {f.numero_comprobante} marcada como pagada.')
            else:
                f.estado = 'anulado'
                f.save(update_fields=['estado'])
                messages.info(request, f'Factura {f.numero_comprobante} anulada.')
            volver = request.POST.get('volver', '')
            if volver and url_has_allowed_host_and_scheme(volver, {request.get_host()}):
                return redirect(volver)
            return redirect('staff:facturacion')

    filtro = request.GET.get('estado', '')
    qs = FacturaCliente.objects.select_related('cliente', 'contratacion__plan__servicio')
    hoy = timezone.localdate()
    if filtro == 'pendiente':
        qs = qs.filter(estado__in=['pendiente', 'vencido'])
    elif filtro == 'vencido':
        qs = qs.filter(estado__in=['pendiente', 'vencido'], fecha_vencimiento__lt=hoy)
    elif filtro == 'pagado':
        qs = qs.filter(estado='pagado')
    return render(request, 'staff/facturacion.html', _ctx(
        'facturacion', form=form, facturas=qs[:300], filtro=filtro,
        cobranza=finanzas.resumen_cobranza(), metodos=FacturaCliente.METODO_PAGO_CHOICES,
    ))


@staff_required
def factura_pdf(request, factura_id):
    f = get_object_or_404(FacturaCliente, pk=factura_id)
    if not f.archivo_pdf:
        raise Http404
    return FileResponse(f.archivo_pdf.open('rb'), filename=f'factura-{f.numero_comprobante}.pdf')


@staff_required
def soporte(request):
    estado = request.GET.get('estado', 'activos')
    qs = Ticket.objects.filter(tipo='soporte').select_related('cliente', 'contratacion__plan__servicio', 'asignado_a') \
        .annotate(n_mensajes=Count('mensajes'))
    if estado == 'activos':
        qs = qs.filter(estado__in=['abierto', 'en_proceso'])
    elif estado in dict(Ticket.ESTADOS):
        qs = qs.filter(estado=estado)
    if request.GET.get('mios'):
        qs = qs.filter(asignado_a=request.user)
    return render(request, 'staff/soporte.html', _ctx('soporte', tickets=qs, estado=estado, estados=Ticket.ESTADOS))


@staff_required
def ticket(request, ticket_id):
    t = get_object_or_404(Ticket.objects.select_related('cliente', 'contratacion__plan__servicio', 'tenant__servicio'),
                          pk=ticket_id)
    form = MensajeForm(request.POST or None)
    gestion = TicketStaffForm(request.POST or None, instance=t, prefix='g')
    if request.method == 'POST':
        if request.POST.get('accion') == 'gestion':
            if gestion.is_valid():
                gestion.save()
                messages.success(request, 'Ticket actualizado.')
        elif form.is_valid():
            interno = bool(request.POST.get('interno'))
            TicketMensaje.objects.create(ticket=t, autor=request.user, mensaje=form.cleaned_data['mensaje'], interno=interno)
            if not interno and t.estado == 'abierto':
                t.estado = 'en_proceso'
            if not t.asignado_a:
                t.asignado_a = request.user
            t.save()
        return redirect('staff:ticket', ticket_id=t.id)
    return render(request, 'staff/ticket.html', _ctx(
        'tareas' if t.tipo == 'desarrollo' else 'soporte',
        ticket=t, form=form, gestion=gestion, mensajes=t.mensajes.select_related('autor'),
    ))


@staff_required
def tareas(request):
    form = TareaForm(request.POST or None, initial={'asignado_a': request.user})
    if request.method == 'POST':
        if request.POST.get('accion') == 'mover':
            t = get_object_or_404(Ticket, pk=request.POST.get('ticket_id'), tipo='desarrollo')
            if request.POST.get('estado') in dict(Ticket.ESTADOS):
                t.estado = request.POST['estado']
                t.save(update_fields=['estado', 'updated_at'])
            return redirect('staff:tareas')
        if form.is_valid():
            t = form.save(commit=False)
            t.tipo = 'desarrollo'
            t.save()
            messages.success(request, 'Tarea creada.')
            return redirect('staff:tareas')
    qs = Ticket.objects.filter(tipo='desarrollo').select_related('cliente', 'asignado_a', 'tenant__servicio')
    if request.GET.get('mias'):
        qs = qs.filter(asignado_a=request.user)
    columnas = [
        ('abierto', 'Pendiente', qs.filter(estado='abierto')),
        ('en_proceso', 'En desarrollo', qs.filter(estado='en_proceso')),
        ('resuelto', 'Hecho (últimas)', qs.filter(estado__in=['resuelto', 'cerrado']).order_by('-updated_at')[:15]),
    ]
    return render(request, 'staff/tareas.html', _ctx('tareas', columnas=columnas, form=form))
