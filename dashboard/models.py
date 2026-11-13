import secrets
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


def generar_token():
    return secrets.token_urlsafe(32)


# =============================================================================
# CLIENTES
# =============================================================================
class ClienteProfile(models.Model):
    CONDICIONES_FISCALES = [
        ('consumidor_final', 'Consumidor Final'),
        ('monotributo', 'Monotributo'),
        ('responsable_inscripto', 'Responsable Inscripto'),
        ('exento', 'Sujeto Exento'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # --- Datos de Contacto e Identidad ---
    nombre = models.CharField(max_length=150, help_text="Nombre y Apellido del titular o representante")
    email = models.EmailField(help_text="Mail principal de contacto y facturación", null=True, blank=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)

    # --- Datos Fiscales y de la Empresa ---
    empresa = models.CharField(max_length=100, blank=True, null=True, help_text="Nombre de fantasía o Razón Social")
    cuit_cuil = models.CharField(max_length=20, blank=True, null=True, help_text="Sin guiones o con guiones (ej. 20-12345678-9)")
    condicion_fiscal = models.CharField(max_length=30, choices=CONDICIONES_FISCALES, default='consumidor_final')
    domicilio_fiscal = models.TextField(blank=True, null=True, help_text="Calle, Número, Localidad, Provincia, CP")
    terminos_aceptados = models.BooleanField(default=False, help_text="Indica si el cliente aceptó los términos y condiciones.")
    fecha_aceptacion_terminos = models.DateTimeField(blank=True, null=True, help_text="Fecha y hora exacta de la aceptación.")

    # --- Datos Internos del Sistema ---
    tokens_usados = models.TextField(blank=True, null=True)
    notas_internas = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.nombre} - {self.empresa or "Sin Empresa"} (CUIT: {self.cuit_cuil or "N/A"})'

    @property
    def nombre_visible(self):
        return self.empresa or self.nombre or self.user.username

    @property
    def iniciales(self):
        base = (self.nombre_visible or '?').split()
        return ''.join(p[0] for p in base[:2]).upper()

    def facturas_vencidas(self):
        hoy = timezone.localdate()
        return self.facturas.filter(estado__in=['pendiente', 'vencido'], fecha_vencimiento__lt=hoy)

    @property
    def en_mora(self):
        return self.facturas_vencidas().exists()


# =============================================================================
# CATÁLOGO: SaaS, planes, métricas y límites
# =============================================================================
class Servicio(models.Model):
    """Cada SaaS de CoreX (GestionAR, StockeAR, Turnos, FacturAR...)."""
    nombre = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50, unique=True, null=True, blank=True,
                            help_text="Identificador corto (ej. gestionar). Se usa en URLs y en la API.")
    prefijo = models.CharField(max_length=10)
    descripcion = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=7, default='#6366f1', help_text="Color del SaaS en gráficos (hex)")
    activo = models.BooleanField(default=True)

    # --- Integración saliente (Hub -> SaaS) ---
    api_url = models.URLField(blank=True, help_text="URL base de la API CoreX del SaaS. Ej: https://api.gestionar.corexit.tech/corex/v1")
    api_token = models.CharField(max_length=255, blank=True, help_text="Token que el Hub envía al SaaS (Authorization: Bearer ...)")

    # --- Integración entrante (SaaS -> Hub) ---
    ingest_token = models.CharField(max_length=64, unique=True, null=True, blank=True,
                                    help_text="Token con el que el SaaS empuja métricas al Hub. Se genera solo.")

    # --- Aprovisionamiento ---
    dominio_base = models.CharField(max_length=120, blank=True,
                                    help_text="Dominio de los tenants. Vacío = usa COREX_DOMINIO_BASE. Ej: gestionar.corexit.tech")
    prefijo_en_schema = models.BooleanField(
        default=True,
        help_text="Antepone el prefijo al identificador del tenant (gestmitienda). Desactivalo si el SaaS "
                  "usa el identificador en URLs visibles (p. ej. la tienda web de GestionAR).")

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.ingest_token:
            self.ingest_token = generar_token()
        super().save(*args, **kwargs)

    @property
    def tiene_api(self):
        return bool(self.api_url and self.api_token)

    def get_dominio_base(self):
        return self.dominio_base or settings.COREX_DOMINIO_BASE


