from django.contrib import admin

from .models import MuestraRequests, MuestraServidor, RegistroActividad


@admin.register(RegistroActividad)
class RegistroActividadAdmin(admin.ModelAdmin):
    list_display = ('creado', 'username', 'tipo', 'descripcion', 'estado_http', 'ip')
    list_filter = ('tipo', 'username')
    search_fields = ('username', 'descripcion', 'ruta', 'ip')
    date_hierarchy = 'creado'

    # Es un registro de auditoría: se lee, no se edita ni se borra a mano.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(MuestraServidor)
admin.site.register(MuestraRequests)
