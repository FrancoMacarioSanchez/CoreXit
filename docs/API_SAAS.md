# API CoreX — contrato Hub ⇄ SaaS

El **Hub** (este proyecto) administra clientes, cobros y soporte. Cada **SaaS**
(GestionAR, StockeAR, Turnos, …) es un proyecto django-tenants independiente.
Se comunican por HTTP + JSON en dos sentidos:

| Sentido | Quién implementa | Autenticación | Para qué |
|---|---|---|---|
| Hub → SaaS | cada SaaS (`sdk/corex_agent`) | `Authorization: Bearer <Servicio.api_token>` | crear/suspender tenants, leer métricas |
| SaaS → Hub | el Hub (`dashboard/api.py`) | `Authorization: Bearer <Servicio.ingest_token>` | empujar métricas y cambios de estado |

Los dos tokens se configuran en **Panel dev → SaaS → Integración**. El token
de ingesta identifica al SaaS: un SaaS nunca puede escribir datos de tenants de otro.

Errores: siempre `{"error": "mensaje"}` con status 4xx/5xx.

---

## 1. Hub → SaaS

Base: `Servicio.api_url`, por ejemplo `https://gestionar.corexit.tech/corex/v1/`
(montado en el urlconf **público** del SaaS). Timeout: `COREX_SAAS_TIMEOUT` (10 s).

### `GET health/`
```json
{"ok": true, "servicio": "gestionar", "version": "1.4.0", "tenants": 12}
```

### `GET tenants/`
```json
{"tenants": [{"id": 3, "schema_name": "gestmitienda", "nombre": "Mi Tienda",
              "dominio": "mitienda.gestionar.corexit.tech", "estado": "activo"}]}
```
Se usa en **Importar del SaaS** para registrar en el Hub los tenants que ya existían.

### `POST tenants/` — crear (idempotente)
```json
{
  "referencia_hub": 41,
  "schema_name": "gestmitienda",
  "dominio": "mitienda.gestionar.corexit.tech",
  "nombre": "Mi Tienda",
  "plan": {"id": 2, "nombre": "Profesional"},
  "limites": {"comprobantes_arca": 1500, "usuarios": 5},
  "admin": {"username": "juanperez", "email": "juan@mitienda.com", "nombre": "Juan Pérez"},
  "cliente": {"nombre": "...", "empresa": "...", "email": "...", "cuit": "...", "condicion_fiscal": "monotributo"},
  "hub_url": "https://hub.corexit.tech"
}
```
Respuestas:
- `201` creado · `200` ya existía (mismo `schema_name`) → mismo cuerpo que `GET tenants/<schema>/`.
- Si el alta es lenta, puede responder `{"estado": "aprovisionando", ...}` y avisar al terminar con `POST /api/v1/tenants/estado/` del Hub.
- **No** devolver contraseñas: el SaaS debe invitar al admin por email para que defina la suya.
  Si no pudo mandar el email puede devolver `link_invitacion` (link de un solo uso) para que el staff lo reenvíe.
- `409` con `{"error": "..."}` si los datos no sirven (p. ej. CUIT duplicado o inválido).
- Campo opcional `advertencias: [..]`: el Hub las muestra en el tenant (panel dev).
- `plan.frecuencia` es `mensual` o `anual`. El Hub envía también `cliente.domicilio`.

### `GET tenants/<schema>/`
Detalle del tenant + `plan` y `limites` vigentes.

### `GET tenants/<schema>/metricas/?desde=YYYY-MM-DD&hasta=YYYY-MM-DD`
Máximo 92 días.
```json
{"tenant": "gestmitienda", "estado": "activo",
 "series": [{"fecha": "2026-11-10", "metricas": {"ventas_cantidad": 37, "ventas_monto": 412500.0,
                                                  "comprobantes_arca": 35, "usuarios": 4}}]}
```

