# Kit para conectar cada SaaS al Hub

## `corex_agent/` — app Django para tus SaaS con django-tenants

Implementa todo el lado SaaS del contrato (`docs/API_SAAS.md`). Probado con
django-tenants 4 + Django 6.1 + PostgreSQL 16.

### Instalación (GestionAR, Turnos, StockeAR…)

1. Copiá la carpeta `corex_agent/` a la raíz del proyecto del SaaS.
2. `settings.py`:
   ```python
   SHARED_APPS = [
       'django_tenants',
       'clientes',          # tu app del modelo Tenant
       'corex_agent',       # <- en SHARED_APPS (vive en el schema public)
       ...
   ]

   MIDDLEWARE = [
       'django_tenants.middleware.main.TenantMainMiddleware',
       'corex_agent.middleware.TenantSuspendidoMiddleware',   # bloquea tenants suspendidos
       ...
   ]

   COREX_AGENT_TOKEN = env('COREX_AGENT_TOKEN')          # = "API token" del servicio en el Hub
   COREX_SERVICIO = 'gestionar'
   COREX_METRICS_COLLECTOR = 'ventas.corex.recolectar'   # ver ejemplo_collector.py
   COREX_TENANT_NAME_FIELD = 'nombre'                    # campo nombre de tu modelo Tenant

   # Solo si además querés empujar métricas (push):
   COREX_HUB_URL = 'https://hub.corexit.tech'
   COREX_HUB_INGEST_TOKEN = env('COREX_HUB_INGEST_TOKEN')
   ```
3. En el urlconf **público** (`PUBLIC_SCHEMA_URLCONF`):
   ```python
   path('corex/v1/', include('corex_agent.urls')),
   ```
4. `python manage.py migrate_schemas --shared`
5. En el Hub → Panel dev → el SaaS → Integración:
   `API URL = https://<dominio-public-del-saas>/corex/v1/` y `API token` = `COREX_AGENT_TOKEN`.
   Probá con **Health check** y después **Importar del SaaS** para traer los tenants que ya tenés.

### Ganchos para adaptarlo a cada SaaS

| Setting | Firma | Default |
|---|---|---|
| `COREX_METRICS_COLLECTOR` | `fn(fecha) -> dict` (corre dentro del schema) | obligatorio para métricas |
| `COREX_TENANT_FACTORY` | `fn(datos) -> tenant` | crea `Tenant` + `Domain` |
| `COREX_ADMIN_FACTORY` | `fn(tenant, admin_dict) -> dict` (se suma a la respuesta) | superusuario sin contraseña |
| `COREX_ON_PLAN` | `fn(tenant, plan, limites) -> [advertencias]` | — (guarda en `EstadoTenant`) |
| `COREX_ON_ESTADO` | `fn(tenant, estado, motivo)` al suspender/reactivar | — |
| `COREX_ESTADO_RESOLVER` | `fn(tenant) -> 'activo' \| 'suspendido' \| 'baja'` | `EstadoTenant` |

Si la fábrica levanta `ValueError` (datos inválidos, CUIT duplicado…), el Hub recibe un 409 con
ese mensaje y lo muestra en el panel dev. Las `advertencias` también llegan al panel dev.
La API CoreX solo responde en el dominio del schema `public`.

Ejemplo completo de integración: FacturAR (`tenant/corex.py`).

Si tu modelo de tenant tiene campos obligatorios extra (plan, CUIT, rubro…),
definí `COREX_TENANT_FACTORY`. El default del admin crea el usuario sin
contraseña: lo ideal es que tu factory le mande un mail de “definí tu contraseña”.

### Push de métricas (opcional)

```bash
python manage.py corex_push_metricas --dias 2   # en cron, cada hora o cada noche
```
Pull y push se pueden combinar: si llegan los dos para el mismo día, el Hub los fusiona.

## `mock_saas.py` — SaaS simulado

Implementa el contrato con datos aleatorios, sin dependencias. Ideal para
desarrollar el Hub sin levantar los SaaS reales:

```bash
python sdk/mock_saas.py --puerto 9001 --token prueba123 --perfil turnos
```
