from django.urls import path

from . import views

app_name = 'monitoreo'

urlpatterns = [
    path('servidor/', views.servidor, name='servidor'),
    path('datos/', views.servidor_datos, name='servidor_datos'),
    path('actividad/', views.actividad, name='actividad'),
]
