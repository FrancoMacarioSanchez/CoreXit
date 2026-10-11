from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import ClienteProfile
from .models import Contratacion, Ticket


from django import forms
from django.contrib.auth.models import User
from django.utils import timezone
from .models import ClienteProfile

class RegistroClienteForm(forms.ModelForm):
    username = forms.CharField(max_length=150, required=True, label="Nombre de usuario")
    password = forms.CharField(widget=forms.PasswordInput, required=True, label="Contraseña")
    
    # Checkbox obligatorio para los TyC
    aceptar_terminos = forms.BooleanField(
        required=True, 
        label="Acepto los Términos y Condiciones de CoreX"
    )
    
    class Meta:
        model = ClienteProfile
        fields = [
            'nombre', 'email', 'telefono', 'empresa', 
            'cuit_cuil', 'condicion_fiscal', 'domicilio_fiscal'
        ]
        labels = {
            'cuit_cuil': 'CUIT / CUIL',
            'empresa': 'Nombre de la Empresa o Razón Social',
        }
        widgets = {
            'domicilio_fiscal': forms.Textarea(attrs={'rows': 2}),
        }

    def save(self, commit=True):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password']
        )
        
        perfil = super().save(commit=False)
        perfil.user = user
        
        # Registramos la aceptación y el momento exacto
        if self.cleaned_data.get('aceptar_terminos'):
            perfil.terminos_aceptados = True
            perfil.fecha_aceptacion_terminos = timezone.now()
        
        if commit:
            perfil.save()
            
        return perfil

class TicketForm(forms.ModelForm):

  class Meta:
    model = Ticket
    fields = ['asunto', 'descripcion', 'prioridad']
    widgets = {
        'asunto': forms.TextInput(
            attrs={
                'class': (
                    'w-full bg-slate-900/60 border border-slate-700/50'
                    ' rounded-xl px-4 py-3 text-white focus:outline-none'
                    ' focus:border-blue-500'
                ),
                'placeholder': 'Ej: Problema con el acceso al sistema',
            }
        ),
        'descripcion': forms.Textarea(
            attrs={
                'class': (
                    'w-full bg-slate-900/60 border border-slate-700/50'
                    ' rounded-xl px-4 py-3 text-white focus:outline-none'
                    ' focus:border-blue-500 h-24'
                ),
                'placeholder': 'Detallanos tu consulta o inconveniente...',
            }
        ),
        'prioridad': forms.Select(
            attrs={
                'class': (
                    'w-full bg-slate-900/60 border border-slate-700/50'
                    ' rounded-xl px-4 py-3 text-white focus:outline-none'
                    ' focus:border-blue-500'
                )
            }
        ),
    }


class SolicitarServicioForm(forms.ModelForm):

  class Meta:
    model = Contratacion
    fields = ['plan', 'url_sistema']
    widgets = {
        'plan': forms.Select(
            attrs={
                'class': (
                    'w-full bg-slate-900/60 border border-slate-700/50'
                    ' rounded-xl px-4 py-3 text-white focus:outline-none'
                    ' focus:border-blue-500'
                )
            }
        ),
        'url_sistema': forms.URLInput(
            attrs={
                'class': (
                    'w-full bg-slate-900/60 border border-slate-700/50'
                    ' rounded-xl px-4 py-3 text-white focus:outline-none'
                    ' focus:border-blue-500'
                ),
                'placeholder': 'https://tusistema.com (si aplica)',
            }
        ),
    }
