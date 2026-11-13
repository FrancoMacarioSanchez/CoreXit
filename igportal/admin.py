from django.contrib import admin

from .models import ConfiguracionInstagram, PublicacionInstagram


@admin.register(PublicacionInstagram)
class PublicacionAdmin(admin.ModelAdmin):
    list_display = ('creado', 'tipo', 'estado', 'programada_para', 'creado_por')
    list_filter = ('estado', 'tipo')
    readonly_fields = ('container_id', 'ig_media_id', 'permalink', 'error', 'intentos', 'publicada_en')


@admin.register(ConfiguracionInstagram)
class ConfiguracionAdmin(admin.ModelAdmin):
    exclude = ('access_token',)     # el token se carga desde el portal y no se ve en el admin
    readonly_fields = ('username', 'token_expira')

    def has_add_permission(self, request):
        return not ConfiguracionInstagram.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
