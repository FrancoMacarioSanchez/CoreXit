from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.site_header = 'CoreX · Administración'
admin.site.site_title = 'CoreX Admin'

urlpatterns = [
    path('admin/', admin.site.urls),

    # Autenticación, registro desde la landing y redirección por rol
    path('cuenta/', include('dashboard.urls')),

    # Cada rol tiene su propia área
    path('portal/', include('portal.urls')),     # clientes
    path('staff/', include('staff.urls')),       # equipo CoreX
    path('dev/monitoreo/', include('monitoreo.urls')),  # métricas del servidor y actividad (antes que dev/)
    path('dev/', include('devpanel.urls')),      # desarrolladores
    path('instagram/', include('igportal.urls')),  # portal de Instagram (staff)

    # API para que los SaaS empujen métricas / estados
    path('api/v1/', include('dashboard.api_urls')),

    # Compatibilidad con links viejos
    path('dashboard/portal/', RedirectView.as_view(pattern_name='portal:inicio', permanent=False)),
    path('dashboard/staff/', RedirectView.as_view(pattern_name='staff:inicio', permanent=False)),
    path('dashboard/login/', RedirectView.as_view(pattern_name='login', permanent=False)),
    path('dashboard/terminos-condiciones/', RedirectView.as_view(pattern_name='terminos_condiciones', permanent=False)),
    path('registro/<int:plan_id>/<str:frecuencia>/', RedirectView.as_view(pattern_name='registro_plan', permanent=False)),

    path('', include('landing.urls')),
]

if settings.DEBUG:
    from django.conf.urls.static import static
    # Solo estáticos en DEBUG; los PDF de facturas van por vistas protegidas.
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
