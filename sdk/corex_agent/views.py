"""
API CoreX del lado del SaaS (django-tenants). Montar en el urlconf PÚBLICO:

    # PUBLIC_SCHEMA_URLCONF
    path('corex/v1/', include('corex_agent.urls')),

Contrato: docs/API_SAAS.md del Hub.
"""
import hmac
import json
import re
from datetime import date, timedelta
from functools import wraps

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django_tenants.utils import (
    get_public_schema_name, get_tenant_domain_model, get_tenant_model, schema_context,
)

from . import conf
from .models import EstadoTenant

SCHEMA_RE = re.compile(r'^[a-z][a-z0-9_]{1,62}$')
MAX_DIAS = 92


def _error(msg, status):
    return JsonResponse({'error': msg}, status=status)


def api(metodos):
    def deco(vista):
        @csrf_exempt
        @wraps(vista)
        def env(request, *args, **kwargs):
            if request.method not in metodos:
                return _error('Método no permitido', 405)
            # La API CoreX solo responde en el dominio del schema public
            if getattr(connection, 'schema_name', get_public_schema_name()) != get_public_schema_name():
                return _error('No encontrado', 404)
            esperado = conf.get('COREX_AGENT_TOKEN') or ''
            auth = request.headers.get('Authorization', '')
            if not esperado or not hmac.compare_digest(auth, f'Bearer {esperado}'):
                return _error('Token inválido', 401)
            datos = {}
            if request.method == 'POST':
                try:
                    datos = json.loads(request.body or b'{}')
                except ValueError:
                    return _error('JSON inválido', 400)
            return vista(request, datos, *args, **kwargs)
        return env
    return deco


# ------------------------------------------------------------------ helpers
def _tenants():
    return get_tenant_model().objects.exclude(schema_name=get_public_schema_name())


def _dominio(tenant):
    d = get_tenant_domain_model().objects.filter(tenant=tenant).order_by('-is_primary').first()
    if not d:
        return ''
    puerto = conf.get('COREX_TENANT_URL_PORT', '')  # desarrollo: empresa.facturar.localhost:8080
    return f'{d.domain}:{puerto}' if puerto else d.domain


def _nombre(tenant):
    campo = conf.get('COREX_TENANT_NAME_FIELD', 'nombre')
    return getattr(tenant, campo, None) or tenant.schema_name


def _estado(schema, tenant=None):
    resolver = conf.gancho('COREX_ESTADO_RESOLVER', None)
    if resolver and tenant is not None:
        return resolver(tenant)
    e = EstadoTenant.objects.filter(schema_name=schema).first()
    return e.estado if e else 'activo'


def _cambiar_estado(tenant, estado, motivo=''):
    EstadoTenant.objects.update_or_create(schema_name=tenant.schema_name, defaults={'estado': estado, 'motivo': motivo[:255]})
    gancho = conf.gancho('COREX_ON_ESTADO', None)
    if gancho:
        gancho(tenant, estado, motivo)


def _cambiar_plan(tenant, plan, limites):
    """Devuelve lista de advertencias (p. ej. plan no encontrado en el SaaS)."""
    EstadoTenant.objects.update_or_create(schema_name=tenant.schema_name, defaults={'plan': plan or {}, 'limites': limites or {}})
    gancho = conf.gancho('COREX_ON_PLAN', None)
    return (gancho(tenant, plan or {}, limites or {}) or []) if gancho else []


def _serializar(tenant):
    return {
        'id': tenant.pk, 'schema_name': tenant.schema_name, 'nombre': _nombre(tenant),
        'dominio': _dominio(tenant), 'estado': _estado(tenant.schema_name, tenant),
    }


def _crear_tenant_default(datos):
    Tenant, Domain = get_tenant_model(), get_tenant_domain_model()
    kwargs = {'schema_name': datos['schema_name']}
    campo = conf.get('COREX_TENANT_NAME_FIELD', 'nombre')
    if campo:
        kwargs[campo] = datos.get('nombre') or datos['schema_name']
    tenant = Tenant(**kwargs)
    tenant.save()  # con auto_create_schema=True crea el schema y migra
    if datos.get('dominio'):
        Domain.objects.create(domain=datos['dominio'], tenant=tenant, is_primary=True)
    return tenant


def _crear_admin_default(tenant, admin):
    """Superusuario sin contraseña: el SaaS debería mandarle un mail para definirla."""
    if not admin or not admin.get('username'):
        return
    User = get_user_model()
    with schema_context(tenant.schema_name):
        if not User.objects.filter(username=admin['username']).exists():
            u = User(username=admin['username'], email=admin.get('email', ''), is_staff=True, is_superuser=True,
                     first_name=(admin.get('nombre') or '')[:150])
            u.set_unusable_password()
            u.save()


