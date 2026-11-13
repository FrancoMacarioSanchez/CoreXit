"""
Cliente mínimo de la API de Instagram (Instagram API con inicio de sesión de Instagram).

Sin dependencias externas: usa urllib. Toda falla se convierte en InstagramError con un
mensaje que se puede mostrar tal cual en pantalla.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 25


class InstagramError(Exception):
    def __init__(self, mensaje, codigo=None):
        super().__init__(mensaje)
        self.codigo = codigo


def _mensaje_api(cuerpo, estado):
    try:
        err = json.loads(cuerpo).get('error', {})
    except (ValueError, AttributeError):
        err = {}
    codigo = err.get('code')
    texto = err.get('error_user_msg') or err.get('message') or f'Respuesta {estado} de Instagram'
    if codigo == 190:
        texto = 'El token de Instagram venció o no es válido. Volvé a conectar la cuenta.'
    elif codigo in (4, 17, 32, 613):
        texto = 'Instagram limitó los pedidos por ahora. Probá de nuevo en unos minutos.'
    elif codigo in (10, 200):
        texto = f'Falta un permiso en la app de Meta: {texto}'
    return texto, codigo


class ClienteInstagram:
    def __init__(self, token, ig_user_id='', host='https://graph.instagram.com', version='v21.0'):
        if not token:
            raise InstagramError('Instagram no está conectado todavía.')
        self.token, self.ig_user_id = token, ig_user_id or 'me'
        self.host, self.version = host.rstrip('/'), version.strip('/')

    @classmethod
    def desde_config(cls, config):
        return cls(config.token, config.ig_user_id, config.api_host, config.api_version)

    # -------------------------------------------------------------- bajo nivel
    def _pedir(self, metodo, ruta, params=None, versionado=True):
        url = f'{self.host}/' + (f'{self.version}/' if versionado else '') + ruta.lstrip('/')
        params = {k: v for k, v in (params or {}).items() if v not in (None, '')}
        datos = None
        if metodo == 'GET':
            if params:
                url += '?' + urllib.parse.urlencode(params)
        else:
            datos = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=datos, method=metodo, headers={
            'Authorization': f'Bearer {self.token}', 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                cuerpo = r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            texto, codigo = _mensaje_api(e.read().decode('utf-8', 'replace'), e.code)
            raise InstagramError(texto, codigo) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise InstagramError(f'No se pudo conectar con Instagram: {getattr(e, "reason", e)}') from None
        try:
            return json.loads(cuerpo) if cuerpo else {}
        except ValueError:
            raise InstagramError('Instagram devolvió una respuesta ilegible.') from None

    # -------------------------------------------------------------- lectura
    def perfil(self):
        return self._pedir('GET', 'me', {
            'fields': 'user_id,username,name,account_type,profile_picture_url,followers_count,follows_count,media_count'})

    def medios(self, limite=12):
        d = self._pedir('GET', f'{self.ig_user_id}/media', {
            'fields': 'id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count',
            'limit': limite})
        return d.get('data', [])

    def metrica_total(self, metrica, desde, hasta):
        d = self._pedir('GET', f'{self.ig_user_id}/insights', {
            'metric': metrica, 'period': 'day', 'metric_type': 'total_value', 'since': int(desde), 'until': int(hasta)})
        return (d.get('data') or [{}])[0].get('total_value', {}).get('value')

    def alcance_diario(self, desde, hasta):
        d = self._pedir('GET', f'{self.ig_user_id}/insights', {
            'metric': 'reach', 'period': 'day', 'since': int(desde), 'until': int(hasta)})
        return (d.get('data') or [{}])[0].get('values', [])

    def comentarios(self, media_id, limite=50):
        d = self._pedir('GET', f'{media_id}/comments', {
            'fields': 'id,text,username,timestamp,like_count,hidden,replies{id,text,username,timestamp}', 'limit': limite})
        return d.get('data', [])

    def limite_publicacion(self):
        d = self._pedir('GET', f'{self.ig_user_id}/content_publishing_limit', {'fields': 'quota_usage,config'})
        item = (d.get('data') or [{}])[0]
        return item.get('quota_usage'), (item.get('config') or {}).get('quota_total')

    # -------------------------------------------------------------- escritura
    def responder(self, comment_id, texto):
        return self._pedir('POST', f'{comment_id}/replies', {'message': texto})

    def ocultar(self, comment_id, ocultar=True):
        return self._pedir('POST', f'{comment_id}', {'hide': 'true' if ocultar else 'false'})

    def crear_contenedor(self, pub):
        params = {'caption': pub.caption if pub.tipo != 'STORIES' else None}
        if pub.tipo == 'IMAGE':
            params['image_url'] = pub.media_url
        elif pub.tipo == 'REELS':
            params.update(media_type='REELS', video_url=pub.media_url, share_to_feed='true')
        else:
            params['media_type'] = 'STORIES'
            params['video_url' if pub.es_video else 'image_url'] = pub.media_url
        return self._pedir('POST', f'{self.ig_user_id}/media', params)['id']

    def estado_contenedor(self, container_id):
        d = self._pedir('GET', container_id, {'fields': 'status_code,status'})
        return d.get('status_code', ''), d.get('status', '')

    def publicar(self, container_id):
        return self._pedir('POST', f'{self.ig_user_id}/media_publish', {'creation_id': container_id})['id']

    def permalink(self, media_id):
        return self._pedir('GET', media_id, {'fields': 'permalink'}).get('permalink', '')

    def renovar_token(self):
        """Devuelve (nuevo_token, segundos_de_vida). El token debe tener más de 24 h y no estar vencido."""
        d = self._pedir('GET', 'refresh_access_token', {'grant_type': 'ig_refresh_token', 'access_token': self.token},
                        versionado=False)
        return d['access_token'], int(d.get('expires_in', 0))
