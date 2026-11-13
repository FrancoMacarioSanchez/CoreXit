"""Lectura de recursos del servidor. Usa psutil si está; si no, /proc (Linux) y la librería estándar."""
import os
import platform
import shutil
import socket
import sys
import time

import django
from django.conf import settings
from django.db import connection

try:
    import psutil
except ImportError:  # opcional: sin él se ven menos datos en Windows
    psutil = None

INICIO_PROCESO = time.time()


def _leer(ruta):
    try:
        with open(ruta, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


def _cpu_proc():
    def tomar():
        partes = _leer('/proc/stat').split('\n', 1)[0].split()[1:]
        valores = [int(x) for x in partes]
        return sum(valores), valores[3] + (valores[4] if len(valores) > 4 else 0)
    try:
        t1, i1 = tomar()
        time.sleep(0.15)
        t2, i2 = tomar()
        return round(100.0 * (1 - (i2 - i1) / (t2 - t1)), 1) if t2 > t1 else None
    except (ValueError, IndexError, ZeroDivisionError):
        return None


def _memoria_proc():
    datos = {}
    for linea in _leer('/proc/meminfo').splitlines():
        clave, _, resto = linea.partition(':')
        try:
            datos[clave] = int(resto.split()[0]) / 1024  # kB -> MB
        except (ValueError, IndexError):
            pass
    total, libre = datos.get('MemTotal'), datos.get('MemAvailable')
    if total and libre is not None:
        usada = total - libre
        return round(100.0 * usada / total, 1), round(usada), round(total)
    return None, None, None


def _proceso_mb():
    if psutil:
        return round(psutil.Process().memory_info().rss / 1048576, 1)
    for linea in _leer('/proc/self/status').splitlines():
        if linea.startswith('VmRSS:'):
            return round(int(linea.split()[1]) / 1024, 1)
    return None


def latencia_db():
    inicio = time.perf_counter()
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
    except Exception:
        return None
    return round((time.perf_counter() - inicio) * 1000, 2)


def muestra():
    """Valores actuales. Lo que no se pueda leer en este sistema queda en None."""
    m = {'cpu': None, 'memoria': None, 'memoria_usada_mb': None, 'memoria_total_mb': None,
         'disco': None, 'disco_libre_gb': None, 'carga': None, 'proceso_mb': _proceso_mb(),
         'db_ms': latencia_db()}
    if psutil:
        m['cpu'] = psutil.cpu_percent(interval=0.2)
        vm = psutil.virtual_memory()
        m['memoria'], m['memoria_usada_mb'], m['memoria_total_mb'] = vm.percent, round(vm.used / 1048576), round(vm.total / 1048576)
    elif os.path.exists('/proc/stat'):
        m['cpu'] = _cpu_proc()
        m['memoria'], m['memoria_usada_mb'], m['memoria_total_mb'] = _memoria_proc()
    try:
        du = shutil.disk_usage(str(settings.BASE_DIR))
        m['disco'] = round(100.0 * du.used / du.total, 1)
        m['disco_libre_gb'] = round(du.free / 1073741824, 1)
    except OSError:
        pass
    if hasattr(os, 'getloadavg'):
        try:
            m['carga'] = round(os.getloadavg()[0], 2)
        except OSError:
            pass
    return m


def _tamano_db():
    try:
        if connection.vendor == 'postgresql':
            with connection.cursor() as cur:
                cur.execute('SELECT pg_database_size(current_database())')
                return round(cur.fetchone()[0] / 1048576, 1)
        if connection.vendor == 'sqlite':
            nombre = connection.settings_dict.get('NAME')
            return round(os.path.getsize(nombre) / 1048576, 1)
    except Exception:
        pass
    return None


def info():
    """Datos estáticos del servidor para mostrar en la pantalla."""
    arranque = None
    if psutil:
        arranque = psutil.boot_time()
    else:
        try:
            arranque = time.time() - float(_leer('/proc/uptime').split()[0])
        except (ValueError, IndexError):
            pass
    return {
        'host': socket.gethostname(),
        'sistema': f'{platform.system()} {platform.release()}',
        'python': sys.version.split()[0],
        'django': django.get_version(),
        'cpus': os.cpu_count(),
        'pid': os.getpid(),
        'psutil': psutil is not None,
        'debug': settings.DEBUG,
        'db_motor': connection.vendor,
        'db_mb': _tamano_db(),
        'uptime_servidor': (time.time() - arranque) if arranque else None,
        'uptime_proceso': time.time() - INICIO_PROCESO,
    }
