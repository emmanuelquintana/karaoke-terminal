# Desplegar en Vercel con Neon

Esta guía describe la configuración revisada y probada para publicar el proyecto.
Los informes de las revisiones y sus registros se conservan localmente; no se
incluyen credenciales ni transcripciones internas en el repositorio público.

La interfaz React se publica en Vercel. El servidor Flask se ejecuta en Docker
con FFmpeg y un disco persistente. Neon guarda las sesiones, las letras ajustadas
por la sincronización y las referencias de los MP4 exportados. Los archivos de
audio y video se guardan en el disco del servidor.

Esta separación conserva el reproductor y el estudio: las peticiones largas y
los archivos multimedia van directamente al backend, sin pasar por funciones o
proxies de Vercel. El servidor actual necesita procesos, archivos y estado que
no se conservan automáticamente entre invocaciones de funciones.

## 1. Crear la base de datos en Neon

1. Crea un proyecto en [Neon](https://console.neon.tech).
2. En **Connect**, copia la cadena PostgreSQL con **Connection pooling** activo.
   Conserva los parámetros que entregue Neon. La aplicación exige
   `verify-full`: valida el certificado de la CA y el nombre del servidor,
   utilizando las CA del sistema del contenedor.
3. Guarda esa cadena como `DATABASE_URL` **solo en el backend**. Ejemplo:

   ```text
   postgresql://USER:PASSWORD@HOST-pooler.REGION.aws.neon.tech/neondb?sslmode=verify-full&sslrootcert=system
   ```

El contenedor crea automáticamente `karaoke_studio_sessions` y
`karaoke_studio_exports` al arrancar, sin borrar tablas ni datos existentes.
El usuario de la conexión debe tener permiso para crear esas tablas. Si Neon no
está disponible, el arranque falla; no cambia silenciosamente a memoria.

## 2. Desplegar el backend

Sube estos cambios a tu repositorio. En [Render](https://dashboard.render.com),
crea un **Blueprint** desde el repositorio y usa `render.yaml`.

La plantilla crea **un servicio Standard de pago y un disco de 10 GB**, para
procesar video con más memoria que un servicio básico. Revisa el costo en Render
antes de crear el servicio. Puedes usar el mismo Dockerfile en otro servidor con
un volumen persistente montado en `/data`.

Registra primero un método de pago en **Billing** de Render. Sin él, la API
rechaza la creación con `Payment information is required to complete this request`.
El plan gratuito no admite el disco persistente necesario para conservar los medios.

Configura las variables que pide el Blueprint:

| Variable del backend | Valor |
| --- | --- |
| `DATABASE_URL` | Cadena de Neon del paso 1 |
| `FRONTEND_ORIGINS` | Origen de la web: `https://tu-proyecto.vercel.app` |

El resto de variables del servidor tienen estos valores predeterminados:

| Variable | Valor y propósito |
| --- | --- |
| `KARAOKE_DATA_DIR` | `/data`; debe coincidir con el disco persistente |
| `IMAGEIO_FFMPEG_EXE` | `/usr/bin/ffmpeg`; usa el binario del sistema instalado en Docker |
| `SSL_CERT_FILE` | `/etc/ssl/certs/ca-certificates.crt`; bundle de CA explícito para OpenSSL de psycopg-binary |
| `PORT` | Render lo inyecta; fuera de Render el contenedor escucha en `8000` |
| `PGSSLROOTCERT` | Opcional: archivo de una CA privada; si no se indica, usa las CA del sistema |

Para una CA privada también puedes indicar `sslrootcert=/ruta/ca.pem` dentro de
`DATABASE_URL`; tiene prioridad sobre `PGSSLROOTCERT`. El archivo debe existir
en el backend y el nombre del servidor debe coincidir con su certificado. No
desactives TLS para solucionar un error de certificados.

`FRONTEND_ORIGINS` admite varios orígenes separados por comas, sin rutas:
`https://tu-proyecto.vercel.app,https://musica.tudominio.com`.
Si todavía no conoces el dominio definitivo, configúralo después del paso 3.
Las previews de Vercel necesitan agregar su origen exacto; no se autoriza todo
`*.vercel.app`.

Cuando el backend termine, abre:

```text
https://DOMINIO-REAL-DEL-BACKEND/api/v1/health
```

Debe responder JSON con `data.status` igual a `ok`. La documentación Swagger
queda en `https://DOMINIO-REAL-DEL-BACKEND/api/v1/docs`.

El Dockerfile incluye FFmpeg, fuentes para Linux, Deno y los componentes de
JavaScript de yt-dlp. Los procesos que atienden peticiones usan un usuario sin
privilegios. `KARAOKE_DATA_DIR=/data` mantiene las cachés en el disco persistente.

## 3. Desplegar la web en Vercel

1. Importa el mismo repositorio en [Vercel](https://vercel.com/new).
2. **Root Directory:** raíz del repositorio (`.`), **no `web`**.
3. El archivo `vercel.json` configura Vite, `npm ci`,
   `npm run build -- --mode vercel` y la salida `web/dist`. El modo explícito
   genera assets en `/assets/` aunque hayas deshabilitado las variables de
   sistema de Vercel. No necesitas instalar Python en Vercel.
4. Agrega esta variable en **Production** y, si usarás previews, en **Preview**:

   ```text
   VITE_API_ORIGIN=https://DOMINIO-REAL-DEL-BACKEND
   ```

   Usa solo el origen HTTPS, sin `/api/v1`. No pongas `DATABASE_URL` ni contraseñas
   en variables `VITE_*`: sus valores se incluyen en el JavaScript público.
5. Después de aprobar la publicación, despliega. Si falta `VITE_API_ORIGIN`, el
   build se detiene con una explicación. Para una primera revisión remota puedes
   usar un despliegue Preview desde una rama distinta de producción; recuerda
   autorizar su origen exacto en el backend. Importar y desplegar la rama de
   producción publica esa versión: no lo hagas antes de revisar los resultados.
6. Copia el dominio real que asignó Vercel y actualiza `FRONTEND_ORIGINS` en Render.
   Espera a que se aplique el cambio antes de probar la web.

Vite integra las variables durante el build. Si cambias `VITE_API_ORIGIN`, debes
hacer **Redeploy** en Vercel. Cambiar solo la variable no modifica builds previos.

## 4. Comprobar el despliegue

- Abre la web de Vercel y carga artista/canción: deben aparecer letras y portada.
- Reproduce audio y salta a otro segundo para comprobar las peticiones `Range`.
- Prepara un video en Estudio, sincroniza, exporta un clip corto y descárgalo.
- Con una sesión preparada, reinicia el backend y vuelve a previsualizar o
  exportar sin recargar la página. Neon recupera la sesión y `/data` el video.
- En Network del navegador, `/api/v1/...`, audio, portadas, videos y descargas
  deben apuntar al dominio del backend. Los assets de la web apuntan a Vercel.

## Desarrollo local

El funcionamiento local conserva el mismo origen y la persistencia en memoria
si no configuras `DATABASE_URL`:

```powershell
python -m pip install -r requirements-server.txt
npm ci
npm run build
python karaoke_web.py --no-open
```

Para desarrollar con Vite, ejecuta además `npm run dev`: `/api` se reenvía al
Flask de `127.0.0.1:8765`. Para usar un backend remoto, copia `.env.example` a
`.env.local` en la raíz, cambia `VITE_API_ORIGIN` y autoriza en el backend el
origen local que imprima Vite.

Para probar Docker, copia `.env.server.example` a `.env.server`, completa los
datos reales y ejecuta:

```powershell
docker build -t karaoke-api .
docker run --rm -p 8000:8000 --env-file .env.server --mount source=karaoke-media,target=/data karaoke-api
```

Para usar Neon sin Docker, exporta `DATABASE_URL` y ejecuta
`python studio_store.py` antes de iniciar Flask. Instala `requirements-asr.txt`
por separado si necesitas el ASR opcional de Whisper; la imagen base conserva
la sincronización por audio, captions y estimación.

Pruebas:

```powershell
npm test
python -m unittest -q
npm run build
```

La prueba opcional de persistencia real se activa configurando
`TEST_DATABASE_URL` con una base PostgreSQL de pruebas que acepte TLS y ejecutando
`python -m unittest test_studio_store -q`. Crea únicamente las tablas del estudio
y elimina las filas que ella misma genere. Para una CA privada incluye
`sslrootcert` en esa URL; también se comprueba el hostname.

Para repetir la integración completa sin cuentas cloud, necesitas Docker activo:

```powershell
$env:RUN_DOCKER_TESTS = "1"
python -m unittest test_docker_deployment -v
Remove-Item Env:\RUN_DOCKER_TESTS
```

La prueba crea una red, volúmenes, PostgreSQL con TLS y un backend aislados, y
los elimina al terminar. Genera audio/video sintéticos con FFmpeg, prepara y
sincroniza una sesión, exporta un MP4, reemplaza el contenedor y verifica el
audio, video y MP4 recuperados, sus peticiones `Range`, CORS, limpieza de
temporales y rechazo de CA/hostname incorrectos. Solo sustituye la consulta de
portada a iTunes; no prueba la descarga real de YouTube ni Whisper. También
ejecuta la suite SQL con PostgreSQL real y comprueba con `ffprobe` el formato,
codecs, dimensiones y duración del MP4.

`npm run check` también compila y reemplaza `web/dist`: no es un chequeo sin
escrituras. Antes de publicar usa el comando de build de Vercel indicado arriba.

## Límites que siguen dependiendo de servicios externos

YouTube puede bloquear descargas desde IPs de datacenter. Neon y Vercel no
eliminan ese bloqueo. Si aparece una verificación de YouTube, puedes ejecutar
este mismo backend en tu PC con `serve_public.ps1`, configurar
`FRONTEND_ORIGINS` con el dominio de Vercel y usar la URL HTTPS del túnel como
`VITE_API_ORIGIN`. La PC debe seguir encendida y una URL de túnel temporal puede
cambiar. Para producción usa un túnel con dominio fijo o un servidor cuya salida
de red permita las descargas.

Mantén una sola instancia del backend mientras los archivos estén en un disco
local. Neon permite recuperar metadatos, pero no replica `/data` a otros
servidores. No borres el disco si quieres conservar videos y exportaciones.
Los segmentos, imágenes y listas temporales de cada exportación se eliminan al
terminar, incluso si FFmpeg falla. Los audios, videos fuente y MP4 finales se
conservan. Vigila el espacio: esas cachés persistentes no tienen caducidad
automática. Cambiar `/data` por otro punto de montaje requiere migrar también
las rutas almacenadas en Neon.

El propietario confirmó que el acceso público es intencional: no hay login ni
API key. CORS restringe qué
sitios pueden leerla desde un navegador; no es autenticación ni impide llamadas
desde otros clientes. Un despliegue público puede consumir CPU, red y disco.
La API limita el cuerpo de las solicitudes a 64 KiB. La configuración tiene un
worker y cuatro hilos; cuatro trabajos largos simultáneos pueden ocuparlos.
No implica capacidad ilimitada ni incluye rate limiting.

Referencias: [Vercel Functions](https://vercel.com/docs/functions/limitations),
[Neon con Python](https://neon.com/docs/guides/python),
[Docker en Render](https://render.com/docs/docker),
[discos persistentes](https://render.com/docs/disks).