class PlanServicio(models.Model):
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name='planes')
    nombre = models.CharField(max_length=100)  # Ej: "Inicial", "Profesional", "Negocio"
    descripcion = models.TextField(blank=True, null=True)
    precio_mensual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    precio_anual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    link_mercadopago_mensual = models.URLField(blank=True, null=True, help_text="Link de suscripción de Mercado Pago para el cobro mensual")
    link_mercadopago_anual = models.URLField(blank=True, null=True, help_text="Link de suscripción de Mercado Pago para el cobro anual")
    activo = models.BooleanField(default=True, help_text="Desmarcar para ocultar el plan de la venta")

    class Meta:
        verbose_name = 'Plan'
        verbose_name_plural = 'Planes'
        ordering = ['servicio__nombre', 'precio_mensual']

    def __str__(self):
        return f"{self.servicio.nombre} - {self.nombre}"

    def limites_dict(self):
        """{clave_metrica: limite} para enviar al SaaS al crear el tenant."""
        return {l.metrica.clave: float(l.limite) for l in self.limites.select_related('metrica')}


class MetricaServicio(models.Model):
    """
    Define qué métricas reporta cada SaaS. Así el Hub sabe cómo mostrar
    cada clave del JSON que llega (nombre, unidad, si la ve el cliente...).
    """
    TIPOS = [
        ('contador', 'Contador (se suma por período: ventas, turnos, comprobantes)'),
        ('nivel', 'Nivel (valor actual: usuarios, almacenamiento, productos)'),
    ]
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name='metricas_definidas')
    clave = models.SlugField(max_length=60, help_text="Clave en el JSON que manda el SaaS. Ej: comprobantes_emitidos")
    nombre = models.CharField(max_length=80)
    unidad = models.CharField(max_length=20, blank=True, help_text="Ej: MB, $, usuarios")
    tipo = models.CharField(max_length=10, choices=TIPOS, default='contador')
    visible_cliente = models.BooleanField(default=True, help_text="El cliente la ve en su portal")
    destacada = models.BooleanField(default=False, help_text="Se muestra en tablas y tarjetas resumen")
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Métrica del SaaS'
        verbose_name_plural = 'Métricas del SaaS'
        ordering = ['servicio', 'orden', 'nombre']
        unique_together = [('servicio', 'clave')]

    def __str__(self):
        return f'{self.servicio.nombre} · {self.nombre}'


class LimitePlan(models.Model):
    """Cupo de un plan para una métrica (por mes si es contador, valor máximo si es nivel)."""
    plan = models.ForeignKey(PlanServicio, on_delete=models.CASCADE, related_name='limites')
    metrica = models.ForeignKey(MetricaServicio, on_delete=models.CASCADE, related_name='limites')
    limite = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = 'Límite del plan'
        verbose_name_plural = 'Límites del plan'
        unique_together = [('plan', 'metrica')]

    def __str__(self):
        return f'{self.plan} · {self.metrica.nombre}: {self.limite}'


# =============================================================================
# CONTRATACIONES Y FACTURACIÓN
# =============================================================================
class Contratacion(models.Model):
    ESTADOS = [
        ('pendiente', 'Pendiente de pago'),
        ('activo', 'Activo'),
        ('suspendido', 'Suspendido (Baja temporal)'),
        ('historico', 'Histórico / Finalizado'),
    ]
    cliente = models.ForeignKey(ClienteProfile, on_delete=models.CASCADE, related_name='contrataciones')
    plan = models.ForeignKey(PlanServicio, on_delete=models.PROTECT, null=True, blank=True)
    url_sistema = models.URLField(blank=True, null=True)
    fecha_inicio = models.DateField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    frecuencia_pago = models.CharField(max_length=10, choices=[('mensual', 'Mensual'), ('anual', 'Anual')], default='mensual')

    class Meta:
        verbose_name = 'Contratación'
        verbose_name_plural = 'Contrataciones'
        ordering = ['-fecha_inicio', '-id']

    def __str__(self):
        cliente = (self.cliente.empresa or self.cliente.nombre) if self.cliente else "Sin cliente"
        if not self.plan:
            return f"{cliente} - Sin plan asignado"
        return f"{cliente} - {self.plan.servicio.nombre} ({self.plan.nombre or 'Sin nombre'})"

    @property
    def servicio(self):
        return self.plan.servicio if self.plan else None

    @property
    def precio(self):
        if not self.plan:
            return Decimal('0')
        return self.plan.precio_mensual if self.frecuencia_pago == 'mensual' else self.plan.precio_anual

    @property
    def valor_mensual(self):
        """Aporte al MRR: las anuales se prorratean en 12."""
        if not self.plan:
            return Decimal('0')
        if self.frecuencia_pago == 'anual':
            return (self.plan.precio_anual or Decimal('0')) / 12
        return self.plan.precio_mensual or Decimal('0')

    @property
    def link_pago(self):
        if not self.plan:
            return None
        return self.plan.link_mercadopago_mensual if self.frecuencia_pago == 'mensual' else self.plan.link_mercadopago_anual

    @property
    def url_acceso(self):
        tenant = getattr(self, 'tenant', None)
        if tenant and tenant.dominio:
            return tenant.url
        return self.url_sistema

    @property
    def dias_para_vencer(self):
        return (self.fecha_vencimiento - timezone.localdate()).days


