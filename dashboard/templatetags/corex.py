from decimal import Decimal, InvalidOperation

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

_BADGES = {
    # verde
    'activo': 'badge-ok', 'pagado': 'badge-ok', 'resuelto': 'badge-ok', 'ok': 'badge-ok',
    # ámbar
    'pendiente': 'badge-warn', 'aprovisionando': 'badge-warn', 'en_proceso': 'badge-info', 'abierto': 'badge-warn',
    'suspendido': 'badge-warn', 'alta': 'badge-warn', 'alto': 'badge-warn', 'media': 'badge-info',
    # rojo
    'vencido': 'badge-bad', 'error': 'badge-bad', 'urgente': 'badge-bad', 'critico': 'badge-bad', 'anulado': 'badge-mute',
    # gris
    'historico': 'badge-mute', 'cerrado': 'badge-mute', 'baja': 'badge-mute',
}

_ETIQUETAS = {
    'activo': 'Activo', 'pendiente': 'Pendiente', 'aprovisionando': 'Aprovisionando', 'suspendido': 'Suspendido',
    'historico': 'Finalizado', 'error': 'Error', 'baja': 'Baja', 'pagado': 'Pagado', 'vencido': 'Vencido',
    'anulado': 'Anulado', 'abierto': 'Abierto', 'en_proceso': 'En proceso', 'resuelto': 'Resuelto', 'cerrado': 'Cerrado',
    'baja_p': 'Baja', 'media': 'Media', 'alta': 'Alta', 'urgente': 'Urgente',
}


@register.filter
def badge(estado):
    """Clase CSS para un estado cualquiera (contratación, factura, ticket, tenant)."""
    return _BADGES.get(str(estado), 'badge-mute')


@register.simple_tag
def estado(valor, texto=None):
    """<span class="badge ...">Texto</span>"""
    v = str(valor)
    etiqueta = texto or _ETIQUETAS.get(v, v.replace('_', ' ').capitalize())
    return mark_safe(f'<span class="badge {badge(v)}">{etiqueta}</span>')


def _miles(entero):
    return f'{entero:,}'.replace(',', '.')


@register.filter
def pesos(valor, decimales=0):
    """1234.5 -> $ 1.235  |  pesos:2 -> $ 1.234,50"""
    try:
        d = Decimal(str(valor or 0))
    except (InvalidOperation, ValueError):
        return valor
    decimales = int(decimales)
    signo = '-' if d < 0 else ''
    d = abs(d).quantize(Decimal(1) / (10 ** decimales)) if decimales else abs(d).quantize(Decimal(1))
    entero, _, frac = f'{d:f}'.partition('.')
    texto = _miles(int(entero)) + (f',{frac}' if decimales else '')
    return f'{signo}$ {texto}'


@register.filter
def num(valor):
    """Número legible: 1234 -> 1.234 ; 12.5 -> 12,5 ; None -> —"""
    if valor is None or valor == '':
        return '—'
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return valor
    if f.is_integer():
        return _miles(int(f))
    entero, frac = f'{f:.2f}'.split('.')
    return f'{_miles(int(entero))},{frac.rstrip("0")}'


@register.filter
def get_item(d, clave):
    if isinstance(d, dict):
        return d.get(clave)
    return None


@register.filter
def barra(pct):
    """Clase de color para una barra de consumo."""
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return 'bg-indigo-500'
    if p >= 90:
        return 'bg-red-500'
    if p >= 75:
        return 'bg-amber-500'
    return 'bg-emerald-500'


@register.filter
def ancho(pct):
    try:
        return max(0, min(float(pct), 100))
    except (TypeError, ValueError):
        return 0


@register.filter
def enmascarar(token):
    t = str(token or '')
    if len(t) <= 8:
        return '•' * len(t)
    return f'{t[:4]}••••••••{t[-4:]}'
