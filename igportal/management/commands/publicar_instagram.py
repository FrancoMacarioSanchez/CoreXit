from django.core.management.base import BaseCommand

from igportal.publicador import procesar_pendientes


class Command(BaseCommand):
    help = 'Publica en Instagram lo programado que ya venció. Programarlo cada 5 minutos (cron / tarea programada).'

    def handle(self, *args, **opts):
        n = procesar_pendientes()
        self.stdout.write(f'{n} publicación(es) procesadas.')
