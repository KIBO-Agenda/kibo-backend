# Requisitos de calidad

### 1. Descripción del producto en desarrollo

- **Tipo:** Plataforma PWA de Gestión de Citas (Micro-SaaS B2B Multi-tenant).
- **Objetivo:** Proporcionar una herramienta extremadamente simple y *mobile-first* para que pequeños negocios de servicios (barberías, spas) gestionen sus agendas, eviten dobles reservas y generen recordatorios manuales por WhatsApp. Todo bajo un modelo de suscripción mensual de bajo costo, eliminando la fricción de herramientas corporativas complejas.
- **Usuarios principales:**
    - **Dueño/Administrador (Tenant Owner):** Gestiona la configuración del negocio, paga la suscripción, ve la agenda global y administra a los empleados.
    - **Staff/Empleado (Tenant User):** Accede únicamente a su propia agenda diaria para registrar y gestionar sus citas.
    - **Administrador SuperUser (Tú):** Gestiona la plataforma, monitorea negocios activos y suspende cuentas por falta de pago a través de un panel interno.
- **Flujo principal (Gestión de Cita):**
Cliente contacta al negocio vía WhatsApp → .Empleado/Dueño abre la PWA → Toca el botón flotante (+) → **Selecciona hora, cliente y servicio** → PWA verifica disponibilidad cruzada → Cita registrada → PWA genera enlace de recordatorio de WhatsApp (wa.me) → Empleado envía el mensaje al cliente con un clic.

### 2. Características de calidad / criterios de aceptación

| Característica | Subcaracterística | Criterio de aceptación |
| --- | --- | --- |
| **Usabilidad** | Accesibilidad Mobile-First | El flujo crítico (crear una cita) debe poder realizarse con una sola mano en dispositivos móviles (botones accesibles en la zona inferior) en un máximo de 3 interacciones (clics/taps). |
| **Seguridad** | Aislamiento Multi-tenant | Un empleado del "Negocio A" no puede consultar, modificar ni inferir información de citas, clientes o configuraciones del "Negocio B" bajo ninguna circunstancia. |
| **Eficiencia** | Tiempo de respuesta | Las consultas a la agenda diaria (el endpoint más crítico) deben resolverse en el backend (FastAPI) en < 150 milisegundos para garantizar una experiencia fluida tipo app nativa. |
| **Fiabilidad** | Prevención de Colisiones | El sistema de base de datos debe utilizar **restricciones nativas de PostgreSQL (`EXCLUDE USING gist`) con rangos de tiempo (`tsrange`)** para evitar a nivel de base de datos que existan citas duplicadas o condiciones de carrera en el mismo bloque horario del mismo especialista. |
| **Modelo de Negocio** | Bloqueo por Suscripción | Si el estado de pago del Tenant pasa a `vencido`, cualquier petición a la API (excepto el login y la pantalla de pago) debe retornar un HTTP 402 (Payment Required), bloqueando el uso operativo de la agenda. |

### 3. Requisitos Funcionales – Solución PWA Micro-SaaS

### RF01 - Autenticación Multi-Tenant, RBAC y Gestión Segura de Sesiones

**Descripción:** El sistema debe autenticar a los dueños y empleados de los negocios, garantizando el aislamiento de datos entre Tenants y restringiendo las acciones según el rol (Dueño vs. Staff).
**Proceso:**

1. El usuario ingresa credenciales en la PWA.
2. FastAPI valida el hash (Bcrypt) y el estado del negocio (activo/suspendido).
3. Se emiten dos tokens: Access Token (JWT, corta duración, con `user_id`, `tenant_id` y `role`) y Refresh Token (Cookie HttpOnly).
**Criterios de aceptación:**
- **CA01 (Aislamiento):** Toda consulta SQL operativa DEBE filtrar por el `tenant_id` del JWT. Para garantizar el rendimiento a medida que escalan los tenants, es estrictamente obligatorio crear un `INDEX` en la columna `tenant_id` en todas las tablas operativas críticas (`appointments`, `clients`, `users`, `services`)
- **CA02 (Roles):** Un usuario con rol `staff` solo puede consultar las citas asociadas a su `user_id`. Un usuario con rol `owner` puede consultar las citas de cualquier `user_id` dentro de su `tenant_id`.

