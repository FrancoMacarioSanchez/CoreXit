from django.urls import path

from . import views

urlpatterns = [
    path('', views.index_view, name='landing-home'),
    path('facturar/', views.facturar_view, name='facturar'),
    path('gestionar/', views.gestionar_view, name='gestionar'),
]
