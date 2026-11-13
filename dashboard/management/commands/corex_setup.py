"""
Deja un SaaS listo en el Hub: servicio, métricas que reporta y conexión API.

    python manage.py corex_setup facturar  --api-url https://facturar.corexit.tech/corex/v1/  --api-token <token>
    python manage.py corex_setup gestionar --api-url https://gestionar.corexit.tech/corex/v1/ --api-token <token>
    python manage.py corex_setup --todos            # solo servicios + métricas, sin API

Es idempotente. Los planes (y sus límites) se cargan en el admin: el NOMBRE de cada plan
del Hub tiene que coincidir con el plan del SaaS (FacturAR) o es solo informativo (GestionAR).
"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from dashboard.models import MetricaServicio, Servicio

# clave, nombre, unidad, tipo, visible para el cliente, destacada en el panel dev
CATALOGO = {
    'facturar': {
        'nombre': 'FacturAR', 'prefijo': 'fac', 'color': '#06b6d4', 'prefijo_en_schema': True,
        'descripcion': 'Facturación electrónica ARCA para empresas y monotributistas.',
        'metricas': [
            ('comprobantes_emitidos', 'Comprobantes emitidos', '', 'contador', True, True),
            ('monto_facturado', 'Monto facturado', '$', 'contador', True, True),
            ('notas_credito', 'Notas de crédito', '', 'contador', True, False),
            ('comprobantes_rechazados', 'Rechazados por ARCA', '', 'contador', True, True),
            ('facturado_12m', 'Facturado últimos 12 meses', '$', 'nivel', True, False),
            ('tope_monotributo_pct', 'Uso del tope de Monotributo', '%', 'nivel', True, True),
            ('clientes', 'Clientes', '', 'nivel', True, False),
            ('puntos_venta', 'Puntos de venta', '', 'nivel', True, False),
            ('usuarios', 'Usuarios', '', 'nivel', True, False),
            ('consultas_aidy', 'Consultas a Aidy', '', 'contador', True, False),
            ('arca_delegacion_activa', 'Delegación ARCA activa (1/0)', '', 'nivel', False, True),
        ],
    },
    'gestionar': {
        # Row-level: el identificador es el slug de la tienda web (/tienda/<slug>/) -> sin prefijo
        'nombre': 'GestionAR', 'prefijo': 'gest', 'color': '#6366f1', 'prefijo_en_schema': False,
        'descripcion': 'Punto de venta, stock, tienda web y facturación electrónica ARCA.',
        'metricas': [
            ('ventas_cantidad', 'Ventas', '', 'contador', True, True),
            ('ventas_monto', 'Monto vendido', '$', 'contador', True, True),
            ('ventas_web', 'Ventas de la tienda web', '', 'contador', True, False),
            ('comprobantes_arca', 'Comprobantes ARCA', '', 'contador', True, True),
            ('pedidos_web_pendientes', 'Pedidos web sin confirmar', '', 'nivel', True, False),
            ('usuarios', 'Usuarios', '', 'nivel', True, True),
            ('productos', 'Productos', '', 'nivel', True, False),
            ('puntos_venta', 'Puntos de venta', '', 'nivel', True, False),
            ('clientes', 'Clientes', '', 'nivel', True, False),
        ],
    },
}


class Command(BaseCommand):
    help = 'Configura un SaaS en el Hub (servicio, métricas y API)'

    def add_arguments(self, parser):
        parser.add_argument('saas', nargs='?', choices=sorted(CATALOGO), help='Qué SaaS configurar')
        parser.add_argument('--todos', action='store_true', help='Todos los SaaS del catálogo (sin API)')
        parser.add_argument('--api-url', default='')
        parser.add_argument('--api-token', default='')
        parser.add_argument('--dominio-base', default='')

    def handle(self, *args, **o):
        if o['todos']:
            if o['api_url'] or o['api_token']:
                raise CommandError('--todos no acepta --api-url/--api-token: configurá cada SaaS por separado.')
            for slug in CATALOGO:
                self._configurar(slug, {})
            return
        if not o['saas']:
            raise CommandError(f'Indicá un SaaS ({", ".join(CATALOGO)}) o --todos.')
        self._configurar(o['saas'], o)

    def _configurar(self, slug, o):
        cfg = CATALOGO[slug]
        s = Servicio.objects.filter(Q(slug=slug) | Q(nombre__iexact=cfg['nombre'])).first()
        nuevo = s is None
        if nuevo:
            s = Servicio(nombre=cfg['nombre'], prefijo=cfg['prefijo'], color=cfg['color'])
        s.slug = slug
        s.descripcion = s.descripcion or cfg['descripcion']
        s.prefijo_en_schema = cfg['prefijo_en_schema']
        if o.get('api_url'):
            s.api_url = o['api_url']
        if o.get('api_token'):
            s.api_token = o['api_token']
        if o.get('dominio_base'):
            s.dominio_base = o['dominio_base']
        s.save()
        for orden, (clave, nombre, unidad, tipo, visible, destacada) in enumerate(cfg['metricas']):
            MetricaServicio.objects.update_or_create(servicio=s, clave=clave, defaults={
                'nombre': nombre, 'unidad': unidad, 'tipo': tipo, 'visible_cliente': visible,
                'destacada': destacada, 'orden': orden})

        self.stdout.write(self.style.SUCCESS(f'{s.nombre} {"creado" if nuevo else "actualizado"} '
                                             f'(servicio #{s.pk}, {len(cfg["metricas"])} métricas).'))
        self.stdout.write(f'  API: {s.api_url or "SIN CONFIGURAR"}')
        self.stdout.write(f'  Token de ingesta (COREX_HUB_INGEST_TOKEN del SaaS): {s.ingest_token}')
        planes = list(s.planes.values_list('nombre', flat=True))
        self.stdout.write(f'  Planes en el Hub: {", ".join(planes) or "ninguno (crealos en el admin)"}')
        if not s.tiene_api:
            self.stdout.write(self.style.WARNING('  Sin API: las altas se harán a mano (tarea interna).'))
