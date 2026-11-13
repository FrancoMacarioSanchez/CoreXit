"""Lectura, agregación y registro de métricas de tenants."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from ..models import LimitePlan, MetricaServicio, MetricaTenant, Tenant


def _num(valor):
    try:
        return float(Decimal(str(valor)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def parsear_fecha(valor, default=None):
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------- escritura
@transaction.atomic
def registrar_metricas(tenant, fecha, datos, origen='pull'):
    """
    Guarda (o fusiona) el snapshot de un día. Solo se aceptan valores numéricos.
    Devuelve el MetricaTenant.
    """
    limpios = {}
    for clave, valor in (datos or {}).items():
        num = _num(valor)
        if num is not None:
            limpios[str(clave)[:60]] = num
    obj, creado = MetricaTenant.objects.select_for_update().get_or_create(
        tenant=tenant, fecha=fecha, defaults={'datos': limpios, 'origen': origen},
    )
    if not creado:
        obj.datos = {**obj.datos, **limpios}
        obj.origen = origen
        obj.save(update_fields=['datos', 'origen', 'recibido'])
    return obj


def sincronizar_tenant(tenant, dias=7, usuario=None):
    """Trae del SaaS las métricas de los últimos `dias` días. Devuelve cantidad de días guardados."""
    from .integracion import SaaSClient

    hasta = timezone.localdate()
    desde = hasta - timedelta(days=dias - 1)
    respuesta = SaaSClient(tenant.servicio, usuario=usuario).metricas(tenant, desde, hasta)
    guardados = 0
    for item in respuesta.get('series', []):
        fecha = parsear_fecha(item.get('fecha'))
        if fecha:
            registrar_metricas(tenant, fecha, item.get('metricas', {}), origen='pull')
            guardados += 1
    estado = respuesta.get('estado')
    if estado in dict(Tenant.ESTADOS):
        tenant.estado = estado
    tenant.ultimo_sync = timezone.now()
    tenant.ultimo_error = ''
    tenant.save(update_fields=['estado', 'ultimo_sync', 'ultimo_error', 'actualizado'])
    return guardados


def sincronizar_servicio(servicio, dias=7, usuario=None):
    """Sincroniza todos los tenants activos de un SaaS. Devuelve (ok, errores)."""
    from .integracion import IntegracionError

    ok, errores = 0, []
    for tenant in servicio.tenants.filter(estado__in=['activo', 'suspendido']):
        try:
            sincronizar_tenant(tenant, dias=dias, usuario=usuario)
            ok += 1
        except IntegracionError as e:
            tenant.ultimo_error = str(e)
            tenant.save(update_fields=['ultimo_error', 'actualizado'])
            errores.append(f'{tenant.schema_name}: {e}')
    return ok, errores


# ----------------------------------------------------------------- lectura
def definiciones(servicio, solo_cliente=False):
    qs = MetricaServicio.objects.filter(servicio=servicio)
    if solo_cliente:
        qs = qs.filter(visible_cliente=True)
    return list(qs)


def ultimo_snapshot(tenant):
    return tenant.metricas.order_by('-fecha').first()


def serie_diaria(tenant, claves, dias=30):
    """
    {'labels': ['01/11', ...], 'series': {clave: [v, ...]}} rellenando días sin datos.
    Para métricas 'nivel' se arrastra el último valor conocido.
    """
    hasta = timezone.localdate()
    desde = hasta - timedelta(days=dias - 1)
    por_fecha = {m.fecha: m.datos for m in tenant.metricas.filter(fecha__gte=desde, fecha__lte=hasta)}
    tipos = dict(MetricaServicio.objects.filter(servicio=tenant.servicio, clave__in=claves).values_list('clave', 'tipo'))
    labels, series = [], {c: [] for c in claves}
    ultimo = {}
    for i in range(dias):
        f = desde + timedelta(days=i)
        labels.append(f.strftime('%d/%m'))
        datos = por_fecha.get(f, {})
        for c in claves:
            if c in datos:
                ultimo[c] = datos[c]
                series[c].append(datos[c])
            elif tipos.get(c) == 'nivel':
                series[c].append(ultimo.get(c))
            else:
                # contador sin dato: 0 si ese día hubo snapshot, hueco si no llegó nada
                series[c].append(0 if f in por_fecha else None)
    return {'labels': labels, 'series': series}


def consumo(tenant, solo_cliente=False):
    """
    Lista de dicts con el consumo del período vs. el límite del plan:
    contador -> suma desde el 1° del mes; nivel -> último valor.
    """
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    defs = definiciones(tenant.servicio, solo_cliente=solo_cliente)
    if not defs:
        return []
    del_mes = list(tenant.metricas.filter(fecha__gte=inicio_mes).values_list('fecha', 'datos'))
    ultimo = ultimo_snapshot(tenant)
    limites = {}
    if tenant.plan:
        limites = {l.metrica_id: float(l.limite) for l in LimitePlan.objects.filter(plan=tenant.plan)}

    resultado = []
    for d in defs:
        if d.tipo == 'contador':
            valor = sum(datos.get(d.clave, 0) or 0 for _, datos in del_mes)
            periodo = 'este mes'
        else:
            valor = (ultimo.datos.get(d.clave) if ultimo else None)
            periodo = 'actual'
        limite = limites.get(d.pk)
        if limite is None and d.unidad == '%':
            limite = 100.0  # métricas que ya son un porcentaje (p. ej. uso del tope de Monotributo)
        pct = None
        if limite and valor is not None:
            pct = round(min(valor / limite * 100, 999), 1) if limite else None
        resultado.append({
            'definicion': d, 'clave': d.clave, 'nombre': d.nombre, 'unidad': d.unidad,
            'valor': valor, 'limite': limite, 'pct': pct, 'periodo': periodo,
            'nivel_alerta': 'critico' if pct and pct >= 90 else 'alto' if pct and pct >= 75 else 'ok',
        })
    return resultado


def resumen_destacadas(tenant):
    """{clave: valor} del último snapshot, solo métricas destacadas (para tablas)."""
    snap = ultimo_snapshot(tenant)
    if not snap:
        return {}
    claves = MetricaServicio.objects.filter(servicio=tenant.servicio, destacada=True).values_list('clave', flat=True)
    return {c: snap.datos.get(c) for c in claves}
