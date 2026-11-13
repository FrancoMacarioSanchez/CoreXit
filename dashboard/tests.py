import json
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .models import (
    ClienteProfile, Contratacion, LimitePlan, MetricaServicio, PlanServicio, Servicio, Tenant, Ticket,
)
from .permisos import GRUPO_DESARROLLADORES
from .servicios import metricas


class Base(TestCase):
    def setUp(self):
        self.servicio = Servicio.objects.create(nombre='GestionAR', slug='gestionar', prefijo='gest')
        self.plan = PlanServicio.objects.create(servicio=self.servicio, nombre='Inicial', precio_mensual=1000, precio_anual=10000)
        self.m_ventas = MetricaServicio.objects.create(servicio=self.servicio, clave='ventas', nombre='Ventas', tipo='contador')
        self.m_users = MetricaServicio.objects.create(servicio=self.servicio, clave='usuarios', nombre='Usuarios', tipo='nivel')
        LimitePlan.objects.create(plan=self.plan, metrica=self.m_ventas, limite=100)
        u = User.objects.create_user('cli', password='x')
        self.cliente = ClienteProfile.objects.create(user=u, nombre='Cliente', empresa='Mi Tienda')
        self.staff = User.objects.create_user('staff', password='x', is_staff=True)
        self.dev = User.objects.create_user('dev', password='x', is_staff=True)
        self.dev.groups.add(Group.objects.get_or_create(name=GRUPO_DESARROLLADORES)[0])

    def contratacion(self, estado='pendiente'):
        return Contratacion.objects.create(cliente=self.cliente, plan=self.plan, estado=estado,
                                           fecha_inicio=date.today(), fecha_vencimiento=date.today() + timedelta(days=30))


class RolesTests(Base):
    def test_cada_rol_en_su_area(self):
        for user, destino in (('cli', 'portal:inicio'), ('staff', 'staff:inicio'), ('dev', 'staff:inicio')):
            self.client.login(username=user, password='x')
            self.assertRedirects(self.client.get(reverse('redirect_post_login')), reverse(destino), fetch_redirect_response=False)
            self.client.logout()

    def test_cliente_no_entra_a_staff_ni_dev(self):
        self.client.login(username='cli', password='x')
        self.assertEqual(self.client.get(reverse('staff:inicio')).status_code, 302)
        self.assertEqual(self.client.get(reverse('devpanel:inicio')).status_code, 302)

    def test_staff_sin_grupo_no_entra_a_dev(self):
        self.client.login(username='staff', password='x')
        self.assertEqual(self.client.get(reverse('devpanel:inicio')).status_code, 302)
        self.client.login(username='dev', password='x')
        self.assertEqual(self.client.get(reverse('devpanel:inicio')).status_code, 200)


class AprovisionamientoTests(Base):
    def test_activar_sin_api_crea_tenant_pendiente_y_tarea(self):
        c = self.contratacion()
        with self.captureOnCommitCallbacks(execute=True):
            c.estado = 'activo'
            c.save()
        t = Tenant.objects.get(contratacion=c)
        self.assertEqual(t.estado, 'pendiente')
        self.assertTrue(t.schema_name.startswith('gestmitienda'))
        self.assertTrue(Ticket.objects.filter(tenant=t, tipo='desarrollo').exists())

    def test_activar_con_api_aprovisiona(self):
        self.servicio.api_url, self.servicio.api_token = 'http://saas/corex/v1/', 't'
        self.servicio.save()
        c = self.contratacion()
        with mock.patch('dashboard.servicios.integracion.SaaSClient._request',
                        return_value={'id': 7, 'estado': 'activo', 'dominio': 'mitienda.x.com'}):
            with self.captureOnCommitCallbacks(execute=True):
                c.estado = 'activo'
                c.save()
        t = Tenant.objects.get(contratacion=c)
        self.assertEqual((t.estado, t.id_externo), ('activo', '7'))
        c.refresh_from_db()
        self.assertEqual(c.url_sistema, 'https://mitienda.x.com')


class ApiIngestaTests(Base):
    def setUp(self):
        super().setUp()
        # Crear la contratación activa dispara la señal y crea el tenant automáticamente
        c = self.contratacion('activo')
        self.tenant = Tenant.objects.get(contratacion=c)
        Tenant.objects.filter(pk=self.tenant.pk).update(schema_name='gestt', estado='activo')
        self.tenant.refresh_from_db()

    def post(self, body, token=None):
        return self.client.post('/api/v1/metricas/', json.dumps(body), content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {token or self.servicio.ingest_token}')

    def test_token_invalido(self):
        self.assertEqual(self.post({}, token='malo').status_code, 401)

    def test_guarda_y_calcula_consumo(self):
        hoy = date.today()
        r = self.post({'items': [{'tenant': 'gestt', 'fecha': hoy.isoformat(), 'metricas': {'ventas': 60, 'usuarios': 3}},
                                 {'tenant': 'gestt', 'fecha': hoy.replace(day=1).isoformat() if hoy.day > 1 else hoy.isoformat(),
                                  'metricas': {'ventas': 25}}]})
        self.assertEqual(r.status_code, 200)
        consumo = {m['clave']: m for m in metricas.consumo(self.tenant)}
        esperado = 85 if date.today().day > 1 else 25
        self.assertEqual(consumo['ventas']['valor'], esperado)
        self.assertEqual(consumo['ventas']['limite'], 100)
        self.assertEqual(consumo['usuarios']['valor'], 3)

    def test_no_escribe_tenants_de_otro_saas(self):
        otro = Servicio.objects.create(nombre='Turnos', slug='turnos', prefijo='tur')
        r = self.post({'tenant': 'gestt', 'metricas': {'ventas': 1}}, token=otro.ingest_token)
        self.assertEqual(r.status_code, 422)
        self.assertFalse(self.tenant.metricas.exists())


class PortalTests(Base):
    def test_cliente_no_ve_servicio_ajeno(self):
        otro_user = User.objects.create_user('otro', password='x')
        otro = ClienteProfile.objects.create(user=otro_user, nombre='Otro')
        c = Contratacion.objects.create(cliente=otro, plan=self.plan, fecha_inicio=date.today(), fecha_vencimiento=date.today())
        self.client.login(username='cli', password='x')
        self.assertEqual(self.client.get(reverse('portal:servicio', args=[c.id])).status_code, 404)
