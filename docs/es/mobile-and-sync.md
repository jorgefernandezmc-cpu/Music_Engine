# 📲 Ecosistema Móvil y Sincronización

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/mobile-and-sync.md">English</a> | <b>Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/integracion-Android_y_Syncthing-16A085?style=for-the-badge&logo=syncthing&logoColor=white" alt="Syncthing">
  <img src="https://img.shields.io/badge/telemetria-ListenBrainz-EB743B?style=for-the-badge&logo=musicbrainz&logoColor=white" alt="ListenBrainz">
  <img src="https://img.shields.io/badge/reproductores-Lune_%7C_Auxio_%7C_Symfonium-purple?style=for-the-badge" alt="Reproductores">
</p>

Music Engine está diseñado para ofrecer una **experiencia móvil orientada al uso sin conexión (*offline-first*)**. Toda tu música, letras sincronizadas, listas de reproducción y comandos se sincronizan de forma bidireccional entre tu PC con Linux y tus dispositivos Android, sin depender de servicios privativos en la nube.

---

## 📑 Tabla de Contenidos

- [Arquitectura del Ecosistema Móvil](#-arquitectura-del-ecosistema-móvil)
- [1. Configuración de Syncthing (Sincronización P2P)](#1-configuración-de-syncthing-sincronización-p2p)
  - [Instalar Syncthing](#instalar-syncthing)
  - [Emparejamiento de Carpetas](#emparejamiento-de-carpetas)
  - [Reglas Recomendadas en .stignore](#reglas-recomendadas-en-stignore)
- [2. Reproductores Móviles y Listas de Reproducción](#2-reproductores-móviles-y-listas-de-reproducción)
  - [Listas Universales .m3u8](#listas-universales-m3u8)
  - [Integración con el Reproductor Android Lune](#integración-con-el-reproductor-android-lune)
  - [Listas Creadas por el Usuario desde el Móvil](#listas-creadas-por-el-usuario-desde-el-móvil)
  - [Visualización de Letras Sincronizadas (.lrc)](#visualización-de-letras-sincronizadas-lrc)
- [3. Bucle de Telemetría (Pano Scrobbler + ListenBrainz)](#3-bucle-de-telemetría-pano-scrobbler--listenbrainz)
  - [Configurar Pano Scrobbler en Android](#configurar-pano-scrobbler-en-android)
  - [Cómo los Scrobbles Desencadenan Promociones](#cómo-los-scrobbles-desencadenan-promociones)
  - [Blindaje por Corazón (Pistas Favoritas)](#blindaje-por-corazón-pistas-favoritas)

---

## 📐 Arquitectura del Ecosistema Móvil

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                         DISPOSITIVO MÓVIL ANDROID                      │
 │                                                                        │
 │  [ Lune / Auxio / Symfonium ] ──▶ [ Pano Scrobbler ] ──▶ [ListenBrainz]│
 │          ▲                                |                (En la nube)│
 └──────────┼────────────────────────────────┼────────────────────┼───────┘
            │                                │                    │
            │ Archivos de audio, .lrc        │ Reproducciones     │
            │ y requests.txt / peticiones.txt│ y favoritos ❤️     │
            ▼                                │                    │
   ═══ [ SYNCTHING ] ═══                     │                    │
            ▲                                │                    │
 ┌──────────┼────────────────────────────────┼────────────────────┼───────┐
 │          ▼                                ▼                    ▼       │
 │   storage.base_dir                  Feedback Corazón      Scrobbles    │
 │   (/home/usuario/Music/Songs)             │                    │       │
 │          │                                └─────────┬──────────┘       │
 │          ▼                                          ▼                  │
 │  ┌─────────────────────────────────────────────────────────────────┐   │
 │  │                        MUSIC ENGINE (PC)                        │   │
 │  │  • FileSyncManager   • TelemetryEngine   • OrderProcessor       │   │
 │  │  • Downloader        • LyricsProvider    • PlaylistGenerator    │   │
 │  └─────────────────────────────────────────────────────────────────┘   │
 │                               LINUX PC                                 │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Configuración de Syncthing (Sincronización P2P)

[Syncthing](https://syncthing.net/) proporciona sincronización descentralizada, cifrada y continua de archivos tanto en tu red Wi-Fi local como a través de Internet.

### Instalar Syncthing

1. **En tu PC (Linux):**
   ```bash
   # Debian / Ubuntu:
   sudo apt install syncthing
   systemctl --user enable --now syncthing

   # Arch Linux:
   sudo pacman -S syncthing
   systemctl --user enable --now syncthing
   ```
2. **En Android:**
   - Instala **Syncthing-Fork** desde [F-Droid](https://f-droid.org/packages/com.github.catfriend1.syncthingandroid/) o Google Play Store.

### Emparejamiento de Carpetas

1. Accede a la interfaz web de Syncthing en tu PC (`http://127.0.0.1:8384`).
2. Añade tu dispositivo Android mediante su ID de dispositivo o escaneando el código QR.
3. Comparte tu carpeta base de música (la indicada como `storage.base_dir` en `config/config.yaml`, por ejemplo `~/Music/Songs`).
4. En tu móvil, acepta la carpeta compartida y selecciona una carpeta local en tu almacenamiento interno o tarjeta SD (por ejemplo `Music/Songs`).
5. Configura el Tipo de Carpeta como **Enviar y Recibir** (*Send & Receive*) en ambos extremos.

### Reglas Recomendadas en `.stignore`

En la raíz de la carpeta de música compartida en tu PC, crea un archivo llamado `.stignore` para evitar sincronizar bloqueos temporales, cachés o entornos virtuales:

```text
(?d).venv*
(?d)__pycache__
(?d)*.pyc
(?d)*.lock
(?d)*.tmp
(?d).stversions
(?d).DS_Store
```

---

## 2. Reproductores Móviles y Listas de Reproducción

### Listas Universales `.m3u8`

Music Engine genera automáticamente listas de reproducción estándar `.m3u8` con codificación UTF-8 en la carpeta `Playlists/`:

| Archivo de Lista | Contenido y Comportamiento |
| :--- | :--- |
| `Permanent.m3u8` | Colección permanente completa ordenada por Artista $\rightarrow$ Álbum $\rightarrow$ Pista. |
| `Conveyor.m3u8` | Todas las canciones que están rotando en el búfer de la Cinta. |
| `Priority_Discovery.m3u8` | Nuevos descubrimientos descargados pendientes de su primera escucha. |
| `Live_Rotation.m3u8` | Mezcla dinámica inteligente: temas más escuchados + novedades + joyas olvidadas. |
| `Cravings.m3u8` | Temas activos en la colección temporal de Antojos. |
| `Artistas/<Artista>.m3u8` | Lista exhaustiva para cada artista que supere el umbral mínimo (por defecto: 10 pistas). |

Estas listas son compatibles de forma inmediata con:
- **Auxio** (Reproductor de código abierto, ligero y limpio para Android)
- **Symfonium** (Reproductor avanzado para música local y en red)
- **Retro Music Player**
- **Musicolet**
- **Poweramp**
- **VLC para Android**

---

### Integración con el Reproductor Android Lune

[Lune](https://github.com/) es un reproductor de música local para Android moderno, ligero y centrado en la privacidad.

Dado que las versiones recientes de Android imponen restricciones para indexar archivos de listas de reproducción directos, Lune gestiona sus listas mediante una base de datos SQLite interna. Music Engine incorpora **integración nativa bidireccional** con Lune:

1. En `config/config.yaml`, asegúrate de tener:
   ```yaml
   playlists:
     generate_lune_backup: true
     lune_backup_file: "lune_playlists_backup.json"
     user_playlists_dir: "Listas Propias"
   ```
2. Al ejecutarse el motor, compila y sincroniza `Playlists/lune_playlists_backup.json`.
3. En la aplicación Lune en tu teléfono:
   - Dirígete a **Ajustes** $\rightarrow$ **Importar listas de reproducción**.
   - Selecciona el archivo `Playlists/lune_playlists_backup.json`.
   - ¡Todas las listas del sistema, de artistas y de usuario se cargarán en Lune de forma inmediata!

---

### Listas Creadas por el Usuario desde el Móvil

Puedes diseñar listas personalizadas directamente en la interfaz de Lune desde tu móvil:
1. Crea tu lista en Lune (por ejemplo, *"Entrenamiento"* o *"Viaje"*).
2. Exporta tus listas en Lune: **Ajustes** $\rightarrow$ **Exportar listas de reproducción** $\rightarrow$ Guárdala como `lune_playlists_backup.json` dentro de tu carpeta sincronizada `Playlists/`.
3. Cuando Syncthing sincroniza este archivo con tu PC, Music Engine:
   - Extrae tus listas personalizadas a archivos `Playlists/Listas Propias/<NombreLista>.m3u8`.
   - Resuelve los títulos de las pistas contra los archivos de tu biblioteca local.
   - Limpia canciones fantasma (pistas que hayas eliminado o purgado previamente).
   - Preserva intactas tus listas de usuario en futuras exportaciones del motor.

---

### Visualización de Letras Sincronizadas (`.lrc`)

Music Engine incrusta las letras directamente en las etiquetas Vorbis/MP4 **y además** genera archivos sidecar `.lrc` contiguos a cada archivo de sonido:
```text
Permanent/Daft Punk/Discovery/Daft Punk - One More Time.opus
Permanent/Daft Punk/Discovery/Daft Punk - One More Time.lrc
```

Al reproducir cualquier tema en **Lune**, **Auxio** o **Symfonium**, las letras sincronizadas tipo karaoke se iluminan automáticamente con precisión de milisegundos sin requerir conexión a Internet.

---

## 3. Bucle de Telemetría (Pano Scrobbler + ListenBrainz)

Para habilitar la promoción automática y la limpieza inteligente, Music Engine sigue tus hábitos reales de escucha a través de **ListenBrainz**.

### Configurar Pano Scrobbler en Android

1. Instala [Pano Scrobbler](https://github.com/kawaiiDango/pno-scrobbler) desde F-Droid o Google Play Store.
2. Concede el permiso de Acceso a Notificaciones (necesario para detectar la música en reproducción).
3. En la sección **Servicios de Scrobble**, selecciona **ListenBrainz** e inicia sesión con tu cuenta.
4. Habilita el **Scrobble sin conexión**: Pano Scrobbler almacena localmente cada reproducción que realizas —incluso en modo avión— y las envía a ListenBrainz tan pronto como recuperas conexión Wi-Fi o datos.

### Cómo los Scrobbles Desencadenan Promociones

1. Cuando escuchas un tema en tu smartphone, Pano Scrobbler registra la reproducción.
2. En el siguiente ciclo del motor en tu PC (`python main.py run` o `python main.py sync-telemetry`):
   - El motor consulta ListenBrainz en busca de tus reproducciones recientes.
   - Mediante coincidencia difusa (*fuzzy matching*) de título y artista, asocia los eventos a tus pistas locales.
   - Actualiza el contador `play_count` y la fecha `last_played_at`.
3. Si una pista en la **Cinta** alcanza el umbral de promoción (por defecto: 15 reproducciones):
   - El motor la promociona a **Permanente**.
   - Resuelve el álbum de estudio canónico.
   - Traslada físicamente los archivos de audio y `.lrc` a `Permanent/<Artista>/<Álbum>/`.

### Blindaje por Corazón (Pistas Favoritas)

En tu reproductor móvil o desde la barra de notificaciones de Pano Scrobbler, pulsa el icono de **❤️ Corazón / Favorito** en cualquier canción.

En la siguiente sincronización, el motor:
1. Detecta que la pista fue marcada como favorita (*Loved*) en ListenBrainz.
2. **La blinda inmediatamente contra la Guillotina**.
3. La promociona a `Permanent/` con independencia de su número de reproducciones.

---

<p align="center">
  <a href="mailbox-commands.md"><b>⬅ Buzón Remoto</b></a> • <a href="automation.md"><b>Siguiente: Automatización en Segundo Plano ➡</b></a>
</p>
