from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import ClienteProfile
from .models import Contratacion, Ticket


class RegistroClienteForm(UserCreationForm):
  email = forms.EmailField(
      required=True,
      widget=forms.EmailInput(
          attrs={
              'class': (
                  'w-full bg-slate-900/60 border border-slate-700/50 rounded-xl'
                  ' px-4 py-3 text-white focus:outline-none'
                  ' focus:border-blue-500'
              )
          }
      ),
  )
  empresa = forms.CharField(
      max_length=100,
      required=False,
      widget=forms.TextInput(
          attrs={
              'class': (
                  'w-full bg-slate-900/60 border border-slate-700/50 rounded-xl'
                  ' px-4 py-3 text-white focus:outline-none'
                  ' focus:border-blue-500'
              )
          }
      ),
  )
  telefono = forms.CharField(
      max_length=20,
      required=False,
      widget=forms.TextInput(
          attrs={
              'class': (
                  'w-full bg-slate-900/60 border border-slate-700/50 rounded-xl'
                  ' px-4 py-3 text-white focus:outline-none'
                  ' focus:border-blue-500'
              )
          }
      ),
  )

  class Meta:
    model = User
    fields = ['username', 'email', 'empresa', 'telefono']
    widgets = {
        'username': forms.TextInput(
            attrs={
                'class': (
                    'w-full bg-slate-900/60 border border-slate-700/50'
                    ' rounded-xl px-4 py-3 text-white focus:outline-none'
                    ' focus:border-blue-500'
                )
            }
        ),
    }

  def save(self, commit=True):
    user = super().save(commit=False)
    user.email = self.cleaned_data['email']
    if commit:
      user.save()
      ClienteProfile.objects.create(
          user=user,
          empresa=self.cleaned_data.get('empresa'),
          telefono=self.cleaned_data.get('telefono'),
      )
    return user

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
    fields = ['servicio', 'url_sistema']
    widgets = {
        'servicio': forms.Select(
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