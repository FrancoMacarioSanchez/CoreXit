from django.urls import path

from . import views

urlpatterns = [
    path('health/', views.health),
    path('tenants/', views.tenants),
    path('tenants/<str:schema>/', views.tenant_detalle),
    path('tenants/<str:schema>/metricas/', views.metricas),
    path('tenants/<str:schema>/suspender/', views.suspender),
    path('tenants/<str:schema>/reactivar/', views.reactivar),
    path('tenants/<str:schema>/plan/', views.plan),
]
