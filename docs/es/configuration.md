# ⚙️ Guía de Configuración y Ajustes

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/configuration.md">🇬🇧 English</a> | <b>🇪🇸 Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/guia-configuracion-orange?style=for-the-badge&logo=gear&logoColor=white" alt="Guía de Configuración">
  <img src="https://img.shields.io/badge/formato-YAML%20y%20ENV-blue?style=for-the-badge" alt="YAML y ENV">
</p>

Esta guía explica cómo configurar cada parámetro de **Music Engine**: rutas del sistema de archivos, búferes de rotación, parámetros de curación por IA, variables de entorno, inicialización de la base de datos y autenticación opcional de YouTube.

---

## 📑 Tabla de Contenidos

- [Resumen de Archivos de Configuración](#-resumen-de-archivos-de-configuración)
- [1. Ajustes del Almacenamiento y del Motor (`config/config.yaml`)](#1-ajustes-del-almacenamiento-y-del-motor-configconfigyaml)
  - [Rutas de Almacenamiento](#rutas-de-almacenamiento)
  - [Ciclo de Vida de la Cinta y Reglas de Rotación](#ciclo-de-vida-de-la-cinta-y-reglas-de-rotación)
  - [Curador de IA (Google Gemini)](#curador-de-ia-google-gemini)
  - [Ajustes del Descargador y Códecs](#ajustes-del-descargador-y-códecs)
  - [Telemetría (ListenBrainz)](#telemetría-listenbrainz)
  - [Listas de Reproducción e Integración con Lune](#listas-de-reproducción-e-integración-con-lune)
  - [Copias de Seguridad Inteligentes y Retención](#copias-de-seguridad-inteligentes-y-retención)
- [2. Secretos y Variables de Entorno (`config/.env`)](#2-secretos-y-variables-de-entorno-configenv)
  - [Obtener una Clave de API de Gemini (Gratis)](#obtener-una-clave-de-api-de-gemini-gratis)
  - [Configurar la Telemetría de ListenBrainz](#configurar-la-telemetría-de-listenbrainz-opcional-recomendado)
- [3. Perfil Semilla de Gustos (`data/taste_profile.json`)](#3-perfil-semilla-de-gustos-datataste_profilejson)
- [4. Inicialización de la Base de Datos (`init_db.py`)](#4-inicialización-de-la-base-de-datos-init_dbpy)
- [5. Autenticación Opcional de YouTube](#5-autenticación-opcional-de-youtube)
- [Verificación de la Configuración](#-verificación-de-la-configuración)

---

## 📂 Resumen de Archivos de Configuración

```text
config/
├── config.yaml.template    # Plantilla de referencia con valores predeterminados documentados
├── config.yaml             # Tu configuración activa (excluida en git)
├── .env.template           # Plantilla para claves de API y tokens secretos
├── .env                    # Tus credenciales secretas (excluida en git)
├── headers_auth.json       # Cabeceras de autenticación opcionales de YTMusic
└── cookies.txt             # Cookies opcionales del navegador para temas con restricción de edad
```

---

## 1. Ajustes del Almacenamiento y del Motor (`config/config.yaml`)

Crea tu archivo de configuración activo copiando la plantilla:

```bash
cp config/config.yaml.template config/config.yaml
```

Edita `config/config.yaml` con tu editor de texto preferido.

### Rutas de Almacenamiento

```yaml
storage:
  # Directorio base donde residirán tu música, listas y buzón de peticiones.
  # El carácter ~ se expande automáticamente a tu directorio personal:
  base_dir: "~/Music/Songs"

  # Subcarpetas relativas a base_dir:
  conveyor_dir: "Conveyor"        # Búfer de descubrimiento temporal (o "Cinta")
  permanent_dir: "Permanent"      # Colección permanente (o "Permanente")
  cravings_dir: "Cravings"        # Colección temporal de antojos (o "Antojos")
  playlists_dir: "Playlists"      # Directorio donde se generan las listas .m3u8
  
  # Archivo buzón para comandos remotos (sincronizado con el móvil vía Syncthing):
  requests_file: "requests.txt"   # O "peticiones.txt"
  
  # Límite de seguridad para prevenir borrados masivos accidentales:
  mass_deletion_failsafe_limit: 50
  
  # Número máximo de copias rotativas de base de datos a conservar:
  max_db_backups: 5
```

> [!NOTE]
> Los alias en español (`cinta_dir`, `permanente_dir`, `antojos_dir`, `peticiones_file`) se admiten con total compatibilidad hacia atrás.

---

### Ciclo de Vida de la Cinta y Reglas de Rotación

Controla cómo circulan las canciones por el búfer de descubrimiento antes de ser promovidas o purgadas:

```yaml
conveyor:
  # Capacidad máxima objetivo de canciones rotando en la Cinta:
  buffer_size: 750

  # Días que una canción puede permanecer sin reproducir antes de ser purgada por la Guillotina:
  grace_period_days: 150

  # Reproducciones necesarias para promocionar automáticamente un tema a Permanente:
  promotion_play_count: 15

  # Máximo de saltos acumulados tolerados antes de descartar la pista:
  max_skips_before_purge: 5

  # Proporción tolerada entre saltos y reproducciones completadas (0.7 = 70% de saltos):
  max_skip_ratio: 0.7

  # Margen de seguridad: si no hay telemetría durante N días, se suspenden las purgas:
  telemetry_safety_margin_days: 7

  # Canciones nuevas recomendadas solicitadas por ciclo de segundo plano:
  curation_batch_per_cycle: 20
```

---

### Curador de IA (Google Gemini)

```yaml
llm:
  # Modelo de Gemini para curación y análisis musical:
  # Opciones recomendadas: gemini-2.5-flash, gemini-1.5-flash
  model: gemini-2.5-flash

  # Ponderaciones de diversidad (deben sumar 1.0):
  diversity_weights:
    exploitation: 0.60    # 60% afinidad directa con artistas y estilos favoritos
    adjacent: 0.25        # 25% artistas adyacentes o géneros afines
    exploration: 0.15     # 15% géneros y estilos completamente novedosos
```

---

### Ajustes del Descargador y Códecs

```yaml
downloader:
  audio_format: "bestaudio/best"
  preferred_codec: "opus"         # "opus" (recomendado por calidad/tamaño) o "m4a"
  fallback_codec: "m4a"
  sleep_interval_min: 3           # Pausa aleatoria mínima en segundos entre descargas
  sleep_interval_max: 8           # Evita límites de peticiones (rate limiting)
  batch_size: 50
  cycle_max_downloads: 50         # Máximo de temas descargados por ciclo
  retry_failed: true              # Reintentar automáticamente descargas con error previo
```

---

### Telemetría (ListenBrainz)

```yaml
telemetry:
  listenbrainz_url: "https://api.listenbrainz.org/1"
  fuzzy_threshold: 80                 # Coincidencia mínima requerida para scrobbles
  loved_fuzzy_artist_threshold: 80
  loved_fuzzy_title_threshold: 85
  lookback_days: 30                   # Días de historial de escucha a consultar
```

---

### Listas de Reproducción e Integración con Lune

```yaml
playlists:
  auto_update_on_change: true
  min_artist_tracks: 10          # Mínimo de pistas de un artista para generar su lista
  
  # Integración nativa con el reproductor Android Lune:
  generate_lune_backup: true     # Genera lune_playlists_backup.json para importar en Android
  lune_include_artists: false    # Si es true, incluye listas de artistas en el backup de Lune
  lune_backup_file: "lune_playlists_backup.json"
  user_playlists_dir: "Listas Propias" # Subcarpeta para listas creadas por el usuario en Lune
  
  system_names:
    permanent: "Permanent"
    conveyor: "Conveyor"
    priority_discovery: "Priority_Discovery"
    live_rotation: "Live_Rotation"
    cravings: "Cravings"
```

---

### Copias de Seguridad Inteligentes y Retención

```yaml
backup:
  auto_backup: true              # Crear instantánea en cada ciclo de ejecución del motor
  dir: "data/backups"            # Carpeta de destino (~ se expande a tu home)
  max_backups: 10                # Máximo de instantáneas a conservar antes de rotación
  format: "bundle"               # "bundle" (archivo .tar.gz unificado) o "db_only" (.sqlite.gz)
  dedup_by_hash: true            # Omitir copia si el hash de la base de datos no ha variado
  include_aux_files: true        # Incluir perfil de gustos, archivos de descarga y estado
```

---

## 2. Secretos y Variables de Entorno (`config/.env`)

Copia la plantilla de secretos y variables de entorno:

```bash
cp config/.env.template config/.env
```

Edita `config/.env`:

```env
# Requerido para la curación con IA:
GEMINI_API_KEY=AIzaSyTuClaveGeneradaDeGeminiAqui

# Opcional para sincronización de reproducciones y feedback ❤️ de favoritos:
LISTENBRAINZ_USER=tu_nombre_de_usuario
LISTENBRAINZ_TOKEN=tu_token_de_usuario_listenbrainz
```

### Obtener una Clave de API de Gemini (Gratis)
1. Accede a [Google AI Studio](https://aistudio.google.com/).
2. Inicia sesión con tu cuenta de Google.
3. Haz clic en **Get API key** y genera una nueva clave.
4. Pégala como `GEMINI_API_KEY` en `config/.env`.

### Configurar la Telemetría de ListenBrainz (Opcional, Recomendado)
1. Crea una cuenta gratuita en [ListenBrainz.org](https://listenbrainz.org/).
2. Dirígete a **Settings** → **API Token**.
3. Copia tu nombre de usuario en `LISTENBRAINZ_USER` y el token generado en `LISTENBRAINZ_TOKEN`.

> [!TIP]
> Sin ListenBrainz, Music Engine seguirá descargando, etiquetando, curando y organizando listas. No obstante, la promoción automática por recuento de reproducciones y el blindaje mediante ❤️ desde el móvil no tendrán efecto automático.

---

## 3. Perfil Semilla de Gustos (`data/taste_profile.json`)

Para inicializar el curador de IA con tus preferencias musicales antes de importar listas, copia la plantilla:

```bash
cp data/taste_profile.json.template data/taste_profile.json
```

Edita `data/taste_profile.json` indicando algunos artistas y géneros favoritos:

```json
{
  "total_tracks": 10,
  "top_artists": {
    "Daft Punk": 50,
    "Pink Floyd": 40,
    "Arctic Monkeys": 30
  },
  "genre_seeds": [
    "Electronic",
    "Psychedelic Rock",
    "Indie Rock"
  ]
}
```

> [!NOTE]
> Cada vez que importas listas de YouTube Music mediante `python main.py import-playlist`, el motor actualiza automáticamente este archivo con tu distribución real de escucha.

---

## 4. Inicialización de la Base de Datos (`init_db.py`)

Ejecuta el script de inicialización para crear la base de datos SQLite en modo WAL (Write-Ahead Logging):

```bash
python database/init_db.py
```

*Salida:*
```text
Database data/conveyor_state.sqlite initialized successfully in WAL mode.
```

Esto genera `data/conveyor_state.sqlite` con todas las tablas requeridas (`tracks`, `listen_events`, `system_metadata`, `orphan_scrobbles`, `artist_genres`) e índices de búsqueda de alto rendimiento.

---

## 5. Autenticación Opcional de YouTube

Por defecto, las descargas y consultas de metadatos funcionan de manera anónima. Sin embargo, si deseas importar listas privadas o descargar canciones con restricción de edad:

### Cookies del Navegador (`config/cookies.txt`)
1. En tu navegador (Firefox, Chrome, Brave), instala una extensión como *Get cookies.txt LOCALLY*.
2. Inicia sesión en YouTube.
3. Exporta tus cookies en formato Netscape.
4. Guarda el archivo exportado como `config/cookies.txt`.

### Cabeceras de YTMusic (`config/headers_auth.json`)
Si deseas autenticar tu cuenta personal de YouTube Music:
1. Ejecuta `ytmusicapi oauth` en tu terminal y sigue los pasos en pantalla, O
2. Copia las cabeceras de petición desde la web de YouTube Music (pestaña Red en las Herramientas de Desarrollador) y guárdalas en `config/headers_auth.json`.

---

## 🔍 Verificación de la Configuración

Comprueba que todo está correctamente configurado consultando el estado del motor:

```bash
python main.py status
```

*Salida esperada:*
```text
=============================================
 CONVEYOR BELT STATUS
=============================================
Base directory:     /home/usuario/Music/Songs
Tracks in CONVEYOR: 0
PERMANENT tracks:   0
CRAVINGS tracks:    0
PENDING tracks:     0
PURGED tracks:      0
---------------------------------------------
Disk space used:    0.00 MB
Last scrobble:      None
Last LB sync:       Never
=============================================
```

---

<p align="center">
  <a href="installation.md"><b>⬅ Guía de Instalación</b></a> • <a href="cli-reference.md"><b>Siguiente: Referencia de CLI ➡</b></a>
</p>
