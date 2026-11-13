"""Pantallas para desarrolladores: métricas del servidor y actividad del staff."""
import csv
from collections import OrderedDict
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from dashboard.permisos import dev_required
from devpanel.views import _ctx

from . import middleware, sistema
from .models import MuestraRequests, MuestraServidor, RegistroActividad

# rango -> (duración, ancho del grupo en segundos)
RANGOS = OrderedDict([
    ('1h', (timedelta(hours=1), 60)),
    ('6h', (timedelta(hours=6), 300)),
    ('24h', (timedelta(hours=24), 900)),
    ('7d', (timedelta(days=7), 3600)),
])
GUARDAR_CADA = 55  # segundos entre muestras guardadas


def _etiqueta(ts, largo):
    ts = timezone.localtime(ts)
    return ts.strftime('%d/%m %H:%M' if largo else '%H:%M')


def _promedio(valores):
    v = [x for x in valores if x is not None]
    return round(sum(v) / len(v), 1) if v else None


def _series(rango):
    duracion, ancho = RANGOS[rango]
    desde = timezone.now() - duracion
    largo = duracion > timedelta(hours=24)

    grupos = OrderedDict()
    for m in MuestraServidor.objects.filter(creado__gte=desde).order_by('creado'):
        k = int(m.creado.timestamp() // ancho) * ancho
        grupos.setdefault(k, []).append(m)
    recursos = {'x': [], 'cpu': [], 'memoria': [], 'disco': [], 'db_ms': []}
    for k, ms in grupos.items():
        recursos['x'].append(_etiqueta(ms[0].creado, largo))
        recursos['cpu'].append(_promedio([m.cpu for m in ms]))
        recursos['memoria'].append(_promedio([m.memoria for m in ms]))
        recursos['disco'].append(_promedio([m.disco for m in ms]))
        recursos['db_ms'].append(_promedio([m.db_ms for m in ms]))

    grupos = OrderedDict()
    for m in MuestraRequests.objects.filter(minuto__gte=desde).order_by('minuto'):
        k = int(m.minuto.timestamp() // ancho) * ancho
        grupos.setdefault(k, []).append(m)
    trafico = {'x': [], 'total': [], 'c4xx': [], 'c5xx': [], 'ms_prom': [], 'ms_max': []}
    for k, ms in grupos.items():
        total = sum(m.total for m in ms)
        trafico['x'].append(_etiqueta(ms[0].minuto, largo))
        trafico['total'].append(total)
        trafico['c4xx'].append(sum(m.c4xx for m in ms))
        trafico['c5xx'].append(sum(m.c5xx for m in ms))
        trafico['ms_prom'].append(round(sum(m.suma_ms for m in ms) / total, 1) if total else None)
        trafico['ms_max'].append(max(m.max_ms for m in ms))
    return recursos, trafico


@dev_required
def servidor(request):
    return render(request, 'monitoreo/servidor.html', _ctx('servidor', info=sistema.info(), rangos=list(RANGOS)))


@dev_required
def servidor_datos(request):
    rango = request.GET.get('rango', '1h')
    if rango not in RANGOS:
        rango = '1h'
    vivo = sistema.muestra()
    ultima = MuestraServidor.objects.order_by('-creado').values_list('creado', flat=True).first()
    if ultima is None or (timezone.now() - ultima).total_seconds() >= GUARDAR_CADA:
        MuestraServidor.objects.create(**{k: vivo[k] for k in (
            'cpu', 'memoria', 'memoria_usada_mb', 'disco', 'carga', 'proceso_mb', 'db_ms')})
    middleware.volcar_pendiente()
    recursos, trafico = _series(rango)
    hace_h = timezone.now() - timedelta(hours=24)
    tot = MuestraRequests.objects.filter(minuto__gte=hace_h)
    from django.db.models import Sum
    agg = tot.aggregate(t=Sum('total'), e5=Sum('c5xx'), e4=Sum('c4xx'), ms=Sum('suma_ms'))
    t = agg['t'] or 0
    return JsonResponse({
        'vivo': vivo, 'recursos': recursos, 'trafico': trafico,
        'resumen_24h': {
            'pedidos': t, 'errores_5xx': agg['e5'] or 0, 'errores_4xx': agg['e4'] or 0,
            'ms_prom': round((agg['ms'] or 0) / t, 1) if t else None,
        },
    })


# ---------------------------------------------------------------- actividad del staff
POR_PAGINA = 50


def _filtrar(request):
    qs = RegistroActividad.objects.all()
    g = request.GET
    if g.get('usuario'):
        qs = qs.filter(username=g['usuario'])
    tipo = g.get('tipo')
    if tipo == 'acciones':
        qs = qs.filter(tipo='accion')
    elif tipo in dict(RegistroActividad.TIPOS):
        qs = qs.filter(tipo=tipo)
    elif tipo != 'todo':
        # por defecto, sin el ruido de cada visita a una pantalla
        qs = qs.exclude(tipo='vista')
    desde, hasta = parse_date(g.get('desde', '') or ''), parse_date(g.get('hasta', '') or '')
    if desde:
        qs = qs.filter(creado__date__gte=desde)
    if hasta:
        qs = qs.filter(creado__date__lte=hasta)
    q = g.get('q', '').strip()
    if q:
        qs = qs.filter(Q(descripcion__icontains=q) | Q(ruta__icontains=q) | Q(ip__icontains=q))
    return qs


@dev_required
def actividad(request):
    qs = _filtrar(request)

    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="actividad_staff.csv"'
        resp.write('﻿')
        w = csv.writer(resp)
        w.writerow(['Fecha', 'Usuario', 'Tipo', 'Descripción', 'Método', 'Ruta', 'Estado', 'IP'])
        for r in qs[:20000]:
            w.writerow([timezone.localtime(r.creado).strftime('%Y-%m-%d %H:%M:%S'), r.username, r.get_tipo_display(),
                        r.descripcion, r.metodo, r.ruta, r.estado_http or '', r.ip or ''])
        return resp

    ahora = timezone.now()
    User = get_user_model()
    por_usuario = (User.objects.filter(is_staff=True)
                   .annotate(
                       ultima=Max('actividad__creado'),
                       acciones_7d=Count('actividad', filter=Q(actividad__tipo='accion', actividad__creado__gte=ahora - timedelta(days=7))),
                       visitas_7d=Count('actividad', filter=Q(actividad__tipo='vista', actividad__creado__gte=ahora - timedelta(days=7))),
                       logins_7d=Count('actividad', filter=Q(actividad__tipo='login', actividad__creado__gte=ahora - timedelta(days=7))))
                   .order_by('-ultima', 'username'))
    base = RegistroActividad.objects
    pag = Paginator(qs.select_related('usuario'), POR_PAGINA).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'monitoreo/actividad.html', _ctx(
        'actividad',
        registros=pag, por_usuario=por_usuario, filtros=request.GET, querystring=params.urlencode(),
        tipos=RegistroActividad.TIPOS,
        kpis={
            'acciones_hoy': base.filter(tipo='accion', creado__date=timezone.localdate()).count(),
            'activos_24h': base.filter(creado__gte=ahora - timedelta(hours=24)).exclude(usuario=None).values('usuario').distinct().count(),
            'fallidos_24h': base.filter(tipo='login_fallido', creado__gte=ahora - timedelta(hours=24)).count(),
        },
    ))
