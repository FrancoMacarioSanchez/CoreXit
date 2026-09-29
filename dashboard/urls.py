from django.urls import path
from .views import (
    registro_view,
    portal_cliente_view,
    crear_ticket_view,
    solicitar_servicio_view,
    portal_empleado_view,
    actualizar_estado_ticket,
    redirect_post_login,
    detalle_cliente_view,
    lista_clientes_staff_view
)

urlpatterns = [
    path('registro/', registro_view, name='registro'),
    path('portal/', portal_cliente_view, name='portal_cliente'),
    path('portal/ticket/nuevo/', crear_ticket_view, name='crear_ticket'),
    path(
        'portal/servicio/solicitar/',
        solicitar_servicio_view,
        name='solicitar_servicio',
    ),
    path('empleado/', portal_empleado_view, name='portal_empleado'),
    path(
        'empleado/cliente/<int:cliente_id>/',
        detalle_cliente_view,
        name='detalle_cliente',
    ),
    path(
        'empleado/ticket/<int:ticket_id>/actualizar/',
        actualizar_estado_ticket,
        name='actualizar_estado_ticket',
    ),
    path(
        'empleado/clientes/',
        lista_clientes_staff_view,
        name='lista_clientes_staff',
    ),
    path('redirect/', redirect_post_login, name='redirect_post_login'),
]