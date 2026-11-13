from django.shortcuts import render

from dashboard.models import PlanServicio

# Orden de los planes de GestionAR en la landing (después, por precio)
ORDEN_GESTIONAR = ['starter', 'ecommerce', 'empresa']

# Qué función incluye cada plan (la hace cumplir GestionAR: gestionar_corex/apps/corex_hub/planes.py)
FUNCIONES_GESTIONAR = [
    ('Caja táctil (POS), stock, clientes y proveedores', {'starter', 'ecommerce', 'empresa'}),
    ('Facturación electrónica ARCA', {'starter', 'ecommerce', 'empresa'}),
    ('Reportes de ventas y exportación de datos', {'starter', 'ecommerce', 'empresa'}),
    ('Tienda web con envíos coordinados', {'ecommerce', 'empresa'}),
    ('Motor de promociones (local y online)', {'ecommerce', 'empresa'}),
    ('Chat interno del equipo', {'ecommerce', 'empresa'}),
    ('Gerencia: métricas y gráficos', {'empresa'}),
    ('Registro de actividad', {'empresa'}),
]
LIMITES_GESTIONAR = [
    ('Puntos de venta', 'puntos_venta'),
    ('Usuarios', 'usuarios'),
    ('Productos', 'productos'),
    ('Comprobantes ARCA por mes', 'comprobantes_arca'),
]


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
    return render(request, 'landing/facturar.html', context)


def _clave(nombre):
    return ''.join(ch for ch in (nombre or '').lower() if ch.isalnum())


def _numero(valor):
    return f'{int(valor):,}'.replace(',', '.')


def gestionar_view(request):
    """Landing de GestionAR: los planes salen de la base (Admin → Planes), igual que FacturAR."""
    qs = (PlanServicio.objects.filter(servicio__slug='gestionar', activo=True)
          .prefetch_related('limites__metrica'))
    planes = []
    for p in qs:
        clave = _clave(p.nombre)
        limites = {l.metrica.clave: l.limite for l in p.limites.all()}
        planes.append({
            'plan': p,
            'clave': clave,
            'lineas': [ln.strip() for ln in (p.descripcion or '').splitlines() if ln.strip()],
            'limites': limites,
            'destacado': clave == 'ecommerce',
            'con_precio': p.precio_mensual > 0,
        })
    planes.sort(key=lambda d: (ORDEN_GESTIONAR.index(d['clave']) if d['clave'] in ORDEN_GESTIONAR else 99,
                               d['plan'].precio_mensual))
    filas_limites = [
        {'nombre': nombre,
         'celdas': [(_numero(d['limites'][clave]) if clave in d['limites'] else 'Sin límite') for d in planes]}
        for nombre, clave in LIMITES_GESTIONAR
    ]
    filas_funciones = [
        {'nombre': nombre, 'celdas': [d['clave'] in planes_con for d in planes]}
        for nombre, planes_con in FUNCIONES_GESTIONAR
    ]
    return render(request, 'landing/gestionar.html', {
        'planes': planes, 'filas_limites': filas_limites, 'filas_funciones': filas_funciones,
    })
