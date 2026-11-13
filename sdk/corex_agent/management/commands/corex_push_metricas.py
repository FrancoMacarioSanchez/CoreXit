"""
Empuja al Hub las métricas de todos los tenants (alternativa/complemento al pull).
Programarlo con cron cada hora o una vez por noche:

    python manage.py corex_push_metricas --dias 2
"""
import json
import urllib.request
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from corex_agent import conf


class Command(BaseCommand):
    help = 'Envía métricas diarias de todos los tenants al Hub de CoreX'

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=1)

    def handle(self, *args, **opts):
        hub, token = conf.get('COREX_HUB_URL'), conf.get('COREX_HUB_INGEST_TOKEN')
        ruta = conf.get('COREX_METRICS_COLLECTOR')
        if not (hub and token and ruta):
            raise CommandError('Faltan COREX_HUB_URL, COREX_HUB_INGEST_TOKEN o COREX_METRICS_COLLECTOR')
        recolectar = import_string(ruta)
        hoy = date.today()
        fechas = [hoy - timedelta(days=i) for i in range(opts['dias'])]
        items = []
        for t in get_tenant_model().objects.exclude(schema_name=get_public_schema_name()):
            with schema_context(t.schema_name):
                for f in fechas:
                    items.append({'tenant': t.schema_name, 'fecha': f.isoformat(), 'metricas': recolectar(f)})
        for i in range(0, len(items), 500):
            lote = items[i:i + 500]
            req = urllib.request.Request(
                hub.rstrip('/') + '/api/v1/metricas/', data=json.dumps({'items': lote}).encode(), method='POST',
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())
            self.stdout.write(f"Lote {i // 500 + 1}: {resp.get('guardados')} guardados, {len(resp.get('rechazados', []))} rechazados")
