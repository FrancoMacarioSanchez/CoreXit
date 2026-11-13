from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import ConfiguracionInstagram, PublicacionInstagram

ENTRADA_FECHA = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M']


class PublicacionForm(forms.ModelForm):
    programada_para = forms.DateTimeField(
        required=False, label='Programar para', input_formats=ENTRADA_FECHA,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        help_text='Dejalo vacío para guardarlo como borrador y publicarlo cuando quieras.')

    class Meta:
        model = PublicacionInstagram
        fields = ['tipo', 'media_url', 'caption', 'programada_para']
        widgets = {'caption': forms.Textarea(attrs={'rows': 5, 'maxlength': 2200})}

    def clean_media_url(self):
        url = self.cleaned_data['media_url'].strip()
        if not url.lower().startswith('https://'):
            raise forms.ValidationError('Instagram solo acepta archivos con una URL pública que empiece con https://')
        return url

    def clean_programada_para(self):
        cuando = self.cleaned_data.get('programada_para')
        if cuando and cuando < timezone.now():
            raise forms.ValidationError('La fecha ya pasó. Elegí un momento futuro.')
        return cuando

    def clean(self):
        data = super().clean()
        if data.get('tipo') == 'REELS' and data.get('media_url', '').lower().split('?')[0].endswith(('.jpg', '.jpeg', '.png', '.webp')):
            self.add_error('media_url', 'Un reel necesita un video (por ejemplo .mp4), no una imagen.')
        if data.get('tipo') == 'IMAGE' and data.get('media_url', '').lower().split('?')[0].endswith(('.mp4', '.mov')):
            self.add_error('media_url', 'Una publicación de imagen necesita una foto en JPG. Para video elegí Reel o Historia.')
        return data


class ConexionForm(forms.ModelForm):
    access_token = forms.CharField(
        required=False, label='Token de acceso', strip=True,
        widget=forms.PasswordInput(attrs={'autocomplete': 'off', 'placeholder': 'Pegá el token nuevo (vacío = conservar el actual)'}),
        help_text='Se guarda en el servidor y no se vuelve a mostrar.')
    expira_en_dias = forms.IntegerField(
        required=False, min_value=1, max_value=90, initial=60, label='Días de vida del token',
        help_text='Los tokens de larga duración duran 60 días.')

    class Meta:
        model = ConfiguracionInstagram
        fields = ['ig_user_id', 'api_host', 'api_version']

    def clean_api_host(self):
        host = self.cleaned_data['api_host'].strip().rstrip('/')
        if host not in ('https://graph.instagram.com', 'https://graph.facebook.com'):
            raise forms.ValidationError('Usá https://graph.instagram.com (o https://graph.facebook.com si conectás con Facebook).')
        return host

    def save(self, commit=True):
        obj = super().save(commit=False)
        token = self.cleaned_data.get('access_token')
        if token:
            obj.access_token = token
            dias = self.cleaned_data.get('expira_en_dias') or 60
            obj.token_expira = timezone.now() + timedelta(days=dias)
        if commit:
            obj.save()
        return obj


class ComentarioForm(forms.Form):
    comment_id = forms.CharField(widget=forms.HiddenInput)
    texto = forms.CharField(max_length=2200, widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Escribí tu respuesta…'}))
