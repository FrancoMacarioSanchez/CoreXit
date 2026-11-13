"""
Roles del Hub:

- Cliente: usuario sin is_staff con ClienteProfile -> /portal/
- Staff: usuario con is_staff -> /staff/
- Desarrollador: superusuario o miembro del grupo "Desarrolladores" -> /dev/
  (un desarrollador normalmente también es staff y puede ver ambas áreas)
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

GRUPO_DESARROLLADORES = 'Desarrolladores'


def es_staff(user):
    return user.is_authenticated and user.is_active and user.is_staff


def es_dev(user):
    if not (user.is_authenticated and user.is_active):
        return False
    if user.is_superuser:
        return True
    cache = getattr(user, '_corex_es_dev', None)
    if cache is None:
        cache = user.groups.filter(name=GRUPO_DESARROLLADORES).exists()
        user._corex_es_dev = cache
    return cache


def es_cliente(user):
    return user.is_authenticated and user.is_active and not user.is_staff


def inicio_para(user):
    """Nombre de URL de la 'home' que le corresponde a cada usuario."""
    if es_staff(user):
        return 'staff:inicio'
    if es_dev(user):
        return 'devpanel:inicio'
    return 'portal:inicio'


def _requiere(chequeo, mensaje):
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not chequeo(request.user):
                messages.warning(request, mensaje)
                return redirect(inicio_para(request.user))
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


cliente_required = _requiere(es_cliente, 'Esa sección es solo para clientes.')
staff_required = _requiere(es_staff, 'Esa sección es solo para el equipo de CoreX.')
dev_required = _requiere(es_dev, 'El panel de desarrolladores requiere permisos de desarrollador.')
