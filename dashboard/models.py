from django.contrib.auth.models import User
from django.db import models


class ClienteProfile(models.Model):
  user = models.OneToOneField(User, on_delete=models.CASCADE)
  empresa = models.CharField(max_length=100, blank=True, null=True)
  telefono = models.CharField(max_length=20, blank=True, null=True)
  # Tokens o llaves de API utilizados por el cliente
  tokens_usados = models.TextField(
      blank=True,
      null=True,
      help_text='Tokens de API o accesos registrados',
  )
  notas_internas = models.TextField(blank=True, null=True)
  created_at = models.DateTimeField(auto_now_add=True)

  def __str__(self):
    return f'{self.user.username} - {self.empresa or "Sin Empresa"}'


class Servicio(models.Model):
  nombre = models.CharField(max_length=100)
  prefijo = models.CharField(max_length=10)
  descripcion = models.TextField(blank=True, null=True)
  precio_base = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )

  def __str__(self):
    return self.nombre


class Contratacion(models.Model):
  ESTADOS = [
      ('activo', 'Activo'),
      ('suspendido', 'Suspendido (Baja temporal)'),
      ('historico', 'Histórico / Finalizado'),
  ]
  cliente = models.ForeignKey(
      ClienteProfile, on_delete=models.CASCADE, related_name='contrataciones'
  )
  servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE)
  url_sistema = models.URLField(blank=True, null=True)
  fecha_inicio = models.DateField()
  fecha_vencimiento = models.DateField()
  estado = models.CharField(max_length=20, choices=ESTADOS, default='activo')


class Membresia(models.Model):
  cliente = models.ForeignKey(
      ClienteProfile, on_delete=models.CASCADE, related_name='membresias'
  )
  nombre_plan = models.CharField(max_length=100)
  total = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )  # 👈 Monto total
  facturado = models.BooleanField(
      default=False
  )  # 👈 ¿Emitido en factura AFIP / sistema?
  pagado = models.BooleanField(default=False)
  fecha_emision = models.DateField(auto_now_add=True)
  fecha_vencimiento = models.DateField()  # Límite de permisos
  fecha_mora = models.DateField(
      blank=True, null=True
  )  # 👈 Cuándo entra en vigor la mora


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