### RF02 - Gestión de Agenda y Control de Colisiones

**Descripción:** El núcleo del sistema. Permite visualizar, crear, reprogramar y cancelar citas, asegurando que no existan reservas dobles para un mismo especialista.
**Proceso:**

1. El usuario visualiza la agenda (Día/Semana).
2. Selecciona un bloque o usa el botón rápido (+).
3. Ingresa datos del cliente (autocompletado si ya existe) y selecciona el servicio (que define la duración).
4. El backend calcula el bloque de tiempo (ej. 10:00 AM a 10:45 AM) y verifica disponibilidad.
**Criterios de aceptación:**
- **CA01 (Validación de Disponibilidad):** Antes de insertar la cita, FastAPI debe validar que no exista superposición de horarios para ese empleado en específico. Si la hay, retorna un HTTP 409 (Conflict).
- **CA02 (Estados de Cita):** Las citas deben transicionar estrictamente entre estos estados: `pendiente` → `confirmada` → `atendida` (o `cancelada`).
- **CA03 (Métricas Rápidas):** El endpoint de la agenda diaria debe devolver, además de la lista de citas, un resumen sumarizado: Total citas, Atendidas, Ingresos proyectados del día (solo visible para el `owner`).

### RF03 - Motor Generador de Recordatorios (WhatsApp Manual)

**Descripción:** Para mantener la simplicidad y bajo costo, el sistema no usará la API oficial de WhatsApp. Generará mensajes pre-formateados con enlaces profundos (`wa.me`) para que el usuario los envíe desde su propia app de WhatsApp.
**Proceso:**

1. En el detalle de una cita, el usuario presiona el botón "Enviar Recordatorio".
2. El frontend toma los datos de la cita y la configuración de plantillas del negocio.
3. Se genera una URL codificada: `https://wa.me/573000000000?text=Hola%20[Nombre]...`**Criterios de aceptación:**
- **CA01 (Plantillas Dinámicas):** El sistema debe reemplazar variables como `{{nombre_cliente}}`, `{{hora}}`, `{{fecha}}` y `{{servicio}}` antes de generar el enlace.
- **CA02 (Detección de Móvil):** Al hacer clic en el botón, el sistema debe intentar abrir directamente la aplicación nativa de WhatsApp en el celular del usuario.

### RF04 - Gestión de Clientes (Mini-CRM) y Lista de Espera

**Descripción:** Registro centralizado de clientes por negocio para ver historial de visitas y gestionar cancelaciones.
**Criterios de aceptación:**

- **CA01 (Creación Implícita):** Si al crear una cita se ingresa un número de teléfono que no existe en el `tenant_id`, el sistema debe crear automáticamente el registro del cliente en la base de datos sin pasos extra.
- **CA02 (Lista de Espera):** Debe existir una cola simple donde el usuario pueda anotar "Nombre - Teléfono - Día de interés". Si una cita se cancela en ese día, la PWA debe mostrar una alerta visual sugiriendo a la persona en la lista de espera.

**RF05 - Configuración de duración de agenda (Time Slots)Descripción:** El sistema debe permitir al dueño del negocio configurar los bloques de tiempo estándar bajo los cuales opera la agenda, simplificando el cálculo de disponibilidad en el frontend y backend.
**Proceso:**

1. En el panel de configuración, el dueño define la duración de los bloques de tiempo (ej. 15, 30 o 60 minutos).
2. La base de datos almacena este valor en la tabla de configuración del tenant (`slot_duration`).
3. El frontend utiliza este valor para renderizar la grilla de la agenda (ej. saltos de 09:00, 09:15, 09:30).
**Criterios de aceptación:**
- **CA01 (Estandarización de grilla):** Todas las citas creadas deben ajustarse (snap) a los múltiplos de tiempo definidos por el `slot_duration` del negocio.
- **CA02 (Cálculo de disponibilidad):** El backend utilizará este `slot_duration` junto con la duración del servicio seleccionado para calcular cuántos "bloques" ocupará una cita en la base de datos.