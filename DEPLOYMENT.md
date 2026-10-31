# Desplegar gratis en Vercel, Neon y Render

Esta guía describe la configuración revisada y probada para publicar el proyecto.
Los informes de las revisiones y sus registros se conservan localmente; no se
incluyen credenciales ni transcripciones internas en el repositorio público.

La interfaz React se publica en Vercel Hobby. El servidor Flask se ejecuta en
Render Free con Docker y FFmpeg. Neon Free guarda las sesiones, las letras
ajustadas y las referencias de las exportaciones. Vercel Blob Hobby conserva
los archivos de audio y video; el disco de Render es una caché temporal.

Esta separación conserva el reproductor y el estudio: las peticiones largas y
los archivos multimedia van directamente al backend, sin pasar por funciones o
proxies de Vercel. El servidor actual necesita procesos, archivos y estado que
no se conservan automáticamente entre invocaciones de funciones.

## 1. Crear la base de datos en Neon

1. Crea un proyecto en [Neon](https://console.neon.tech) con plan **Free**.
2. En **Connect**, copia la cadena PostgreSQL con **Connection pooling** activo.
   Conserva los parámetros que entregue Neon. La aplicación exige
   `verify-full`: valida el certificado de la CA y el nombre del servidor,
   utilizando las CA del sistema del contenedor.
3. Guarda esa cadena como `DATABASE_URL` **solo en el backend**. Ejemplo:

   ```text
   postgresql://USER:PASSWORD@HOST-pooler.REGION.aws.neon.tech/neondb?sslmode=verify-full&sslrootcert=system
   ```

El contenedor crea automáticamente `karaoke_studio_sessions` y
`karaoke_studio_exports` y `karaoke_media_blobs` al arrancar, sin borrar tablas ni datos existentes.
El usuario de la conexión debe tener permiso para crear esas tablas. Si Neon no
está disponible, el arranque falla; no cambia silenciosamente a memoria.

## 2. Crear el almacenamiento gratuito de medios

1. Comprueba que el equipo de Vercel esté en **Hobby**, sin activar Pro ni trials.
2. En el proyecto, abre **Storage**, crea un store **Blob** privado y vincúlalo
   solo a este proyecto.
3. Copia `BLOB_READ_WRITE_TOKEN` a las variables del backend en Render. Es una
   credencial privada: no uses el prefijo `VITE_` ni la incluyas en Git.

Blob Hobby incluye 1 GB de almacenamiento y 10 GB de transferencia al mes,
compartidos con otros stores del mismo equipo. Al superar sus cuotas se bloquea
el acceso hasta el siguiente ciclo; Hobby no factura los excesos. El proyecto
necesita espacio disponible para fuentes y exportaciones. No es almacenamiento
ilimitado. Consulta los [límites vigentes de Blob](https://vercel.com/docs/vercel-blob/usage-and-pricing).

## 3. Desplegar el backend gratuito

Sube estos cambios a tu repositorio. En [Render](https://dashboard.render.com),
crea un **Blueprint** desde el repositorio y usa `render.yaml`.
Selecciona la rama que contiene estos cambios; no asumas que `main` ya incluye
el Dockerfile y la configuración revisados.

La plantilla crea **un servicio Free sin disco de pago**. No registres tarjeta
ni cambies a un plan de pago para seguir esta configuración. Si Render pide
facturación al importar el Blueprint, comprueba que el servicio esté en Free y
que no se esté solicitando un disco persistente; también puedes crear el web
service Docker manualmente con estos mismos valores.

Configura las variables que pide el Blueprint:

| Variable del backend | Valor |
| --- | --- |
| `DATABASE_URL` | Cadena de Neon del paso 1 |
| `FRONTEND_ORIGINS` | Origen de la web: `https://tu-proyecto.vercel.app` |
| `BLOB_READ_WRITE_TOKEN` | Token privado del store del paso 2; obligatorio para persistir medios en Free |

El resto de variables del servidor tienen estos valores predeterminados:

| Variable | Valor y propósito |
| --- | --- |
| `KARAOKE_DATA_DIR` | `/data`; caché temporal en Render Free |
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
Si todavía no conoces el dominio definitivo, configúralo después del paso 4.
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
privilegios. Los medios se recuperan desde Blob cuando Render pierde su caché.

## 4. Desplegar la web en Vercel

1. Importa el mismo repositorio en [Vercel](https://vercel.com/new).
   Selecciona como rama de producción la que contiene esta implementación.
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

## 5. Comprobar el despliegue

- Abre la web de Vercel y carga artista/canción: deben aparecer letras y portada.
- Reproduce audio y salta a otro segundo para comprobar las peticiones `Range`.
- Prepara un video en Estudio, sincroniza, exporta un clip corto y descárgalo.
- Con una sesión preparada, reinicia el backend y vuelve a previsualizar o
  exportar sin recargar la página. Neon recupera la sesión y Blob el video.
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

Render Free dispone de 512 MB y 0.1 CPU, se suspende tras 15 minutos de
inactividad y puede tardar alrededor de un minuto en despertar. Sus 750 horas
mensuales son compartidas por todos los servicios Free del workspace. Sin
método de pago, agotar transferencia o builds provoca suspensión o bloqueo de
builds; no se contrata capacidad adicional. Revisa el consumo del servicio
existente antes de asumir que quedan 750 horas para este proyecto. Render
también puede suspender servicios Free por tráfico saliente elevado.
[Límites de Render Free](https://render.com/docs/free).

Mantén una sola instancia. Neon guarda metadatos y Blob guarda medios; ambos
deben estar disponibles para recuperar una sesión. Sin `BLOB_READ_WRITE_TOKEN`,
el modo local conserva los archivos únicamente en disco y no ofrece persistencia
de medios en Render Free.
Los segmentos, imágenes y listas temporales de cada exportación se eliminan al
terminar, incluso si FFmpeg falla. Los audios, videos fuente y MP4 finales se
conservan. Vigila las cuotas: esos medios no tienen caducidad automática.
Cambiar `/data` por otro punto de montaje requiere migrar también
las rutas almacenadas en Neon.

El propietario confirmó que el acceso público es intencional: no hay login ni
API key. CORS restringe qué
sitios pueden leerla desde un navegador; no es autenticación ni impide llamadas
desde otros clientes. Un despliegue público puede consumir CPU, red y disco.
La API limita el cuerpo de las solicitudes a 64 KiB. La configuración tiene un
worker y cuatro hilos. El estudio procesa un trabajo pesado a la vez para
limitar la memoria; otro trabajo de estudio recibe 503 y puede reintentarse.
No implica capacidad ilimitada ni incluye rate limiting.

Referencias: [Vercel Functions](https://vercel.com/docs/functions/limitations),
[Neon con Python](https://neon.com/docs/guides/python),
[Docker en Render](https://render.com/docs/docker),
[discos persistentes](https://render.com/docs/disks).
