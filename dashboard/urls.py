from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.auth_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='landing-home'), name='logout'),
    path('redirect/', views.redirect_post_login, name='redirect_post_login'),
    path('registro/<int:plan_id>/<str:frecuencia>/', views.registro_plan_view, name='registro_plan'),
    path('terminos-condiciones/', views.terminos_condiciones_view, name='terminos_condiciones'),
]
