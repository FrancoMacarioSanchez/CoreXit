from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from datetime import date, timedelta
from django.contrib import messages

from .models import ClienteProfile, Contratacion, FacturaCliente, Membresia, Ticket, PlanServicio
from .forms import RegistroClienteForm, TicketForm

@login_required
def redirect_post_login(request):
    """Redirige al usuario según su rol después de iniciar sesión."""
    if request.user.is_superuser or request.user.is_staff:
        return redirect('portal_empleado')
    else:
        return redirect('portal_cliente')

def auth_view(request):
    """Maneja el Login y el Registro general desde la misma plantilla HTML."""
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
                messages.success(request, "Cuenta creada exitosamente. Por favor, inicia sesión.")
                return redirect('login') # O el nombre de tu URL de auth

    context = {
        'login_form': login_form,
        'registro_form': registro_form,
    }
    return render(request, 'auth.html', context)

from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone


def registro_plan_view(request, plan_id, frecuencia):
    """Maneja el registro o inicio de sesión de un cliente que viene a comprar un plan."""
    plan = get_object_or_404(PlanServicio, id=plan_id, activo=True)
    error_login = None

    if request.method == 'POST':
        tipo_accion = request.POST.get('tipo_accion', 'registro')
        perfil = None

        # --- MODO 1: YA TENGO CUENTA (LOGIN) ---
        if tipo_accion == 'login':
            form = RegistroClienteForm()  # Instancia limpia para no disparar errores de campos vacíos
            username = request.POST.get('username')
            password = request.POST.get('password')

            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                # Obtenemos el perfil de cliente asociado al usuario.
                # NOTA: Si tu modelo de perfil no tiene related_name, ajustá esto
                # por ejemplo a: Cliente.objects.filter(user=user).first()
                perfil = getattr(user, 'perfil', None) or getattr(user, 'cliente', None)

                if not perfil:
                    error_login = "Tu usuario no tiene un perfil de cliente asociado."
            else:
                error_login = "Usuario o contraseña incorrectos."

        # --- MODO 2: SOY NUEVO CLIENTE (REGISTRO) ---
        else:
            form = RegistroClienteForm(request.POST)
            if form.is_valid():
                perfil = form.save()

        # --- SI OBTUVIMOS EL PERFIL (POR LOGIN O REGISTRO), CREAMOS LA CONTRATACIÓN ---
        if perfil:
            Contratacion.objects.create(
                cliente=perfil,
                plan=plan,
                fecha_inicio=timezone.now().date(),
                fecha_vencimiento=timezone.now().date() + timedelta(days=30 if frecuencia == 'mensual' else 365),
                estado='suspendido',
                frecuencia_pago=frecuencia
            )

            # Redirigir a Mercado Pago
            link_pago = plan.link_mercadopago_mensual if frecuencia == 'mensual' else plan.link_mercadopago_anual
            if link_pago:
                return redirect(link_pago)
            else:
                messages.warning(request, "Este plan no tiene configurado un link de pago.")
                return redirect('login')
    else:
        form = RegistroClienteForm()

    return render(request, 'registro_plan.html', {
        'form': form,
        'plan': plan,
        'frecuencia': frecuencia,
        'error_login': error_login,
    })

