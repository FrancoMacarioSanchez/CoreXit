from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Contratacion


@receiver(pre_save, sender=Contratacion)
def capturar_estado_anterior(sender, instance, **kwargs):
    if instance.pk:
        instance._estado_anterior = (
            Contratacion.objects.filter(pk=instance.pk).values_list('estado', flat=True).first()
        )
    else:
        instance._estado_anterior = None


@receiver(post_save, sender=Contratacion)
def sincronizar_tenant(sender, instance, created, **kwargs):
    """
    Activo  -> se crea/aprovisiona (o reactiva) el tenant en el SaaS.
    Suspendido/Histórico desde Activo -> se suspende el tenant.
    """
    from .servicios import aprovisionamiento

    anterior = getattr(instance, '_estado_anterior', None)
    if instance.estado == anterior:
        return
    if instance.estado == 'activo':
        aprovisionamiento.al_activar(instance)
    elif anterior == 'activo' and instance.estado in ('suspendido', 'historico'):
        aprovisionamiento.al_suspender(instance)
