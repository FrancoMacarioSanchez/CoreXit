from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from .forms import RegistroClienteForm
from django.contrib.auth.decorators import login_required

from django.shortcuts import redirect


@login_required
def redirect_post_login(request):
  if request.user.is_superuser or request.user.is_staff:
    return redirect('portal_empleado')
  else:
    return redirect('portal_cliente')

def registro_view(request):
  login_form = AuthenticationForm()
  registro_form = RegistroClienteForm()

  if request.method == 'POST':
    if 'action_login' in request.POST:
      login_form = AuthenticationForm(request, data=request.POST)
      if login_form.is_valid():
        user = login_form.get_user()
        login(request, user)
        return redirect('redirect_post_login')
    elif 'action_register' in request.POST:
      registro_form = RegistroClienteForm(request.POST)
      if registro_form.is_valid():
        registro_form.save()
        return redirect('registro')

  context = {
      'login_form': login_form,
      'registro_form': registro_form,
  }
  return render(request, 'dashboard/auth.html', context)

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from .models import ClienteProfile, Contratacion, Membresia, Ticket, Servicio


@login_required
def portal_cliente_view(request):
  if request.user.is_superuser or request.user.is_staff:
    return redirect('/admin/')

  perfil, created = ClienteProfile.objects.get_or_create(user=request.user)

  contrataciones = perfil.contrataciones.all()
  membresias = perfil.membresias.all()
  tickets = perfil.tickets.all()
  servicios_disponibles = Servicio.objects.all()  # 👈 Acá se obtienen

  context = {
      'perfil': perfil,
      'contrataciones': contrataciones,
      'membresias': membresias,
      'tickets': tickets,
      'servicios_disponibles': servicios_disponibles,  # 👈 Se pasan al template
  }
  return render(request, 'dashboard/portal_cliente.html', context)

from django.utils import timezone
from datetime import timedelta
from .forms import RegistroClienteForm, TicketForm, SolicitarServicioForm


@login_required
def crear_ticket_view(request):
  perfil = get_object_or_404(ClienteProfile, user=request.user)
  if request.method == 'POST':
    form = TicketForm(request.POST)
    if form.is_valid():
      ticket = form.save(commit=False)
      ticket.cliente = perfil
      ticket.save()
      return redirect('portal_cliente')
  return redirect('portal_cliente')


@login_required
def solicitar_servicio_view(request):
  perfil = get_object_or_404(ClienteProfile, user=request.user)
  if request.method == 'POST':
    form = SolicitarServicioForm(request.POST)
    if form.is_valid():
      contratacion = form.save(commit=False)
      contratacion.cliente = perfil
      contratacion.fecha_inicio = timezone.now().date()
      # Por defecto le damos 30 días de vigencia inicial de prueba/contrato
      contratacion.fecha_vencimiento = timezone.now().date() + timedelta(
          days=30
      )
      contratacion.estado = 'activo'
      contratacion.save()
      return redirect('portal_cliente')
  return redirect('portal_cliente')

from django.contrib.admin.views.decorators import staff_member_required


@staff_member_required
def portal_empleado_view(request):
  clientes = ClienteProfile.objects.all()
  contrataciones = Contratacion.objects.all()
  membresias = Membresia.objects.all()
  tickets = Ticket.objects.all()

  # Separamos los tickets por estado para el tablero Kanban
  tickets_abiertos = tickets.filter(estado='abierto')
  tickets_proceso = tickets.filter(estado='en_proceso')
  tickets_resueltos = tickets.filter(estado='resuelto')
  tickets_cerrados = tickets.filter(estado='cerrado')

  context = {
      'clientes': clientes,
      'contrataciones': contrataciones,
      'membresias': membresias,
      'tickets': tickets,
      'tickets_abiertos': tickets_abiertos,
      'tickets_proceso': tickets_proceso,
      'tickets_resueltos': tickets_resueltos,
      'tickets_cerrados': tickets_cerrados,
  }
  return render(request, 'dashboard/portal_empleado.html', context)


@staff_member_required
def detalle_cliente_view(request, cliente_id):
  cliente = get_object_or_404(ClienteProfile, id=cliente_id)
  contrataciones = cliente.contrataciones.all()
  membresias = cliente.membresias.all()
  tickets = cliente.tickets.all()

  context = {
      'cliente': cliente,
      'contrataciones': contrataciones,
      'membresias': membresias,
      'tickets': tickets,
  }
  return render(request, 'dashboard/detalle_cliente.html', context)


@staff_member_required
def actualizar_estado_ticket(request, ticket_id):
  ticket = get_object_or_404(Ticket, id=ticket_id)
  if request.method == 'POST':
    nuevo_estado = request.POST.get('estado')
    if nuevo_estado in dict(Ticket.ESTADOS):
      ticket.estado = nuevo_estado
      ticket.save()
  return redirect('portal_empleado')

from django.utils import timezone


@staff_member_required
def lista_clientes_staff_view(request):
  clientes = ClienteProfile.objects.all()
  hoy = timezone.now().date()

  # Preparamos información analítica rápida para cada cliente
  clientes_data = []
  for cli in clientes:
    membresias = cli.membresias.all()
    contrataciones = cli.contrataciones.all()

    # Detectar si tiene alguna membresía en mora o vencida
    en_mora = any(
        m.fecha_mora and m.fecha_mora <= hoy and not m.pagado
        for m in membresias
    )
    deuda_pendiente = any(not m.pagado for m in membresias)

    clientes_data.append({
        'perfil': cli,
        'total_servicios': contrataciones.filter(estado='activo').count(),
        'total_membresias': membresias.count(),
        'en_mora': en_mora,
        'deuda_pendiente': deuda_pendiente,
    })

  context = {
      'clientes_data': clientes_data,
  }
  return render(request, 'dashboard/lista_clientes.html', context)