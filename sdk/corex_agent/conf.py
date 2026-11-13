"""
Configuración del agente (settings.py del SaaS):

COREX_AGENT_TOKEN        = '...'   # el mismo valor que "API token" del Servicio en el Hub
COREX_HUB_URL            = 'https://hub.corexit.tech'
COREX_HUB_INGEST_TOKEN   = '...'   # "token de ingesta" que muestra el Panel dev del Hub
COREX_SERVICIO           = 'gestionar'

# Ganchos (rutas "modulo.funcion"):
COREX_METRICS_COLLECTOR  = 'ventas.corex.recolectar'   # fn(fecha) -> {clave: numero}  (corre dentro del schema)
COREX_TENANT_FACTORY     = None   # fn(datos) -> tenant ; default: crea Tenant + Domain de django-tenants
COREX_ADMIN_FACTORY      = None   # fn(tenant, admin_dict) ; default: crea superusuario sin contraseña
COREX_TENANT_NAME_FIELD  = 'nombre'  # campo "nombre" del modelo Tenant del SaaS (None si no tiene)
COREX_ON_ESTADO          = None   # fn(tenant, estado, motivo)  al suspender/reactivar
COREX_ON_PLAN            = None   # fn(tenant, plan, limites) -> [advertencias]  al crear o cambiar de plan
COREX_ESTADO_RESOLVER    = None   # fn(tenant) -> 'activo'|'suspendido'|...  (default: EstadoTenant)

COREX_ADMIN_FACTORY puede devolver un dict que se suma a la respuesta (p. ej. {"invitacion_enviada": True}).
"""
from django.conf import settings
from django.utils.module_loading import import_string


def get(nombre, default=None):
    return getattr(settings, nombre, default)


def gancho(nombre, default):
    ruta = get(nombre)
    return import_string(ruta) if ruta else default
