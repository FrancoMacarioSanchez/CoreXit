"""
Carga datos de demostración para recorrer el Hub completo (solo desarrollo).

    python manage.py corex_demo

Crea: SaaS (GestionAR, Turnos, StockeAR) con métricas y planes con límites,
usuarios dev/staff/clientes, contrataciones, tenants con 90 días de métricas,
facturas y tickets. Contraseña de todos los usuarios demo: corex1234
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from dashboard.models import (
    ClienteProfile, Contratacion, FacturaCliente, LimitePlan, MetricaServicio, MetricaTenant, PlanServicio,
    Servicio, Tenant, Ticket, TicketMensaje,
)
from dashboard.permisos import GRUPO_DESARROLLADORES

PASS = 'corex1234'

CATALOGO = {
    'GestionAR': {
        'slug': 'gestionar', 'prefijo': 'gest', 'color': '#6366f1',
        'descripcion': 'Punto de venta, stock y facturación electrónica ARCA.',
        'metricas': [
            ('ventas_cantidad', 'Ventas', '', 'contador', True, True),
            ('ventas_monto', 'Monto vendido', '$', 'contador', True, False),
            ('comprobantes_arca', 'Comprobantes ARCA', '', 'contador', True, True),
            ('usuarios', 'Usuarios', '', 'nivel', True, True),
            ('productos', 'Productos', '', 'nivel', True, False),
            ('almacenamiento_mb', 'Almacenamiento', 'MB', 'nivel', True, False),
        ],
        'planes': [
            ('Inicial', 14900, 149000, {'comprobantes_arca': 300, 'usuarios': 2, 'productos': 1000, 'almacenamiento_mb': 500}),
            ('Profesional', 29900, 299000, {'comprobantes_arca': 1500, 'usuarios': 5, 'productos': 5000, 'almacenamiento_mb': 2000}),
            ('Negocio', 54900, 549000, {'comprobantes_arca': 6000, 'usuarios': 15, 'almacenamiento_mb': 10000}),
        ],
        'rango': {'ventas_cantidad': (8, 60), 'ventas_monto': (60000, 800000), 'comprobantes_arca': (6, 55),
                  'usuarios': (1, 5), 'productos': (200, 1500), 'almacenamiento_mb': (40, 450)},
    },
    'Turnos': {
        'slug': 'turnos', 'prefijo': 'tur', 'color': '#10b981',
        'descripcion': 'Agenda online multirubro con página pública de reservas.',
        'metricas': [
            ('turnos_reservados', 'Turnos reservados', '', 'contador', True, True),
            ('turnos_cancelados', 'Turnos cancelados', '', 'contador', True, False),
            ('recordatorios_enviados', 'Recordatorios', '', 'contador', True, False),
            ('profesionales', 'Profesionales', '', 'nivel', True, True),
            ('clientes', 'Clientes', '', 'nivel', True, True),
        ],
        'planes': [
            ('Solo', 9900, 99000, {'turnos_reservados': 400, 'profesionales': 1, 'recordatorios_enviados': 400}),
            ('Equipo', 19900, 199000, {'turnos_reservados': 2000, 'profesionales': 6, 'recordatorios_enviados': 2000}),
        ],
        'rango': {'turnos_reservados': (4, 45), 'turnos_cancelados': (0, 6), 'recordatorios_enviados': (4, 45),
                  'profesionales': (1, 5), 'clientes': (40, 600)},
    },
    'StockeAR': {
        'slug': 'stockear', 'prefijo': 'stk', 'color': '#f59e0b',
        'descripcion': 'Catálogo B2B y pedidos entre proveedores y comercios.',
        'metricas': [
            ('pedidos', 'Pedidos recibidos', '', 'contador', True, True),
            ('visitas_catalogo', 'Visitas al catálogo', '', 'contador', True, False),
            ('productos_catalogo', 'Productos publicados', '', 'nivel', True, True),
            ('compradores', 'Compradores', '', 'nivel', False, True),
        ],
        'planes': [
            ('Proveedor', 24900, 249000, {'productos_catalogo': 3000}),
        ],
        'rango': {'pedidos': (0, 20), 'visitas_catalogo': (20, 400), 'productos_catalogo': (300, 2500), 'compradores': (5, 120)},
    },
}

CLIENTES = [
    ('ferreteria', 'Ferretería El Tornillo', 'Carlos Gómez', '20-28111222-3', 'monotributo',
     [('GestionAR', 'Profesional', 'mensual', 'activo'), ('Turnos', 'Solo', 'mensual', 'pendiente')]),
    ('kinesio', 'Kinesio Salud', 'Lucía Fernández', '27-33444555-6', 'responsable_inscripto',
     [('Turnos', 'Equipo', 'anual', 'activo')]),
    ('almacen', 'Almacén Don Pepe', 'José Pérez', '20-22999888-1', 'monotributo',
     [('GestionAR', 'Inicial', 'mensual', 'activo')]),
    ('distri', 'Distribuidora Norte', 'Ana Ruiz', '30-71234567-9', 'responsable_inscripto',
     [('StockeAR', 'Proveedor', 'mensual', 'activo'), ('GestionAR', 'Negocio', 'anual', 'activo')]),
    ('pilates', 'Estudio Pilates Core', 'Martina Sosa', '27-40111222-4', 'monotributo',
     [('Turnos', 'Solo', 'mensual', 'suspendido')]),
]


class Command(BaseCommand):
    help = 'Carga datos de demostración (solo desarrollo)'

    def add_arguments(self, parser):
        parser.add_argument('--forzar', action='store_true', help='Permite correrlo con DEBUG=False')

    @transaction.atomic
    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts['forzar']:
            raise CommandError('Esto carga datos falsos. Usalo solo en desarrollo (o con --forzar).')
        rnd = random.Random(42)
        hoy = timezone.localdate()

        grupo, _ = Group.objects.get_or_create(name=GRUPO_DESARROLLADORES)
        dev = self._usuario('dev', 'Franco', 'Dev', staff=True, superuser=True)
        dev.groups.add(grupo)
        staff = self._usuario('staff', 'Sofía', 'Soporte', staff=True)

        servicios, planes = {}, {}
        for nombre, cfg in CATALOGO.items():
            s, _ = Servicio.objects.update_or_create(nombre=nombre, defaults={
                'slug': cfg['slug'], 'prefijo': cfg['prefijo'], 'color': cfg['color'], 'descripcion': cfg['descripcion']})
            servicios[nombre] = s
            defs = {}
            for orden, (clave, nom, unidad, tipo, visible, destacada) in enumerate(cfg['metricas']):
                defs[clave], _ = MetricaServicio.objects.update_or_create(servicio=s, clave=clave, defaults={
                    'nombre': nom, 'unidad': unidad, 'tipo': tipo, 'visible_cliente': visible,
                    'destacada': destacada, 'orden': orden})
            for pnom, pm, pa, limites in cfg['planes']:
                p, _ = PlanServicio.objects.update_or_create(servicio=s, nombre=pnom, defaults={
                    'precio_mensual': pm, 'precio_anual': pa, 'activo': True,
                    'link_mercadopago_mensual': 'https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_plan_id=demo',
                    'descripcion': f'Plan {pnom} de {nombre}.'})
                for clave, lim in limites.items():
                    LimitePlan.objects.update_or_create(plan=p, metrica=defs[clave], defaults={'limite': lim})
                planes[(nombre, pnom)] = p

        n_fact = 100
        for user_slug, empresa, titular, cuit, cond, contratos in CLIENTES:
            u = self._usuario(user_slug, titular.split()[0], titular.split()[1])
            perfil, _ = ClienteProfile.objects.update_or_create(user=u, defaults={
                'nombre': titular, 'empresa': empresa, 'email': u.email, 'cuit_cuil': cuit, 'condicion_fiscal': cond,
                'telefono': '+54 9 11 5555-' + str(rnd.randint(1000, 9999)), 'domicilio_fiscal': 'Av. Siempre Viva 742, CABA',
                'terminos_aceptados': True, 'fecha_aceptacion_terminos': timezone.now()})
            for sv, pnom, frec, estado in contratos:
                plan = planes[(sv, pnom)]
                inicio = hoy - timedelta(days=rnd.randint(70, 200))
                c, _ = Contratacion.objects.get_or_create(cliente=perfil, plan=plan, defaults={
                    'fecha_inicio': inicio, 'frecuencia_pago': frec, 'estado': 'pendiente',
                    'fecha_vencimiento': hoy + timedelta(days=rnd.randint(3, 25) if frec == 'mensual' else 200)})
                if estado != 'pendiente':
                    # Sin API configurada en la demo: la señal deja el tenant 'pendiente' + tarea.
                    # Acá lo dejamos directamente operativo con historia de métricas.
                    Contratacion.objects.filter(pk=c.pk).update(estado=estado)
                    c.refresh_from_db()
                    t, _ = Tenant.objects.update_or_create(contratacion=c, defaults={
                        'servicio': plan.servicio, 'cliente': perfil, 'nombre': empresa,
                        'schema_name': f'{plan.servicio.prefijo}{user_slug}',
                        'dominio': f'{user_slug}.{plan.servicio.slug}.corexit.tech',
                        'estado': 'activo' if estado == 'activo' else 'suspendido',
                        'ultimo_sync': timezone.now() - timedelta(hours=rnd.randint(1, 20))})
                    c.url_sistema = t.url
                    c.save(update_fields=['url_sistema'])
                    self._metricas(t, CATALOGO[sv]['rango'], rnd, hoy, dias=90 if estado == 'activo' else 40)
                    # 4 meses de facturas
                    for m in range(4, 0, -1):
                        emision = (hoy.replace(day=1) - timedelta(days=30 * (m - 1))).replace(day=1)
                        pagada = m > 1 or rnd.random() < .5
                        monto = c.precio if frec == 'mensual' else (c.precio if m == 4 else None)
                        if monto is None:
                            continue
                        n_fact += 1
                        FacturaCliente.objects.get_or_create(cliente=perfil, numero_comprobante=f'00002-{n_fact:08d}', defaults={
                            'contratacion': c, 'tipo_comprobante': 'A' if cond == 'responsable_inscripto' else 'C',
                            'periodo_facturado': emision.strftime('%m/%Y'), 'fecha_emision': emision,
                            'fecha_vencimiento': emision + timedelta(days=10), 'monto': monto,
                            'estado': 'pagado' if pagada else 'pendiente',
                            'fecha_pago': timezone.make_aware(timezone.datetime.combine(emision + timedelta(days=rnd.randint(1, 9)),
                                                                                         timezone.datetime.min.time())) if pagada else None,
                            'metodo_pago': 'mercadopago' if pagada else None})

            if user_slug in ('ferreteria', 'kinesio'):
                c = perfil.contrataciones.first()
                tk, creado = Ticket.objects.get_or_create(cliente=perfil, asunto='No puedo emitir factura B' if user_slug == 'ferreteria' else 'Quiero agregar un profesional', defaults={
                    'descripcion': 'Desde ayer me tira error al emitir. ¿Pueden revisar?', 'contratacion': c,
                    'tenant': getattr(c, 'tenant', None), 'prioridad': 'alta'})
                if creado:
                    TicketMensaje.objects.create(ticket=tk, autor=staff, mensaje='¡Hola! Ya lo estamos revisando, te aviso en un rato.')
                    tk.estado = 'en_proceso'
                    tk.asignado_a = staff
                    tk.save()

        # Una contratación activa sin tenant aprovisionado → aparece en "requieren atención"
        Tenant.objects.get_or_create(servicio=servicios['Turnos'], schema_name='turnuevo', defaults={
            'nombre': 'Consultorio Nuevo', 'estado': 'error', 'ultimo_error': 'No se pudo conectar: Connection refused'})
        Ticket.objects.get_or_create(tipo='desarrollo', asunto='Configurar API CoreX en GestionAR', defaults={
            'descripcion': 'Instalar sdk/corex_agent en GestionAR y cargar api_url/api_token en el Hub.',
            'prioridad': 'alta', 'asignado_a': dev})

        self.stdout.write(self.style.SUCCESS(
            f'Datos demo listos. Usuarios (contraseña "{PASS}"): dev (superusuario + panel dev), staff, '
            + ', '.join(c[0] for c in CLIENTES) + ' (clientes).'))

    def _usuario(self, username, nombre, apellido, staff=False, superuser=False):
        u, creado = User.objects.get_or_create(username=username, defaults={
            'first_name': nombre, 'last_name': apellido, 'email': f'{username}@demo.corexit.tech',
            'is_staff': staff, 'is_superuser': superuser})
        if creado:
            u.set_password(PASS)
            u.save()
        return u

    def _metricas(self, tenant, rango, rnd, hoy, dias):
        defs = dict(MetricaServicio.objects.filter(servicio=tenant.servicio).values_list('clave', 'tipo'))
        base = {k: rnd.randint(*v) for k, v in rango.items()}
        for i in range(dias, -1, -1):
            f = hoy - timedelta(days=i)
            datos = {}
            for clave, (lo, hi) in rango.items():
                if defs.get(clave) == 'nivel':
                    datos[clave] = max(lo, int(base[clave] * (1 - i / (dias * 3))))
                else:
                    factor = 0.35 if f.weekday() == 6 else 1
                    datos[clave] = int(rnd.randint(lo, hi) * factor * (1 + (dias - i) / (dias * 2)))
            MetricaTenant.objects.update_or_create(tenant=tenant, fecha=f, defaults={'datos': datos, 'origen': 'push'})
