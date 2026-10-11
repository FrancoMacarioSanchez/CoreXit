from django.contrib import admin
from django.urls import include, path

from dashboard.views import registro_plan_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'accounts/', include('django.contrib.auth.urls')
    ),  # Rutas de login/logout
    path('dashboard/', include('dashboard.urls')),  # Rutas del sistema
    path('', include('landing.urls')),  # 👈 Esta debe ser la raíz '/'
    path('registro/<int:plan_id>/<str:frecuencia>/', registro_plan_view, name='registro_plan'),

]