@login_required
def portal_cliente_view(request):
    if request.user.is_superuser or request.user.is_staff:
        return redirect('portal_empleado')

    perfil, created = ClienteProfile.objects.get_or_create(user=request.user)

    # Manejar creación de tickets o actualización de perfil desde el portal
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'crear_ticket':
            asunto = request.POST.get('asunto')
            descripcion = request.POST.get('descripcion')
            if asunto and descripcion:
                Ticket.objects.create(cliente=perfil, asunto=asunto, descripcion=descripcion, tipo='soporte')
                messages.success(request, "Ticket de soporte creado correctamente.")
        elif action == 'actualizar_perfil':
            perfil.empresa = request.POST.get('empresa', perfil.empresa)
            perfil.cuit_cuil = request.POST.get('cuit_cuil', perfil.cuit_cuil)
            perfil.domicilio_fiscal = request.POST.get('domicilio_fiscal', perfil.domicilio_fiscal)
            perfil.save()
            messages.success(request, "Datos fiscales actualizados con éxito.")
        return redirect('portal_cliente')

    facturas = perfil.facturas.all()
    servicios_activos = perfil.contrataciones.filter(estado='activo').count()
    facturas_pendientes = facturas.filter(estado='pendiente').count()
    total_pagado = sum(f.monto for f in facturas.filter(estado='pagado'))

    kpis = {
        'servicios_activos': servicios_activos,
        'facturas_pendientes': facturas_pendientes,
        'total_pagado': total_pagado,
    }

    context = {
        'perfil': perfil,
        'contrataciones': perfil.contrataciones.all(),
        'facturas': facturas,
        'tickets': perfil.tickets.all(),
        'kpis': kpis,
    }
    return render(request, 'dashboard/portal_cliente.html', context)


@staff_member_required
def portal_empleado_view(request):
  if request.method == 'POST':
    action = request.POST.get('action')
    if action == 'crear_factura':
      cliente_id = request.POST.get('cliente_id')
      tipo_comprobante = request.POST.get('tipo_comprobante')
      numero_comprobante = request.POST.get('numero_comprobante')
      periodo_facturado = request.POST.get('periodo_facturado')
      monto = request.POST.get('monto')
      fecha_vencimiento = request.POST.get('fecha_vencimiento')
      estado = request.POST.get('estado', 'pendiente')
      archivo_pdf = request.FILES.get('archivo_pdf')

      cliente = get_object_or_404(ClienteProfile, id=cliente_id)
      FacturaCliente.objects.create(
          cliente=cliente,
          tipo_comprobante=tipo_comprobante,
          numero_comprobante=numero_comprobante,
          periodo_facturado=periodo_facturado,
          monto=monto,
          fecha_vencimiento=fecha_vencimiento,
          estado=estado,
          archivo_pdf=archivo_pdf,
      )
      messages.success(request, 'Factura creada y publicada con éxito.')
      return redirect('portal_empleado')

    elif action == 'marcar_pagada':
      factura_id = request.POST.get('factura_id')
      factura = get_object_or_404(FacturaCliente, id=factura_id)
      factura.estado = 'pagado'
      factura.fecha_pago = timezone.now()
      factura.save()
      messages.success(
          request, f'Factura {factura.numero_comprobante} marcada como pagada.'
      )
      return redirect('portal_empleado')

  clientes = ClienteProfile.objects.all()
  contrataciones = Contratacion.objects.all()
  todas_las_facturas = FacturaCliente.objects.all()

  # Separación de Tickets de Soporte y Tareas de Desarrollo/Internas
  tickets_soporte = Ticket.objects.filter(tipo='soporte')
  tareas_pendientes = Ticket.objects.filter(tipo='desarrollo')

  mrr = sum(
      c.plan.precio_mensual
      for c in contrataciones.filter(estado='activo', frecuencia_pago='mensual')
  )
  monto_pendiente = sum(
      f.monto for f in todas_las_facturas.filter(estado='pendiente')
  )

  kpis = {
      'mrr': mrr,
      'total_clientes': clientes.count(),
      'contrataciones_activas': contrataciones.filter(estado='activo').count(),
      'monto_pendiente': monto_pendiente,
      'facturas_pendientes_count': todas_las_facturas.filter(
          estado='pendiente'
      ).count(),
  }

  context = {
      'clientes': clientes,
      'contrataciones': contrataciones,
      'todas_las_facturas': todas_las_facturas,
      'tickets_soporte': tickets_soporte,
      'tareas_pendientes': tareas_pendientes,
      'tickets_abiertos_count': tickets_soporte.filter(estado='abierto').count(),
      'kpis': kpis,
  }
  return render(request, 'dashboard/portal_empleado.html', context)

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

# --- VISTAS DEL EMPLEADO / STAFF ---

