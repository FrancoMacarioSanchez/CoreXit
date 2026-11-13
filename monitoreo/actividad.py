"""Qué se registra de la actividad del staff y cómo se describe en lenguaje humano."""
import re

from django.conf import settings

from .models import RegistroActividad

AREAS = ('/staff/', '/dev/', '/admin/', '/instagram/')
# Pantallas que se refrescan solas: no son "actividad" de una persona.
IGNORAR = ('/dev/monitoreo/datos/', '/admin/jsi18n/', '/admin/login/')
METODOS_ACCION = {'POST', 'PUT', 'PATCH', 'DELETE'}

# nombre de URL -> cómo se muestra
DESCRIPCIONES = {
    'staff:inicio': 'Dashboard de staff',
    'staff:clientes': 'Lista de clientes',
    'staff:cliente': 'Ficha de cliente',
    'staff:facturacion': 'Facturación y cobros',
    'staff:factura_pdf': 'Descarga de factura (PDF)',
    'staff:soporte': 'Soporte a clientes',
    'staff:ticket': 'Ticket de soporte',
    'staff:tareas': 'Tareas internas',
    'devpanel:inicio': 'Estado general (dev)',
    'devpanel:servicio': 'Detalle de SaaS',
    'devpanel:tenant': 'Detalle de tenant',
    'devpanel:tenant_nuevo': 'Nuevo tenant',
    'devpanel:tenant_editar': 'Edición de tenant',
    'devpanel:eventos': 'Log de integración',
    'devpanel:docs': 'Contrato de API',
    'monitoreo:servidor': 'Métricas del servidor',
    'monitoreo:actividad': 'Actividad del staff',
    'igportal:panel': 'Instagram · panel',
    'igportal:publicaciones': 'Instagram · publicaciones',
    'igportal:nueva': 'Instagram · nueva publicación',
    'igportal:editar': 'Instagram · edición de publicación',
    'igportal:publicar': 'Instagram · publicar',
    'igportal:cancelar': 'Instagram · volver a borrador',
    'igportal:eliminar': 'Instagram · eliminar publicación',
    'igportal:verificar': 'Instagram · verificar estado',
    'igportal:comentarios': 'Instagram · comentarios',
    'igportal:conexion': 'Instagram · conexión',
}

_ADMIN = re.compile(r'^/admin/(?:(?P<app>[\w]+)/(?P<modelo>[\w]+)/(?:(?P<id>[^/]+)/)?(?P<accion>change|delete|history|add)?/?)?$')
_ACCION_ADMIN = {'change': 'Modificó', 'add': 'Creó', 'delete': 'Eliminó', 'history': 'Consultó historial de'}


def ip_de(request):
    if getattr(settings, 'COREX_TRUST_PROXY', False):
        adelante = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if adelante:
            return adelante.split(',')[0].strip() or None
    return request.META.get('REMOTE_ADDR') or None


def describir(request, metodo):
    ruta = request.path
    if ruta.startswith('/admin/'):
        m = _ADMIN.match(ruta)
        if m and m.group('app'):
            modelo = f"{m.group('app')}.{m.group('modelo')}"
            ident = m.group('id')
            accion = m.group('accion')
            if ident in ('add',):
                accion, ident = 'add', None
            if ident and accion is None and ident.isdigit():
                accion = 'change'
            verbo = _ACCION_ADMIN.get(accion, 'Abrió' if metodo == 'GET' else 'Operó sobre')
            return f'Admin: {verbo} {modelo}' + (f' #{ident}' if ident and ident.isdigit() else '')
        return 'Admin de Django'
    match = getattr(request, 'resolver_match', None)
    nombre = match.view_name if match else ''
    base = DESCRIPCIONES.get(nombre) or nombre or ruta
    if metodo in METODOS_ACCION:
        base = f'{base} (envió formulario)' if metodo == 'POST' else base
    if match and match.kwargs:
        ids = ', '.join(f'{k}={v}' for k, v in match.kwargs.items())
        base = f'{base} [{ids}]'
    return base[:255]


def registrar(usuario, tipo, request=None, descripcion='', username=''):
    RegistroActividad.objects.create(
        usuario=usuario if (usuario is not None and getattr(usuario, 'pk', None)) else None,
        username=(username or getattr(usuario, 'username', '') or '')[:150],
        tipo=tipo,
        metodo=((getattr(request, 'method', None) or '') if request else '')[:8],
        ruta=((getattr(request, 'path', None) or '') if request else '')[:300],
        descripcion=descripcion[:255],
        ip=ip_de(request) if request else None,
        user_agent=(request.META.get('HTTP_USER_AGENT', '')[:200] if request else ''),
    )


def registrar_request(request, response):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated or not user.is_staff:
        return
    ruta = request.path
    if not ruta.startswith(AREAS) or ruta.startswith(IGNORAR):
        return
    metodo = request.method
    if metodo in METODOS_ACCION:
        tipo = 'accion'
    elif metodo == 'GET' and response.status_code == 200 and request.headers.get('x-requested-with') != 'XMLHttpRequest':
        tipo = 'vista'
    else:
        return
    match = getattr(request, 'resolver_match', None)
    RegistroActividad.objects.create(
        usuario=user, username=user.get_username()[:150], tipo=tipo, metodo=metodo[:8], ruta=ruta[:300],
        vista=(match.view_name if match else '')[:120], descripcion=describir(request, metodo),
        estado_http=response.status_code, ip=ip_de(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:200],
    )
