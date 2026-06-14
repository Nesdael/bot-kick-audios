# 🎵 Bot de Audios para Kick — TutoManX
### v2.0.0

Bot para el canal [kick.com/tutomanx](https://kick.com/tutomanx) que permite reproducir audios en el stream cuando los espectadores escriben comandos en el chat. El panel de administración permite gestionar los sonidos, y el audio se reproduce directamente en OBS usando una Browser Source.

---

## ¿Cómo funciona?

1. Un espectador escribe `!comando` en el chat de Kick.
2. El bot (hospedado en Render) detecta el mensaje en tiempo real vía Pusher WebSocket.
3. El servidor envía una señal a OBS a través de un WebSocket interno.
4. La Browser Source en OBS reproduce el audio del comando.

```
Chat de Kick → Bot en Render → WebSocket → OBS Browser Source → 🔊 Audio en stream
```

---

## Tecnologías utilizadas

| Tecnología | Uso |
|---|---|
| **FastAPI** (Python) | Servidor backend y API REST |
| **Supabase** | Base de datos PostgreSQL + almacenamiento de archivos de audio |
| **Render** | Hosting gratuito del servidor 24/7 |
| **Pusher / Kick WebSocket** | Lectura del chat de Kick en tiempo real |
| **OBS Browser Source** | Reproducción de audio en el stream |
| **Web Audio API** | Amplificación de volumen más allá del 100% |

---

## Características

- **Comandos de chat personalizados** — asigna cualquier comando (`!sonido`, `!risa`, etc.) a cualquier audio
- **Panel de administración web** — sube, edita y elimina sonidos desde el navegador
- **Control de volumen por sonido** — cada audio tiene su propia barra de volumen (0–200%)
- **Volumen global** — controla el volumen general desde el header del panel
- **Cooldown por comando** — evita el spam configurando un tiempo mínimo entre usos
- **Cooldown por rol** — espera diferente según el rol del espectador en Kick
- **Dos roles de panel**
  - 👑 **TutoManX** (admin): puede subir, editar y eliminar sonidos
  - 🛡️ **Moderadores**: pueden subir y editar, pero no eliminar
- **Roles de Kick integrados**
  - 📡 **Broadcaster y Moderadores** — sin restricciones, sin cooldown
  - 💎 **VIP** — acceso a sonidos de subs y VIP, cooldown de 10 segundos
  - ⭐ **Suscriptores** — acceso a sonidos de subs, cooldown de 10 segundos
  - 👤 **Regulares** — solo sonidos sin restricción, cooldown de 60 segundos
- **Sonidos exclusivos** — marca sonidos como "Solo subs ⭐" o "Solo VIP 💎" desde el panel
- **`!sonidos` en el chat** — muestra en el stream todos los comandos disponibles
- **`!sonidosubs` en el chat** — muestra solo los sonidos exclusivos para Subs y VIP
- **Amplificación de audio** — volumen hasta 200% usando la Web Audio API con GainNode
- **Persistencia** — el navegador recuerda el volumen global y el usuario seleccionado
- **Diseño TutoManX** — colores azul y dorado, fondo de circuito, favicon con logo del canal
- **Notificación en stream** — cuando suena un audio aparece una tarjeta arriba a la derecha con el nombre del comando y una barra de progreso que dura lo que dura el sonido
- **Subida masiva** — script `subir_sonidos.py` para cargar cientos de audios de una sola vez

---

## Requisitos previos

Antes de desplegar necesitas tener creadas las siguientes cuentas gratuitas:

- [Render](https://render.com) — para hospedar el servidor
- [Supabase](https://supabase.com) — para la base de datos y el almacenamiento de audios
- [GitHub](https://github.com) — para conectar el repositorio con Render

---

## Configuración inicial

### 1. Supabase — base de datos y almacenamiento

1. Crea un proyecto en Supabase.
2. Ve a **SQL Editor** y ejecuta el contenido de [`supabase_setup.sql`](supabase_setup.sql). Esto crea:
   - La tabla `sounds` con todas las columnas necesarias
   - Un bucket de almacenamiento público llamado `audios`
3. Si ya tenías la tabla sin la columna `volume`, ejecuta también:
   ```sql
   ALTER TABLE sounds ADD COLUMN IF NOT EXISTS volume INTEGER DEFAULT 80;
   ```
4. En **Project Settings → API**, copia:
   - **Project URL** → es tu `SUPABASE_URL`
   - **service_role secret key** → es tu `SUPABASE_SERVICE_KEY`

### 2. Render — servidor en la nube

1. Crea un **Web Service** en Render conectado a este repositorio de GitHub.
2. Configura el comando de inicio:
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
3. En la sección **Environment**, agrega las siguientes variables de entorno:

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SUPABASE_URL` | URL de tu proyecto Supabase | `https://xxxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Clave secreta de Supabase (`sb_secret_...`) | |
| `KICK_CHANNEL` | Nombre del canal de Kick | `tutomanx` |
| `KICK_CHATROOM_ID` | ID del chatroom (evita bloqueos de Cloudflare) | `45621891` |
| `ADMIN_PASSWORD` | Contraseña para el rol TutoManX | |
| `MOD_PASSWORD` | Contraseña para el rol Moderadores | |
| `APP_URL` | URL pública del servicio en Render | `https://tu-app.onrender.com` |

4. Selecciona el plan **Free** y despliega.

> **Nota:** El servidor se mantiene activo con un auto-ping cada 10 minutos para evitar que Render lo duerma.

### 3. OBS — Browser Source

1. En OBS, agrega una nueva fuente de tipo **Navegador** (Browser Source).
2. Configura la URL como:
   ```
   https://tu-app.onrender.com/obs
   ```
3. Dimensiones recomendadas: **1920 × 1080 px**.
4. En las propiedades avanzadas de audio de esa fuente, activa **"Monitor y salida"** para que el audio se escuche tanto en el stream como en tus auriculares.

---

## Uso del panel de administración

Accede en `https://tu-app.onrender.com` e inicia sesión con tu perfil:

- **TutoManX 👑** — acceso completo
- **Moderadores 🛡️** — puede agregar y editar, no eliminar

### Agregar un sonido

1. Escribe el comando (ej. `!risa`) — el `!` se agrega automáticamente si lo omites
2. Ajusta el cooldown en segundos (tiempo mínimo entre usos del mismo comando)
3. Ajusta el volumen del sonido (0–200%)
4. Arrastra o selecciona un archivo de audio (MP3, WAV, OGG — máximo 20 MB)
5. Haz clic en **Subir sonido**

### Probar un sonido

Haz clic en el botón ▶ en la tabla para reproducirlo directamente en OBS sin necesidad de escribirlo en el chat.

### Sonidos exclusivos

En la tabla de sonidos puedes activar dos toggles por sonido:
- **Subs ⭐** — solo suscriptores, VIP, mods y broadcaster pueden usarlo
- **VIP 💎** — solo VIP, mods y broadcaster pueden usarlo

### Comandos disponibles en el chat

| Comando | Resultado |
|---|---|
| `!nombre` | Reproduce el audio asignado a ese comando |
| `!sonidos` | Muestra en el stream los sonidos disponibles para todos |
| `!sonidosubs` | Muestra en el stream los sonidos exclusivos de Subs y VIP |

---

## Estructura del proyecto

```
bot-kick-audios/
├── main.py                 # Servidor FastAPI, bot de Kick, WebSocket, API y proxy de audio
├── requirements.txt        # Dependencias Python
├── supabase_setup.sql      # SQL para crear la base de datos y el storage
├── subir_sonidos.py        # Script para subida masiva de audios
└── static/
    ├── admin.html          # Panel de administración (frontend)
    ├── obs.html            # Página de reproducción para OBS Browser Source
    ├── favicon.png         # Ícono del panel (logo TutoManX)
    └── bg.jpg              # Fondo del panel
```

---

## Endpoints de la API

| Método | Ruta | Descripción | Rol mínimo |
|---|---|---|---|
| `GET` | `/` | Panel de administración | — |
| `GET` | `/obs` | Página para OBS | — |
| `GET` | `/health` | Estado del servidor | — |
| `POST` | `/api/auth` | Verificar contraseña y obtener rol | — |
| `GET` | `/api/sounds` | Listar todos los sonidos | — |
| `POST` | `/api/sounds` | Crear o reemplazar un sonido | mod |
| `PUT` | `/api/sounds/{id}` | Editar comando, cooldown o volumen | mod |
| `DELETE` | `/api/sounds/{id}` | Eliminar un sonido | admin |
| `POST` | `/api/test/{id}` | Probar un sonido en OBS | mod |
| `GET` | `/audio/{filename}` | Proxy de audio (resuelve CORS) | — |
| `WS` | `/ws` | WebSocket para OBS | — |

---

## Solución de problemas comunes

**El bot no se conecta al chat**
- Verifica que `KICK_CHATROOM_ID` esté configurado correctamente en Render.
- El ID del chatroom de TutoManX es `45621891`.

**El audio no se escucha en OBS**
- Asegúrate de que la Browser Source esté usando la URL `/obs` de tu servidor.
- En las propiedades de audio avanzadas de OBS, la fuente debe estar en **"Monitor y salida"**, no en "Monitorización desactivada".

**El volumen se escucha bajo aunque esté al 200%**
- El archivo de audio en sí puede tener un volumen bajo. El 200% amplifica, pero si la grabación original es muy baja hay un límite físico.
- Prueba con la amplificación adicional de OBS en el filtro de audio de la fuente.

**Error al subir un audio**
- Verifica que el archivo no supere 20 MB.
- Solo se aceptan formatos MP3, WAV, OGG y M4A.

**Un usuario regular no puede usar ningún sonido**
- Verifica que el sonido no tenga activado "Solo subs ⭐" o "Solo VIP 💎".
- El cooldown de 60 segundos por usuario es global — si alguien usó un sonido hace menos de un minuto, debe esperar.

**La notificación o el panel de sonidos no aparecen en OBS**
- Refresca la caché de la Browser Source en OBS: clic derecho → Propiedades → "Actualizar caché de la página actual".
- Verifica que la Browser Source tenga dimensiones **1920 × 1080 px**.

---

## Licencia

Proyecto privado para uso exclusivo del canal [kick.com/tutomanx](https://kick.com/tutomanx).