from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
# Importa tus modelos (ClienteProfile, Contratacion, Membresia, Ticket, etc.)

@staff_member_required
def detalle_cliente_view(request, cliente_id):
    cliente = get_object_or_404(ClienteProfile, id=cliente_id)
    context = {
        'cliente': cliente,
        'contrataciones': cliente.contrataciones.all(),
        'membresias': cliente.membresias.all(),
        'tickets': cliente.tickets.all(),
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

@staff_member_required
def lista_clientes_staff_view(request):
    hoy = timezone.now().date()
    clientes_data = []
    
    for cli in ClienteProfile.objects.all():
        membresias = cli.membresias.all()
        en_mora = any(m.fecha_mora and m.fecha_mora <= hoy and not m.pagado for m in membresias)
        
        clientes_data.append({
            'perfil': cli,
            'total_servicios': cli.contrataciones.filter(estado='activo').count(),
            'total_membresias': membresias.count(),
            'en_mora': en_mora,
            'deuda_pendiente': any(not m.pagado for m in membresias),
        })

    return render(request, 'dashboard/lista_clientes.html', {'clientes_data': clientes_data})

@login_required
def checkout_view(request, contratacion_id):
    """Vista para que clientes logueados paguen contrataciones pendientes."""
    
    # Buscamos la contratación que le pertenece a este usuario y que esté suspendida/pendiente
    contratacion = get_object_or_404(
        Contratacion, 
        id=contratacion_id, 
        cliente__user=request.user, 
        estado='suspendido'
    )
    
    # Obtenemos el link correcto según la frecuencia de pago elegida
    link_pago = contratacion.plan.link_mercadopago_mensual if contratacion.frecuencia_pago == 'mensual' else contratacion.plan.link_mercadopago_anual
    
    # OPCIÓN A: Redirección directa a Mercado Pago (Recomendada para menos clics)
    if request.method == 'POST':
        if link_pago:
            return redirect(link_pago)
        else:
            messages.error(request, "Error: No hay link de pago configurado para este plan.")
            return redirect('portal_cliente')

    # OPCIÓN B: Pantalla de resumen (Muestra detalles antes de mandarlo a pagar)
    context = {
        'contratacion': contratacion,
        'plan': contratacion.plan,
        'link_pago': link_pago,
        'precio': contratacion.plan.precio_mensual if contratacion.frecuencia_pago == 'mensual' else contratacion.plan.precio_anual
    }
    return render(request, 'dashboard/checkout.html', context)

@login_required
def solicitar_servicio_view(request):
    perfil = get_object_or_404(ClienteProfile, user=request.user)
    
    if request.method == 'POST':
        plan_id = request.POST.get('plan')
        frecuencia = request.POST.get('frecuencia', 'mensual') # Capturamos la frecuencia
        url_sistema = request.POST.get('url_sistema')
        
        plan = get_object_or_404(PlanServicio, id=plan_id)
        
        # 1. Creamos la contratación en estado SUSPENDIDO
        contratacion = Contratacion.objects.create(
            cliente=perfil,
            plan=plan,
            url_sistema=url_sistema,
            fecha_inicio=timezone.now().date(),
            fecha_vencimiento=timezone.now().date() + timedelta(days=30 if frecuencia == 'mensual' else 365),
            estado='suspendido',
            frecuencia_pago=frecuencia # Guardamos si eligió anual o mensual
        )
        
        # 2. Redirigimos al checkout para que lo pague
        return redirect('checkout', contratacion_id=contratacion.id)
        
    return redirect('portal_cliente')

import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from .models import Ticket # Asegúrate de importar tu modelo

@staff_member_required
@require_POST
def actualizar_estado_ticket(request):
    try:
        data = json.loads(request.body)
        ticket_id = data.get('ticket_id')
        nuevo_estado = data.get('estado')
        
        ticket = Ticket.objects.get(id=ticket_id)
        ticket.estado = nuevo_estado
        ticket.save()
        
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
def terminos_condiciones_view(request):
    return render(request, 'registration/tyc.html')