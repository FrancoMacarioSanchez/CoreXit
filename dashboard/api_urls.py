from django.urls import path

from . import api

app_name = 'api'

urlpatterns = [
    path('ping/', api.ping, name='ping'),
    path('metricas/', api.recibir_metricas, name='metricas'),
    path('tenants/estado/', api.estado_tenant, name='estado_tenant'),
]
