from django.urls import path

from . import views

app_name = 'devpanel'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('saas/<int:servicio_id>/', views.servicio, name='servicio'),
    path('tenants/nuevo/', views.tenant_form, name='tenant_nuevo'),
    path('tenants/<int:tenant_id>/', views.tenant, name='tenant'),
    path('tenants/<int:tenant_id>/editar/', views.tenant_form, name='tenant_editar'),
    path('eventos/', views.eventos, name='eventos'),
    path('api/', views.documentacion, name='docs'),
]
