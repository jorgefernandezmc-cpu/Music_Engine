# ❓ Solución de Problemas y Preguntas Frecuentes (FAQ)

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/troubleshooting.md">English</a> | <b>Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/guia-solucion_de_problemas_y_faq-red?style=for-the-badge&logo=shield&logoColor=white" alt="Solución de Problemas">
  <img src="https://img.shields.io/badge/estado-soluciones-green?style=for-the-badge" alt="Soluciones">
</p>

Esta guía aborda los mensajes de error más comunes, dudas de configuración, casos particulares y preguntas operativas habituales al ejecutar **Music Engine**.

---

## 📑 Tabla de Contenidos

- [Comandos de Diagnóstico Rápido](#-comandos-de-diagnóstico-rápido)
- [Mensajes de Error Comunes y Soluciones](#-mensajes-de-error-comunes-y-soluciones)
  - [`ERROR: Critical environment variables missing in config/.env`](#1-error-critical-environment-variables-missing-in-configenv)
  - [`sqlite3.OperationalError: database is locked`](#2-sqlite3operationalerror-database-is-locked)
  - [`FileLockTimeout: Could not acquire lock data/engine.lock`](#3-filelocktimeout-could-not-acquire-lock-dataenginelock)
  - [`ffmpeg: command not found` / Fallos de Transcodificación con yt-dlp](#4-ffmpeg-command-not-found--fallos-de-transcodificación-con-yt-dlp)
  - [`Sign in to confirm you’re not a bot` / Errores 429 de YouTube](#5-sign-in-to-confirm-youre-not-a-bot--errores-429-de-youtube)
- [Preguntas sobre el Ciclo de Vida y Comportamiento](#-preguntas-sobre-el-ciclo-de-vida-y-comportamiento)
  - [¿Por qué se purgan canciones de la Cinta antes de lo esperado?](#por-qué-se-purgan-canciones-de-la-cinta-antes-de-lo-esperado)
  - [¿Por qué una canción no sube a Permanente tras varias reproducciones?](#por-qué-una-canción-no-sube-a-permanente-tras-varias-reproducciones)
  - [¿Cómo evito que una canción concreta se borre alguna vez?](#cómo-evito-que-una-canción-concreta-se-borre-alguna-vez)
- [Preguntas sobre Móvil y Sincronización](#-preguntas-sobre-móvil-y-sincronización)
  - [Syncthing crea archivos `.sync-conflict`](#syncthing-crea-archivos-sync-conflict)
  - [El reproductor Lune no refleja las listas actualizadas](#el-reproductor-lune-no-refleja-las-listas-actualizadas)
  - [Pano Scrobbler no envía reproducciones a ListenBrainz](#pano-scrobbler-no-envía-reproducciones-a-listenbrainz)
- [Preguntas sobre Systemd y Automatización](#-preguntas-sobre-systemd-y-automatización)
  - [No aparecen las notificaciones de escritorio (`notify-send`)](#no-aparecen-las-notificaciones-de-escritorio-notify-send)
  - [El temporizador de systemd no se ejecuta con la sesión cerrada](#el-temporizador-de-systemd-no-se-ejecuta-con-la-sesión-cerrada)

---

## 🩺 Comandos de Diagnóstico Rápido

Ejecuta estas comprobaciones antes de profundizar en problemas más complejos:

```bash
# 1. Comprobar la conexión con la base de datos y contadores:
python main.py status

# 2. Comprobar la disponibilidad de ffmpeg:
ffmpeg -version | head -n 1

# 3. Probar la conectividad con la API de Gemini:
python -c "from dotenv import load_dotenv; import os, google.genai as genai; load_dotenv('config/.env'); client = genai.Client(api_key=os.getenv('GEMINI_API_KEY')); print('✓ API de Gemini conectada con éxito')"

# 4. Comprobar el estado del temporizador de systemd (Linux):
systemctl --user status music-engine.timer

# 5. Inspeccionar las últimas 50 líneas de registro:
tail -n 50 logs/engine.log
```

---

## ⚠️ Mensajes de Error Comunes y Soluciones

### 1. `ERROR: Critical environment variables missing in config/.env`
- **Causa:** La variable `GEMINI_API_KEY` está vacía, no definida o contiene texto por defecto.
- **Solución:**
  1. Abre `config/.env`.
  2. Asegúrate de que `GEMINI_API_KEY=AIzaSy...` contiene una clave válida de [Google AI Studio](https://aistudio.google.com/).
  3. Evita comillas o espacios innecesarios alrededor de la clave.

---

### 2. `sqlite3.OperationalError: database is locked`
- **Causa:** Otro proceso o visor de base de datos externo (como DB Browser for SQLite) mantiene una transacción de escritura abierta sin confirmar.
- **Solución:**
  1. Cierra cualquier programa de base de datos externo que tenga abierto `data/conveyor_state.sqlite`.
  2. Verifica si existen procesos residuales de Python:
     ```bash
     ps aux | grep "main.py"
     ```
  3. Fuerza un punto de control (*checkpoint*) en el registro WAL:
     ```bash
     python -c "import sqlite3; conn = sqlite3.connect('data/conveyor_state.sqlite'); conn.execute('PRAGMA wal_checkpoint(TRUNCATE);'); conn.close(); print('✓ Checkpoint forzado con éxito')"
     ```

---

### 3. `FileLockTimeout: Could not acquire lock data/engine.lock`
- **Causa:** La ejecución previa del motor se interrumpió de forma abrupta (`kill -9`), dejando el archivo de bloqueo huérfano.
- **Solución:**
  1. Verifica que no haya ninguna instancia en ejecución: `pgrep -f "python.*main.py"`.
  2. Si no hay procesos activos, elimina el archivo de bloqueo:
     ```bash
     rm -f data/engine.lock
     ```

---

### 4. `ffmpeg: command not found` / Fallos de Transcodificación con `yt-dlp`
- **Causa:** `yt-dlp` necesita `ffmpeg` para extraer las pistas de audio de los contenedores de vídeo y convertirlas a Opus o M4A.
- **Solución:** Instala ffmpeg en tu sistema operativo:
  ```bash
  # Ubuntu / Debian:
  sudo apt install ffmpeg

  # Arch Linux:
  sudo pacman -S ffmpeg

  # Fedora:
  sudo dnf install ffmpeg ffmpeg-free

  # macOS:
  brew install ffmpeg
  ```

---

### 5. `Sign in to confirm you’re not a bot` / Errores 429 de YouTube
- **Causa:** YouTube ha limitado las peticiones anónimas de descarga o el tema requiere verificación de edad.
- **Solución:**
  1. Instala una extensión de navegador (como *Get cookies.txt LOCALLY*) en Chrome o Firefox.
  2. Inicia sesión en YouTube en el navegador.
  3. Exporta las cookies en formato Netscape y guárdalas como `config/cookies.txt`.
  4. Music Engine detecta y utiliza automáticamente `config/cookies.txt` en cada descarga.

---

## 🔄 Preguntas sobre el Ciclo de Vida y Comportamiento

### ¿Por qué se purgan canciones de la Cinta antes de lo esperado?
Revisa las siguientes directivas en `config/config.yaml`:
1. **`grace_period_days` (por defecto: 150):** Si no has escuchado un tema en 150 días, la Guillotina interpreta que no es de tu agrado y lo purga para liberar espacio. Aumenta este valor a `365` si deseas un margen mayor.
2. **`max_skips_before_purge` (por defecto: 5) y `max_skip_ratio` (por defecto: 0.7):** Si saltas un tema con frecuencia sin dejar que termine, el motor lo considera una señal negativa y lo descarta.
3. **Margen de Seguridad de Telemetría:** Si han transcurrido más días de los indicados en `telemetry_safety_margin_days` (por defecto: 7) sin sincronizar con ListenBrainz, el motor suspende automáticamente todas las purgas por precaución.

### ¿Por qué una canción no sube a Permanente tras varias reproducciones?
1. **Scrobbles pendientes:** Asegúrate de que Pano Scrobbler ha enviado las reproducciones a ListenBrainz y de que has ejecutado `python main.py sync-telemetry` o `python main.py run`.
2. **Umbral de reproducción:** El valor por defecto es `promotion_play_count: 15`. Puedes reducirlo a `5` o `10` en `config/config.yaml` bajo `conveyor.promotion_play_count`.
3. **Discrepancia de título:** Si las etiquetas del reproductor móvil difieren sustancialmente de YouTube Music, revisa la tabla `orphan_scrobbles` en SQLite.

### ¿Cómo evito que una canción concreta se borre alguna vez?
**¡Muy fácil!** Elige cualquiera de estas opciones:
- Pulsa el icono de **❤️ Corazón / Favorito** en tu reproductor móvil.
- Añade `favorita: Nombre de la Canción` o `permanente: Nombre de la Canción` en `requests.txt`.
- Ejecuta `python main.py set-album "<Pista>" "<Álbum>"`.

---

## 📱 Preguntas sobre Móvil y Sincronización

### Syncthing crea archivos `.sync-conflict`
- **Causa:** Ediciones simultáneas en el móvil y en el PC sobre el mismo archivo (habitualmente `requests.txt` o listas `.m3u8`).
- **Solución:**
  1. Asegúrate de contar con el archivo `.stignore` en la carpeta compartida (ver [Guía Móvil y Sincronización](mobile-and-sync.md)).
  2. Elimina los archivos de conflicto residuales:
     ```bash
     find ~/Music/Songs -name "*.sync-conflict-*" -delete
     ```

### El reproductor Lune no refleja las listas actualizadas
- **Causa:** Android restringe el acceso directo a archivos `.m3u8`. Lune utiliza copias de seguridad en formato JSON.
- **Solución:**
  1. Asegúrate de que `generate_lune_backup: true` está habilitado en `config/config.yaml`.
  2. En Lune en Android, accede a **Ajustes** $\rightarrow$ **Importar listas de reproducción** $\rightarrow$ Selecciona `Playlists/lune_playlists_backup.json`.

### Pano Scrobbler no envía reproducciones a ListenBrainz
- **Causa:** La optimización de batería de Android detiene Pano Scrobbler en segundo plano.
- **Solución:**
  1. En Android: **Ajustes** $\rightarrow$ **Aplicaciones** $\rightarrow$ **Pano Scrobbler** $\rightarrow$ **Batería** $\rightarrow$ Seleccionar **Sin restricciones**.
  2. Comprueba que el permiso de **Acceso a notificaciones** sigue concedido a Pano Scrobbler.

---

## ⏰ Preguntas sobre Systemd y Automatización

### No aparecen las notificaciones de escritorio (`notify-send`)
- **Causa:** El servicio de usuario de systemd puede carecer de las variables de sesión gráfica (`$DBUS_SESSION_BUS_ADDRESS`).
- **Solución:**
  El módulo de notificaciones (`src/notifications.py`) detecta entornos sin entorno gráfico y omite los avisos de forma silenciosa sin provocar errores. Para habilitarlas:
  ```bash
  systemctl --user import-environment DISPLAY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS
  ```

### El temporizador de systemd no se ejecuta con la sesión cerrada
- **Causa:** Por defecto, systemd suspende los gestores de usuario al cerrar la última sesión interactiva.
- **Solución:** Habilita el modo persistente (*lingering*):
  ```bash
  sudo loginctl enable-linger $USER
  ```

---

<p align="center">
  <a href="backup-and-migration.md"><b>⬅ Copias de Seguridad y Migración</b></a> • <a href="architecture.md"><b>Siguiente: Arquitectura del Sistema ➡</b></a>
</p>
