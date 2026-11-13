"""Lleva una publicación de Instagram de 'programada' a 'publicada' (idempotente: se puede llamar muchas veces)."""
import time

from django.utils import timezone

from .client import ClienteInstagram, InstagramError
from .models import ConfiguracionInstagram, PublicacionInstagram

ESPERAS = 4          # veces que se consulta el estado del archivo en una misma llamada
ESPERA_SEG = 2


def avanzar(pub, cliente=None, esperar=True):
    """
    Crea el contenedor si falta, consulta su estado y publica cuando Instagram terminó de procesarlo.
    Devuelve el estado final de la publicación.
    """
    if pub.estado == 'publicada':
        return pub.estado
    try:
        cli = cliente or ClienteInstagram.desde_config(ConfiguracionInstagram.cargar())
        pub.intentos += 1
        if not pub.container_id:
            pub.container_id = cli.crear_contenedor(pub)
            pub.estado, pub.error = 'procesando', ''
            pub.save(update_fields=['container_id', 'estado', 'error', 'intentos'])
        for i in range(ESPERAS if esperar else 1):
            codigo, detalle = cli.estado_contenedor(pub.container_id)
            if codigo == 'FINISHED':
                media_id = cli.publicar(pub.container_id)
                pub.ig_media_id, pub.estado, pub.error = media_id, 'publicada', ''
                pub.publicada_en = timezone.now()
                try:
                    pub.permalink = cli.permalink(media_id)
                except InstagramError:
                    pass
                pub.save()
                return pub.estado
            if codigo in ('ERROR', 'EXPIRED'):
                raise InstagramError(f'Instagram no pudo procesar el archivo ({detalle or codigo}). '
                                     'Revisá que la URL sea pública y el formato sea válido.')
            if esperar and i < ESPERAS - 1:
                time.sleep(ESPERA_SEG)
        pub.save(update_fields=['intentos'])
        return pub.estado
    except InstagramError as e:
        pub.estado, pub.error = 'error', str(e)
        pub.container_id = ''      # al reintentar se crea un contenedor nuevo
        pub.save(update_fields=['estado', 'error', 'container_id', 'intentos'])
        return pub.estado


def procesar_pendientes(cliente=None):
    """Publica lo programado que ya venció y termina lo que quedó procesando. Devuelve cuántas se tocaron."""
    ahora = timezone.now()
    pendientes = list(PublicacionInstagram.objects.filter(estado='procesando')) + list(
        PublicacionInstagram.objects.filter(estado='programada', programada_para__lte=ahora))
    for pub in pendientes:
        avanzar(pub, cliente, esperar=False)
    return len(pendientes)
