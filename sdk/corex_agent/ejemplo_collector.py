"""
Ejemplo de recolector para GestionAR. Copialo a tu app (p. ej. ventas/corex.py)
y apuntá COREX_METRICS_COLLECTOR = 'ventas.corex.recolectar'.

Corre DENTRO del schema del tenant, así que las consultas ya son del tenant.
- Métricas "contador": lo que pasó ese día.
- Métricas "nivel": el valor total en ese momento.
Las claves deben coincidir con las definidas en el Hub (Panel dev → SaaS → Métricas).
"""
from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.utils import timezone


def recolectar(fecha):
    inicio = timezone.make_aware(datetime.combine(fecha, time.min))
    fin = timezone.make_aware(datetime.combine(fecha, time.max))

    from ventas.models import Venta            # ajustá a tus modelos
    from inventario.models import Producto
    from facturacion.models import Comprobante

    ventas = Venta.objects.filter(fecha__range=(inicio, fin)).aggregate(n=Count('id'), total=Sum('total'))
    return {
        'ventas_cantidad': ventas['n'] or 0,
        'ventas_monto': float(ventas['total'] or 0),
        'comprobantes_arca': Comprobante.objects.filter(fecha__range=(inicio, fin), cae__isnull=False).count(),
        'usuarios': get_user_model().objects.filter(is_active=True).count(),
        'productos': Producto.objects.count(),
    }
