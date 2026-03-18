# Contexto Completo De API Para Frontend (IA Agent)

## 1. Estado Del Backend
El backend puede considerarse completo para el proposito actual de la aplicacion.

Modulos disponibles en API:
1. `auth`
2. `super_admin`
3. `tenant`
4. `payments`
5. `users`
6. `clients`
7. `services`
8. `appointments`

Prefijo base de API:
- `API_V1_PREFIX`: `"/api/v1"`
- Base real de endpoints: `/<host>/api/v1/...`

Healthcheck:
- `GET /health`
- Respuesta: `{ "status": "ok" }`

## 2. Modelo De Autenticacion Y Autorizacion

### 2.1 Tipos de token
Existen dos contextos de autenticacion:
1. `super_admin` token
2. `tenant_user` token

Claims relevantes del JWT:
1. `sub`: id del usuario autenticado
2. `tenant_id`: solo en token de tenant user
3. `role`: `owner` o `staff` para tenant users
4. `scope`: `"super_admin"` o `"tenant_user"`
5. `exp`: expiracion

### 2.2 Header requerido
Para endpoints protegidos:
- `Authorization: Bearer <access_token>`

Errores comunes por auth:
1. `401 Missing or invalid authorization header`
2. `401 Invalid token`
3. `401 Token missing tenant_id`
4. `403 Super admin access required`
5. `403 Owner role required`
6. `401 User not found or inactive`

### 2.3 Reglas por rol tenant
1. `owner`
- Puede gestionar `services` (crear, actualizar, borrar logico).
- Puede gestionar appointments de cualquier usuario del mismo tenant.

2. `staff`
- Puede consultar `services`.
- En `appointments` solo puede ver/crear/editar/cancelar los suyos.
- No puede reasignar citas a otro usuario.

## 3. Enums Del Dominio

### 3.1 UserRole
Valores:
1. `owner`
2. `staff`

### 3.2 SubscriptionStatus
Valores:
1. `active`
2. `past_due`
3. `suspended`

### 3.3 AppointmentStatus
Valores:
1. `pending`
2. `confirmed`
3. `attended`
4. `cancelled`

## 4. Contrato De Endpoints

## 4.1 Auth

### 4.1.1 Login tenant user
- `POST /api/v1/auth/login`
- Auth: no requiere token

Request body:
```json
{
  "email": "user@example.com",
  "password": "string"
}
```

Response 200:
```json
{
  "access_token": "jwt",
  "refresh_token": "jwt",
  "token_type": "bearer"
}
```

Errores relevantes:
1. `401 Invalid credentials`
2. `403 User is inactive`

### 4.1.2 Login super admin
- `POST /api/v1/auth/super-admin/login`
- Auth: no requiere token

Request body:
```json
{
  "email": "admin@example.com",
  "password": "string"
}
```

Response 200 igual a login tenant.

Errores:
1. `401 Invalid credentials`

### 4.1.3 Forgot password (email)
- `POST /api/v1/auth/forgot-password`
- Auth: no requiere token

Request body:
```json
{
  "email": "user@example.com"
}
```

Response 200:
```json
{
  "message": "If the email exists, a recovery link has been sent"
}
```

Nota:
1. Responde 200 aun cuando el email no exista (evita enumeracion de usuarios).

### 4.1.4 Reset password (JWT)
- `POST /api/v1/auth/reset-password`
- Auth: no requiere token de sesion

Request body:
```json
{
  "token": "jwt_password_reset",
  "new_password": "NuevaClave123!"
}
```

Response 200:
```json
{
  "message": "Password updated successfully"
}
```

Errores:
1. `400 Invalid reset token`
2. `400 Invalid reset token type`
3. `404 User not found` / `404 Super admin not found`
4. `422 Password must be at least 8 characters`

### 4.1.5 Change password (convencional)
- `POST /api/v1/auth/change-password`
- Auth: requiere `Authorization: Bearer <access_token>`

Request body:
```json
{
  "current_password": "Actual123!",
  "new_password": "Nueva123!"
}
```

Response 200:
```json
{
  "message": "Password changed successfully"
}
```

Errores:
1. `401 Current password is incorrect`
2. `401 Missing or invalid authorization header`
3. `422 Password must be at least 8 characters`

## 4.2 Super Admin

### 4.2.1 Crear super admin
- `POST /api/v1/super-admins`
- Auth: actualmente no protegido (uso inicial/bootstrap)

