from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from datetime import date, timedelta
from django.contrib import messages

from .models import ClienteProfile, Contratacion, Membresia, Ticket, PlanServicio
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
    return render(request, 'dashboard/auth.html', context)

def registro_plan_view(request, plan_id, frecuencia):
    """Maneja el registro de un cliente que viene directo a comprar un plan."""
    plan = get_object_or_404(PlanServicio, id=plan_id, activo=True)
    
    if request.method == 'POST':
        form = RegistroClienteForm(request.POST)
        if form.is_valid():
            perfil = form.save()
            
            # Crear contratación suspendida hasta que Mercado Pago confirme
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

    return render(request, 'registro_plan.html', {'form': form, 'plan': plan, 'frecuencia': frecuencia})

@login_required
def portal_cliente_view(request):
    if request.user.is_superuser or request.user.is_staff:
        return redirect('portal_empleado')

    perfil, created = ClienteProfile.objects.get_or_create(user=request.user)

    context = {
        'perfil': perfil,
        'contrataciones': perfil.contrataciones.all(),
        'membresias': perfil.membresias.all(),
        'tickets': perfil.tickets.all(),
        'planes_disponibles': PlanServicio.objects.filter(activo=True).select_related('servicio'), 
    }
    return render(request, 'dashboard/portal_cliente.html', context)

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

@staff_member_required
def portal_empleado_view(request):
    tickets = Ticket.objects.all()
    context = {
        'clientes': ClienteProfile.objects.all(),
        'contrataciones': Contratacion.objects.all(),
        'membresias': Membresia.objects.all(),
        'tickets': tickets,
        'tickets_abiertos': tickets.filter(estado='abierto'),
        'tickets_proceso': tickets.filter(estado='en_proceso'),
        'tickets_resueltos': tickets.filter(estado='resuelto'),
        'tickets_cerrados': tickets.filter(estado='cerrado'),
    }
    return render(request, 'dashboard/portal_empleado.html', context)

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