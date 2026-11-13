"""
Dos middlewares:

- MetricasRequestMiddleware: cuenta pedidos, errores y latencia por minuto.
- ActividadMiddleware: deja registro de lo que hace el equipo (staff) en el Hub.

Ninguno puede romper una respuesta: si falla el registro, se loguea y se sigue.
"""
import logging
import threading
import time

from django.utils import timezone

from . import actividad

logger = logging.getLogger(__name__)

_IGNORAR_METRICAS = ('/static/', '/favicon.ico', '/sw.js', '/dev/monitoreo/datos/')

_lock = threading.Lock()
_cubeta = {'minuto': None, 'total': 0, 'ok': 0, 'c4xx': 0, 'c5xx': 0, 'suma_ms': 0, 'max_ms': 0}


def _vaciar_cubeta():
    """Devuelve lo acumulado (o None) y deja la cubeta en cero. Llamar con el lock tomado."""
    if not _cubeta['total']:
        return None
    copia = dict(_cubeta)
    _cubeta.update(total=0, ok=0, c4xx=0, c5xx=0, suma_ms=0, max_ms=0)
    return copia


def _volcar(datos):
    if not datos:
        return
    from django.db.models import F
    from django.db.models.functions import Greatest

    from .models import MuestraRequests
    obj, creado = MuestraRequests.objects.get_or_create(minuto=datos['minuto'], defaults={
        k: datos[k] for k in ('total', 'ok', 'c4xx', 'c5xx', 'suma_ms', 'max_ms')})
    if not creado:
        MuestraRequests.objects.filter(pk=obj.pk).update(
            total=F('total') + datos['total'], ok=F('ok') + datos['ok'],
            c4xx=F('c4xx') + datos['c4xx'], c5xx=F('c5xx') + datos['c5xx'],
            suma_ms=F('suma_ms') + datos['suma_ms'],
            max_ms=Greatest(F('max_ms'), datos['max_ms']))


def volcar_pendiente():
    """Guarda ahora lo acumulado del minuto en curso (lo usa la pantalla de métricas)."""
    with _lock:
        minuto = _cubeta['minuto']
        datos = _vaciar_cubeta()
        if datos:
            datos['minuto'] = minuto
    try:
        _volcar(datos)
    except Exception:
        logger.exception('No se pudo guardar el tráfico del minuto')


class MetricasRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inicio = time.perf_counter()
        status = 500
        try:
            response = self.get_response(request)
            status = response.status_code
            return response
        finally:
            try:
                self._contar(request, status, int((time.perf_counter() - inicio) * 1000))
            except Exception:
                logger.exception('Error al medir el pedido')

    def _contar(self, request, status, ms):
        if request.path.startswith(_IGNORAR_METRICAS):
            return
        minuto = timezone.now().replace(second=0, microsecond=0)
        pendiente = None
        with _lock:
            if _cubeta['minuto'] is not None and _cubeta['minuto'] != minuto:
                pendiente = _vaciar_cubeta()
                if pendiente:
                    pendiente['minuto'] = _cubeta['minuto']
            _cubeta['minuto'] = minuto
            _cubeta['total'] += 1
            _cubeta['suma_ms'] += ms
            _cubeta['max_ms'] = max(_cubeta['max_ms'], ms)
            if status >= 500:
                _cubeta['c5xx'] += 1
            elif status >= 400:
                _cubeta['c4xx'] += 1
            else:
                _cubeta['ok'] += 1
        _volcar(pendiente)


class ActividadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            actividad.registrar_request(request, response)
        except Exception:
            logger.exception('No se pudo registrar la actividad')
        return response