class Membresia(models.Model):
    """Modelo heredado (cobros manuales). Las facturas nuevas usan FacturaCliente."""
    cliente = models.ForeignKey(ClienteProfile, on_delete=models.CASCADE, related_name='membresias')
    contratacion = models.ForeignKey(Contratacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='membresias_generadas')
    concepto = models.CharField(max_length=150, null=True, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    link_pago = models.URLField(blank=True, null=True, help_text="Link de pago único de Mercado Pago para esta factura específica (opcional)")
    facturado = models.BooleanField(default=False)
    pagado = models.BooleanField(default=False)
    fecha_emision = models.DateField(auto_now_add=True)
    fecha_vencimiento = models.DateField()
    fecha_mora = models.DateField(blank=True, null=True)

    def __str__(self):
        cliente = self.cliente.nombre_visible if self.cliente else "Sin cliente"
        return f"{cliente} - {self.concepto or 'Membresía'} (${self.total})"


class FacturaCliente(models.Model):
    TIPO_CHOICES = [('A', 'Factura A'), ('B', 'Factura B'), ('C', 'Factura C')]
    ESTADO_PAGO_CHOICES = [
        ('pendiente', 'Pendiente de Pago'),
        ('pagado', 'Pagado'),
        ('vencido', 'Vencido'),
        ('anulado', 'Anulado'),
    ]
    METODO_PAGO_CHOICES = [
        ('mercadopago', 'Mercado Pago'),
        ('transferencia', 'Transferencia Bancaria'),
        ('efectivo', 'Efectivo / Otro'),
    ]

    cliente = models.ForeignKey(ClienteProfile, on_delete=models.CASCADE, related_name='facturas')
    contratacion = models.ForeignKey(Contratacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='facturas')
    tipo_comprobante = models.CharField(max_length=2, choices=TIPO_CHOICES, default='C')
    numero_comprobante = models.CharField(max_length=20, help_text="Ej: 00001-00000145")
    cae = models.CharField(max_length=30, blank=True, null=True, help_text="CAE de ARCA (opcional)")
    periodo_facturado = models.CharField(max_length=50, help_text="Ej: Octubre 2026")
    fecha_emision = models.DateField(default=timezone.now)
    fecha_vencimiento = models.DateField()
    fecha_pago = models.DateTimeField(blank=True, null=True)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=15, choices=ESTADO_PAGO_CHOICES, default='pendiente')
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES, blank=True, null=True)
    referencia_pago = models.CharField(max_length=100, blank=True, null=True, help_text="ID de operación MP o comprobante")
    link_pago = models.URLField(blank=True, null=True, help_text="Link de Mercado Pago si está pendiente")
    archivo_pdf = models.FileField(upload_to='facturas_clientes/', blank=True, null=True)

    class Meta:
        ordering = ['-fecha_emision', '-id']
        verbose_name = 'Factura'
        verbose_name_plural = 'Facturas'

    def __str__(self):
        return f"Factura {self.tipo_comprobante} {self.numero_comprobante} - {self.cliente.nombre_visible}"

    @property
    def esta_vencida(self):
        return self.estado in ('pendiente', 'vencido') and self.fecha_vencimiento < timezone.localdate()

    @property
    def estado_real(self):
        """Estado a mostrar: una pendiente con fecha pasada se muestra como vencida."""
        return 'vencido' if self.esta_vencida else self.estado


# =============================================================================
# SOPORTE Y TAREAS INTERNAS
# =============================================================================
class Ticket(models.Model):
    TIPOS_CHOICES = [
        ('soporte', 'Soporte al Cliente'),
        ('desarrollo', 'Desarrollo / Tarea Interna'),
    ]
    ESTADOS = [
        ('abierto', 'Abierto'),
        ('en_proceso', 'En Proceso'),
        ('resuelto', 'Resuelto'),
        ('cerrado', 'Cerrado'),
    ]
    PRIORIDADES = [
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('urgente', 'Urgente'),
    ]

    cliente = models.ForeignKey(ClienteProfile, on_delete=models.CASCADE, related_name='tickets', null=True, blank=True)
    contratacion = models.ForeignKey(Contratacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets',
                                     help_text="Servicio sobre el que trata el ticket (opcional)")
    tenant = models.ForeignKey('Tenant', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    asignado_a = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_asignados',
                                   limit_choices_to={'is_staff': True})
    asunto = models.CharField(max_length=200)
    descripcion = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='abierto')
    prioridad = models.CharField(max_length=20, choices=PRIORIDADES, default='media')
    tipo = models.CharField(max_length=20, choices=TIPOS_CHOICES, default='soporte')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Ticket #{self.id} - {self.asunto}"

    @property
    def esta_abierto(self):
        return self.estado in ('abierto', 'en_proceso')


