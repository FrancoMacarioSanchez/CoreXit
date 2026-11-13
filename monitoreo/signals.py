import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from . import actividad

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def al_ingresar(sender, request, user, **kwargs):
    if user.is_staff:
        try:
            actividad.registrar(user, 'login', request, 'Inició sesión')
        except Exception:
            logger.exception('No se pudo registrar el login')


@receiver(user_logged_out)
def al_salir(sender, request, user, **kwargs):
    if user is not None and user.is_staff:
        try:
            actividad.registrar(user, 'logout', request, 'Cerró sesión')
        except Exception:
            logger.exception('No se pudo registrar el logout')


@receiver(user_login_failed)
def al_fallar(sender, credentials, request=None, **kwargs):
    # Nunca se guarda la contraseña: solo el nombre de usuario que se intentó.
    try:
        actividad.registrar(None, 'login_fallido', request, 'Intento de ingreso fallido',
                            username=str(credentials.get('username', ''))[:150])
    except Exception:
        logger.exception('No se pudo registrar el intento fallido')
