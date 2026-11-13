#!/usr/bin/env python
"""
SaaS simulado que implementa la API CoreX (docs/API_SAAS.md).

Sirve para probar el Hub sin tocar los SaaS reales. No usa dependencias.

    python sdk/mock_saas.py --puerto 9001 --token prueba123 --perfil gestionar

En el Hub (Panel dev → SaaS → Integración):
    API URL   = http://127.0.0.1:9001/corex/v1/
    API token = prueba123

Perfiles de métricas: gestionar, turnos, stockear.
"""
import argparse
import json
import random
import re
import threading
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PERFILES = {
    'gestionar': {
        'contador': {'ventas_cantidad': (10, 80), 'ventas_monto': (80000, 900000), 'comprobantes_arca': (8, 70)},
        'nivel': {'usuarios': (1, 6), 'productos': (150, 2500), 'puntos_venta': (1, 3), 'almacenamiento_mb': (40, 900)},
    },
    'turnos': {
        'contador': {'turnos_reservados': (5, 60), 'turnos_cancelados': (0, 8), 'recordatorios_enviados': (5, 60)},
        'nivel': {'profesionales': (1, 8), 'clientes': (40, 900)},
    },
    'stockear': {
        'contador': {'pedidos': (0, 25), 'visitas_catalogo': (30, 600)},
        'nivel': {'productos_catalogo': (100, 5000), 'compradores': (5, 300)},
    },
}

ESTADO = {'tenants': {}, 'lock': threading.Lock()}


def metricas_del_dia(schema, fecha, perfil):
    """Datos pseudoaleatorios pero estables para (schema, fecha)."""
    rnd = random.Random(f'{schema}-{fecha.isoformat()}')
    base = random.Random(schema)
    datos = {}
    for clave, (lo, hi) in PERFILES[perfil]['contador'].items():
        datos[clave] = rnd.randint(lo, hi) if fecha.weekday() < 6 else rnd.randint(0, max(lo, 1))
    for clave, (lo, hi) in PERFILES[perfil]['nivel'].items():
        nivel = base.randint(lo, hi)
        dias = (date.today() - fecha).days
        datos[clave] = max(lo, int(nivel - dias * (hi - lo) / 400))  # crece despacio con el tiempo
    return datos


class Handler(BaseHTTPRequestHandler):
    token = ''
    perfil = 'gestionar'
    prefijo = '/corex/v1/'

    def log_message(self, fmt, *args):
        print(f'[mock-saas] {self.address_string()} {fmt % args}')

    # ---------------------------------------------------------------- utils
    def _json(self, status, datos):
        cuerpo = json.dumps(datos).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _auth(self):
        if self.headers.get('Authorization', '') != f'Bearer {self.token}':
            self._json(401, {'error': 'Token inválido'})
            return False
        return True

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def _ruta(self):
        u = urlparse(self.path)
        if not u.path.startswith(self.prefijo):
            return None, {}
        return u.path[len(self.prefijo):].strip('/'), parse_qs(u.query)

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        if not self._auth():
            return
        ruta, qs = self._ruta()
        tenants = ESTADO['tenants']
        if ruta == 'health':
            return self._json(200, {'ok': True, 'servicio': f'mock-{self.perfil}', 'version': '0.1.0', 'tenants': len(tenants)})
        if ruta == 'tenants':
            return self._json(200, {'tenants': list(tenants.values())})
        m = re.fullmatch(r'tenants/([\w-]+)(/metricas)?', ruta or '')
        if m:
            t = tenants.get(m.group(1))
            if not t:
                return self._json(404, {'error': 'Tenant inexistente'})
            if not m.group(2):
                return self._json(200, t)
            hasta = date.fromisoformat(qs.get('hasta', [date.today().isoformat()])[0])
            desde = date.fromisoformat(qs.get('desde', [(hasta - timedelta(days=6)).isoformat()])[0])
            if (hasta - desde).days > 92:
                return self._json(400, {'error': 'Rango máximo: 92 días'})
            creado = date.fromisoformat(t['creado'][:10])
            series, f = [], max(desde, creado)
            while f <= hasta:
                series.append({'fecha': f.isoformat(), 'metricas': metricas_del_dia(t['schema_name'], f, self.perfil)})
                f += timedelta(days=1)
            return self._json(200, {'tenant': t['schema_name'], 'estado': t['estado'], 'series': series})
        self._json(404, {'error': 'Ruta inexistente'})

    # --------------------------------------------------------------- POST
    def do_POST(self):
        if not self._auth():
            return
        ruta, _ = self._ruta()
        try:
            datos = self._body()
        except ValueError:
            return self._json(400, {'error': 'JSON inválido'})
        tenants = ESTADO['tenants']
        with ESTADO['lock']:
            if ruta == 'tenants':
                schema = datos.get('schema_name', '')
                if not re.fullmatch(r'[a-z][a-z0-9_]{1,62}', schema or ''):
                    return self._json(400, {'error': 'schema_name inválido'})
                if schema in tenants:  # idempotente
                    return self._json(200, tenants[schema])
                # Arranca 60 días atrás para que haya historia que mostrar
                t = {'id': len(tenants) + 1, 'schema_name': schema, 'nombre': datos.get('nombre') or schema,
                     'dominio': datos.get('dominio') or f'{schema}.localhost', 'estado': 'activo',
                     'plan': datos.get('plan'), 'limites': datos.get('limites', {}),
                     'creado': (datetime.now() - timedelta(days=60)).isoformat(timespec='seconds')}
                tenants[schema] = t
                return self._json(201, t)
            m = re.fullmatch(r'tenants/([\w-]+)/(suspender|reactivar|plan)', ruta or '')
            if m:
                t = tenants.get(m.group(1))
                if not t:
                    return self._json(404, {'error': 'Tenant inexistente'})
                if m.group(2) == 'suspender':
                    t['estado'] = 'suspendido'
                elif m.group(2) == 'reactivar':
                    t['estado'] = 'activo'
                else:
                    t['plan'], t['limites'] = datos.get('plan'), datos.get('limites', {})
                return self._json(200, {'ok': True, 'estado': t['estado']})
        self._json(404, {'error': 'Ruta inexistente'})


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--puerto', type=int, default=9001)
    p.add_argument('--token', default='prueba123')
    p.add_argument('--perfil', choices=PERFILES, default='gestionar')
    p.add_argument('--tenants', type=int, default=3, help='Tenants que ya "existen" para probar la importación')
    a = p.parse_args()
    Handler.token, Handler.perfil = a.token, a.perfil
    for i in range(a.tenants):
        schema = f'demo{a.perfil[:4]}{i + 1}'
        ESTADO['tenants'][schema] = {
            'id': i + 1, 'schema_name': schema, 'nombre': f'Comercio demo {i + 1}', 'dominio': f'{schema}.localhost',
            'estado': 'activo', 'creado': (datetime.now() - timedelta(days=90)).isoformat(timespec='seconds')}
    srv = ThreadingHTTPServer(('127.0.0.1', a.puerto), Handler)
    print(f'SaaS simulado ({a.perfil}) en http://127.0.0.1:{a.puerto}{Handler.prefijo}  token={a.token}')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