def _tenant_o_404(schema):
    t = _tenants().filter(schema_name=schema).first()
    return t, (None if t else _error('Tenant inexistente', 404))


# -------------------------------------------------------------------- vistas
@api(['GET'])
def health(request, datos):
    return JsonResponse({'ok': True, 'servicio': conf.get('COREX_SERVICIO', ''), 'version': conf.get('COREX_VERSION', ''),
                         'tenants': _tenants().count()})


@api(['GET', 'POST'])
def tenants(request, datos):
    if request.method == 'GET':
        return JsonResponse({'tenants': [_serializar(t) for t in _tenants()]})

    schema = str(datos.get('schema_name', ''))
    if not SCHEMA_RE.match(schema) or schema == get_public_schema_name():
        return _error('schema_name inválido', 400)
    existente = _tenants().filter(schema_name=schema).first()
    if existente:  # idempotente: el Hub puede reintentar
        return JsonResponse(_serializar(existente), status=200)
    if datos.get('dominio') and get_tenant_domain_model().objects.filter(domain=datos['dominio']).exists():
        return _error('El dominio ya está en uso', 409)

    fabrica = conf.gancho('COREX_TENANT_FACTORY', _crear_tenant_default)
    crear_admin = conf.gancho('COREX_ADMIN_FACTORY', _crear_admin_default)
    try:
        tenant = fabrica(datos)
    except ValueError as e:  # datos inválidos (p. ej. CUIT duplicado): error del cliente
        return _error(str(e), 409)
    except Exception as e:  # noqa: BLE001 - se informa al Hub
        return _error(f'No se pudo crear el tenant: {e}', 500)
    extra = {}
    try:
        extra = crear_admin(tenant, datos.get('admin') or {}) or {}
    except Exception as e:  # noqa: BLE001 - el tenant ya existe; se informa sin fallar
        extra = {'advertencias': [f'No se pudo crear el administrador: {e}']}
    EstadoTenant.objects.update_or_create(schema_name=schema, defaults={
        'estado': 'activo', 'referencia_hub': str(datos.get('referencia_hub') or '')})
    advertencias = list(extra.pop('advertencias', [])) + _cambiar_plan(tenant, datos.get('plan'), datos.get('limites'))
    respuesta = {**_serializar(tenant), **extra}
    if advertencias:
        respuesta['advertencias'] = advertencias
    return JsonResponse(respuesta, status=201)


@api(['GET'])
def tenant_detalle(request, datos, schema):
    t, err = _tenant_o_404(schema)
    if err:
        return err
    e = EstadoTenant.objects.filter(schema_name=schema).first()
    return JsonResponse({**_serializar(t), 'plan': e.plan if e else {}, 'limites': e.limites if e else {}})


@api(['GET'])
def metricas(request, datos, schema):
    t, err = _tenant_o_404(schema)
    if err:
        return err
    try:
        hasta = date.fromisoformat(request.GET.get('hasta') or date.today().isoformat())
        desde = date.fromisoformat(request.GET.get('desde') or (hasta - timedelta(days=6)).isoformat())
    except ValueError:
        return _error('Fechas inválidas (YYYY-MM-DD)', 400)
    if desde > hasta or (hasta - desde).days > MAX_DIAS:
        return _error(f'Rango inválido (máximo {MAX_DIAS} días)', 400)
    recolectar = conf.gancho('COREX_METRICS_COLLECTOR', None)
    if not recolectar:
        return _error('COREX_METRICS_COLLECTOR no configurado', 501)
    series = []
    with schema_context(schema):
        f = desde
        while f <= hasta:
            series.append({'fecha': f.isoformat(), 'metricas': recolectar(f)})
            f += timedelta(days=1)
    return JsonResponse({'tenant': schema, 'estado': _estado(schema, t), 'series': series})


@api(['POST'])
def suspender(request, datos, schema):
    t, err = _tenant_o_404(schema)
    if err:
        return err
    _cambiar_estado(t, 'suspendido', str(datos.get('motivo', '')))
    return JsonResponse({'ok': True, 'estado': 'suspendido'})


@api(['POST'])
def reactivar(request, datos, schema):
    t, err = _tenant_o_404(schema)
    if err:
        return err
    _cambiar_estado(t, 'activo')
    return JsonResponse({'ok': True, 'estado': 'activo'})


@api(['POST'])
def plan(request, datos, schema):
    t, err = _tenant_o_404(schema)
    if err:
        return err
    with transaction.atomic():
        advertencias = _cambiar_plan(t, datos.get('plan'), datos.get('limites'))
    return JsonResponse({'ok': True, 'advertencias': advertencias} if advertencias else {'ok': True})
