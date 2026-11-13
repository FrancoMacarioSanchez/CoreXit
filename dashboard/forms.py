from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from .models import ClienteProfile, Contratacion, FacturaCliente, MetricaServicio, Servicio, Tenant, Ticket

INPUT = 'input'


class EstiloMixin:
    """Aplica la clase CSS 'input' (definida en base_app.html) a todos los campos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            w = campo.widget
            if isinstance(w, (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple)):
                continue
            w.attrs['class'] = (w.attrs.get('class', '') + ' ' + INPUT).strip()


# ----------------------------------------------------------------- registro
class RegistroClienteForm(forms.ModelForm):
    username = forms.CharField(max_length=150, required=True, label="Nombre de usuario")
    password = forms.CharField(widget=forms.PasswordInput, required=True, label="Contraseña")
    aceptar_terminos = forms.BooleanField(required=True, label="Acepto los Términos y Condiciones de CoreX")

    class Meta:
        model = ClienteProfile
        fields = ['nombre', 'email', 'telefono', 'empresa', 'cuit_cuil', 'condicion_fiscal', 'domicilio_fiscal']
        labels = {'cuit_cuil': 'CUIT / CUIL', 'empresa': 'Nombre de la Empresa o Razón Social'}
        widgets = {'domicilio_fiscal': forms.Textarea(attrs={'rows': 2})}

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Ese nombre de usuario ya está en uso.')
        return username

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if not email:
            raise forms.ValidationError('El email es obligatorio.')
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        validate_password(password)
        return password

    def save(self, commit=True):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            first_name=(self.cleaned_data.get('nombre') or '')[:150],
        )
        perfil = super().save(commit=False)
        perfil.user = user
        if self.cleaned_data.get('aceptar_terminos'):
            perfil.terminos_aceptados = True
            perfil.fecha_aceptacion_terminos = timezone.now()
        if commit:
            perfil.save()
        return perfil


# ------------------------------------------------------------------ cliente
class PerfilFiscalForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = ClienteProfile
        fields = ['nombre', 'empresa', 'email', 'telefono', 'cuit_cuil', 'condicion_fiscal', 'domicilio_fiscal']
        labels = {'cuit_cuil': 'CUIT / CUIL', 'empresa': 'Razón social / Nombre de fantasía'}
        widgets = {'domicilio_fiscal': forms.Textarea(attrs={'rows': 2})}


class TicketClienteForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['contratacion', 'asunto', 'descripcion', 'prioridad']
        labels = {'contratacion': 'Servicio', 'descripcion': 'Contanos qué pasa'}
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, cliente=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Contratacion.objects.none()
        if cliente:
            qs = cliente.contrataciones.select_related('plan__servicio')
        self.fields['contratacion'].queryset = qs
        self.fields['contratacion'].required = False
        self.fields['contratacion'].empty_label = 'Consulta general'
        self.fields['contratacion'].label_from_instance = lambda c: f'{c.servicio} · {c.plan.nombre}' if c.plan else str(c)
        self.fields['prioridad'].choices = [c for c in Ticket.PRIORIDADES if c[0] != 'urgente']


class MensajeForm(EstiloMixin, forms.Form):
    mensaje = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Escribí tu respuesta...'}), label='')


# -------------------------------------------------------------------- staff
class FacturaForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = FacturaCliente
        fields = ['cliente', 'contratacion', 'tipo_comprobante', 'numero_comprobante', 'cae', 'periodo_facturado',
                  'fecha_emision', 'fecha_vencimiento', 'monto', 'estado', 'link_pago', 'archivo_pdf']
        widgets = {
            'fecha_emision': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'fecha_vencimiento': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contratacion'].required = False
        self.fields['contratacion'].queryset = Contratacion.objects.select_related('cliente', 'plan__servicio')
        self.fields['estado'].choices = [c for c in FacturaCliente.ESTADO_PAGO_CHOICES if c[0] in ('pendiente', 'pagado')]
        self.fields['archivo_pdf'].widget.attrs['accept'] = '.pdf'

    def clean(self):
        datos = super().clean()
        c, cli = datos.get('contratacion'), datos.get('cliente')
        if c and cli and c.cliente_id != cli.pk:
            self.add_error('contratacion', 'La contratación no pertenece a ese cliente.')
        return datos


class TicketStaffForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['estado', 'prioridad', 'asignado_a']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asignado_a'].queryset = User.objects.filter(is_staff=True, is_active=True)
        self.fields['asignado_a'].label_from_instance = lambda u: u.get_full_name() or u.username


class TareaForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['asunto', 'descripcion', 'prioridad', 'asignado_a', 'cliente', 'tenant']
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asignado_a'].queryset = User.objects.filter(is_staff=True, is_active=True)
        self.fields['cliente'].required = False
        self.fields['tenant'].required = False


class NotasInternasForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = ClienteProfile
        fields = ['notas_internas']
        widgets = {'notas_internas': forms.Textarea(attrs={'rows': 5})}
        labels = {'notas_internas': ''}


# ---------------------------------------------------------------------- dev
class TenantForm(EstiloMixin, forms.ModelForm):
    aprovisionar_ahora = forms.BooleanField(required=False, initial=False,
                                            label='Pedir al SaaS que lo cree ahora (vía API)')

    class Meta:
        model = Tenant
        fields = ['servicio', 'cliente', 'contratacion', 'nombre', 'schema_name', 'dominio', 'estado', 'id_externo']
        help_texts = {'contratacion': 'Vincula el tenant con lo que el cliente paga (y sus límites de plan).'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contratacion'].queryset = Contratacion.objects.select_related('cliente', 'plan__servicio')
        self.fields['contratacion'].required = False
        self.fields['cliente'].required = False

    def clean(self):
        datos = super().clean()
        c = datos.get('contratacion')
        if c:
            if c.plan and datos.get('servicio') and c.plan.servicio_id != datos['servicio'].pk:
                self.add_error('contratacion', 'La contratación es de otro SaaS.')
            otro = Tenant.objects.filter(contratacion=c).exclude(pk=self.instance.pk).first()
            if otro:
                self.add_error('contratacion', f'Ya está vinculada al tenant {otro.schema_name}.')
            if not datos.get('cliente'):
                datos['cliente'] = c.cliente
        return datos


class ServicioIntegracionForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = Servicio
        fields = ['slug', 'color', 'api_url', 'api_token', 'dominio_base', 'prefijo_en_schema', 'activo']
        widgets = {'color': forms.TextInput(attrs={'type': 'color'}), 'api_token': forms.PasswordInput(render_value=True)}


class MetricaServicioForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = MetricaServicio
        fields = ['clave', 'nombre', 'unidad', 'tipo', 'visible_cliente', 'destacada', 'orden']