class TicketMensaje(models.Model):
    """Conversación dentro del ticket entre el cliente y CoreX."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='mensajes')
    autor = models.ForeignKey(User, on_delete=models.CASCADE)
    mensaje = models.TextField()
    interno = models.BooleanField(default=False, help_text="Nota interna: el cliente no la ve")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Mensaje de {self.autor.username} en Ticket #{self.ticket.id}'


# =============================================================================
# TENANTS Y MÉTRICAS (puente entre el Hub y cada SaaS)
# =============================================================================
class Tenant(models.Model):
    """Una instancia (schema de django-tenants) de un cliente dentro de un SaaS."""
    ESTADOS = [
        ('pendiente', 'Pendiente de aprovisionar'),
        ('aprovisionando', 'Aprovisionando'),
        ('activo', 'Activo'),
        ('suspendido', 'Suspendido'),
        ('error', 'Error'),
        ('baja', 'Dado de baja'),
    ]
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name='tenants')
    cliente = models.ForeignKey(ClienteProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='tenants')
    contratacion = models.OneToOneField(Contratacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='tenant')
    nombre = models.CharField(max_length=150)
    schema_name = models.CharField(max_length=63, help_text="Schema de PostgreSQL en el SaaS (django-tenants)")
    dominio = models.CharField(max_length=253, blank=True, help_text="Ej: mitienda.gestionar.corexit.tech")
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    id_externo = models.CharField(max_length=64, blank=True, help_text="ID del tenant dentro del SaaS")
    ultimo_sync = models.DateTimeField(null=True, blank=True)
    ultimo_error = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['servicio__nombre', 'nombre']
        unique_together = [('servicio', 'schema_name')]

    def __str__(self):
        return f'{self.servicio.nombre} · {self.nombre} ({self.schema_name})'

    @property
    def url(self):
        if not self.dominio:
            return None
        if self.dominio.startswith('http'):
            return self.dominio
        host = self.dominio.split(':')[0]
        local = host in ('localhost', '127.0.0.1') or host.endswith('.localhost')
        return f'{"http" if local else "https"}://{self.dominio}'

    @property
    def plan(self):
        return self.contratacion.plan if self.contratacion else None


class MetricaTenant(models.Model):
    """Snapshot diario de métricas de un tenant. 'datos' es {clave: valor}."""
    ORIGENES = [('push', 'Enviada por el SaaS'), ('pull', 'Consultada por el Hub'), ('manual', 'Carga manual')]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='metricas')
    fecha = models.DateField()
    datos = models.JSONField(default=dict)
    origen = models.CharField(max_length=10, choices=ORIGENES, default='pull')
    recibido = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha']
        unique_together = [('tenant', 'fecha')]
        verbose_name = 'Métrica diaria de tenant'
        verbose_name_plural = 'Métricas diarias de tenants'

    def __str__(self):
        return f'{self.tenant} · {self.fecha}'


class EventoIntegracion(models.Model):
    """Log de cada llamada entre el Hub y los SaaS (para el panel de desarrolladores)."""
    DIRECCIONES = [('saliente', 'Hub → SaaS'), ('entrante', 'SaaS → Hub')]
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, null=True, blank=True, related_name='eventos')
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, null=True, blank=True, related_name='eventos')
    direccion = models.CharField(max_length=10, choices=DIRECCIONES)
    accion = models.CharField(max_length=40)
    metodo = models.CharField(max_length=8, blank=True)
    url = models.CharField(max_length=500, blank=True)
    exito = models.BooleanField(default=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    duracion_ms = models.PositiveIntegerField(null=True, blank=True)
    detalle = models.TextField(blank=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Evento de integración'
        verbose_name_plural = 'Eventos de integración'

    def __str__(self):
        return f'[{self.creado:%d/%m %H:%M}] {self.get_direccion_display()} {self.accion} {"OK" if self.exito else "ERROR"}'
