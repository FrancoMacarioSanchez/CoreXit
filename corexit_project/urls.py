from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'accounts/', include('django.contrib.auth.urls')
    ),  # Rutas de login/logout
    path('dashboard/', include('dashboard.urls')),  # Rutas del sistema
    path('', include('landing.urls')),  # 👈 Esta debe ser la raíz '/'
]