Request body:
```json
{
  "name": "Nombre",
  "email": "admin@example.com",
  "password": "min 8 chars"
}
```

Response 201:
```json
{
  "id": "uuid",
  "name": "Nombre",
  "email": "admin@example.com",
  "created_at": "datetime"
}
```

### 4.2.2 Listar super admins
- `GET /api/v1/super-admins`
- Auth: actualmente no protegido

Response 200: `SuperAdminResponse[]`

## 4.3 Tenants
Todos los endpoints de `tenants` requieren token `super_admin`.

### 4.3.1 Crear tenant
- `POST /api/v1/tenants`

Request body:
```json
{
  "name": "Negocio",
  "phone": "string opcional",
  "slot_duration": 15
}
```

Validaciones:
1. `slot_duration` entre `5` y `120`.

Response 201 (`TenantResponse`):
```json
{
  "id": "uuid",
  "name": "Negocio",
  "phone": "string|null",
  "subscription_status": "active|past_due|suspended",
  "subscription_valid_until": "datetime",
  "slot_duration": 15,
  "created_at": "datetime"
}
```

Regla de negocio:
1. Se crea con trial inicial de 30 dias.

### 4.3.2 Obtener tenant
- `GET /api/v1/tenants/{tenant_id}`
- Response 200: `TenantResponse`
- Error: `404 Tenant not found`

### 4.3.3 Listar tenants
- `GET /api/v1/tenants`
- Response 200: `TenantResponse[]`

### 4.3.4 Actualizar tenant
- `PATCH /api/v1/tenants/{tenant_id}`

Request body (`TenantUpdate`):
```json
{
  "name": "opcional",
  "phone": "opcional",
  "slot_duration": 30
}
```

Response 200: `TenantResponse`

## 4.4 Payments
Endpoints tenant-scoped (`tenant_id` tomado del JWT).

### 4.4.1 Registrar pago
- `POST /api/v1/payments`
- Auth: tenant user token

Request body:
```json
{
  "amount": 50000.00,
  "payment_method": "Cash",
  "reference_code": "opcional"
}
```

Response 201 (`PaymentResponse`):
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "amount": 50000.00,
  "payment_date": "datetime",
  "payment_method": "Cash",
  "reference_code": "string|null"
}
```

Reglas de negocio:
1. Si `reference_code` se repite: `409`.
2. Al registrar pago, extiende subscription `+30 dias`.

Errores:
1. `404 Tenant not found`
2. `409 Payment with this reference code already exists`

### 4.4.2 Listar pagos
- `GET /api/v1/payments`
- Auth: tenant user
- Response 200: `PaymentResponse[]`

## 4.5 Users
Tenant-scoped (`tenant_id` sale del token).

### 4.5.1 Crear usuario
- `POST /api/v1/users`
- Auth: tenant user token

Request body:
```json
{
  "email": "staff@example.com",
  "name": "Nombre",
  "password": "min 8",
  "role": "owner|staff"
}
```

Response 201 (`UserResponse`):
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Nombre",
  "email": "staff@example.com",
  "role": "owner|staff",
  "is_active": true,
  "created_at": "datetime"
}
```

Notas de implementacion actual:
1. El endpoint no exige `owner` explicitamente a nivel de dependencia.
2. Si el frontend quiere politicas estrictas, debe ocultar UI segun `role`.

### 4.5.2 Obtener usuario
- `GET /api/v1/users/{user_id}`
- Response 200: `UserResponse`
- Error: `404 User not found`

### 4.5.3 Listar usuarios
- `GET /api/v1/users`
- Response 200: `UserResponse[]`

### 4.5.4 Actualizar usuario
- `PATCH /api/v1/users/{user_id}`

Request body:
```json
{
  "name": "opcional",
  "role": "owner|staff (opcional)",
  "is_active": true
}
```

Response 200: `UserResponse`

### 4.5.5 Eliminar usuario (soft delete)
- `DELETE /api/v1/users/{user_id}`
- Response 204
- Efecto: `is_active=false` (no hard delete)

## 4.6 Clients
Tenant-scoped por token.

### 4.6.1 Crear client
- `POST /api/v1/clients`

Request body:
```json
{
  "name": "Cliente",
  "phone": "3110001111",
  "notes": "opcional"
}
```

