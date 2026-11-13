import json
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.permisos import GRUPO_DESARROLLADORES

from . import middleware
from .models import MuestraRequests, MuestraServidor, RegistroActividad


class Base(TestCase):
    def setUp(self):
        self.cli = User.objects.create_user('cliente', password='x')
        self.staff = User.objects.create_user('ana', password='x', is_staff=True)
        self.dev = User.objects.create_user('dev', password='x', is_staff=True)
        self.dev.groups.add(Group.objects.get_or_create(name=GRUPO_DESARROLLADORES)[0])
        middleware._cubeta.update(minuto=None, total=0, ok=0, c4xx=0, c5xx=0, suma_ms=0, max_ms=0)


class ActividadTests(Base):
    def test_staff_get_se_registra_como_visita(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('staff:clientes')).status_code, 200)
        r = RegistroActividad.objects.get(tipo='vista')
        self.assertEqual((r.username, r.descripcion), ('ana', 'Lista de clientes'))

    def test_post_se_registra_como_accion_sin_guardar_el_contenido(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('staff:clientes'), {'q': 'secreto-123'})
        r = RegistroActividad.objects.get(tipo='accion')
        self.assertEqual(r.metodo, 'POST')
        self.assertNotIn('secreto-123', str(r.__dict__))

    def test_cliente_no_se_registra(self):
        self.client.force_login(self.cli)
        self.client.get(reverse('portal:inicio'))
        self.assertEqual(RegistroActividad.objects.count(), 0)

    def test_login_logout_y_fallido(self):
        self.client.post(reverse('login'), {'action_login': '1', 'username': 'ana', 'password': 'x'})
        self.client.post(reverse('logout'))
        self.client.post(reverse('login'), {'action_login': '1', 'username': 'ana', 'password': 'mala-clave'})
        self.assertEqual(sorted(RegistroActividad.objects.values_list('tipo', flat=True)), ['login', 'login_fallido', 'logout'])
        texto = ' '.join(f'{r.descripcion}{r.ruta}{r.username}' for r in RegistroActividad.objects.all())
        self.assertNotIn('mala-clave', texto)

    def test_login_de_cliente_no_se_registra(self):
        self.client.post(reverse('login'), {'action_login': '1', 'username': 'cliente', 'password': 'x'})
        self.assertFalse(RegistroActividad.objects.filter(tipo='login').exists())

    def test_descripcion_de_admin(self):
        su = User.objects.create_superuser('root', 'r@x.com', 'x')
        self.client.force_login(su)
        self.client.get('/admin/auth/user/%d/change/' % self.cli.pk)
        self.assertEqual(RegistroActividad.objects.get(tipo='vista').descripcion, f'Admin: Modificó auth.user #{self.cli.pk}')

    def test_solo_desarrolladores_ven_la_actividad(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('monitoreo:actividad')).status_code, 302)
        self.client.force_login(self.dev)
        self.assertEqual(self.client.get(reverse('monitoreo:actividad')).status_code, 200)

    def test_filtros_y_csv(self):
        RegistroActividad.objects.create(usuario=self.staff, username='ana', tipo='accion', descripcion='Cambió algo')
        RegistroActividad.objects.create(usuario=self.dev, username='dev', tipo='accion', descripcion='Otra cosa')
        self.client.force_login(self.dev)
        r = self.client.get(reverse('monitoreo:actividad'), {'usuario': 'ana'})
        self.assertContains(r, 'Cambió algo')
        self.assertNotContains(r, 'Otra cosa')
        csv = self.client.get(reverse('monitoreo:actividad'), {'export': 'csv'})
        self.assertEqual(csv['Content-Type'].split(';')[0], 'text/csv')
        self.assertIn('Cambió algo', csv.content.decode('utf-8'))

    def test_el_registro_sobrevive_al_borrado_del_usuario(self):
        RegistroActividad.objects.create(usuario=self.staff, username='ana', tipo='accion')
        self.staff.delete()
        self.assertEqual(RegistroActividad.objects.get().username, 'ana')

    def test_si_falla_el_registro_la_pagina_igual_responde(self):
        self.client.force_login(self.staff)
        with mock.patch('monitoreo.actividad.RegistroActividad.objects.create', side_effect=RuntimeError('boom')):
            with self.assertLogs('monitoreo.middleware', level='ERROR'):
                self.assertEqual(self.client.get(reverse('staff:clientes')).status_code, 200)


class ServidorTests(Base):
    def test_trafico_se_acumula_y_se_guarda(self):
        self.client.get('/')
        self.client.get('/no-existe/')
        middleware.volcar_pendiente()
        m = MuestraRequests.objects.get()
        self.assertEqual((m.total, m.ok, m.c4xx, m.c5xx), (2, 1, 1, 0))
        self.client.get('/')
        middleware.volcar_pendiente()
        self.assertEqual(MuestraRequests.objects.get().total, 3)   # suma al mismo minuto, no duplica

    def test_no_cuenta_estaticos_ni_el_polling(self):
        self.client.force_login(self.dev)
        self.client.get(reverse('monitoreo:servidor_datos'))
        self.client.get('/static/x.css')
        self.assertEqual(middleware._cubeta['total'], 0)

    def test_datos_devuelve_json_y_guarda_una_muestra_por_minuto(self):
        self.client.force_login(self.dev)
        for _ in range(2):
            r = self.client.get(reverse('monitoreo:servidor_datos'), {'rango': '6h'})
            self.assertEqual(r.status_code, 200)
        d = json.loads(r.content)
        self.assertEqual(set(d), {'vivo', 'recursos', 'trafico', 'resumen_24h'})
        self.assertIn('disco', d['vivo'])
        self.assertEqual(MuestraServidor.objects.count(), 1)

    def test_rango_invalido_usa_el_default(self):
        self.client.force_login(self.dev)
        self.assertEqual(self.client.get(reverse('monitoreo:servidor_datos'), {'rango': 'zzz'}).status_code, 200)

    def test_series_agrupan_y_promedian(self):
        ahora = timezone.now()
        for i in range(3):
            MuestraServidor.objects.create(creado=ahora - timedelta(minutes=i), cpu=10 * (i + 1), memoria=50, disco=70)
        MuestraRequests.objects.create(minuto=ahora.replace(second=0, microsecond=0), total=10, ok=8, c4xx=1, c5xx=1,
                                       suma_ms=500, max_ms=90)
        self.client.force_login(self.dev)
        d = json.loads(self.client.get(reverse('monitoreo:servidor_datos'), {'rango': '1h'}).content)
        self.assertEqual(d['trafico']['ms_prom'], [50.0])
        self.assertEqual(d['resumen_24h']['errores_5xx'], 1)

    def test_pagina_solo_para_devs(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('monitoreo:servidor')).status_code, 302)
        self.client.force_login(self.dev)
        self.assertContains(self.client.get(reverse('monitoreo:servidor')), 'Métricas del servidor')

    def test_comandos(self):
        out = StringIO()
        call_command('muestrear_servidor', stdout=out)
        self.assertEqual(MuestraServidor.objects.count(), 1)
        MuestraServidor.objects.create(creado=timezone.now() - timedelta(days=60))
        RegistroActividad.objects.create(username='x', tipo='vista', creado=timezone.now() - timedelta(days=120))
        RegistroActividad.objects.create(username='x', tipo='accion', creado=timezone.now() - timedelta(days=120))
        call_command('limpiar_monitoreo', stdout=out)
        self.assertEqual(MuestraServidor.objects.count(), 1)
        self.assertEqual(list(RegistroActividad.objects.values_list('tipo', flat=True)), ['accion'])
