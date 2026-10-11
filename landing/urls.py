from django.urls import path
from .views import index_view
from landing import views

urlpatterns = [
    path('', index_view, name='landing-home'),
    path('facturar/', views.facturar_view, name='facturar'),
]