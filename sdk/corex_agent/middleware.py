"""
Bloquea el acceso a tenants que CoreX suspendió. Agregar DESPUÉS de
django_tenants.middleware.main.TenantMainMiddleware:

    'corex_agent.middleware.TenantSuspendidoMiddleware',
"""
from django.db import connection
from django.http import HttpResponse

from . import conf
from .models import EstadoTenant

PAGINA = """<!doctype html><html lang="es"><meta charset="utf-8"><title>Servicio suspendido</title>
<body style="font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0;background:#0b1120;color:#e2e8f0">
<div style="max-width:420px;text-align:center"><h1>Servicio suspendido</h1>
<p>El acceso a este sistema está suspendido temporalmente. Ingresá a tu portal de CoreX para regularizar la cuenta.</p>
</div></body></html>"""


class TenantSuspendidoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        schema = getattr(connection, 'schema_name', None)
        tenant = getattr(request, 'tenant', None)
        if tenant is not None and schema and schema != 'public':
            resolver = conf.gancho('COREX_ESTADO_RESOLVER', None)
            if resolver:
                bloqueado = resolver(tenant) in ('suspendido', 'baja')
            else:
                bloqueado = EstadoTenant.objects.filter(schema_name=tenant.schema_name, estado='suspendido').exists()
            if bloqueado:
                return HttpResponse(PAGINA, status=402)
        return self.get_response(request)
