from django.shortcuts import render

from dashboard.models import PlanServicio

def index_view(request):
    return render(request, 'landing/index.html')

def facturar_view(request):
    # Traemos los planes activos de FacturAR ordenados por precio
    planes = PlanServicio.objects.filter(
        servicio__nombre__icontains='FacturAR', 
        activo=True
    ).order_by('precio_mensual')
    
    context = {
        'planes': planes
    }
    return render(request, 'landing/Facturar.html', context)