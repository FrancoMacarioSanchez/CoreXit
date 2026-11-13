from .permisos import es_cliente, es_dev, es_staff


def roles(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'rol_staff': False, 'rol_dev': False, 'rol_cliente': False}
    return {
        'rol_staff': es_staff(user),
        'rol_dev': es_dev(user),
        'rol_cliente': es_cliente(user),
    }
