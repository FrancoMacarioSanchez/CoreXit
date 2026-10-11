import re
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Contratacion, Ticket

@receiver(pre_save, sender=Contratacion)
def capturar_estado_anterior(sender, instance, **kwargs):
    if instance.pk:
        instance._estado_anterior = Contratacion.objects.get(pk=instance.pk).estado
    else:
        instance._estado_anterior = None

@receiver(post_save, sender=Contratacion)
def generar_ticket_aprovisionamiento(sender, instance, created, **kwargs):
    estado_anterior = getattr(instance, '_estado_anterior', None)
    
    # Cuando el pago se aprueba y pasa a 'activo' por primera vez
    if instance.estado == 'activo' and estado_anterior != 'activo':
        
        # Generamos la sugerencia del subdominio para facilitarte el trabajo
        empresa_nombre = instance.cliente.empresa or instance.cliente.nombre
        nombre_limpio = re.sub(r'[^a-z0-9]', '', empresa_nombre.lower())
        subdominio_sugerido = f"{instance.plan.servicio.prefijo.lower()}{nombre_limpio}"
        
        # Creamos el Ticket interno automáticamente
        cuerpo_ticket = (
            f"Se ha confirmado una nueva suscripción y requiere aprovisionamiento manual.\n\n"
            f"DATOS DEL CLIENTE\n"
            f"- Empresa: {empresa_nombre}\n"
            f"- CUIT: {instance.cliente.cuit_cuil or 'No registrado'}\n"
            f"- Email Admin: {instance.cliente.user.email}\n\n"
            f"DATOS DEL SERVICIO\n"
            f"- Sistema: {instance.plan.servicio.nombre}\n"
            f"- Plan: {instance.plan.nombre}\n\n"
            f"ACCIÓN REQUERIDA\n"
            f"1. Crear esquema en PostgreSQL: CREATE SCHEMA {subdominio_sugerido};\n"
            f"2. Ejecutar migraciones en ese esquema.\n"
            f"3. Crear el superusuario.\n"
            f"4. Actualizar la 'URL del sistema' en la Contratación a: https://{subdominio_sugerido}.corexit.tech\n"
            f"5. Cerrar este ticket para notificar al cliente."
        )

        Ticket.objects.create(
            cliente=instance.cliente,
            # Corrección del error de sintaxis en el salto de línea:
            asunto=f"Aprovisionamiento manual: {instance.plan.servicio.prefijo.upper()} - {empresa_nombre}",
            descripcion=cuerpo_ticket,
            estado='abierto',
            prioridad='urgente' # Prioridad máxima para que lo veas apenas entres al panel
        )