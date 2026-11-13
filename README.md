# CoreX Hub

Portal de CoreX con tres áreas separadas por rol:

| Área | URL | Quién | Qué hace |
|---|---|---|---|
| **Portal cliente** | `/portal/` | clientes | servicios, **consumo vs. plan y estadísticas de uso**, facturas (PDF protegido), soporte con conversación, datos fiscales, contratar |
| **Backoffice staff** | `/staff/` | `is_staff` | KPIs reales (MRR/ARR, cobranza), clientes y legajo, activar/suspender servicios, facturación, soporte, tablero de tareas |
| **Panel desarrolladores** | `/dev/` | superusuario o grupo **Desarrolladores** | estado de cada SaaS, tenants y sus métricas, aprovisionar/suspender vía API, log de integración |

Login y registro: `/cuenta/login/` (cada rol aterriza en su área). API para los SaaS: `/api/v1/`.

## Puesta en marcha

```bash
docker compose up -d              # PostgreSQL en el 5433
python -m venv venv && venv\Scripts\activate      # (Windows)
pip install -r requirements.txt
copy .env.example .env            # y completar
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Para recorrerlo con datos de ejemplo (solo desarrollo):
```bash
python manage.py corex_demo       # usuarios dev / staff / ferreteria / kinesio ... clave corex1234
```

## Cómo se conecta todo

```
Servicio (SaaS) ─┬─ PlanServicio ─── LimitePlan ── MetricaServicio
                 └─ Tenant ─── MetricaTenant (snapshot diario)
ClienteProfile ── Contratacion ──(1:1)── Tenant
       ├── FacturaCliente (→ contratación)
       └── Ticket (→ contratación / tenant) ── TicketMensaje (con notas internas)
EventoIntegracion: log de cada llamada Hub ⇄ SaaS
```

- Al **activar** una contratación se crea el `Tenant` y, si el SaaS tiene API, se aprovisiona solo; si no, queda una tarea interna urgente.
- Al **suspender** o dar de **baja**, se suspende el tenant en el SaaS.
- Las métricas llegan por pull (`python manage.py sync_metricas`, programarlo cada hora) o por push desde el SaaS.

Contrato completo: [`docs/API_SAAS.md`](docs/API_SAAS.md). Kit para cada SaaS: [`sdk/`](sdk/README.md).

## SaaS conectados

| SaaS | Multi-tenant | Cómo se conecta | Configurar en el Hub |
|---|---|---|---|
| **FacturAR** | django-tenants (schemas) | `corex_agent` + ganchos en `tenant/corex.py` (ver `COREX_HUB.md` en FacturAR) | `python manage.py corex_setup facturar --api-url ... --api-token ...` |
| **GestionAR** | por filas (`Tenant` FK) | app propia `apps/corex_hub` con el mismo contrato (ver `COREX_HUB.md` en GestionAR) | `python manage.py corex_setup gestionar --api-url ... --api-token ...` |
| StockeAR, Turnos | django-tenants | `sdk/corex_agent` + un `recolectar(fecha)` | agregarlos a `CATALOGO` en `corex_setup.py` |

Los dos SaaS y el Hub deben usar **bases de datos distintas**.

## Pasar un usuario a desarrollador
Admin → Usuarios → marcar *Es staff* y agregarlo al grupo **Desarrolladores** (la migración lo crea).
