import io
import json
import urllib.error
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dashboard.permisos import GRUPO_DESARROLLADORES

from . import publicador
from .client import ClienteInstagram, InstagramError, _mensaje_api
from .models import ConfiguracionInstagram, PublicacionInstagram


class Falso:
    """Reemplazo del cliente real: no sale a internet."""
    def __init__(self, estados=('FINISHED',), falla_en=None):
        self.estados, self.falla_en, self.llamadas = list(estados), falla_en, []

    def crear_contenedor(self, pub):
        if self.falla_en == 'crear':
            raise InstagramError('URL no accesible')
        self.llamadas.append('crear')
        return 'CONT1'

    def estado_contenedor(self, cid):
        e = self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]
        return e, ''

    def publicar(self, cid):
        self.llamadas.append('publicar')
        return 'MEDIA1'

    def permalink(self, mid):
        return 'https://instagram.com/p/abc/'

    def perfil(self):
        return {'user_id': '99', 'username': 'corex', 'name': 'CoreX', 'account_type': 'BUSINESS',
                'followers_count': 120, 'follows_count': 10, 'media_count': 3}

    def medios(self, limite=12):
        return [{'id': 'm1', 'caption': 'Hola', 'media_type': 'IMAGE', 'media_url': 'https://x/y.jpg',
                 'permalink': 'https://i/p', 'timestamp': '2026-11-13T18:00:00+0000', 'like_count': 5, 'comments_count': 2}]

    def metrica_total(self, m, d, h):
        return 4242

    def alcance_diario(self, d, h):
        return [{'value': 10, 'end_time': '2026-11-12T08:00:00+0000'}]

    def comentarios(self, mid, limite=50):
        return [{'id': 'c1', 'text': 'Precio?', 'username': 'juan', 'timestamp': '2026-11-13T18:05:00+0000'}]

    def responder(self, cid, texto):
        self.llamadas.append(('responder', cid, texto))
        return {}

    def ocultar(self, cid, ocultar=True):
        self.llamadas.append(('ocultar', cid, ocultar))
        return {}

    def limite_publicacion(self):
        return 3, 100


def nueva(**kw):
    datos = dict(tipo='IMAGE', media_url='https://cdn.corexit.tech/a.jpg', caption='Hola')
    datos.update(kw)
    return PublicacionInstagram.objects.create(**datos)


class PublicadorTests(TestCase):
    def test_publica_cuando_el_archivo_esta_listo(self):
        p, f = nueva(), Falso()
        self.assertEqual(publicador.avanzar(p, f), 'publicada')
        p.refresh_from_db()
        self.assertEqual((p.ig_media_id, p.permalink), ('MEDIA1', 'https://instagram.com/p/abc/'))
        self.assertIsNotNone(p.publicada_en)

    def test_video_en_proceso_queda_procesando_y_luego_se_completa(self):
        p, f = nueva(tipo='REELS', media_url='https://x/v.mp4'), Falso(estados=['IN_PROGRESS'])
        self.assertEqual(publicador.avanzar(p, f, esperar=False), 'procesando')
        self.assertEqual(f.llamadas, ['crear'])
        f.estados = ['FINISHED']
        self.assertEqual(publicador.avanzar(p, f, esperar=False), 'publicada')
        self.assertEqual(f.llamadas, ['crear', 'publicar'])      # no creó otro contenedor

    def test_error_del_contenedor_se_informa_y_permite_reintentar(self):
        p = nueva()
        self.assertEqual(publicador.avanzar(p, Falso(estados=['ERROR'])), 'error')
        p.refresh_from_db()
        self.assertIn('no pudo procesar', p.error)
        self.assertEqual(p.container_id, '')

    def test_falla_al_crear(self):
        p = nueva()
        self.assertEqual(publicador.avanzar(p, Falso(falla_en='crear')), 'error')
        self.assertEqual(PublicacionInstagram.objects.get().error, 'URL no accesible')

    def test_sin_conexion_no_explota(self):
        p = nueva()
        self.assertEqual(publicador.avanzar(p), 'error')
        self.assertIn('no está conectado', PublicacionInstagram.objects.get().error)

    def test_no_republica_lo_publicado(self):
        p = nueva(estado='publicada')
        f = Falso()
        self.assertEqual(publicador.avanzar(p, f), 'publicada')
        self.assertEqual(f.llamadas, [])

    def test_pendientes_solo_toca_lo_vencido(self):
        ahora = timezone.now()
        vencida = nueva(estado='programada', programada_para=ahora - timedelta(minutes=1))
        futura = nueva(estado='programada', programada_para=ahora + timedelta(hours=2))
        borrador = nueva()
        self.assertEqual(publicador.procesar_pendientes(Falso()), 1)
        for o in (vencida, futura, borrador):
            o.refresh_from_db()
        self.assertEqual((vencida.estado, futura.estado, borrador.estado), ('publicada', 'programada', 'borrador'))


