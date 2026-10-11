from django.contrib.auth.models import User
from django.db import models


class ClienteProfile(models.Model):
    # Opciones estándar de ARCA/AFIP para la facturación
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
    condicion_fiscal = models.CharField(
        max_length=30, 
        choices=CONDICIONES_FISCALES, 
        default='consumidor_final'
    )
    domicilio_fiscal = models.TextField(blank=True, null=True, help_text="Calle, Número, Localidad, Provincia, CP")
    terminos_aceptados = models.BooleanField(
        default=False, 
        help_text="Indica si el cliente aceptó los términos y condiciones."
    )
    fecha_aceptacion_terminos = models.DateTimeField(
        blank=True, 
        null=True,
        help_text="Fecha y hora exacta de la aceptación."
    )

    # --- Datos Internos del Sistema ---
    tokens_usados = models.TextField(blank=True, null=True)
    notas_internas = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.nombre} - {self.empresa or "Sin Empresa"} (CUIT: {self.cuit_cuil or "N/A"})'


class Servicio(models.Model):
    nombre = models.CharField(max_length=100)
    prefijo = models.CharField(max_length=10)
    descripcion = models.TextField(blank=True, null=True)
    api_url = models.URLField(help_text="URL base de la API interna del servicio")
    api_token = models.CharField(max_length=255, help_text="Token para autenticación entre servidores")

    def __str__(self):
        return self.nombre


class PlanServicio(models.Model):
    servicio = models.ForeignKey(
        Servicio, on_delete=models.CASCADE, related_name='planes'
    )
    nombre = models.CharField(max_length=100)  # Ej: "Inicial", "Profesional", "Negocio"
    descripcion = models.TextField(blank=True, null=True)
    precio_mensual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    precio_anual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # Nuevos campos para los links de suscripción de Mercado Pago
    link_mercadopago_mensual = models.URLField(
        blank=True, null=True, 
        help_text="Link de suscripción de Mercado Pago para el cobro mensual"
    )
    link_mercadopago_anual = models.URLField(
        blank=True, null=True, 
        help_text="Link de suscripción de Mercado Pago para el cobro anual"
    )
    
    activo = models.BooleanField(default=True, help_text="Desmarcar para ocultar el plan de la venta")

    def __str__(self):
        return f"{self.servicio.nombre} - {self.nombre}"


class Contratacion(models.Model):
    ESTADOS = [
        ('activo', 'Activo'),
        ('suspendido', 'Suspendido (Baja temporal)'),
        ('historico', 'Histórico / Finalizado'),
    ]
    cliente = models.ForeignKey(
        ClienteProfile, on_delete=models.CASCADE, related_name='contrataciones'
    )
    plan = models.ForeignKey(PlanServicio, on_delete=models.PROTECT, null=True, blank=True)    
    url_sistema = models.URLField(blank=True, null=True)
    fecha_inicio = models.DateField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='activo')
    
    frecuencia_pago = models.CharField(
        max_length=10, 
        choices=[('mensual', 'Mensual'), ('anual', 'Anual')],
        default='mensual'
    )

    
    def __str__(self):
        cliente = (
            self.cliente.empresa or self.cliente.nombre
            if self.cliente
            else "Sin cliente"
        )

        if not self.plan:
            return f"{cliente} - Sin plan asignado"

        servicio = (
            self.plan.servicio.nombre
            if self.plan.servicio
            else "Sin servicio"
        )

        nombre_plan = self.plan.nombre or "Sin nombre"

        return f"{cliente} - {servicio} ({nombre_plan})"



class Membresia(models.Model):
    cliente = models.ForeignKey(
        ClienteProfile, on_delete=models.CASCADE, related_name='membresias'
    )
    contratacion = models.ForeignKey(
        Contratacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='membresias_generadas'
    )
    concepto = models.CharField(max_length=150, null=True, blank=True) 
    total = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    ) 
    # Link de pago único por si el cliente no está suscripto y debe pagar esta factura manual
    link_pago = models.URLField(
        blank=True, null=True, 
        help_text="Link de pago único de Mercado Pago para esta factura específica (opcional)"
    )
    facturado = models.BooleanField(default=False) 
    pagado = models.BooleanField(default=False)
    fecha_emision = models.DateField(auto_now_add=True)
    fecha_vencimiento = models.DateField() 
    fecha_mora = models.DateField(blank=True, null=True)

    

    def __str__(self):
        cliente = self.cliente.empresa if self.cliente else "Sin cliente"
        plan = self.plan

        if not plan:
            return f"{cliente} - Sin plan"

        servicio = plan.servicio.nombre if plan.servicio else "Sin servicio"
        nombre_plan = plan.nombre or "Sin nombre"

        return f"{cliente} - {servicio} ({nombre_plan})"




class Ticket(models.Model):
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

    cliente = models.ForeignKey(
        ClienteProfile, on_delete=models.CASCADE, related_name='tickets'
    )
    asunto = models.CharField(max_length=200)
    descripcion = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='abierto')
    prioridad = models.CharField(
        max_length=20, choices=PRIORIDADES, default='media'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ticket #{self.id} - {self.asunto}"


class TicketMensaje(models.Model):
    """Permite una conversación tipo chat o hilo dentro del ticket entre el cliente y CoreX."""
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name='mensajes'
    )
    autor = models.ForeignKey(
        User, on_delete=models.CASCADE
    )  # Puede ser el cliente o un empleado
    mensaje = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Mensaje de {self.autor.username} en Ticket #{self.ticket.id}'