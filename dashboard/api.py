"""
API entrante: SaaS -> Hub.

Autenticación: header  Authorization: Bearer <Servicio.ingest_token>
El token identifica a qué SaaS pertenece la llamada, así un SaaS nunca puede
escribir métricas de tenants de otro SaaS.

Endpoints (ver docs/API_SAAS.md):
  GET  /api/v1/ping/              -> verifica el token
  POST /api/v1/metricas/          -> uno o varios snapshots diarios
  POST /api/v1/tenants/estado/    -> el SaaS informa cambios de estado de un tenant
"""
import hmac
import json
from functools import wraps

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import EventoIntegracion, Servicio, Tenant
from .servicios.metricas import parsear_fecha, registrar_metricas

MAX_ITEMS = 500


def _error(mensaje, status):
    return JsonResponse({'ok': False, 'error': mensaje}, status=status)


def _servicio_desde_token(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    servicio = Servicio.objects.filter(ingest_token=token, activo=True).first()
    if servicio and hmac.compare_digest(servicio.ingest_token, token):
        return servicio
    return None


def api_saas(vista):
    @csrf_exempt
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        servicio = _servicio_desde_token(request)
        if not servicio:
            return _error('Token inválido o servicio inactivo', 401)
        payload = {}
        if request.method == 'POST':
            try:
                payload = json.loads(request.body or b'{}')
            except ValueError:
                return _error('El cuerpo debe ser JSON', 400)
        return vista(request, servicio, payload, *args, **kwargs)
    return envoltura


def _log(servicio, accion, exito, detalle, tenant=None, status=200):
    EventoIntegracion.objects.create(
        servicio=servicio, tenant=tenant, direccion='entrante', accion=accion,
        metodo='POST', exito=exito, status_code=status, detalle=detalle[:2000],
    )


@require_http_methods(['GET'])
@api_saas
def ping(request, servicio, payload):
    return JsonResponse({'ok': True, 'servicio': servicio.slug or servicio.nombre, 'hora': timezone.now().isoformat()})


@require_http_methods(['POST'])
@api_saas
def recibir_metricas(request, servicio, payload):
    """
    Acepta:
      {"tenant": "schema", "fecha": "2026-11-10", "metricas": {"ventas": 12}}
    o en lote:
      {"items": [{"tenant": ..., "fecha": ..., "metricas": {...}}, ...]}
    """
    items = payload.get('items') if isinstance(payload.get('items'), list) else [payload]
    if len(items) > MAX_ITEMS:
        return _error(f'Máximo {MAX_ITEMS} items por llamada', 413)

    tenants = {t.schema_name: t for t in Tenant.objects.filter(
        servicio=servicio, schema_name__in=[str(i.get('tenant', '')) for i in items])}
    guardados, rechazados = 0, []
    for i, item in enumerate(items):
        schema = str(item.get('tenant', ''))
        tenant = tenants.get(schema)
        fecha = parsear_fecha(item.get('fecha'), default=timezone.localdate())
        metricas = item.get('metricas')
        if not tenant:
            rechazados.append({'indice': i, 'tenant': schema, 'error': 'tenant desconocido para este servicio'})
            continue
        if not isinstance(metricas, dict):
            rechazados.append({'indice': i, 'tenant': schema, 'error': '"metricas" debe ser un objeto'})
            continue
        registrar_metricas(tenant, fecha, metricas, origen='push')
        guardados += 1

    if guardados:
        Tenant.objects.filter(pk__in=[t.pk for t in tenants.values()]).update(ultimo_sync=timezone.now())
    _log(servicio, 'metricas', not rechazados or bool(guardados),
         json.dumps({'guardados': guardados, 'rechazados': rechazados}, ensure_ascii=False),
         tenant=next(iter(tenants.values())) if len(tenants) == 1 else None,
         status=200 if guardados or not rechazados else 422)
    status = 200 if guardados or not rechazados else 422
    return JsonResponse({'ok': guardados > 0 or not rechazados, 'guardados': guardados, 'rechazados': rechazados}, status=status)


@require_http_methods(['POST'])
@api_saas
def estado_tenant(request, servicio, payload):
    """{"tenant": "schema", "estado": "activo", "dominio": "...", "id": "...", "error": "..."}"""
    schema = str(payload.get('tenant', ''))
    tenant = Tenant.objects.filter(servicio=servicio, schema_name=schema).first()
    if not tenant:
        _log(servicio, 'estado_tenant', False, f'Tenant desconocido: {schema}', status=404)
        return _error('Tenant desconocido para este servicio', 404)
    estado = payload.get('estado')
    if estado not in dict(Tenant.ESTADOS):
        return _error(f'Estado inválido. Opciones: {", ".join(dict(Tenant.ESTADOS))}', 400)

    tenant.estado = estado
    if payload.get('dominio'):
        tenant.dominio = str(payload['dominio'])[:253]
    if payload.get('id'):
        tenant.id_externo = str(payload['id'])[:64]
    tenant.ultimo_error = str(payload.get('error') or '')[:2000] if estado == 'error' else ''
    tenant.save()
    if tenant.contratacion and tenant.url and tenant.contratacion.url_sistema != tenant.url:
        tenant.contratacion.url_sistema = tenant.url
        tenant.contratacion.save(update_fields=['url_sistema'])
    _log(servicio, 'estado_tenant', True, json.dumps(payload, ensure_ascii=False), tenant=tenant)
    return JsonResponse({'ok': True, 'tenant': tenant.schema_name, 'estado': tenant.estado})