class ClienteTests(TestCase):
    def test_mensajes_de_error(self):
        txt, code = _mensaje_api(json.dumps({'error': {'message': 'x', 'code': 190}}), 400)
        self.assertEqual(code, 190)
        self.assertIn('venció', txt)
        self.assertIn('limitó', _mensaje_api(json.dumps({'error': {'code': 4}}), 400)[0])
        self.assertIn('503', _mensaje_api('<html>', 503)[0])

    def test_sin_token(self):
        with self.assertRaises(InstagramError):
            ClienteInstagram('')

    def test_arma_pedido_y_manda_el_token_por_cabecera(self):
        visto = {}

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def falso(req, timeout):
            visto['url'], visto['hdr'], visto['data'] = req.full_url, dict(req.header_items()), req.data
            return R(b'{"id": "17"}')
        c = ClienteInstagram('TOK', '123')
        with mock.patch('urllib.request.urlopen', falso):
            pub = PublicacionInstagram(tipo='IMAGE', media_url='https://x/a.jpg', caption='hi')
            self.assertEqual(c.crear_contenedor(pub), '17')
        self.assertEqual(visto['url'], 'https://graph.instagram.com/v21.0/123/media')
        self.assertNotIn('TOK', visto['url'])
        self.assertEqual(visto['hdr']['Authorization'], 'Bearer TOK')
        self.assertIn(b'image_url=', visto['data'])

    def test_reel_y_historia_usan_los_campos_correctos(self):
        enviados = []
        c = ClienteInstagram('T', '1')
        c._pedir = lambda m, r, p=None, **k: enviados.append(p) or {'id': 'x'}
        c.crear_contenedor(PublicacionInstagram(tipo='REELS', media_url='https://x/v.mp4', caption='c'))
        c.crear_contenedor(PublicacionInstagram(tipo='STORIES', media_url='https://x/s.jpg', caption='c'))
        c.crear_contenedor(PublicacionInstagram(tipo='STORIES', media_url='https://x/s.mp4', caption='c'))
        self.assertEqual(enviados[0]['media_type'], 'REELS')
        self.assertIn('video_url', enviados[0])
        self.assertIsNone(enviados[1]['caption'])
        self.assertIn('image_url', enviados[1])
        self.assertIn('video_url', enviados[2])

    def test_error_http_se_traduce(self):
        err = urllib.error.HTTPError('u', 400, 'bad', {}, io.BytesIO(b'{"error":{"message":"m","code":190}}'))
        with mock.patch('urllib.request.urlopen', side_effect=err):
            with self.assertRaises(InstagramError) as cm:
                ClienteInstagram('T', '1').perfil()
        self.assertEqual(cm.exception.codigo, 190)

    def test_sin_red(self):
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('sin dns')):
            with self.assertRaises(InstagramError):
                ClienteInstagram('T', '1').perfil()


class VistasTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('ana', password='x', is_staff=True)
        self.dev = User.objects.create_user('dev', password='x', is_staff=True)
        self.dev.groups.add(Group.objects.get_or_create(name=GRUPO_DESARROLLADORES)[0])
        self.cli = User.objects.create_user('cliente', password='x')
        c = ConfiguracionInstagram.cargar()
        c.access_token = 'SECRETO-TOKEN-123'
        c.save()
        self.patch = mock.patch('igportal.views.ClienteInstagram.desde_config', return_value=Falso())
        self.patch.start()
        self.addCleanup(self.patch.stop)
        cache.clear()

    def test_clientes_no_entran(self):
        self.client.force_login(self.cli)
        self.assertEqual(self.client.get(reverse('igportal:panel')).status_code, 302)

    def test_panel_muestra_perfil_y_publicaciones(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse('igportal:panel'))
        self.assertContains(r, '@corex')
        self.assertContains(r, 'Hola')
        self.assertContains(r, '4242')
        self.assertNotContains(r, 'SECRETO-TOKEN-123')

    def test_panel_sin_conexion(self):
        ConfiguracionInstagram.objects.update(access_token='')
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse('igportal:panel')), 'Conectá la cuenta')

    def test_panel_con_api_caida_no_da_500(self):
        with mock.patch('igportal.views.ClienteInstagram.desde_config', side_effect=InstagramError('Instagram caído')):
            self.client.force_login(self.staff)
            r = self.client.get(reverse('igportal:panel'))
        self.assertContains(r, 'Instagram caído')

    def test_crear_borrador_y_programada(self):
        self.client.force_login(self.staff)
        url = reverse('igportal:nueva')
        r = self.client.post(url, {'tipo': 'IMAGE', 'media_url': 'https://x.com/a.jpg', 'caption': 'Hola'})
        self.assertEqual(r.status_code, 302)
        cuando = (timezone.localtime() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        self.client.post(url, {'tipo': 'IMAGE', 'media_url': 'https://x.com/b.jpg', 'caption': 'x', 'programada_para': cuando})
        estados = sorted(PublicacionInstagram.objects.values_list('estado', flat=True))
        self.assertEqual(estados, ['borrador', 'programada'])
        self.assertEqual(PublicacionInstagram.objects.first().creado_por, self.staff)

    def test_validaciones_del_formulario(self):
        self.client.force_login(self.staff)
        url = reverse('igportal:nueva')
        self.assertContains(self.client.post(url, {'tipo': 'IMAGE', 'media_url': 'http://x.com/a.jpg'}), 'https://')
        self.assertContains(self.client.post(url, {'tipo': 'REELS', 'media_url': 'https://x.com/a.jpg'}), 'necesita un video')
        pasado = (timezone.localtime() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        r = self.client.post(url, {'tipo': 'IMAGE', 'media_url': 'https://x.com/a.jpg', 'programada_para': pasado})
        self.assertContains(r, 'ya pasó')
        self.assertEqual(PublicacionInstagram.objects.count(), 0)

    def test_guardar_y_publicar_ahora(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('igportal:nueva'), {'tipo': 'IMAGE', 'media_url': 'https://x.com/a.jpg', 'accion': 'publicar'})
        self.assertEqual(PublicacionInstagram.objects.get().estado, 'publicada')

    def test_publicar_cancelar_eliminar(self):
        self.client.force_login(self.staff)
        p = nueva(estado='programada', programada_para=timezone.now() + timedelta(hours=1))
        self.client.post(reverse('igportal:cancelar', args=[p.pk]))
        p.refresh_from_db()
        self.assertEqual((p.estado, p.programada_para), ('borrador', None))
        self.client.post(reverse('igportal:publicar', args=[p.pk]))
        p.refresh_from_db()
        self.assertEqual(p.estado, 'publicada')
        self.assertEqual(self.client.get(reverse('igportal:editar', args=[p.pk])).status_code, 302)   # ya no se edita
        self.client.post(reverse('igportal:eliminar', args=[p.pk]))
        self.assertEqual(PublicacionInstagram.objects.count(), 0)

    def test_publicar_exige_post(self):
        self.client.force_login(self.staff)
        p = nueva()
        self.assertEqual(self.client.get(reverse('igportal:publicar', args=[p.pk])).status_code, 405)

    def test_comentarios_responder_y_ocultar(self):
        falso = Falso()
        with mock.patch('igportal.views.ClienteInstagram.desde_config', return_value=falso):
            self.client.force_login(self.staff)
            url = reverse('igportal:comentarios', args=['m1'])
            self.assertContains(self.client.get(url), 'Precio?')
            self.client.post(url, {'accion': 'responder', 'comment_id': 'c1', 'texto': 'Sí, escribinos'})
            self.client.post(url, {'accion': 'ocultar', 'comment_id': 'c1'})
        self.assertEqual(falso.llamadas, [('responder', 'c1', 'Sí, escribinos'), ('ocultar', 'c1', True)])

    def test_conexion_solo_devs_y_nunca_muestra_el_token(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('igportal:conexion')).status_code, 302)
        self.client.force_login(self.dev)
        r = self.client.get(reverse('igportal:conexion'))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'SECRETO-TOKEN-123')

    def test_guardar_token_define_vencimiento_y_vacio_conserva(self):
        self.client.force_login(self.dev)
        url = reverse('igportal:conexion')
        base = {'accion': 'guardar', 'ig_user_id': '', 'api_host': 'https://graph.instagram.com', 'api_version': 'v21.0'}
        self.client.post(url, {**base, 'access_token': 'NUEVO', 'expira_en_dias': 60})
        c = ConfiguracionInstagram.cargar()
        self.assertEqual(c.access_token, 'NUEVO')
        self.assertTrue(59 <= c.dias_para_vencer <= 60)
        self.client.post(url, {**base, 'access_token': ''})
        self.assertEqual(ConfiguracionInstagram.cargar().access_token, 'NUEVO')

    def test_host_no_permitido(self):
        self.client.force_login(self.dev)
        r = self.client.post(reverse('igportal:conexion'),
                             {'accion': 'guardar', 'api_host': 'https://malo.example', 'api_version': 'v21.0'})
        self.assertContains(r, 'graph.instagram.com')

    def test_probar_y_desconectar(self):
        self.client.force_login(self.dev)
        url = reverse('igportal:conexion')
        self.client.post(url, {'accion': 'probar'})
        self.assertEqual(ConfiguracionInstagram.cargar().username, 'corex')
        self.client.post(url, {'accion': 'desconectar'})
        c = ConfiguracionInstagram.cargar()
        self.assertEqual((c.access_token, c.username), ('', ''))

    @override_settings(INSTAGRAM_ACCESS_TOKEN='DESDE-ENTORNO')
    def test_token_de_entorno_tiene_prioridad(self):
        self.assertEqual(ConfiguracionInstagram.cargar().token, 'DESDE-ENTORNO')
