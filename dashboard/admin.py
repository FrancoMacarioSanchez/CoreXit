from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    ClienteProfile, Contratacion, EventoIntegracion, FacturaCliente, LimitePlan, Membresia, MetricaServicio,
    MetricaTenant, PlanServicio, Servicio, Tenant, Ticket, TicketMensaje,
)


class MetricaServicioInline(admin.TabularInline):
    model = MetricaServicio
    extra = 0


class PlanInline(admin.TabularInline):
    model = PlanServicio
    extra = 0
    fields = ('nombre', 'precio_mensual', 'precio_anual', 'activo')
    show_change_link = True


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'prefijo', 'activo', 'tiene_api', 'n_tenants')
    prepopulated_fields = {'slug': ('nombre',)}
    readonly_fields = ('ingest_token',)
    inlines = [PlanInline, MetricaServicioInline]
    fieldsets = (
        (None, {'fields': ('nombre', 'slug', 'prefijo', 'descripcion', 'color', 'activo')}),
        ('Integración', {'fields': ('api_url', 'api_token', 'ingest_token', 'dominio_base', 'prefijo_en_schema'),
                         'description': 'Ver docs/API_SAAS.md. El token de ingesta se rota desde el panel de desarrolladores.'}),
    )

    @admin.display(boolean=True, description='API')
    def tiene_api(self, obj):
        return obj.tiene_api

    @admin.display(description='Tenants')
    def n_tenants(self, obj):
        return obj.tenants.count()


class LimitePlanInline(admin.TabularInline):
    model = LimitePlan
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Solo métricas del mismo SaaS que el plan
        if db_field.name == 'metrica':
            plan_id = request.resolver_match.kwargs.get('object_id')
            if plan_id:
                plan = PlanServicio.objects.filter(pk=plan_id).first()
                if plan:
                    kwargs['queryset'] = MetricaServicio.objects.filter(servicio=plan.servicio)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(PlanServicio)
class PlanServicioAdmin(admin.ModelAdmin):
    list_display = ('servicio', 'nombre', 'precio_mensual', 'precio_anual', 'activo')
    list_filter = ('servicio', 'activo')
    inlines = [LimitePlanInline]


@admin.register(ClienteProfile)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'empresa', 'cuit_cuil', 'email', 'condicion_fiscal', 'created_at', 'legajo')
    search_fields = ('nombre', 'empresa', 'cuit_cuil', 'email', 'user__username')
    list_filter = ('condicion_fiscal',)

    @admin.display(description='')
    def legajo(self, obj):
        return format_html('<a href="{}">Legajo →</a>', reverse('staff:cliente', args=[obj.pk]))


@admin.register(Contratacion)
class ContratacionAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'plan', 'estado', 'frecuencia_pago', 'fecha_inicio', 'fecha_vencimiento')
    list_filter = ('estado', 'plan__servicio', 'frecuencia_pago')
    search_fields = ('cliente__nombre', 'cliente__empresa')
    autocomplete_fields = ('cliente',)


@admin.register(FacturaCliente)
class FacturaAdmin(admin.ModelAdmin):
    list_display = ('numero_comprobante', 'tipo_comprobante', 'cliente', 'periodo_facturado', 'monto', 'estado', 'fecha_vencimiento')
    list_filter = ('estado', 'tipo_comprobante')
    search_fields = ('numero_comprobante', 'cliente__nombre', 'cliente__empresa')
    autocomplete_fields = ('cliente',)


class TicketMensajeInline(admin.TabularInline):
    model = TicketMensaje
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'asunto', 'tipo', 'cliente', 'estado', 'prioridad', 'asignado_a', 'created_at')
    list_filter = ('tipo', 'estado', 'prioridad')
    search_fields = ('asunto', 'descripcion')
    inlines = [TicketMensajeInline]


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'servicio', 'schema_name', 'dominio', 'estado', 'cliente', 'ultimo_sync')
    list_filter = ('servicio', 'estado')
    search_fields = ('nombre', 'schema_name', 'dominio')


@admin.register(MetricaTenant)
class MetricaTenantAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'fecha', 'origen', 'recibido')
    list_filter = ('tenant__servicio', 'origen')
    date_hierarchy = 'fecha'


@admin.register(EventoIntegracion)
class EventoAdmin(admin.ModelAdmin):
    list_display = ('creado', 'servicio', 'tenant', 'direccion', 'accion', 'exito', 'status_code', 'duracion_ms')
    list_filter = ('servicio', 'direccion', 'exito', 'accion')
    readonly_fields = [f.name for f in EventoIntegracion._meta.fields]


admin.site.register(Membresia)
