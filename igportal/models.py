import os
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class ConfiguracionInstagram(models.Model):
    """Conexión con la cuenta de Instagram de CoreX (una sola fila)."""
    ig_user_id = models.CharField('ID de usuario de Instagram', max_length=40, blank=True)
    username = models.CharField(max_length=100, blank=True)
    access_token = models.TextField(blank=True, help_text='Token de acceso de larga duración. Nunca se muestra en pantalla.')
    token_expira = models.DateTimeField(null=True, blank=True)
    api_host = models.CharField(max_length=100, default='https://graph.instagram.com')
    api_version = models.CharField(max_length=10, default='v21.0')
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'configuración de Instagram'
        verbose_name_plural = 'configuración de Instagram'

    def __str__(self):
        return f'Instagram @{self.username}' if self.username else 'Instagram (sin conectar)'

    @classmethod
    def cargar(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def token(self):
        """Prioriza la variable de entorno (más seguro en producción)."""
        return os.environ.get('INSTAGRAM_ACCESS_TOKEN') or getattr(settings, 'INSTAGRAM_ACCESS_TOKEN', '') or self.access_token

    @property
    def conectado(self):
        return bool(self.token)

    @property
    def dias_para_vencer(self):
        if not self.token_expira:
            return None
        return (self.token_expira - timezone.now()).days

    @property
    def por_vencer(self):
        d = self.dias_para_vencer
        return d is not None and d <= 7


class PublicacionInstagram(models.Model):
    TIPOS = [('IMAGE', 'Imagen'), ('REELS', 'Reel'), ('STORIES', 'Historia')]
    ESTADOS = [
        ('borrador', 'Borrador'),
        ('programada', 'Programada'),
        ('procesando', 'Procesando en Instagram'),
        ('publicada', 'Publicada'),
        ('error', 'Con error'),
    ]
    tipo = models.CharField(max_length=8, choices=TIPOS, default='IMAGE')
    media_url = models.URLField('URL pública del archivo', max_length=500)
    caption = models.TextField('Texto', blank=True, max_length=2200)
    estado = models.CharField(max_length=12, choices=ESTADOS, default='borrador', db_index=True)
    programada_para = models.DateTimeField(null=True, blank=True, db_index=True)
    container_id = models.CharField(max_length=60, blank=True)
    ig_media_id = models.CharField(max_length=60, blank=True)
    permalink = models.URLField(blank=True)
    error = models.TextField(blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='publicaciones_instagram')
    creado = models.DateTimeField(auto_now_add=True)
    publicada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'publicación de Instagram'
        verbose_name_plural = 'publicaciones de Instagram'

    def __str__(self):
        return f'{self.get_tipo_display()} · {self.get_estado_display()} · {self.caption[:40]}'

    @property
    def editable(self):
        return self.estado in ('borrador', 'programada', 'error')

    @property
    def es_video(self):
        ruta = self.media_url.split('?')[0].lower()
        return self.tipo == 'REELS' or ruta.endswith(('.mp4', '.mov', '.m4v'))

    @property
    def vencida(self):
        return self.estado == 'programada' and self.programada_para and self.programada_para <= timezone.now() - timedelta(hours=1)