Response 201 (`ClientResponse`):
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Cliente",
  "phone": "3110001111",
  "notes": "opcional",
  "created_at": "datetime"
}
```

Reglas:
1. Telefono unico por tenant.

Errores:
1. `409 Client phone already exists for this tenant`

### 4.6.2 Obtener client
- `GET /api/v1/clients/{client_id}`
- Response 200: `ClientResponse`
- Error: `404 Client not found`

### 4.6.3 Listar clients
- `GET /api/v1/clients`
- Response 200: `ClientResponse[]`

### 4.6.4 Actualizar client
- `PATCH /api/v1/clients/{client_id}`

Request body:
```json
{
  "name": "opcional",
  "phone": "opcional",
  "notes": "opcional"
}
```

Response 200: `ClientResponse`

### 4.6.5 Eliminar client
- `DELETE /api/v1/clients/{client_id}`
- Response 204
- En este caso es hard delete.

## 4.7 Services
Tenant-scoped por token.

### 4.7.1 Crear service (solo owner)
- `POST /api/v1/services`
- Auth: requiere `owner`

Request body:
```json
{
  "name": "Corte Clasico",
  "duration": 45,
  "price": 25000.00
}
```

Response 201 (`ServiceResponse`):
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Corte Clasico",
  "duration": 45,
  "price": 25000.00,
  "is_active": true,
  "created_at": "datetime"
}
```

Error de autorizacion:
1. `403 Owner role required`

### 4.7.2 Obtener service
- `GET /api/v1/services/{service_id}`
- Auth: tenant user (owner o staff)
- Response 200: `ServiceResponse`

### 4.7.3 Listar services
- `GET /api/v1/services?only_active=false`
- Auth: tenant user
- Query param:
1. `only_active` (bool, opcional, default `false`)

Response 200: `ServiceResponse[]`

### 4.7.4 Actualizar service (solo owner)
- `PATCH /api/v1/services/{service_id}`

Request body:
```json
{
  "name": "opcional",
  "duration": 60,
  "price": 30000.00
}
```

Response 200: `ServiceResponse`

### 4.7.5 Borrado logico service (solo owner)
- `DELETE /api/v1/services/{service_id}`
- Response 204
- Efecto: `is_active=false`

## 4.8 Appointments
Tenant-scoped por token + reglas owner/staff.

### 4.8.1 Crear appointment
- `POST /api/v1/appointments`

Request body:
```json
{
  "client_id": "uuid",
  "user_id": "uuid",
  "service_id": "uuid",
  "appointment_date": "YYYY-MM-DD",
  "time_start": "HH:MM:SS",
  "notes": "opcional"
}
```

