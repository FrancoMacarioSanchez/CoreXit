"""
Cliente HTTP Hub -> SaaS.

Cada SaaS expone la "API CoreX" descripta en docs/API_SAAS.md. Este módulo
la consume usando solo la librería estándar (urllib) y deja registro de cada
llamada en EventoIntegracion para verla desde el panel de desarrolladores.
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from ..models import EventoIntegracion

logger = logging.getLogger('corex.integracion')


class IntegracionError(Exception):
    def __init__(self, mensaje, status_code=None, respuesta=None):
        super().__init__(mensaje)
        self.status_code = status_code
        self.respuesta = respuesta


class SaaSClient:
    def __init__(self, servicio, usuario=None, timeout=None):
        self.servicio = servicio
        self.usuario = usuario
        self.timeout = timeout or settings.COREX_SAAS_TIMEOUT

    # ------------------------------------------------------------------ base
    def _url(self, ruta):
        base = (self.servicio.api_url or '').rstrip('/')
        return f'{base}/{ruta.lstrip("/")}'

    def _request(self, metodo, ruta, accion, payload=None, params=None, tenant=None, timeout=None):
        if not self.servicio.tiene_api:
            raise IntegracionError(f'{self.servicio.nombre} no tiene API configurada (api_url / api_token).')

        url = self._url(ruta)
        if params:
            url += '?' + urllib.parse.urlencode(params)
        cuerpo = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=cuerpo, method=metodo, headers={
            'Authorization': f'Bearer {self.servicio.api_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'CoreX-Hub/1.0',
        })

        inicio = time.monotonic()
        status, datos, error = None, None, None
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                status = resp.status
                texto = resp.read().decode('utf-8') or '{}'
                datos = json.loads(texto)
        except urllib.error.HTTPError as e:
            status = e.code
            texto = e.read().decode('utf-8', errors='replace')
            try:
                datos = json.loads(texto)
            except ValueError:
                datos = {'raw': texto[:500]}
            error = (datos or {}).get('error') or f'HTTP {e.code}'
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            error = f'No se pudo conectar: {getattr(e, "reason", e)}'
        except ValueError:
            error = 'La respuesta del SaaS no es JSON válido'

        duracion = int((time.monotonic() - inicio) * 1000)
        exito = error is None
        detalle = error or json.dumps(datos, ensure_ascii=False)[:2000]
        EventoIntegracion.objects.create(
            servicio=self.servicio, tenant=tenant, direccion='saliente', accion=accion,
            metodo=metodo, url=url[:500], exito=exito, status_code=status,
            duracion_ms=duracion, detalle=detalle, usuario=self.usuario,
        )
        if not exito:
            logger.warning('[%s] %s %s -> %s', self.servicio.nombre, metodo, url, error)
            raise IntegracionError(error, status_code=status, respuesta=datos)
        return datos

    # ------------------------------------------------------------ endpoints
    def health(self):
        return self._request('GET', 'health/', 'health')

    def listar_tenants(self):
        datos = self._request('GET', 'tenants/', 'listar_tenants')
        return datos.get('tenants', datos if isinstance(datos, list) else [])

    def crear_tenant(self, tenant, admin=None):
        contratacion = tenant.contratacion
        plan = contratacion.plan if contratacion else None
        payload = {
            'referencia_hub': tenant.pk,
            'schema_name': tenant.schema_name,
            'dominio': tenant.dominio,
            'nombre': tenant.nombre,
            'plan': _datos_plan(contratacion),
            'limites': plan.limites_dict() if plan else {},
            'admin': admin or {},
            'cliente': _datos_cliente(tenant.cliente),
            'hub_url': settings.COREX_HUB_URL,
        }
        # Crear un tenant migra un schema entero: se le da más margen que al resto
        return self._request('POST', 'tenants/', 'crear_tenant', payload=payload, tenant=tenant,
                             timeout=max(self.timeout, settings.COREX_SAAS_TIMEOUT_ALTA))

    def detalle_tenant(self, tenant):
        return self._request('GET', f'tenants/{tenant.schema_name}/', 'detalle_tenant', tenant=tenant)

    def metricas(self, tenant, desde, hasta):
        return self._request(
            'GET', f'tenants/{tenant.schema_name}/metricas/', 'metricas',
            params={'desde': desde.isoformat(), 'hasta': hasta.isoformat()}, tenant=tenant,
        )

    def suspender(self, tenant, motivo=''):
        return self._request('POST', f'tenants/{tenant.schema_name}/suspender/', 'suspender',
                             payload={'motivo': motivo}, tenant=tenant)

    def reactivar(self, tenant):
        return self._request('POST', f'tenants/{tenant.schema_name}/reactivar/', 'reactivar', payload={}, tenant=tenant)

    def actualizar_plan(self, tenant):
        plan = tenant.plan
        return self._request('POST', f'tenants/{tenant.schema_name}/plan/', 'actualizar_plan', payload={
            'plan': _datos_plan(tenant.contratacion),
            'limites': plan.limites_dict() if plan else {},
        }, tenant=tenant)


def _datos_plan(contratacion):
    if not contratacion or not contratacion.plan:
        return None
    p = contratacion.plan
    return {'id': p.pk, 'nombre': p.nombre, 'frecuencia': contratacion.frecuencia_pago}


def _datos_cliente(cliente):
    if not cliente:
        return None
    return {
        'nombre': cliente.nombre,
        'empresa': cliente.empresa,
        'email': cliente.email or cliente.user.email,
        'telefono': cliente.telefono,
        'cuit': cliente.cuit_cuil,
        'condicion_fiscal': cliente.condicion_fiscal,
        'domicilio': cliente.domicilio_fiscal,
    }
