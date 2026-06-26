# 🎵 Terminal Karaoke

**Terminal Karaoke** es un reproductor de letras sincronizadas minimalista, elegante y potente diseñado para ejecutarse directamente en tu consola. Transforma tu terminal en una experiencia de karaoke interactiva con animaciones fluidas, emojis dinámicos y soporte de audio opcional.

---

## ✨ Características Principales

- 🖥️ **Interfaz Visual (NUEVO):** Modo navegador estilo reproductor con carátula del álbum, mini-player, letra sincronizada con auto-scroll y fondo con efecto *blur* de la portada.
- 🎤 **Sincronización en Tiempo Real:** Visualización de letras línea por línea con barra de progreso.
- 🔍 **Búsqueda Automática:** Conexión con `lrclib.net` para obtener letras sincronizadas y planas.
- 🎧 **Soporte de Audio:** Descarga automática de audio desde YouTube o reproducción de archivos locales.
- 🧠 **Modo Inteligente:** Si no hay letras sincronizadas, el sistema estima los tiempos basándose en el contenido.
- 🎨 **Estética Premium:** Uso de colores ANSI, emojis contextuales y centro de texto dinámico.
- 🔤 **Letra ASCII:** Opción para dibujar la línea actual como arte ASCII progresivo en la terminal.
- 🕹️ **Modo Demo:** Prueba la experiencia visual al instante sin necesidad de internet.
- 📂 **Caché Eficiente:** Guarda las letras y el audio descargado para un acceso rápido sin conexión.

---

## 🚀 Instalación Rápida

### 1. Clonar el repositorio (o descargar el archivo)
```bash
git clone https://github.com/tu-usuario/Player-terminal-music.git
cd Player-terminal-music
```

### 2. Instalar dependencias
Asegúrate de tener Python 3.9+ instalado:
```bash
pip install -r requirements.txt
```

> [!IMPORTANT]
> Para la descarga y conversión de audio, se recomienda tener **FFmpeg** instalado en el sistema. El paquete `imageio-ffmpeg` incluido en los requisitos maneja la mayoría de las tareas, pero para una compatibilidad total con `yt-dlp`, una instalación global de FFmpeg es ideal.

---

## 🛠️ Uso y Comandos

### 🖥️ Interfaz Visual (carátula + mini-player + letra animada)
La nueva experiencia visual se ejecuta en tu navegador y reutiliza todo el motor (letras de lrclib, descarga de audio, etc.). El audio del navegador da sincronía perfecta y el fondo toma la carátula con *blur*.

```bash
# Opción A: desde el script principal
python karaoke_terminal.py --web

# Opción B: directamente el servidor
python karaoke_web.py
```

Se abre solo en `http://127.0.0.1:8765/`. Escribe artista y canción (o usa una sugerencia) y listo. Atajos: **Espacio** (play/pausa), **←/→** (±5s), clic en una línea para saltar a ese momento.

> La carátula se obtiene de la **iTunes Search API** (gratuita, sin API key). El audio se descarga con `yt-dlp`; si no está instalado, la letra igual avanza con un reloj interno.

### 🌐 Compartir por una URL pública (Cloudflare Tunnel)
¿Quieres que alguien más lo abra desde su navegador conservando el audio? Exponlo con un túnel **desde tu PC** (la IP residencial evita el bloqueo de YouTube a `yt-dlp`):

```powershell
# 1) Instala cloudflared una sola vez
winget install --id Cloudflare.cloudflared

# 2) Lanza app + túnel con un comando
./serve_public.ps1
```

El script imprime una URL `https://<algo>.trycloudflare.com` que funciona desde cualquier lado **mientras tu PC esté encendida**. El servidor sigue escuchando solo en `localhost`; solo el túnel lo expone.

> **Nota:** la URL del modo rápido cambia en cada ejecución. Para una URL fija necesitas una cuenta de Cloudflare + un túnel con nombre y tu propio dominio. Hospedarlo en la nube (Render/Railway/Vercel) corre la app, pero la descarga de audio fallará porque YouTube bloquea las IPs de datacenter; para eso usa la versión de solo letra.

### Iniciar Karaoke Interactivo
Simplemente ejecuta el script y sigue las instrucciones en pantalla:
```bash
python karaoke_terminal.py
```

### Lanzar con argumentos específicos
Si ya sabes qué quieres cantar:
```bash
python karaoke_terminal.py --artist "Enjambre" --song "Vida en el Espejo"
```

### Reproducir con Audio Automático
Activa la búsqueda y descarga de audio:
```bash
python karaoke_terminal.py --artist "Coldplay" --song "Yellow" --with-audio
```

### Dibujar la Letra en ASCII
Ejecuta el karaoke normalmente. Antes de comenzar, la terminal te preguntará si quieres activar el render progresivo de la línea actual como arte ASCII:
```bash
python karaoke_terminal.py --artist "Enjambre" --song "Vida en el Espejo"
```

### Usar un Archivo de Audio Local
```bash
python karaoke_terminal.py --artist "Daft Punk" --song "Get Lucky" --audio-file "ruta/a/tu/archivo.mp3"
```

### Parámetros Disponibles
| Argumento | Descripción |
| :--- | :--- |
| `--artist` | Nombre del artista o banda. |
| `--song` | Título de la canción. |
| `--with-audio` | Intenta descargar y reproducir el audio. |
| `--audio-file` | Ruta a un archivo de audio local. |
| `--audio-volume` | Control de volumen (0.0 a 1.0). Default: 0.75. |
| `--demo` | Lanza el modo demostración instantáneo. |

---

## 📺 Demo Instantánea
¿Quieres ver cómo se ve sin configurar nada? Ejecuta:
```bash
python karaoke_terminal.py --demo
```

---

## 🛡️ Estructura del Proyecto
- `karaoke_terminal.py`: Script principal (modo terminal + motor de letras/audio).
- `karaoke_web.py`: Servidor web de la interfaz visual (Flask + iTunes Search API).
- `web/`: Frontend de la interfaz visual (`index.html`, `style.css`, `app.js`).
- `.karaoke_cache.json`: Almacén local de letras.
- `.audio_cache/`: Directorio donde se guardan los archivos mp3 descargados.
- `requirements.txt`: Dependencias del sistema.

---

## 📄 Licencia
Este proyecto está bajo la licencia MIT. ¡Siéntete libre de usarlo y mejorarlo!

---
*Desarrollado con ❤️ para los amantes de la música y la terminal.*
