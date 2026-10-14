# 🏗️ Arquitectura del Sistema e Internos del Código

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/architecture.md">English</a> | <b>Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/arquitectura-python_modular-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python Modular">
  <img src="https://img.shields.io/badge/base_de_datos-SQLite_WAL-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/rol-referencia_desarrollo-green?style=for-the-badge" alt="Referencia de Desarrollo">
</p>

Esta referencia técnica proporciona un desglose arquitectónico detallado de **Music Engine** para desarrolladores, administradores de sistemas y agentes de IA que extiendan o mantengan el código fuente.

---

## 📑 Tabla de Contenidos

- [Topología del Sistema y Flujo de Alto Nivel](#-topología-del-sistema-y-flujo-de-alto-nivel)
- [Máquina de Estados de la Cinta Transportadora](#-máquina-de-estados-de-la-cinta-transportadora)
- [Esquema e Índices de la Base de Datos SQLite](#-esquema-e-índices-de-la-base-de-datos-sqlite)
- [Jerarquía de Almacenamiento en Disco](#-jerarquía-de-almacenamiento-en-disco)
- [Catálogo de Módulos y Responsabilidades](#-catálogo-de-módulos-y-responsabilidades)
- [Modelo de Concurrencia y Bloqueos](#-modelo-de-concurrencia-y-bloqueos)
- [Directrices para Desarrolladores y Colaboradores](#-directrices-para-desarrolladores-y-colaboradores)

---

## 📐 Topología del Sistema y Flujo de Alto Nivel

```text
 ┌───────────────────────────────────────────────────────────────────────┐
 │                           CLIENTE MÓVIL                               │
 │                                                                       │
 │   [ Reproductor Lune ] ─────▶ [ Pano Scrobbler ] ─────▶ [ListenBrainz │
 │             ▲                          |                 API en Nube] │
 └─────────────┼──────────────────────────┼───────────────────────┼──────┘
               │                          │                       │
               │ Archivos de audio        │ Feedback con corazón  │ Scrobbles
               │ y sidecars .lrc          │ (Pistas favoritas ❤️)  │ (Reproducciones)
               ▼                          │                       │
      === [ SYNCTHING ] ===               │                       │
               ▲                          │                       │
 ┌─────────────┼──────────────────────────┼───────────────────────┼──────┐
 │             ▼                          ▼                       ▼      │
 │       Canciones Root             Updates de Corazón      API Scrobbles │
 │     (storage.base_dir)                 │                       │      │
 │             │                          └───────────┬───────────┘      │
 │             ▼                                      ▼                  │
 │  ┌─────────────────────────────────────────────────────────────────┐  │
 │  │                        MUSIC ENGINE (PC)                        │  │
 │  │                                                                 │  │
 │  │  • StoragePaths    : Traducción de rutas y abstracción de alias │  │
 │  │  • AlbumResolver   : Resolución de álbum de estudio (+100 ptos) │  │
 │  │  • TelemetryEngine : Sincronización ListenBrainz y fuzzy match  │  │
 │  │  • FileSyncManager : Detección de traslados y limpieza fantasma │  │
 │  │  • OrderProcessor  : Intérprete de peticiones en requests.txt   │  │
 │  │  • CuratorLLM      : Curación con IA Gemini + radios de YTM     │  │
 │  │  • Downloader      : Extracción con yt-dlp + etiquetas Vorbis   │  │
 │  │  • LyricsProvider  : Cascada multifuente de letras (.lrc)       │  │
 │  │  • PlaylistGen     : Compilador de M3U8 UTF-8 y backup de Lune  │  │
 │  │  • BackupManager   : Instantáneas WAL y paquetes portables .tar │  │
 │  │                                                                 │  │
 │  │                   Base de Datos SQLite (Modo WAL)               │  │
 │  │                    (data/conveyor_state.sqlite)                 │  │
 │  └─────────────────────────────────────────────────────────────────┘  │
 │                                LINUX PC                                │
 └───────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Máquina de Estados de la Cinta Transportadora

Cada canción registrada en el motor pasa por una máquina de estados determinista:

```text
                     ┌───────────────┐
                     │ Curador IA /  │
                     │ Orden Usuario │
                     └───────┬───────┘
                             │
                             ▼
                     ┌───────────────┐
            ┌───────▶│    PENDING    │◀────────┐
            │        └───────┬───────┘         │
            │ Error de       │ Descarga        │ Descarga
            │ Descarga       │ Exitosa         │ (Antojo)
            │                ▼                 │
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │    FAILED    │ │    CINTA     │ │    ANTOJO    │
     └──────────────┘ │  (Conveyor)  │ │  (Cravings)  │
                      └──────┬───────┘ └──────┬───────┘
                             │                │
            ┌────────────────┼────────────────┤
            │ ≥15 repros O   │                │ Caducidad
            │ Pista con ❤️    │ Sin reproducir │ Retención
            │                │ (150 días)     │ (30 días)
            ▼                ▼                ▼
     ┌──────────────┐ ┌───────────────────────────────┐
     │  PERMANENT   │ │            PURGED             │
     │  (Protegida) │ │   (Borrada, Nunca Re-añadida) │
     └──────────────┘ └───────────────────────────────┘
```

### Definición de Estados de Pistas

| Estado | Duración | Ubicación en Disco | Descripción |
| :--- | :--- | :--- | :--- |
| `PENDING` | Transitorio | Ninguna (en cola) | ID de video catalogado; esperando descarga mediante `Downloader`. |
| `CINTA` | Efímero | `Conveyor/<Artista> - <Título>.opus` | Pista de descubrimiento activa en la cinta transportadora. |
| `PERMANENT` | Indefinido | `Permanent/<Artista>/<Álbum>/<Pista>.opus` | Pista de la colección fija. Intocable por purgas automáticas. |
| `ANTOJO` | 30 Días | `Cravings/<Artista>/<Álbum>/<Pista>.opus` | Pista temporal de antojo; purgada tras `retention_days`. |
| `PURGED` | Permanente | Ninguna (borrada del disco) | Pista descartada. Retenida en la base de datos para no re-curarla jamás. |
| `FAILED` | Transitorio | Ninguna | Fallo de descarga; reintentada automáticamente a `PENDING` en la siguiente pasada. |

---

## 🗄️ Esquema e Índices de la Base de Datos SQLite

Ubicada en `data/conveyor_state.sqlite`. Definida en [`database/schema.sql`](../../database/schema.sql).

### Tabla `tracks`
```sql
CREATE TABLE tracks (
    id TEXT PRIMARY KEY,                 -- ID de video de YouTube (ej. 'dQw4w9WgXcQ')
    title TEXT NOT NULL,                 -- Título normalizado de la pista
    artist TEXT NOT NULL,                -- Cadena completa de artistas (con colaboradores)
    album TEXT,                          -- Título canónico del álbum de estudio
    duration_seconds INTEGER,            -- Duración exacta de la pista
    status TEXT NOT NULL,                -- PENDING, CINTA, PERMANENT, ANTOJO, PURGED, FAILED
    is_permanent BOOLEAN DEFAULT 0,      -- 1 si es permanente, 0 en caso contrario
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_played_at DATETIME,             -- Timestamp UTC del scrobble más reciente
    play_count INTEGER DEFAULT 0,        -- Contador acumulado de reproducciones
    skip_count INTEGER DEFAULT 0,        -- Contador acumulado de saltos sin terminar
    file_path TEXT,                      -- Ruta absoluta al archivo físico de audio
    genre TEXT,                          -- Género musical asignado
    track_number INTEGER,                -- Número oficial de pista en el álbum
    release_date TEXT                    -- Fecha oficial de lanzamiento (YYYY-MM-DD o YYYY)
);
```

### Tabla `listen_events`
```sql
CREATE TABLE listen_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    listened_at DATETIME NOT NULL,
    source TEXT,                         -- 'listenbrainz'
    FOREIGN KEY(track_id) REFERENCES tracks(id)
);
```

### Tabla `artist_genres`
```sql
CREATE TABLE artist_genres (
    artist TEXT PRIMARY KEY,
    genre TEXT NOT NULL,
    source TEXT NOT NULL,                -- 'musicbrainz', 'gemini', 'user'
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Índices de Alto Rendimiento
```sql
CREATE INDEX idx_tracks_status ON tracks(status);
CREATE INDEX idx_tracks_status_perm ON tracks(status, is_permanent);
CREATE INDEX idx_tracks_file_path ON tracks(file_path);
CREATE INDEX idx_tracks_artist_title ON tracks(artist, title);
CREATE INDEX idx_tracks_play_count ON tracks(play_count);
CREATE INDEX idx_listen_events_track_id ON listen_events(track_id);
CREATE INDEX idx_listen_events_listened_at ON listen_events(listened_at);
```

---

## 📁 Jerarquía de Almacenamiento en Disco

Configurada mediante `storage.base_dir` en `config/config.yaml`:

```text
~/Music/Songs/
├── requests.txt                     # Buzón remoto de peticiones y comandos
│
├── Conveyor/                        # Búfer efímero de descubrimientos (directorio plano)
│   ├── Artista A - Pista Uno.opus
│   ├── Artista A - Pista Uno.lrc
│   └── Artista B - Pista Dos.opus
│
├── Permanent/                       # Colección permanente (jerarquía estricta de 2 niveles)
│   ├── Daft Punk/
│   │   ├── Discovery/
│   │   │   ├── Daft Punk - One More Time.opus
│   │   │   ├── Daft Punk - One More Time.lrc
│   │   │   └── Daft Punk - Aerodynamic.opus
│   │   └── Random Access Memories/
│   │       ├── Daft Punk - Get Lucky.opus
│   │       └── Daft Punk - Get Lucky.lrc
│   └── Pink Floyd/
│       └── The Dark Side of the Moon/
│           ├── Pink Floyd - Time.opus
│           └── Pink Floyd - Time.lrc
│
├── Cravings/                        # Colección temporal de antojos
│   └── Charli xcx/
│       └── Brat/
│           ├── Charli xcx - Apple.opus
│           └── Charli xcx - Apple.lrc
│
└── Playlists/                       # Listas UTF-8 autogeneradas y copias de Lune
    ├── Permanent.m3u8
    ├── Conveyor.m3u8
    ├── Priority_Discovery.m3u8
    ├── Live_Rotation.m3u8
    ├── Cravings.m3u8
    ├── lune_playlists_backup.json   # Copia nativa para importar en Lune en Android
    ├── Artistas/                    # Listas individuales por artista
    │   ├── Daft Punk.m3u8
    │   └── Pink Floyd.m3u8
    └── Listas Propias/              # Listas creadas por el usuario en Lune
        └── Mi Selección.m3u8
```

> [!IMPORTANT]
> **Regla Estricta de Jerarquía:** Dentro de `Permanent/`, los archivos de audio se ordenan obligatoriamente bajo el esquema `Permanent/<Artista_Principal>/<Álbum>/`. Quedan terminantemente prohibidas subcarpetas intermedias como `Favoritos/`, `Sencillos/` o `Descubrimientos/` para garantizar la limpieza de carpetas y la compatibilidad con scrobblers.

---

## 🧩 Catálogo de Módulos y Responsabilidades

Todos los módulos de Python residen en [`src/`](../../src/):

| Módulo | Clase / Funciones Principales | Responsabilidades Clave |
| :--- | :--- | :--- |
| [`src/paths.py`](../../src/paths.py) | `StoragePaths` | Resolución dinámica de rutas personales (`~`), saneamiento de directorios, alias en inglés y español. |
| [`src/db.py`](../../src/db.py) | `get_db_connection` | Conexión segura con modo WAL (`PRAGMA journal_mode=WAL`), timeout de espera (30s) y optimización de caché. |
| [`src/album_resolver.py`](../../src/album_resolver.py) | `resolve_album_track`, `get_primary_artist` | Resolución semántica de álbumes de estudio, bonificación heurística (+100 puntos) y filtro antagónico. |
| [`src/downloader.py`](../../src/downloader.py) | `Downloader` | Extracción de audio en lotes con `yt-dlp`, etiquetas Vorbis/MP4, incrustación de carátulas e intervalos de pausa. |
| [`src/engine.py`](../../src/engine.py) | `MusicEngine` | Orquestador central: radar de lanzamientos, copias de seguridad, sincronización, telemetría, purgas y descargas. |
| [`src/curator_llm.py`](../../src/curator_llm.py) | `CuratorLLM` | Prompts de IA con Gemini, evaluación del perfil de gustos y recomendaciones de radios de YouTube Music. |
| [`src/telemetry.py`](../../src/telemetry.py) | `TelemetryEngine` | Integración con la API de ListenBrainz y coincidencia difusa (`thefuzz`) entre scrobbles y pistas locales. |
| [`src/order_processor.py`](../../src/order_processor.py) | `OrderProcessor` | Análisis de lenguaje natural y regex en `requests.txt`, traslados de álbumes y solicitudes de purga. |
| [`src/lyrics_provider.py`](../../src/lyrics_provider.py) | `LyricsProvider` | Cascada de letras sincronizadas `.lrc`: LRCLIB $\rightarrow$ syncedlyrics $\rightarrow$ YouTube Music $\rightarrow$ lyrics.ovh. |
| [`src/genre_resolver.py`](../../src/genre_resolver.py) | `resolve_genre`, `enrich_library_genres` | Clasificación granular de géneros utilizando caché local en SQLite, API de MusicBrainz e IA de Gemini. |
| [`src/enrich_track_meta.py`](../../src/enrich_track_meta.py) | `enrich_library_metadata` | Inyección de números canónicos de pista y fechas de lanzamiento en las etiquetas físicas y en SQLite. |
| [`src/playlist_gen.py`](../../src/playlist_gen.py) | `PlaylistGenerator` | Compilación de listas `.m3u8` en UTF-8, generación de copias de seguridad para Lune y monitor de carpetas. |
| [`src/backup_manager.py`](../../src/backup_manager.py) | `BackupManager` | Instantáneas en caliente de SQLite, deduplicación SHA-256, paquetes `.tar.gz` y reasignación de rutas. |
| [`src/sync.py`](../../src/sync.py) | `FileSyncManager` | Detección de reorganizaciones manuales de archivos, limpieza de sidecars huérfanos y límite antiborrado masivo. |
| [`src/notifications.py`](../../src/notifications.py) | `send_notification` | Notificaciones no bloqueantes de escritorio en Linux vía `notify-send` con degradación elegante sin entorno gráfico. |
| [`src/cli.py`](../../src/cli.py) | `main` | Análisis de argumentos y enrutamiento de subcomandos para `main.py`. |

---

## 🔒 Modelo de Concurrencia y Bloqueos

Music Engine emplea un modelo de seguridad por capas para evitar condiciones de carrera:

1. **Bloqueo a Nivel de Proceso:** Al arrancar, `MusicEngine` adquiere un bloqueo exclusivo sobre `data/engine.lock` mediante la librería `filelock`. Si un cron o temporizador de systemd se activa mientras hay una ejecución manual en curso, el segundo proceso termina de forma limpia sin colisionar.
2. **Concurrencia WAL de SQLite:** SQLite opera en modo WAL con `PRAGMA synchronous=NORMAL` y un tiempo de espera ante ocupación de 30.000 ms, permitiendo lecturas concurrentes continuas mientras los hilos de fondo realizan escrituras.
3. **Mecanismo Antiborrado Masivo:** Implementado en `FileSyncManager`. Si se eliminan más de 50 archivos de golpe fuera del control del motor, las purgas se pausan automáticamente para proteger contra desconexiones accidentales de discos o errores de sincronización.

---

## 🤖 Directrices para Desarrolladores y Colaboradores

Cualquier colaborador humano o asistente de programación de IA debe seguir las directrices recogidas en [`CONTEXT.md`](../../CONTEXT.md):

1. **Código Estrictamente en Inglés:** Todo el código, nombres de variables, funciones, docstrings, comentarios en código, líneas de registro en terminal y mensajes de commit de git deben redactarse en inglés claro.
2. **Privacidad de Datos e Higiene de Git:** Nunca incluyas en commits archivos de audio personales, bases de datos reales (`*.sqlite`), copias de seguridad (`data/backups/`), claves secretas (`.env`) ni cookies del navegador (`cookies.txt`). Actualiza siempre `.gitignore` al introducir nuevo estado en tiempo de ejecución.
3. **Sincronización Continua de Documentación:** Cualquier cambio en el esquema de la base de datos, opciones de la CLI, parámetros de configuración o arquitectura del motor debe actualizarse en sincronía en `README.md`, `CONTEXT.md` y en los documentos correspondientes en `docs/`.

---

<p align="center">
  <a href="troubleshooting.md"><b>⬅ Solución de Problemas y FAQ</b></a> • <a href="README.md"><b>Volver al Portal de Documentación ➡</b></a>
</p>