Response 201 (`AppointmentResponse`):
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "client_id": "uuid",
  "user_id": "uuid",
  "service_id": "uuid",
  "appointment_date": "YYYY-MM-DD",
  "time_start": "HH:MM:SS",
  "time_end": "HH:MM:SS",
  "status": "pending|confirmed|attended|cancelled",
  "notes": "opcional",
  "created_at": "datetime"
}
```

Reglas de negocio:
1. `time_end` se calcula automaticamente con `service.duration`.
2. Si hay solapamiento de horario para el mismo `user_id` y fecha: `409`.
3. `staff` solo puede crear cita para si mismo (`user_id` propio).

Errores comunes:
1. `404 Client not found`
2. `404 Assigned user not found`
3. `404 Service not found or inactive`
4. `403 Staff can only manage their own appointments`
5. `409 Appointment overlaps with existing schedule`

### 4.8.2 Obtener appointment
- `GET /api/v1/appointments/{appointment_id}`

Reglas:
1. `owner` puede ver cualquier cita del tenant.
2. `staff` solo sus citas.

Errores:
1. `404 Appointment not found`
2. `403 Staff can only access their own appointments`

### 4.8.3 Listar appointments
- `GET /api/v1/appointments?appointment_date=YYYY-MM-DD`
- Query opcional:
1. `appointment_date`

Reglas:
1. `owner`: lista del tenant.
2. `staff`: lista solo de su `user_id`.

Response 200: `AppointmentResponse[]`

### 4.8.4 Actualizar appointment
- `PATCH /api/v1/appointments/{appointment_id}`

Request body:
```json
{
  "client_id": "uuid opcional",
  "user_id": "uuid opcional",
  "service_id": "uuid opcional",
  "appointment_date": "YYYY-MM-DD opcional",
  "time_start": "HH:MM:SS opcional",
  "status": "pending|confirmed|attended|cancelled opcional",
  "notes": "opcional"
}
```

Reglas:
1. Recalcula `time_end` con la duracion del service final.
2. Vuelve a validar solapamientos.
3. `staff` no puede reasignar appointment a otro user.
4. `staff` solo puede actualizar sus citas.

Errores:
1. `403 Staff can only manage their own appointments`
2. `403 Staff cannot reassign appointments`
3. `409 Appointment overlaps with existing schedule`

### 4.8.5 Cancelar appointment
- `DELETE /api/v1/appointments/{appointment_id}`
- Response 204

Regla:
1. No elimina fila; cambia estado a `cancelled`.
2. `staff` solo puede cancelar sus citas.

## 5. Mapeo De Pantallas Frontend Recomendado

### 5.1 Pantalla login
1. Selector de contexto:
- Login tenant user: `POST /auth/login`
- Login super admin: `POST /auth/super-admin/login`

2. Guardar en cliente:
- `access_token`
- `refresh_token`
- `token_type`

### 5.2 Panel super admin
1. Gestion tenants: `POST/GET/PATCH /tenants`
2. Historial admins: `GET /super-admins`

### 5.3 Panel tenant owner
1. Usuarios: CRUD `users`
2. Clientes: CRUD `clients`
3. Servicios: CRUD `services` (incluye soft delete)
4. Agenda: CRUD `appointments` sobre owner y staff
5. Pagos: `POST/GET /payments`

### 5.4 Panel tenant staff
1. Clientes: CRUD `clients` (actual implementacion permite)
2. Servicios: solo lectura (`GET`)
3. Agenda: solo citas propias (`appointments`)
4. Pagos: actual implementacion permite endpoint con token tenant user

## 6. Criterios De UI Para IA Agent

### 6.1 Deteccion de rol
El frontend debe leer `role` del JWT (`owner` o `staff`) para render condicional de UI:
1. Mostrar gestion de servicios solo si `role=owner`.
2. En formularios de citas, para `staff` fijar `user_id` al propio.
3. En listados de citas, confiar en backend para filtro final, pero mantener UX coherente por rol.

### 6.2 Manejo de errores
Mapeo recomendado:
1. `401`: forzar relogin / token expirado
2. `403`: mostrar "No tienes permisos"
3. `404`: recurso no encontrado
4. `409`: conflicto de negocio (duplicado, solapamiento)
5. `422`: errores de validacion de payload

### 6.3 Formatos
1. UUID siempre como string.
2. `date` en formato `YYYY-MM-DD`.
3. `time` en formato `HH:MM:SS`.
4. `datetime` ISO string.
5. Decimal en JSON como numero o string parseable.

## 7. Ejemplos Rapidos De Flujo

### 7.1 Flujo owner para crear cita de un staff
1. Login owner -> token
2. `GET /users` para obtener `staff.id`
3. `GET /clients` o `POST /clients`
4. `GET /services?only_active=true`
5. `POST /appointments` con `user_id=staff.id`

### 7.2 Flujo staff para gestionar su agenda
1. Login staff -> token
2. `GET /appointments?appointment_date=...`
3. `POST /appointments` con `user_id` propio
4. `PATCH /appointments/{id}` solo de citas propias
5. `DELETE /appointments/{id}` para cancelar propias

## 8. Notas Tecnicas Importantes Para El Agente Frontend
1. El backend ya impone aislamiento por tenant en repositorio/servicio.
2. En `appointments`, la validacion de solape es server-side.
3. `services` usa borrado logico, por eso conviene usar `only_active=true` en vistas operativas.
4. `users` y `payments` hoy aceptan cualquier token tenant_user; si se requiere restriccion fuerte solo-owner, se puede reforzar luego en router con `require_owner`.
5. Siempre enviar `Authorization` en cada request protegido.

## 9. Checklist De Integracion Frontend
1. Centralizar cliente HTTP con interceptor de token.
2. Decodificar JWT para `scope`, `role`, `tenant_id`, `sub`.
3. Rutas protegidas por scope:
- super admin area (`scope=super_admin`)
- tenant area (`scope=tenant_user`)
4. Feature flags por role para vistas owner/staff.
5. Formularios con validacion espejo a backend (min/max, required).
6. Manejo de `409` con mensajes de negocio (cita solapada, telefono duplicado, referencia pago duplicada).

---
Documento generado sobre la implementacion real actual de rutas, schemas, dependencias y servicios.
