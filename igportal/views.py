"""Portal de Instagram: panel, publicaciones (con programación), comentarios y conexión."""
import time
from datetime import timedelta

from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from dashboard.permisos import dev_required, staff_required
from staff.views import _ctx as _ctx_staff

from . import publicador
from .client import ClienteInstagram, InstagramError
from .forms import ComentarioForm, ConexionForm, PublicacionForm
from .models import ConfiguracionInstagram, PublicacionInstagram

CACHE_SEG = 300


def _ctx(**extra):
    return _ctx_staff('instagram', **extra)


def _fecha(valor):
    # Instagram manda "2026-11-13T18:00:00+0000"; Django necesita "+00:00".
    if not valor:
        return None
    if len(valor) > 5 and valor[-5] in '+-' and valor[-3] != ':':
        valor = valor[:-2] + ':' + valor[-2:]
    return parse_datetime(valor)


def _cargar_panel(cli):
    d = {'perfil': None, 'medios': [], 'metricas': {}, 'alcance': [], 'avisos': []}
    try:
        d['perfil'] = cli.perfil()
    except InstagramError as e:
        d['avisos'].append(str(e))
        return d
    try:
        d['medios'] = cli.medios(12)
        for m in d['medios']:
            m['fecha'] = _fecha(m.get('timestamp'))
            m['imagen'] = m.get('thumbnail_url') or m.get('media_url')
    except InstagramError as e:
        d['avisos'].append(f'Publicaciones: {e}')
    ahora = time.time()
    desde = ahora - 7 * 86400
    for clave, nombre in (('profile_views', 'Visitas al perfil'), ('accounts_engaged', 'Cuentas que interactuaron'),
                          ('total_interactions', 'Interacciones')):
        try:
            d['metricas'][nombre] = cli.metrica_total(clave, desde, ahora)
        except InstagramError as e:
            d['avisos'].append(f'{nombre}: {e}')
    try:
        d['alcance'] = [{'dia': (_fecha(v.get('end_time')) or timezone.now()).strftime('%d/%m'), 'valor': v.get('value', 0)}
                        for v in cli.alcance_diario(desde, ahora)]
    except InstagramError as e:
        d['avisos'].append(f'Alcance: {e}')
    return d


@staff_required
def panel(request):
    config = ConfiguracionInstagram.cargar()
    datos = None
    if config.conectado:
        clave = f'ig_panel_{int(config.actualizado.timestamp())}'
        if request.GET.get('refrescar'):
            cache.delete(clave)
        datos = cache.get(clave)
        if datos is None:
            try:
                datos = _cargar_panel(ClienteInstagram.desde_config(config))
            except InstagramError as e:
                datos = {'perfil': None, 'medios': [], 'metricas': {}, 'alcance': [], 'avisos': [str(e)]}
            if datos['perfil']:
                cache.set(clave, datos, CACHE_SEG)
    return render(request, 'igportal/panel.html', _ctx(config=config, datos=datos, puede_conectar=request.user.is_superuser or _es_dev(request.user)))


def _es_dev(user):
    from dashboard.permisos import es_dev
    return es_dev(user)


@staff_required
def publicaciones(request):
    estado = request.GET.get('estado', '')
    qs = PublicacionInstagram.objects.select_related('creado_por')
    if estado in dict(PublicacionInstagram.ESTADOS):
        qs = qs.filter(estado=estado)
    conteo = {e: PublicacionInstagram.objects.filter(estado=e).count() for e, _ in PublicacionInstagram.ESTADOS}
    return render(request, 'igportal/publicaciones.html', _ctx(
        publicaciones=qs[:100], estado=estado, estados=PublicacionInstagram.ESTADOS, conteo=conteo,
        config=ConfiguracionInstagram.cargar()))


@staff_required
def publicacion_form(request, pub_id=None):
    pub = get_object_or_404(PublicacionInstagram, pk=pub_id) if pub_id else None
    if pub and not pub.editable:
        messages.warning(request, 'Esa publicación ya no se puede editar.')
        return redirect('igportal:publicaciones')
    form = PublicacionForm(request.POST or None, instance=pub)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        if not obj.pk:
            obj.creado_por = request.user
        obj.estado = 'programada' if obj.programada_para else 'borrador'
        obj.error, obj.container_id = '', ''
        obj.save()
        if request.POST.get('accion') == 'publicar':
            return _publicar_y_avisar(request, obj)
        messages.success(request, 'Programada para %s.' % timezone.localtime(obj.programada_para).strftime('%d/%m/%Y %H:%M')
                         if obj.programada_para else 'Guardada como borrador.')
        return redirect('igportal:publicaciones')
    return render(request, 'igportal/publicacion_form.html', _ctx(form=form, pub=pub, config=ConfiguracionInstagram.cargar()))


def _publicar_y_avisar(request, pub, esperar=True):
    estado = publicador.avanzar(pub, esperar=esperar)
    if estado == 'publicada':
        messages.success(request, '¡Publicada en Instagram!')
    elif estado == 'procesando':
        messages.info(request, 'Instagram sigue procesando el archivo (los videos tardan). Tocá «Verificar» en un momento.')
    else:
        messages.error(request, f'No se pudo publicar: {pub.error}')
    return redirect('igportal:publicaciones')


