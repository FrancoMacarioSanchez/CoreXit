from django.db import models


class EstadoTenant(models.Model):
    """
    Estado que define CoreX para cada tenant (vive en el schema public).
    Lo usa TenantSuspendidoMiddleware para bloquear el acceso a tenants suspendidos.
    """
    schema_name = models.CharField(max_length=63, unique=True)
    estado = models.CharField(max_length=20, default='activo')
    motivo = models.CharField(max_length=255, blank=True)
    plan = models.JSONField(default=dict, blank=True)
    limites = models.JSONField(default=dict, blank=True)
    referencia_hub = models.CharField(max_length=32, blank=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.schema_name}: {self.estado}'
