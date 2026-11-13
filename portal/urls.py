from django.urls import path

from . import views

app_name = 'portal'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('servicios/', views.servicios, name='servicios'),
    path('servicios/<int:contratacion_id>/', views.servicio_detalle, name='servicio'),
    path('servicios/<int:contratacion_id>/cancelar/', views.cancelar_solicitud, name='cancelar_solicitud'),
    path('contratar/', views.contratar, name='contratar'),
    path('checkout/<int:contratacion_id>/', views.checkout, name='checkout'),
    path('facturas/', views.facturas, name='facturas'),
    path('facturas/<int:factura_id>/pdf/', views.factura_pdf, name='factura_pdf'),
    path('soporte/', views.soporte, name='soporte'),
    path('soporte/<int:ticket_id>/', views.ticket, name='ticket'),
    path('perfil/', views.perfil, name='perfil'),
]
