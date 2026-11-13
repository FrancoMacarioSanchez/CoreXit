"""
Panel de desarrolladores: estado de cada SaaS, sus tenants y sus métricas.

Desde acá se ve la salud de la integración (llamadas Hub <-> SaaS), se crean
o importan tenants y se fuerza la sincronización de métricas.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from dashboard.forms import MetricaServicioForm, ServicioIntegracionForm, TenantForm
from dashboard.models import EventoIntegracion, MetricaServicio, MetricaTenant, Servicio, Tenant
from dashboard.permisos import dev_required
from dashboard.servicios import aprovisionamiento, metricas
from dashboard.servicios.integracion import IntegracionError, SaaSClient

DIAS_OPCIONES = (7, 30, 90)


def _ctx(seccion, **extra):
    return {
        'seccion': seccion,
        'servicios_nav': Servicio.objects.filter(activo=True).only('id', 'nombre', 'color'),
        'errores_24h': EventoIntegracion.objects.filter(exito=False, creado__gte=timezone.now() - timedelta(hours=24)).count(),
        **extra,
    }


def _salud(servicio):
    """Último health check de cada SaaS (sin llamar a la API: usa el log)."""
    ev = servicio.eventos.filter(accion='health').order_by('-creado').first()
    if not servicio.tiene_api:
        return {'estado': 'sin_api', 'texto': 'Sin API', 'clase': 'badge-mute', 'evento': None}
    if not ev:
        return {'estado': 'desconocido', 'texto': 'Sin chequear', 'clase': 'badge-mute', 'evento': None}
    if ev.exito:
        return {'estado': 'ok', 'texto': f'OK · {ev.duracion_ms} ms', 'clase': 'badge-ok', 'evento': ev}
    return {'estado': 'caido', 'texto': 'Con errores', 'clase': 'badge-bad', 'evento': ev}


@dev_required
def inicio(request):
    hace24 = timezone.now() - timedelta(hours=24)
    servicios = (Servicio.objects.annotate(
        n_tenants=Count('tenants', distinct=True),
        n_activos=Count('tenants', filter=Q(tenants__estado='activo'), distinct=True),
        n_problemas=Count('tenants', filter=Q(tenants__estado__in=['error', 'pendiente', 'aprovisionando']), distinct=True),
        ultimo_sync=Max('tenants__ultimo_sync'),
    ))
    tarjetas = []
    for s in servicios:
        ev = s.eventos.filter(creado__gte=hace24)
        tarjetas.append({
            's': s, 'salud': _salud(s),
            'llamadas_24h': ev.count(), 'errores_24h': ev.filter(exito=False).count(),
        })

    # Actividad de métricas recibidas por día (todas las fuentes), últimos 14 días
    desde = timezone.localdate() - timedelta(days=13)
    por_dia = dict(MetricaTenant.objects.filter(fecha__gte=desde).values('fecha')
                   .annotate(n=Count('id')).values_list('fecha', 'n'))
    dias = [desde + timedelta(days=i) for i in range(14)]
    chart_actividad = {'labels': [d.strftime('%d/%m') for d in dias], 'data': [por_dia.get(d, 0) for d in dias]}

    estados = dict(Tenant.objects.values('estado').annotate(n=Count('id')).values_list('estado', 'n'))
    return render(request, 'devpanel/inicio.html', _ctx(
        'inicio', tarjetas=tarjetas, chart_actividad=chart_actividad,
        estados={k: estados.get(k, 0) for k, _ in Tenant.ESTADOS}, total_tenants=sum(estados.values()),
        problemas=Tenant.objects.filter(estado__in=['error', 'pendiente', 'aprovisionando'])
                                .select_related('servicio', 'cliente')[:10],
        sin_datos=Tenant.objects.filter(estado='activo').filter(
            Q(ultimo_sync__isnull=True) | Q(ultimo_sync__lt=timezone.now() - timedelta(days=2))
        ).select_related('servicio')[:10],
        eventos=EventoIntegracion.objects.select_related('servicio', 'tenant')[:12],
    ))


@dev_required
def servicio(request, servicio_id):
    s = get_object_or_404(Servicio, pk=servicio_id)
    config_form = ServicioIntegracionForm(instance=s, prefix='cfg')
    metrica_form = MetricaServicioForm(prefix='m')

    if request.method == 'POST':
        accion = request.POST.get('accion')
        cliente = SaaSClient(s, usuario=request.user)
        try:
            if accion == 'health':
                r = cliente.health()
                messages.success(request, f'{s.nombre} respondió OK: {r}')
            elif accion == 'sync':
                ok, errores = metricas.sincronizar_servicio(s, dias=int(request.POST.get('dias', 7)), usuario=request.user)
                messages.success(request, f'{ok} tenants sincronizados.')
                for e in errores[:5]:
                    messages.error(request, e)
            elif accion == 'importar':
                creados, existentes = _importar_tenants(s, cliente.listar_tenants())
                messages.success(request, f'Importación: {creados} tenants nuevos, {existentes} ya existían.')
            elif accion == 'config':
                config_form = ServicioIntegracionForm(request.POST, instance=s, prefix='cfg')
                if config_form.is_valid():
                    config_form.save()
                    messages.success(request, 'Configuración guardada.')
                    return redirect('devpanel:servicio', servicio_id=s.id)
                messages.error(request, 'Revisá la configuración.')
            elif accion == 'rotar_token':
                s.ingest_token = None
                s.save()
                messages.warning(request, 'Se generó un nuevo token de ingesta. Actualizalo en el SaaS.')
            elif accion == 'metrica':
                metrica_form = MetricaServicioForm(request.POST, prefix='m')
                if metrica_form.is_valid():
                    m = metrica_form.save(commit=False)
                    m.servicio = s
                    m.save()
                    messages.success(request, f'Métrica "{m.nombre}" agregada.')
                    return redirect('devpanel:servicio', servicio_id=s.id)
            elif accion == 'borrar_metrica':
                MetricaServicio.objects.filter(servicio=s, pk=request.POST.get('metrica_id')).delete()
                messages.info(request, 'Métrica eliminada.')
        except IntegracionError as e:
            messages.error(request, f'Error con la API de {s.nombre}: {e}')
        form_con_errores = (config_form.is_bound and config_form.errors) or (metrica_form.is_bound and metrica_form.errors)
        if not form_con_errores:
            return redirect('devpanel:servicio', servicio_id=s.id)

    estado = request.GET.get('estado', '')
    q = request.GET.get('q', '').strip()
    tenants = s.tenants.select_related('cliente', 'contratacion__plan')
    if estado:
        tenants = tenants.filter(estado=estado)
    if q:
        tenants = tenants.filter(Q(nombre__icontains=q) | Q(schema_name__icontains=q) | Q(dominio__icontains=q))
    destacadas = list(s.metricas_definidas.filter(destacada=True))
    filas = [{'t': t, 'valores': metricas.resumen_destacadas(t)} for t in tenants]

    # Totales del SaaS: suma diaria de cada métrica destacada (30 días)
    desde = timezone.localdate() - timedelta(days=29)
    agregados = {}
    for fecha, datos in MetricaTenant.objects.filter(tenant__servicio=s, fecha__gte=desde).values_list('fecha', 'datos'):
        for d in destacadas:
            if d.clave in datos:
                agregados.setdefault(d.clave, {}).setdefault(fecha, 0)
                agregados[d.clave][fecha] += datos[d.clave] or 0
    dias = [desde + timedelta(days=i) for i in range(30)]
    chart = {'labels': [d.strftime('%d/%m') for d in dias],
             'series': [{'nombre': d.nombre, 'datos': [agregados.get(d.clave, {}).get(x) for x in dias]} for d in destacadas]}

    return render(request, 'devpanel/servicio.html', _ctx(
        f'servicio-{s.id}', s=s, salud=_salud(s), filas=filas, destacadas=destacadas, estado=estado, q=q,
        estados=Tenant.ESTADOS, config_form=config_form, metrica_form=metrica_form,
        definiciones=s.metricas_definidas.all(), chart=chart,
        ingest_url=request.build_absolute_uri(reverse('api:metricas')),
        estado_url=request.build_absolute_uri(reverse('api:estado_tenant')),
        eventos=s.eventos.select_related('tenant')[:15],
    ))


def _importar_tenants(servicio, lista):
    creados = existentes = 0
    for item in lista:
        schema = str(item.get('schema_name') or item.get('schema') or '').strip()
        if not schema or schema == 'public':
            continue
        _, creado = Tenant.objects.get_or_create(
            servicio=servicio, schema_name=schema,
            defaults={
                'nombre': item.get('nombre') or schema,
                'dominio': item.get('dominio') or '',
                'estado': item.get('estado') if item.get('estado') in dict(Tenant.ESTADOS) else 'activo',
                'id_externo': str(item.get('id') or ''),
            },
        )
        creados += creado
        existentes += not creado
    return creados, existentes


@dev_required
def tenant(request, tenant_id):
    t = get_object_or_404(Tenant.objects.select_related('servicio', 'cliente__user', 'contratacion__plan'), pk=tenant_id)
    if request.method == 'POST':
        accion = request.POST.get('accion')
        try:
            if accion == 'sync':
                n = metricas.sincronizar_tenant(t, dias=int(request.POST.get('dias', 30)), usuario=request.user)
                messages.success(request, f'{n} días de métricas sincronizados.')
            elif accion == 'aprovisionar':
                if aprovisionamiento.aprovisionar(t, usuario=request.user):
                    messages.success(request, 'Tenant aprovisionado en el SaaS.')
                else:
                    messages.warning(request, 'No se pudo aprovisionar automáticamente; se creó una tarea interna.')
            elif accion == 'suspender':
                aprovisionamiento.suspender(t, usuario=request.user, motivo=request.POST.get('motivo', ''))
                messages.warning(request, 'Tenant suspendido.')
            elif accion == 'reactivar':
                aprovisionamiento.reactivar(t, usuario=request.user)
                messages.success(request, 'Tenant reactivado.')
            elif accion == 'plan':
                SaaSClient(t.servicio, usuario=request.user).actualizar_plan(t)
                messages.success(request, 'Límites del plan enviados al SaaS.')
            elif accion == 'marcar_activo':
                t.estado = 'activo'
                t.ultimo_error = ''
                t.save()
                messages.success(request, 'Marcado como activo.')
        except IntegracionError as e:
            t.ultimo_error = str(e)
            t.save(update_fields=['ultimo_error', 'actualizado'])
            messages.error(request, f'Error con la API: {e}')
        return redirect('devpanel:tenant', tenant_id=t.id)

    try:
        dias = int(request.GET.get('dias', 30))
    except ValueError:
        dias = 30
    dias = dias if dias in DIAS_OPCIONES else 30
    defs = metricas.definiciones(t.servicio)
    ultimo = metricas.ultimo_snapshot(t)
    claves = [d.clave for d in defs]
    # Claves que llegan pero no están definidas (para detectar métricas nuevas del SaaS)
    no_definidas = sorted(set(ultimo.datos) - set(claves)) if ultimo else []
    serie = metricas.serie_diaria(t, claves + no_definidas, dias=dias)
    nombres = {d.clave: d for d in defs}
    graficos = [{'clave': c, 'nombre': nombres[c].nombre if c in nombres else c,
                 'unidad': nombres[c].unidad if c in nombres else '',
                 'tipo': nombres[c].tipo if c in nombres else 'nivel',
                 'datos': serie['series'][c]} for c in claves + no_definidas]
    return render(request, 'devpanel/tenant.html', _ctx(
        f'servicio-{t.servicio_id}', t=t, consumo=metricas.consumo(t), ultimo=ultimo, no_definidas=no_definidas,
        chart={'labels': serie['labels'], 'graficos': graficos}, dias=dias, dias_opciones=DIAS_OPCIONES,
        historial=t.metricas.all()[:15], eventos=t.eventos.all()[:20],
        tickets=t.tickets.all()[:10],
    ))


@dev_required
def tenant_form(request, tenant_id=None):
    instancia = get_object_or_404(Tenant, pk=tenant_id) if tenant_id else None
    inicial = {}
    if not instancia:
        if request.GET.get('servicio'):
            inicial['servicio'] = request.GET['servicio']
        if request.GET.get('contratacion'):
            from dashboard.models import Contratacion
            c = Contratacion.objects.filter(pk=request.GET['contratacion']).select_related('plan__servicio', 'cliente').first()
            if c and c.plan:
                inicial.update(servicio=c.plan.servicio_id, contratacion=c.pk, cliente=c.cliente_id,
                               nombre=c.cliente.nombre_visible,
                               schema_name=aprovisionamiento.sugerir_schema(c.plan.servicio, c.cliente),
                               dominio=aprovisionamiento.sugerir_dominio(c.plan.servicio, c.cliente))
    form = TenantForm(request.POST or None, instance=instancia, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        t = form.save(commit=False)
        if not t.cliente_id and t.contratacion_id:
            t.cliente = t.contratacion.cliente
        t.save()
        if form.cleaned_data.get('aprovisionar_ahora'):
            ok = aprovisionamiento.aprovisionar(t, usuario=request.user)
            (messages.success if ok else messages.warning)(
                request, 'Aprovisionado en el SaaS.' if ok else 'No se pudo aprovisionar; quedó una tarea interna.')
        else:
            messages.success(request, 'Tenant guardado.')
        return redirect('devpanel:tenant', tenant_id=t.id)
    return render(request, 'devpanel/tenant_form.html', _ctx('tenant_nuevo' if not instancia else f'servicio-{instancia.servicio_id}',
                                                             form=form, instancia=instancia))


@dev_required
def eventos(request):
    qs = EventoIntegracion.objects.select_related('servicio', 'tenant', 'usuario')
    if request.GET.get('servicio'):
        qs = qs.filter(servicio_id=request.GET['servicio'])
    if request.GET.get('error'):
        qs = qs.filter(exito=False)
    if request.GET.get('direccion') in ('entrante', 'saliente'):
        qs = qs.filter(direccion=request.GET['direccion'])
    return render(request, 'devpanel/eventos.html', _ctx('eventos', eventos=qs[:300], servicios=Servicio.objects.all()))


@dev_required
def documentacion(request):
    return render(request, 'devpanel/documentacion.html', _ctx(
        'docs', hub_url=request.build_absolute_uri('/').rstrip('/'),
        timeout=settings.COREX_SAAS_TIMEOUT,
    ))
