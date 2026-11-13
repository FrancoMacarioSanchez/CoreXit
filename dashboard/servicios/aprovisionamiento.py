"""
Ciclo de vida de los tenants: alta, aprovisionamiento vía API, suspensión.

Si el SaaS tiene API configurada se aprovisiona automáticamente; si no (o si
falla), se genera una tarea interna para hacerlo a mano. Nunca se pierde el
pedido: el Tenant queda registrado en estado 'pendiente' o 'error'.
"""
import re

from django.db import transaction
from django.utils import timezone

from ..models import Tenant, Ticket
from .integracion import IntegracionError, SaaSClient


def _limpiar(texto, largo=30):
    texto = (texto or '').lower()
    for a, b in (('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ñ', 'n'), ('ü', 'u')):
        texto = texto.replace(a, b)
    return re.sub(r'[^a-z0-9]', '', texto)[:largo] or 'cliente'


def sugerir_schema(servicio, cliente):
    """Schema único dentro del SaaS: <prefijo><empresa>, con sufijo si ya existe."""
    prefijo = _limpiar(servicio.prefijo, 10) if servicio.prefijo_en_schema and servicio.prefijo else ''
    base = f'{prefijo}{_limpiar(cliente.nombre_visible)}'
    base = base[:55]
    candidato, n = base, 2
    while Tenant.objects.filter(servicio=servicio, schema_name=candidato).exists():
        candidato, n = f'{base}{n}', n + 1
    return candidato


def sugerir_dominio(servicio, cliente, schema=None):
    sub = _limpiar(cliente.nombre_visible) if cliente else schema
    return f'{sub}.{servicio.get_dominio_base()}'


def tenant_para_contratacion(contratacion):
    """
    Devuelve el Tenant de la contratación, creándolo en 'pendiente' si no existe.

    Cambio de plan: si el cliente ya tiene un tenant en ese SaaS vinculado a otra
    contratación, se reutiliza (se mueve a la nueva) y la anterior pasa a histórico.
    Devuelve (tenant, 'existente' | 'cambio_plan' | 'nuevo').
    """
    existente = Tenant.objects.filter(contratacion=contratacion).first()
    if existente:
        return existente, 'existente'
    servicio = contratacion.plan.servicio
    cliente = contratacion.cliente

    previo = (Tenant.objects.filter(servicio=servicio, cliente=cliente)
              .exclude(estado__in=['baja']).select_related('contratacion').first())
    if previo:
        anterior = previo.contratacion
        previo.contratacion = contratacion
        previo.save(update_fields=['contratacion', 'actualizado'])
        if anterior and anterior.pk != contratacion.pk and anterior.estado != 'historico':
            # Instancia fresca: la cacheada todavía "ve" el tenant y la señal lo suspendería
            anterior = type(anterior).objects.get(pk=anterior.pk)
            anterior.estado = 'historico'
            anterior.save()
        return previo, 'cambio_plan'

    schema = sugerir_schema(servicio, cliente)
    tenant = Tenant.objects.create(
        servicio=servicio, cliente=cliente, contratacion=contratacion,
        nombre=cliente.nombre_visible, schema_name=schema,
        dominio=sugerir_dominio(servicio, cliente, schema),
    )
    return tenant, 'nuevo'


def aprovisionar(tenant, usuario=None):
    """
    Pide al SaaS que cree el tenant. Devuelve True si quedó creado.
    Si no hay API o falla, deja una tarea interna de desarrollo.
    """
    servicio = tenant.servicio
    if not servicio.tiene_api:
        _tarea_manual(tenant, motivo='El SaaS todavía no tiene API CoreX configurada.')
        return False

    tenant.estado = 'aprovisionando'
    tenant.save(update_fields=['estado', 'actualizado'])
    cliente = tenant.cliente
    admin = {}
    if cliente:
        admin = {
            'username': cliente.user.username,
            'email': cliente.email or cliente.user.email,
            'nombre': cliente.nombre,
        }
    try:
        resp = SaaSClient(servicio, usuario=usuario).crear_tenant(tenant, admin=admin)
    except IntegracionError as e:
        tenant.estado = 'error'
        tenant.ultimo_error = str(e)
        tenant.save(update_fields=['estado', 'ultimo_error', 'actualizado'])
        _tarea_manual(tenant, motivo=f'Falló el aprovisionamiento automático: {e}')
        return False

    # El SaaS puede aprovisionar en forma asíncrona y devolver 'aprovisionando';
    # en ese caso avisa después por POST /api/v1/tenants/estado/
    tenant.estado = resp.get('estado', 'activo') if resp.get('estado') in dict(Tenant.ESTADOS) else 'activo'
    tenant.id_externo = str(resp.get('id', '') or '')
    tenant.dominio = resp.get('dominio') or tenant.dominio
    advertencias = resp.get('advertencias') or []
    tenant.ultimo_error = ('Advertencias del SaaS: ' + ' | '.join(map(str, advertencias))) if advertencias else ''
    tenant.ultimo_sync = timezone.now()
    tenant.save()
    _sincronizar_url_contratacion(tenant)
    return True


