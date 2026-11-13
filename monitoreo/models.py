from django.conf import settings
from django.db import models
from django.utils import timezone


class RegistroActividad(models.Model):
    """Qué hizo cada usuario del equipo (staff) dentro del Hub."""
    TIPOS = [
        ('login', 'Inicio de sesión'),
        ('logout', 'Cierre de sesión'),
        ('login_fallido', 'Intento fallido'),
        ('accion', 'Acción'),
        ('vista', 'Visita'),
    ]
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='actividad')
    # Se guarda el nombre aparte: el registro sigue siendo legible si se borra el usuario.
    username = models.CharField(max_length=150, db_index=True)
    tipo = models.CharField(max_length=14, choices=TIPOS)
    metodo = models.CharField(max_length=8, blank=True)
    ruta = models.CharField(max_length=300, blank=True)
    vista = models.CharField(max_length=120, blank=True)
    descripcion = models.CharField(max_length=255, blank=True)
    estado_http = models.PositiveSmallIntegerField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    creado = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-creado', '-id']
        verbose_name = 'registro de actividad'
        verbose_name_plural = 'registros de actividad'
        indexes = [
            models.Index(fields=['usuario', '-creado']),
            models.Index(fields=['tipo', '-creado']),
        ]

    def __str__(self):
        return f'{self.username} · {self.get_tipo_display()} · {self.descripcion or self.ruta}'


class MuestraServidor(models.Model):
    """Foto de los recursos del servidor (una por minuto como máximo)."""
    creado = models.DateTimeField(default=timezone.now, db_index=True)
    cpu = models.FloatField(null=True, blank=True)
    memoria = models.FloatField(null=True, blank=True)
    memoria_usada_mb = models.FloatField(null=True, blank=True)
    disco = models.FloatField(null=True, blank=True)
    carga = models.FloatField(null=True, blank=True)
    proceso_mb = models.FloatField(null=True, blank=True)
    db_ms = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'muestra del servidor'
        verbose_name_plural = 'muestras del servidor'

    def __str__(self):
        return f'{self.creado:%d/%m %H:%M} CPU {self.cpu} RAM {self.memoria}'


class MuestraRequests(models.Model):
    """Tráfico del Hub agregado por minuto."""
    minuto = models.DateTimeField(unique=True)
    total = models.PositiveIntegerField(default=0)
    ok = models.PositiveIntegerField(default=0)
    c4xx = models.PositiveIntegerField(default=0)
    c5xx = models.PositiveIntegerField(default=0)
    suma_ms = models.BigIntegerField(default=0)
    max_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-minuto']
        verbose_name = 'tráfico por minuto'
        verbose_name_plural = 'tráfico por minuto'