@staff_required
@require_POST
def publicar(request, pub_id):
    pub = get_object_or_404(PublicacionInstagram, pk=pub_id)
    if pub.estado == 'publicada':
        messages.info(request, 'Esa publicación ya está publicada.')
        return redirect('igportal:publicaciones')
    return _publicar_y_avisar(request, pub)


@staff_required
@require_POST
def verificar(request, pub_id):
    pub = get_object_or_404(PublicacionInstagram, pk=pub_id)
    return _publicar_y_avisar(request, pub, esperar=False)


@staff_required
@require_POST
def cancelar(request, pub_id):
    pub = get_object_or_404(PublicacionInstagram, pk=pub_id, estado='programada')
    pub.estado, pub.programada_para = 'borrador', None
    pub.save(update_fields=['estado', 'programada_para'])
    messages.success(request, 'Volvió a borrador: no se publicará sola.')
    return redirect('igportal:publicaciones')


@staff_required
@require_POST
def eliminar(request, pub_id):
    pub = get_object_or_404(PublicacionInstagram, pk=pub_id)
    if pub.estado == 'procesando':
        messages.warning(request, 'Está procesándose en Instagram: esperá a que termine.')
    else:
        aviso = ' (el post sigue en Instagram: se borra desde la app)' if pub.estado == 'publicada' else ''
        pub.delete()
        messages.success(request, 'Eliminada del portal' + aviso + '.')
    return redirect('igportal:publicaciones')


@staff_required
def comentarios(request, media_id):
    config = ConfiguracionInstagram.cargar()
    if not config.conectado:
        messages.warning(request, 'Conectá la cuenta de Instagram primero.')
        return redirect('igportal:panel')
    cli = ClienteInstagram.desde_config(config)
    if request.method == 'POST':
        accion = request.POST.get('accion')
        cid = request.POST.get('comment_id', '')
        try:
            if accion == 'responder':
                form = ComentarioForm(request.POST)
                if form.is_valid():
                    cli.responder(form.cleaned_data['comment_id'], form.cleaned_data['texto'])
                    messages.success(request, 'Respuesta enviada.')
                else:
                    messages.error(request, 'Escribí la respuesta antes de enviar.')
            elif accion in ('ocultar', 'mostrar') and cid:
                cli.ocultar(cid, accion == 'ocultar')
                messages.success(request, 'Comentario oculto.' if accion == 'ocultar' else 'Comentario visible otra vez.')
        except InstagramError as e:
            messages.error(request, str(e))
        return redirect('igportal:comentarios', media_id=media_id)
    lista, error = [], ''
    try:
        lista = cli.comentarios(media_id)
        for c in lista:
            c['fecha'] = _fecha(c.get('timestamp'))
            c['respuestas'] = (c.get('replies') or {}).get('data', [])
    except InstagramError as e:
        error = str(e)
    return render(request, 'igportal/comentarios.html', _ctx(comentarios=lista, error=error, media_id=media_id))


@dev_required
def conexion(request):
    config = ConfiguracionInstagram.cargar()
    form = ConexionForm(instance=config)
    if request.method == 'POST':
        accion = request.POST.get('accion', 'guardar')
        if accion == 'guardar':
            form = ConexionForm(request.POST, instance=config)
            if form.is_valid():
                form.save()
                cache.clear()
                messages.success(request, 'Datos guardados. Probá la conexión para confirmar que funciona.')
                return redirect('igportal:conexion')
        elif accion == 'probar':
            try:
                cli = ClienteInstagram.desde_config(config)
                p = cli.perfil()
                config.username = p.get('username', '')
                config.ig_user_id = str(p.get('user_id') or config.ig_user_id)
                config.save()
                msg = f'Conectado como @{config.username}.'
                try:
                    usado, total = cli.limite_publicacion()
                    if usado is not None:
                        msg += f' Publicaciones de las últimas 24 h: {usado} de {total}.'
                except InstagramError:
                    pass
                messages.success(request, msg)
            except InstagramError as e:
                messages.error(request, str(e))
            return redirect('igportal:conexion')
        elif accion == 'renovar':
            try:
                nuevo, seg = ClienteInstagram.desde_config(config).renovar_token()
                config.access_token = nuevo
                config.token_expira = timezone.now() + timedelta(seconds=seg or 60 * 86400)
                config.save()
                cache.clear()
                messages.success(request, 'Token renovado por otros 60 días.')
            except InstagramError as e:
                messages.error(request, str(e))
            return redirect('igportal:conexion')
        elif accion == 'desconectar':
            config.access_token, config.token_expira, config.username = '', None, ''
            config.save()
            cache.clear()
            messages.success(request, 'Cuenta desconectada y token borrado.')
            return redirect('igportal:conexion')
    return render(request, 'igportal/conexion.html', _ctx(form=form, config=config))
