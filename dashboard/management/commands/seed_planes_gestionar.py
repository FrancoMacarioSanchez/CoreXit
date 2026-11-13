"""Carga (o actualiza) los 3 planes de GestionAR: Starter, Ecommerce y Empresa.

    python manage.py seed_planes_gestionar

- Es idempotente: se puede correr todas las veces que haga falta.
- NO pisa los precios ni los links de Mercado Pago que ya cargaste en el admin; los planes nuevos quedan en
  $0 y la landing los muestra como «Próximamente» hasta que les pongas precio (Admin → Planes).
- Sí actualiza descripciones y límites, que deben coincidir con lo que GestionAR hace cumplir
  (gestionar_corex/apps/corex_hub/planes.py).
- `--desactivar-otros` oculta de la venta cualquier otro plan de GestionAR (p. ej. los de la demo).
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from dashboard.models import LimitePlan, MetricaServicio, PlanServicio, Servicio

# (clave, nombre, unidad, tipo, visible_cliente, destacada). Son las claves que GestionAR reporta.
METRICAS = [
    ('ventas_cantidad', 'Ventas', '', 'contador', True, True),
    ('ventas_monto', 'Monto vendido', '$', 'contador', True, False),
    ('ventas_web', 'Ventas web', '', 'contador', True, False),
    ('comprobantes_arca', 'Comprobantes ARCA', '', 'contador', True, True),
    ('pedidos_web_pendientes', 'Pedidos web pendientes', '', 'nivel', False, False),
    ('usuarios', 'Usuarios', '', 'nivel', True, True),
    ('puntos_venta', 'Puntos de venta', '', 'nivel', True, False),
    ('productos', 'Productos', '', 'nivel', True, False),
    ('clientes', 'Clientes', '', 'nivel', False, False),
]

# Una línea = un renglón en la tarjeta de la landing. Mantener en sintonía con GestionAR (planes.py).
PLANES = [
    {
        'nombre': 'Starter',
        'limites': {'puntos_venta': 1, 'usuarios': 2, 'productos': 1000, 'comprobantes_arca': 300},
        'descripcion': (
            "1 punto de venta con caja táctil\n"
            "2 usuarios\n"
            "Hasta 1.000 productos\n"
            "Stock, clientes y proveedores\n"
            "Facturación electrónica ARCA (300 comprobantes por mes)\n"
            "Reportes de ventas y exportación de datos"
        ),
    },
    {
        'nombre': 'Ecommerce',
        'limites': {'puntos_venta': 2, 'usuarios': 6, 'productos': 10000, 'comprobantes_arca': 1500},
        'descripcion': (
            "Todo lo de Starter\n"
            "Tienda web propia con carrito y envíos coordinados\n"
            "Motor de promociones para local y online\n"
            "Chat interno del equipo\n"
            "2 puntos de venta y 6 usuarios\n"
            "Hasta 10.000 productos\n"
            "1.500 comprobantes ARCA por mes"
        ),
    },
    {
        'nombre': 'Empresa',
        'limites': {'puntos_venta': 10, 'usuarios': 25, 'comprobantes_arca': 6000},   # productos: sin límite
        'descripcion': (
            "Todo lo de Ecommerce\n"
            "Gerencia: métricas y gráficos del negocio\n"
            "Registro de actividad: quién hizo qué y cuándo\n"
            "10 puntos de venta y 25 usuarios\n"
            "Productos sin límite\n"
            "6.000 comprobantes ARCA por mes"
        ),
    },
]


class Command(BaseCommand):
    help = 'Carga los planes Starter, Ecommerce y Empresa de GestionAR (idempotente)'

    def add_arguments(self, parser):
        parser.add_argument('--desactivar-otros', action='store_true',
                            help='Oculta de la venta los demás planes de GestionAR')

    @transaction.atomic
    def handle(self, *args, **opts):
        servicio = (Servicio.objects.filter(slug='gestionar').first()
                    or Servicio.objects.filter(nombre__iexact='GestionAR').first())
        if servicio is None:
            servicio = Servicio.objects.create(
                nombre='GestionAR', slug='gestionar', prefijo='ges', color='#6366f1',
                descripcion='Punto de venta, stock, tienda web y facturación electrónica ARCA.',
                prefijo_en_schema=False)
            self.stdout.write(self.style.WARNING('Se creó el servicio GestionAR (completá api_url y api_token con corex_setup).'))
        elif not servicio.slug:
            servicio.slug = 'gestionar'
            servicio.save(update_fields=['slug'])

        defs = {}
        for orden, (clave, nombre, unidad, tipo, visible, destacada) in enumerate(METRICAS):
            defs[clave], creada = MetricaServicio.objects.get_or_create(
                servicio=servicio, clave=clave,
                defaults={'nombre': nombre, 'unidad': unidad, 'tipo': tipo, 'visible_cliente': visible,
                          'destacada': destacada, 'orden': orden})
            if creada:
                self.stdout.write(f'  + métrica {clave}')

        nombres = []
        for cfg in PLANES:
            plan, creado = PlanServicio.objects.get_or_create(
                servicio=servicio, nombre=cfg['nombre'], defaults={'activo': True})
            plan.descripcion = cfg['descripcion']
            plan.activo = True
            plan.save()
            # Límites exactamente los del plan: lo que no figura queda sin límite
            LimitePlan.objects.filter(plan=plan).exclude(metrica__clave__in=cfg['limites']).delete()
            for clave, valor in cfg['limites'].items():
                LimitePlan.objects.update_or_create(plan=plan, metrica=defs[clave], defaults={'limite': valor})
            nombres.append(cfg['nombre'])
            precio = f'${plan.precio_mensual:.0f}/mes' if plan.precio_mensual else 'SIN PRECIO'
            self.stdout.write(self.style.SUCCESS(f"{'Creado' if creado else 'Actualizado'}: {plan.nombre} ({precio})"))

        if opts['desactivar_otros']:
            n = PlanServicio.objects.filter(servicio=servicio, activo=True).exclude(nombre__in=nombres).update(activo=False)
            self.stdout.write(f'Planes ocultados de la venta: {n}')
        otros = PlanServicio.objects.filter(servicio=servicio, activo=True).exclude(nombre__in=nombres)
        if otros.exists():
            self.stdout.write(self.style.WARNING(
                'Hay otros planes activos de GestionAR (' + ', '.join(p.nombre for p in otros) +
                '). Corré con --desactivar-otros para que la landing muestre solo los 3 nuevos.'))
        sin_precio = PlanServicio.objects.filter(servicio=servicio, nombre__in=nombres, precio_mensual=0)
        if sin_precio.exists():
            self.stdout.write(self.style.WARNING(
                'Falta definir precio (mensual/anual) y link de Mercado Pago en: ' + ', '.join(p.nombre for p in sin_precio)))
