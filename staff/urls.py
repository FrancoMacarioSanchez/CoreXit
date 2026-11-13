from django.urls import path

from . import views

app_name = 'staff'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('clientes/', views.clientes, name='clientes'),
    path('clientes/<int:cliente_id>/', views.cliente_detalle, name='cliente'),
    path('facturacion/', views.facturacion, name='facturacion'),
    path('facturacion/<int:factura_id>/pdf/', views.factura_pdf, name='factura_pdf'),
    path('soporte/', views.soporte, name='soporte'),
    path('tickets/<int:ticket_id>/', views.ticket, name='ticket'),
    path('tareas/', views.tareas, name='tareas'),
]
