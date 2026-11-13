"""
Trae métricas de todos los SaaS con API configurada.

Programarlo con cron / Programador de tareas de Windows, por ejemplo cada hora:
    python manage.py sync_metricas --dias 2
"""
from django.core.management.base import BaseCommand

from dashboard.models import Servicio
from dashboard.servicios.metricas import sincronizar_servicio


class Command(BaseCommand):
    help = 'Sincroniza las métricas de los tenants desde la API de cada SaaS'

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=2, help='Cantidad de días hacia atrás (default 2)')
        parser.add_argument('--servicio', help='Slug del servicio (default: todos)')

    def handle(self, *args, **opts):
        qs = Servicio.objects.filter(activo=True).exclude(api_url='').exclude(api_token='')
        if opts['servicio']:
            qs = qs.filter(slug=opts['servicio'])
        if not qs.exists():
            self.stdout.write(self.style.WARNING('No hay servicios con API configurada.'))
            return
        for servicio in qs:
            ok, errores = sincronizar_servicio(servicio, dias=opts['dias'])
            self.stdout.write(f'{servicio.nombre}: {ok} tenants sincronizados, {len(errores)} errores')
            for e in errores:
                self.stdout.write(self.style.ERROR(f'  - {e}'))
