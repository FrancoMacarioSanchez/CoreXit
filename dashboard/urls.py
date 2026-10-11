from django.urls import path
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import (
    checkout_view,
    portal_cliente_view,
    crear_ticket_view,
    portal_empleado_view,
    actualizar_estado_ticket,
    redirect_post_login,
    detalle_cliente_view,
    lista_clientes_staff_view,
    registro_plan_view
    
)

urlpatterns = [
    path('registro/<int:plan_id>/<str:frecuencia>/', registro_plan_view, name='registro_plan'),
    path('registro/', registro_plan_view, name='registro'),
    path('portal/', portal_cliente_view, name='portal_cliente'),
    path('portal/ticket/nuevo/', crear_ticket_view, name='crear_ticket'),
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
    
    # Flujo de Checkout y Activación
    path('checkout/<int:contratacion_id>/', checkout_view, name='checkout'),
    # --- AUTENTICACIÓN Y REGISTRO ---
    path('login/', views.auth_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('redirect/', views.redirect_post_login, name='redirect_post_login'),
    
    # --- REGISTRO DESDE LA LANDING (Usuario Nuevo) ---
    path('registro/<int:plan_id>/<str:frecuencia>/', views.registro_plan_view, name='registro_plan'),
    
    # --- PORTAL DEL CLIENTE ---
    path('portal/', views.portal_cliente_view, name='portal_cliente'),
    path('portal/solicitar-servicio/', views.solicitar_servicio_view, name='solicitar_servicio'),
    path('portal/crear-ticket/', views.crear_ticket_view, name='crear_ticket'),
    
    # --- PAGOS / CHECKOUT ---
    path('checkout/<int:contratacion_id>/', views.checkout_view, name='checkout'),

    # --- PORTAL DEL EMPLEADO / STAFF ---
    path('staff/', views.portal_empleado_view, name='portal_empleado'),
    path('staff/clientes/', views.lista_clientes_staff_view, name='lista_clientes'),
    path('staff/clientes/<int:cliente_id>/', views.detalle_cliente_view, name='detalle_cliente'),
    path('staff/ticket/<int:ticket_id>/actualizar/', views.actualizar_estado_ticket, name='actualizar_estado_ticket'),
]
