from django.contrib import admin
from .models import (
    ClienteProfile,
    PlanServicio,
    Servicio,
    Contratacion,
    Membresia,
    Ticket,
    TicketMensaje,
)

admin.site.register(ClienteProfile)
admin.site.register(Servicio)
admin.site.register(Contratacion)
admin.site.register(Membresia)
admin.site.register(Ticket)
admin.site.register(TicketMensaje)
admin.site.register(PlanServicio)