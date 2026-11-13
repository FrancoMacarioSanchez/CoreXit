"""KPIs y series de facturación reales (reemplaza los datos de ejemplo de los gráficos)."""
from collections import OrderedDict
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from ..models import Contratacion, FacturaCliente

MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def _ultimos_meses(n):
    hoy = timezone.localdate().replace(day=1)
    meses = []
    a, m = hoy.year, hoy.month
    for _ in range(n):
        meses.append(date(a, m, 1))
        m -= 1
        if m == 0:
            a, m = a - 1, 12
    return list(reversed(meses))


def serie_facturacion(facturas_qs, meses=12):
    """Facturado (emitido, no anulado) vs. cobrado por mes."""
    lista = _ultimos_meses(meses)
    desde = lista[0]
    base = facturas_qs.exclude(estado='anulado')

    facturado = OrderedDict((m, Decimal('0')) for m in lista)
    for fila in (base.filter(fecha_emision__gte=desde).annotate(mes=TruncMonth('fecha_emision'))
                 .values('mes').annotate(total=Sum('monto'))):
        mes = fila['mes'].date() if hasattr(fila['mes'], 'date') else fila['mes']
        if mes in facturado:
            facturado[mes] = fila['total'] or Decimal('0')

    cobrado = OrderedDict((m, Decimal('0')) for m in lista)
    for f in base.filter(estado='pagado', fecha_pago__isnull=False, fecha_pago__date__gte=desde):
        mes = timezone.localtime(f.fecha_pago).date().replace(day=1)
        if mes in cobrado:
            cobrado[mes] += f.monto

    return {
        'labels': [f'{MESES[m.month - 1]} {str(m.year)[2:]}' for m in lista],
        'facturado': [float(v) for v in facturado.values()],
        'cobrado': [float(v) for v in cobrado.values()],
    }


def mrr(contrataciones_qs=None):
    qs = (contrataciones_qs if contrataciones_qs is not None else Contratacion.objects.all())
    return sum((c.valor_mensual for c in qs.filter(estado='activo').select_related('plan')), Decimal('0'))


def suscripciones_por_servicio():
    filas = (Contratacion.objects.filter(estado='activo', plan__isnull=False)
             .values('plan__servicio__nombre', 'plan__servicio__color')
             .annotate(n=Count('id')).order_by('-n'))
    return {
        'labels': [f['plan__servicio__nombre'] for f in filas],
        'data': [f['n'] for f in filas],
        'colores': [f['plan__servicio__color'] or '#6366f1' for f in filas],
    }


def suscripciones_por_plan():
    filas = (Contratacion.objects.filter(estado='activo', plan__isnull=False)
             .values('plan__servicio__nombre', 'plan__nombre')
             .annotate(n=Count('id')).order_by('-n'))
    return {
        'labels': [f"{f['plan__servicio__nombre']} · {f['plan__nombre']}" for f in filas],
        'data': [f['n'] for f in filas],
    }


def resumen_cobranza(facturas_qs=None):
    qs = facturas_qs if facturas_qs is not None else FacturaCliente.objects.all()
    hoy = timezone.localdate()
    pendientes = qs.filter(estado__in=['pendiente', 'vencido'])
    vencidas = pendientes.filter(fecha_vencimiento__lt=hoy)
    return {
        'pendiente_monto': pendientes.aggregate(t=Sum('monto'))['t'] or Decimal('0'),
        'pendiente_count': pendientes.count(),
        'vencido_monto': vencidas.aggregate(t=Sum('monto'))['t'] or Decimal('0'),
        'vencido_count': vencidas.count(),
        'cobrado_total': qs.filter(estado='pagado').aggregate(t=Sum('monto'))['t'] or Decimal('0'),
    }