### `POST tenants/<schema>/suspender/` · `POST tenants/<schema>/reactivar/`
Body opcional `{"motivo": "..."}` → `{"ok": true, "estado": "suspendido"}`.
El SaaS debe bloquear el acceso (el agente trae `TenantSuspendidoMiddleware`).

### `POST tenants/<schema>/plan/`
`{"plan": {...}, "limites": {...}}` → `{"ok": true}` (opcional `advertencias`). Se envía al cambiar de plan:
cuando el cliente activa un plan nuevo del mismo SaaS, el Hub **reutiliza su tenant** y la contratación anterior pasa a histórico.

---

## 2. SaaS → Hub

Base: `https://<hub>/api/v1/`

### `GET ping/`
Verifica el token → `{"ok": true, "servicio": "gestionar"}`

### `POST metricas/`
Uno o hasta 500 snapshots por llamada:
```json
{"items": [
  {"tenant": "gestmitienda", "fecha": "2026-11-10", "metricas": {"ventas_cantidad": 37, "usuarios": 4}}
]}
```
También acepta un solo item sin `items`. Respuesta:
```json
{"ok": true, "guardados": 1, "rechazados": [{"indice": 1, "tenant": "x", "error": "tenant desconocido para este servicio"}]}
```
- Si ya hay datos para ese día se **fusionan** (clave por clave).
- Solo se guardan valores numéricos.
- Si falta `fecha`, se usa hoy.

### `POST tenants/estado/`
```json
{"tenant": "gestmitienda", "estado": "activo", "dominio": "mitienda.gestionar.corexit.tech", "id": "3"}
```
Estados: `pendiente`, `aprovisionando`, `activo`, `suspendido`, `error` (con `"error": "detalle"`), `baja`.

---

## 3. Métricas

Cada SaaS define sus claves en **Panel dev → SaaS → Métricas**:

| Tipo | Significado | Consumo mostrado | Límite de plan |
|---|---|---|---|
| `contador` | lo que pasó ese día (ventas, turnos, comprobantes) | suma desde el 1° del mes | por mes |
| `nivel` | valor en ese momento (usuarios, productos, MB) | último valor | máximo |

Flags: `visible_cliente` (aparece en el portal del cliente) y `destacada` (columna en la tabla de tenants).
Los límites se cargan en el admin → Planes → Límites del plan.

Claves sugeridas:

- **GestionAR**: `ventas_cantidad`, `ventas_monto`, `ventas_web`, `comprobantes_arca` (contadores); `pedidos_web_pendientes`, `usuarios`, `productos`, `puntos_venta`, `clientes` (niveles). Se cargan con `python manage.py corex_setup gestionar`.
- **Turnos**: `turnos_reservados`, `turnos_cancelados`, `recordatorios_enviados`; `profesionales`, `clientes`.
- **FacturAR**: `comprobantes_emitidos`, `monto_facturado`, `notas_credito`, `comprobantes_rechazados`, `consultas_aidy` (contadores); `facturado_12m`, `tope_monotributo_pct` (%), `clientes`, `puntos_venta`, `usuarios`, `arca_delegacion_activa` (niveles). Se cargan con `python manage.py corex_setup facturar`.
- **StockeAR**: `pedidos`, `visitas_catalogo`; `productos_catalogo`, `compradores`.

---

## 4. Ciclo de vida

```
Cliente contrata ─► Contratación "pendiente" ─► paga (MP) ─► staff "Activar"
                                                           │
                         señal post_save ◄─────────────────┘
                               │
               ┌───────────────┴────────────────┐
         SaaS con API                       SaaS sin API / falla
   POST tenants/ → Tenant "activo"     Tenant "pendiente"/"error"
   URL copiada a la contratación       + tarea interna urgente
               │
   métricas: pull (sync_metricas) y/o push (corex_push_metricas)
               │
   Portal cliente: consumo vs. plan · Panel dev: estado por tenant

Suspender/Baja contratación ─► POST suspender/ ─► el SaaS bloquea (402)
Reactivar ─► POST reactivar/
```
