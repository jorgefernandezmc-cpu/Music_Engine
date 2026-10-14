# 💻 Referencia de Comandos CLI

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/cli-reference.md">🇬🇧 English</a> | <b>🇪🇸 Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/guia-referencia_cli-brightgreen?style=for-the-badge&logo=gnubash&logoColor=white" alt="Referencia de CLI">
  <img src="https://img.shields.io/badge/interfaz-main.py-blue?style=for-the-badge" alt="Interfaz main.py">
</p>

Todas las operaciones de gestión, curación, enriquecimiento, mantenimiento y copias de seguridad en **Music Engine** se ejecutan a través de un único punto de entrada unificado: [`main.py`](../../main.py).

---

## 📑 Tabla de Contenidos

- [Sintaxis General de Comandos](#-sintaxis-general-de-comandos)
- [Tabla Resumen de Comandos](#-tabla-resumen-de-comandos)
- [Ciclo de Vida y Ejecuciones del Motor](#ciclo-de-vida-y-ejecuciones-del-motor)
  - [`run`](#1-run)
  - [`status`](#2-status)
- [Importación y Descargas](#importación-y-descargas)
  - [`import-playlist`](#3-import-playlist)
  - [`download-pending`](#4-download-pending)
- [Metadatos, Géneros y Letras](#metadatos-géneros-y-letras)
  - [`enrich-lyrics`](#5-enrich-lyrics)
  - [`enrich-genres`](#6-enrich-genres)
  - [`enrich-metadata`](#7-enrich-metadata)
  - [`fix-metadata`](#8-fix-metadata)
  - [`set-album`](#9-set-album)
- [Listas de Reproducción y Monitorización](#listas-de-reproducción-y-monitorización)
  - [`update-playlists`](#10-update-playlists)
  - [`watch-folders`](#11-watch-folders)
- [Telemetría](#telemetría)
  - [`sync-telemetry`](#12-sync-telemetry)
- [Copias de Seguridad y Recuperación](#copias-de-seguridad-y-recuperación)
  - [`backup`](#13-backup)
  - [`export-backup`](#14-export-backup)
  - [`restore-backup`](#15-restore-backup)
- [Script de Ejecución Rápida](#-script-de-ejecución-rápida)

---

## ⌨️ Sintaxis General de Comandos

```bash
# Con el entorno virtual activado:
python main.py <comando> [opciones]

# Invocando directamente el binario del entorno virtual:
.venv/bin/python main.py <comando> [opciones]
```

---

## 📊 Tabla Resumen de Comandos

| Comando | Argumentos / Opciones | Rol Principal |
| :--- | :--- | :--- |
| [`run`](#1-run) | `[--fill]` | Ejecuta un ciclo autónomo completo del motor. |
| [`status`](#2-status) | — | Muestra contadores de pistas, estados y uso de disco. |
| [`import-playlist`](#3-import-playlist) | `<URL_o_ID> [--download] [--no-album-search]` | Indexa una lista de YouTube Music directamente en la biblioteca Permanente. |
| [`download-pending`](#4-download-pending) | — | Descarga las pistas en cola (`PENDING`) sin invocar al curador de IA. |
| [`enrich-lyrics`](#5-enrich-lyrics) | `[--limit N] [--all] [--no-upgrade]` | Escanea la biblioteca y descarga letras sincronizadas pendientes (`.lrc`). |
| [`enrich-genres`](#6-enrich-genres) | `[--limit N] [--all] [--force-all] [--no-ai]` | Clasifica géneros musicales mediante IA y MusicBrainz en etiquetas y BD. |
| [`enrich-metadata`](#7-enrich-metadata) | `[--limit N] [--force-all]` | Completa números de pista y fechas de lanzamiento oficiales. |
| [`fix-metadata`](#8-fix-metadata) | `[--use-ai]` | Audita y repara versiones dudosas (karaoke, directos piratas, versiones acústicas). |
| [`set-album`](#9-set-album) | `"<cancion>" "<nuevo_album>"` | Reasigna un tema permanente a un álbum y mueve los archivos en disco. |
| [`update-playlists`](#10-update-playlists) | — | Fuerza la regeneración de todas las listas `.m3u8` y la copia de Lune. |
| [`watch-folders`](#11-watch-folders) | `[--interval SEGUNDOS]` | Monitoriza cambios manuales en carpetas y actualiza listas en tiempo real. |
| [`sync-telemetry`](#12-sync-telemetry) | — | Sincroniza scrobbles y favoritos ❤️ desde ListenBrainz sin descargar. |
| [`backup`](#13-backup) | `[--tag ETIQUETA] [--force] [--list]` | Crea o lista instantáneas SQLite en caliente deduplicadas. |
| [`export-backup`](#14-export-backup) | `[-o RUTA_DESTINO]` | Exporta un paquete `.tar.gz` portable para migrar de equipo. |
| [`restore-backup`](#15-restore-backup) | `<ORIGEN> [--target-base-dir DIR] [--no-rebase]` | Restaura el estado con reasignación automática de rutas de archivos. |

---

## Ciclo de Vida y Ejecuciones del Motor

### 1. `run`
Ejecuta una pasada completa del ciclo de vida autónomo:
1. Radar de lanzamientos diarios de artistas favoritos.
2. Copia de seguridad en caliente de la base de datos.
3. Sincronización inversa (detecta movimientos manuales) y limpieza de fantasmas (archivos `.lrc` huérfanos o pistas eliminadas).
4. Telemetría de ListenBrainz (actualiza scrobbles y promociona pistas con ❤️).
5. Procesamiento del buzón remoto de `requests.txt`.
6. Purga por retención de antojos (temas que superan `retention_days`).
7. Promoción de la Cinta (temas con $\ge 15$ reproducciones pasan a Permanente).
8. Purga de Guillotina (temas no reproducidos tras el periodo de gracia o con alta tasa de saltos).
9. Curación progresiva con IA (Gemini) y descarga de pistas (`yt-dlp`).
10. Regeneración de listas de reproducción y notificación de escritorio consolidada.

```bash
# Ejecución periódica normal (descarga hasta cycle_max_downloads, por defecto 50):
python main.py run

# Modo de reabastecimiento completo (se ejecuta hasta llenar el búfer de la Cinta):
python main.py run --fill
```

---

### 2. `status`
Muestra un resumen limpio de los estados de las pistas en base de datos, espacio en disco consumido y marcas de tiempo de telemetría:

```bash
python main.py status
```

*Ejemplo de salida:*
```text
=============================================
 CONVEYOR BELT STATUS
=============================================
Base directory:     /home/usuario/Music/Songs
Tracks in CONVEYOR: 284
PERMANENT tracks:   1120
CRAVINGS tracks:    14
PENDING tracks:     12
PURGED tracks:      95
---------------------------------------------
Disk space used:    14.85 GB
Last scrobble:      2026-10-12T18:42:10
Last LB sync:       2026-10-12T19:00:00
=============================================
```

---

## Importación y Descargas

### 3. `import-playlist`
Importa una lista de reproducción de YouTube Music directamente a la biblioteca **Permanente**. Por defecto, prioriza versiones canónicas de álbum de estudio frente a sencillos sueltos o videoclips.

```bash
# Solo indexar en base de datos (encoladas como PENDING):
python main.py import-playlist "https://music.youtube.com/playlist?list=PLxxxxxxxx"

# Indexar y descargar inmediatamente todas las canciones:
python main.py import-playlist "PLxxxxxxxx" --download

# Importar exactamente las versiones de la lista sin buscar álbumes de estudio:
python main.py import-playlist "PLxxxxxxxx" --download --no-album-search
```

---

### 4. `download-pending`
Descarga todas las pistas en estado `PENDING`. Muy útil tras importar varias listas o cuando deseas descargar temas pendientes sin invocar recomendaciones de IA.

```bash
python main.py download-pending
```

---

## Metadatos, Géneros y Letras

### 5. `enrich-lyrics`
Escanea la biblioteca en busca de letras ausentes y mejora letras existentes en texto plano al formato sincronizado `.lrc`:

```bash
# Procesar un lote de hasta 50 pistas (por defecto):
python main.py enrich-lyrics

# Procesar un lote personalizado de 100 pistas:
python main.py enrich-lyrics --limit 100

# Escanear toda la biblioteca sin límite de lote:
python main.py enrich-lyrics --all

# Escanear únicamente letras faltantes sin intentar actualizar las no sincronizadas:
python main.py enrich-lyrics --no-upgrade
```

---

### 6. `enrich-genres`
Clasifica géneros musicales con alta precisión mediante MusicBrainz y Gemini AI, incrustando etiquetas Vorbis/MP4 y actualizando SQLite:

```bash
# Enriquecer un lote de 50 temas con género pendiente:
python main.py enrich-genres

# Enriquecer todas las pistas pendientes en la biblioteca:
python main.py enrich-genres --all

# Forzar el reanálisis de todas las pistas, incluso si ya tienen género:
python main.py enrich-genres --all --force-all

# Basarse exclusivamente en MusicBrainz / Deezer sin consultar la IA de Gemini:
python main.py enrich-genres --all --no-ai
```

---

### 7. `enrich-metadata`
Audita e inyecta números de pista oficiales (`track_number`) y fechas de lanzamiento (`release_date`) consultando el catálogo de YouTube Music:

```bash
# Enriquecer hasta 50 pistas:
python main.py enrich-metadata --limit 50

# Enriquecer toda la biblioteca:
python main.py enrich-metadata --limit 0

# Forzar reevaluación de todas las canciones:
python main.py enrich-metadata --force-all
```

---

### 8. `fix-metadata`
Audita la biblioteca en busca de temas sospechosos (versiones karaoke, directos no oficiales, tributos acústicos o versiones chip-tune) y los reemplaza por las versiones oficiales de álbum de estudio:

```bash
# Auditoría y reparación heurística:
python main.py fix-metadata

# Auditoría utilizando la IA de Gemini como desempate avanzado:
python main.py fix-metadata --use-ai
```

---

### 9. `set-album`
Reasigna una pista permanente a un álbum específico. El motor actualiza la base de datos, renombra y mueve físicamente los archivos de audio y `.lrc` en disco, actualiza las etiquetas y elimina directorios vacíos:

```bash
python main.py set-album "Get Lucky" "Random Access Memories"
python main.py set-album "Pink Floyd Time" "The Dark Side of the Moon"
```

---

## Listas de Reproducción y Monitorización

### 10. `update-playlists`
Regenera todas las listas `.m3u8` (`Permanent.m3u8`, `Conveyor.m3u8`, `Priority_Discovery.m3u8`, `Live_Rotation.m3u8`, `Cravings.m3u8`, listas por artista) y la copia de seguridad JSON para el reproductor Lune:

```bash
python main.py update-playlists
```

---

### 11. `watch-folders`
Ejecuta un monitor ligero del sistema de archivos que detecta movimientos de archivos, adiciones o reorganizaciones manuales, refrescando las listas de reproducción en tiempo real:

```bash
# Monitorizar cambios cada 5 segundos (por defecto):
python main.py watch-folders

# Comprobar cada 2 segundos:
python main.py watch-folders --interval 2
```

---

## Telemetría

### 12. `sync-telemetry`
Se conecta a la API de ListenBrainz para obtener scrobbles recientes y pistas marcadas con ❤️ sin ejecutar el ciclo completo del motor ni iniciar descargas:

```bash
python main.py sync-telemetry
```

---

## Copias de Seguridad y Recuperación

### 13. `backup`
Crea instantáneas SQLite en caliente utilizando las APIs de copia de seguridad WAL de SQLite con deduplicación por hash SHA-256:

```bash
# Crear una instantánea (se omite si el estado no ha cambiado):
python main.py backup

# Etiquetar la instantánea con una etiqueta personalizada:
python main.py backup --tag "antes_de_importacion_grande"

# Forzar la creación omitiendo la deduplicación por hash:
python main.py backup --force

# Listar todas las instantáneas disponibles con fechas y tamaños:
python main.py backup --list
```

---

### 14. `export-backup`
Exporta un paquete portable autocontenido (`.tar.gz`) que incluye la base de datos, el perfil de gustos, el histórico de descargas, el estado de carpetas y el manifiesto para migrar fácilmente a otro PC:

```bash
# Exportar al destino predeterminado (data/backups/):
python main.py export-backup

# Exportar a una ruta personalizada:
python main.py export-backup -o ~/Desktop/music_engine_migracion.tar.gz
```

---

### 15. `restore-backup`
Restaura cualquier instantánea o paquete de migración. Crea automáticamente una instantánea de seguridad de emergencia antes de modificar datos activos y reasigna las rutas de archivos para adaptarlas a tu nuevo sistema:

```bash
# Restaurar en el mismo equipo:
python main.py restore-backup data/backups/music_engine_backup_20261012_120000.tar.gz

# Restaurar en un nuevo ordenador con una ruta de música diferente:
python main.py restore-backup ~/migracion.tar.gz --target-base-dir ~/Music/Songs

# Restaurar sin modificar las rutas almacenadas en base de datos:
python main.py restore-backup backup.sqlite --no-rebase
```

---

## ⚡ Script de Ejecución Rápida

Para una ejecución interactiva desde la terminal sin necesidad de recordar parámetros, utiliza el script auxiliar:

```bash
./scripts/update_now.sh
```

---

<p align="center">
  <a href="configuration.md"><b>⬅ Guía de Configuración</b></a> • <a href="mailbox-commands.md"><b>Siguiente: Comandos del Buzón Remoto ➡</b></a>
</p>