def _sincronizar_url_contratacion(tenant):
    c = tenant.contratacion
    if c and tenant.url and c.url_sistema != tenant.url:
        c.url_sistema = tenant.url
        c.save(update_fields=['url_sistema'])


def _tarea_manual(tenant, motivo):
    c = tenant.contratacion
    cliente = tenant.cliente
    abierta = Ticket.objects.filter(tenant=tenant, tipo='desarrollo', estado__in=['abierto', 'en_proceso']).exists()
    if abierta:
        return
    email = (cliente.email or cliente.user.email) if cliente else '-'
    cuerpo = (
        f"{motivo}\n\n"
        f"CLIENTE\n- Empresa: {cliente.nombre_visible if cliente else '-'}\n"
        f"- CUIT: {(cliente.cuit_cuil if cliente else None) or 'No registrado'}\n"
        f"- Email admin: {email}\n\n"
        f"SERVICIO\n- Sistema: {tenant.servicio.nombre}\n"
        f"- Plan: {c.plan.nombre if c and c.plan else '-'}\n\n"
        f"ACCIÓN REQUERIDA\n"
        f"1. Crear el tenant con schema '{tenant.schema_name}' y dominio '{tenant.dominio}'.\n"
        f"2. Crear el usuario administrador ({email}).\n"
        f"3. En el panel de desarrolladores, marcar el tenant como Activo (o usar 'Reintentar aprovisionamiento').\n"
    )
    Ticket.objects.create(
        cliente=cliente, contratacion=c, tenant=tenant, tipo='desarrollo', prioridad='urgente',
        asunto=f"Aprovisionar {tenant.servicio.prefijo.upper()} - {tenant.nombre}",
        descripcion=cuerpo,
    )


def suspender(tenant, usuario=None, motivo=''):
    if tenant.servicio.tiene_api:
        SaaSClient(tenant.servicio, usuario=usuario).suspender(tenant, motivo=motivo)
    tenant.estado = 'suspendido'
    tenant.save(update_fields=['estado', 'actualizado'])


def reactivar(tenant, usuario=None):
    if tenant.servicio.tiene_api:
        SaaSClient(tenant.servicio, usuario=usuario).reactivar(tenant)
    tenant.estado = 'activo'
    tenant.save(update_fields=['estado', 'actualizado'])


def activar_contratacion(contratacion):
    """
    Punto único para dar de alta un servicio pagado. Lo usan el staff (botón
    'Activar') y en el futuro el webhook de Mercado Pago.
    """
    contratacion.estado = 'activo'
    contratacion.save()  # la señal post_save se encarga del tenant


def al_activar(contratacion):
    """Lo llama la señal cuando una contratación pasa a 'activo'."""
    if not contratacion.plan:
        return
    tenant, origen = tenant_para_contratacion(contratacion)
    if tenant.estado in ('pendiente', 'error'):
        transaction.on_commit(lambda: aprovisionar(tenant))
    elif origen == 'cambio_plan' and tenant.servicio.tiene_api:
        def _plan():
            try:
                if tenant.estado == 'suspendido':
                    reactivar(tenant)
                resp = SaaSClient(tenant.servicio).actualizar_plan(tenant)
                adv = resp.get('advertencias') or []
                tenant.ultimo_error = ('Advertencias del SaaS: ' + ' | '.join(map(str, adv))) if adv else ''
                tenant.save(update_fields=['ultimo_error', 'actualizado'])
            except IntegracionError as e:
                tenant.ultimo_error = str(e)
                tenant.save(update_fields=['ultimo_error', 'actualizado'])
        transaction.on_commit(_plan)
    elif tenant.estado == 'suspendido':
        def _reactivar():
            try:
                reactivar(tenant)
            except IntegracionError as e:
                tenant.ultimo_error = str(e)
                tenant.save(update_fields=['ultimo_error'])
        transaction.on_commit(_reactivar)


def al_suspender(contratacion):
    tenant = getattr(contratacion, 'tenant', None)
    if not tenant or tenant.estado != 'activo':
        return

    def _suspender():
        try:
            suspender(tenant, motivo='Contratación suspendida en CoreX')
        except IntegracionError as e:
            tenant.ultimo_error = str(e)
            tenant.save(update_fields=['ultimo_error'])
    transaction.on_commit(_suspender)
