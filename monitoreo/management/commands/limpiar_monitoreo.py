from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from monitoreo.models import MuestraRequests, MuestraServidor, RegistroActividad


class Command(BaseCommand):
    help = 'Borra métricas y actividad antiguas.'

    def add_arguments(self, parser):
        parser.add_argument('--dias-metricas', type=int, default=30)
        parser.add_argument('--dias-actividad', type=int, default=365)
        parser.add_argument('--dias-visitas', type=int, default=90,
                            help='Las simples visitas a pantallas se conservan menos que las acciones.')

    def handle(self, *args, **o):
        ahora = timezone.now()
        a = MuestraServidor.objects.filter(creado__lt=ahora - timedelta(days=o['dias_metricas'])).delete()[0]
        b = MuestraRequests.objects.filter(minuto__lt=ahora - timedelta(days=o['dias_metricas'])).delete()[0]
        c = RegistroActividad.objects.filter(tipo='vista', creado__lt=ahora - timedelta(days=o['dias_visitas'])).delete()[0]
        d = RegistroActividad.objects.filter(creado__lt=ahora - timedelta(days=o['dias_actividad'])).delete()[0]
        self.stdout.write(f'Borrado: {a} muestras, {b} tráfico, {c} visitas, {d} registros de actividad.')
