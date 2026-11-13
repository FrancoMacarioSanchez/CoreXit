"""Vistas compartidas: login/registro, redirección por rol, registro desde la landing y T&C."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import RegistroClienteForm
from .models import ClienteProfile, Contratacion, PlanServicio
from .permisos import inicio_para


@login_required
def redirect_post_login(request):
    """Cada rol aterriza en su propia área."""
    return redirect(inicio_para(request.user))


def auth_view(request):
    """Login y registro general desde la misma pantalla."""
    if request.user.is_authenticated and request.method == 'GET':
        return redirect(inicio_para(request.user))

    login_form = AuthenticationForm(request)
    registro_form = RegistroClienteForm()
    tab = 'login'
    siguiente = request.POST.get('next') or request.GET.get('next') or ''

    if request.method == 'POST':
        if 'action_login' in request.POST:
            login_form = AuthenticationForm(request, data=request.POST)
            if login_form.is_valid():
                login(request, login_form.get_user())
                if siguiente and url_has_allowed_host_and_scheme(siguiente, {request.get_host()}, request.is_secure()):
                    return redirect(siguiente)
                return redirect('redirect_post_login')
        elif 'action_register' in request.POST:
            tab = 'register'
            registro_form = RegistroClienteForm(request.POST)
            if registro_form.is_valid():
                perfil = registro_form.save()
                login(request, perfil.user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(request, '¡Bienvenido a CoreX! Tu cuenta está lista.')
                return redirect('portal:inicio')

    return render(request, 'registration/login.html', {
        'login_form': login_form, 'registro_form': registro_form, 'tab': tab, 'next': siguiente,
    })


def _crear_contratacion(perfil, plan, frecuencia):
    return Contratacion.objects.create(
        cliente=perfil, plan=plan,
        fecha_inicio=timezone.localdate(),
        fecha_vencimiento=timezone.localdate() + timedelta(days=30 if frecuencia == 'mensual' else 365),
        estado='pendiente', frecuencia_pago=frecuencia,
    )


def registro_plan_view(request, plan_id, frecuencia):
    """Un visitante elige un plan en la landing: se registra (o ingresa) y va a pagar."""
    plan = get_object_or_404(PlanServicio, id=plan_id, activo=True)
    if frecuencia not in ('mensual', 'anual'):
        frecuencia = 'mensual'
    error_login = None

    # Ya logueado como cliente: directo al checkout
    if request.user.is_authenticated and not request.user.is_staff:
        perfil, _ = ClienteProfile.objects.get_or_create(
            user=request.user, defaults={'nombre': request.user.get_full_name() or request.user.username,
                                         'email': request.user.email})
        c = _crear_contratacion(perfil, plan, frecuencia)
        return redirect('portal:checkout', contratacion_id=c.id)

    form = RegistroClienteForm()
    if request.method == 'POST':
        perfil = None
        if request.POST.get('tipo_accion') == 'login':
            user = authenticate(request, username=request.POST.get('username'), password=request.POST.get('password'))
            if user is None:
                error_login = 'Usuario o contraseña incorrectos.'
            elif user.is_staff:
                error_login = 'Las cuentas del equipo CoreX no pueden contratar planes.'
            else:
                login(request, user)
                perfil, _ = ClienteProfile.objects.get_or_create(
                    user=user, defaults={'nombre': user.get_full_name() or user.username, 'email': user.email})
        else:
            form = RegistroClienteForm(request.POST)
            if form.is_valid():
                perfil = form.save()
                login(request, perfil.user, backend='django.contrib.auth.backends.ModelBackend')

        if perfil:
            c = _crear_contratacion(perfil, plan, frecuencia)
            return redirect('portal:checkout', contratacion_id=c.id)

    return render(request, 'registro_plan.html', {
        'form': form, 'plan': plan, 'frecuencia': frecuencia, 'error_login': error_login,
    })


def terminos_condiciones_view(request):
    return render(request, 'registration/tyc.html')
