from django.core.management.base import BaseCommand

from monitoreo import middleware, sistema
from monitoreo.models import MuestraServidor


class Command(BaseCommand):
    help = 'Guarda una muestra de recursos del servidor. Programarlo cada minuto (cron / tarea programada).'

    def handle(self, *args, **opts):
        m = sistema.muestra()
        MuestraServidor.objects.create(**{k: m[k] for k in (
            'cpu', 'memoria', 'memoria_usada_mb', 'disco', 'carga', 'proceso_mb', 'db_ms')})
        middleware.volcar_pendiente()
        self.stdout.write(f"CPU {m['cpu']}% · RAM {m['memoria']}% · Disco {m['disco']}%")
