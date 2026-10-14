# 💾 Copias de Seguridad, Instantáneas y Migración entre PCs

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/backup-and-migration.md">English</a> | <b>Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/copias_seguridad-cero_inactividad-brightgreen?style=for-the-badge&logo=sqlite&logoColor=white" alt="Copia de Seguridad Cero Inactividad">
  <img src="https://img.shields.io/badge/deduplicacion-SHA--256-blue?style=for-the-badge" alt="Deduplicación SHA-256">
  <img src="https://img.shields.io/badge/migracion-un_comando-orange?style=for-the-badge" alt="Migración en un Comando">
</p>

Music Engine cuenta con un motor inteligente y centralizado de copias de seguridad y migración implementado en [`src/backup_manager.py`](../../src/backup_manager.py). Garantiza instantáneas en caliente sin tiempo de inactividad, rotación automática de retención, deduplicación por hash SHA-256 y transferencia fluida del estado de tu biblioteca a un nuevo PC con reasignación automática de rutas (*path rebasing*).

---

## 📑 Tabla de Contenidos

- [Principios Fundamentales del Motor de Respaldo](#-principios-fundamentales-del-motor-de-respaldo)
- [1. Arquitectura de Paquete Unificado en un Solo Archivo](#1-arquitectura-de-paquete-unificado-en-un-solo-archivo)
- [2. Instantáneas SQLite en Caliente (Sin Inactividad)](#2-instantáneas-sqlite-en-caliente-sin-inactividad)
- [3. Deduplicación por Hash SHA-256](#3-deduplicación-por-hash-sha-256)
- [4. Retención y Rotación Automáticas](#4-retención-y-rotación-automáticas)
- [5. Creación Manual de Instantáneas](#5-creación-manual-de-instantáneas)
- [6. Exportación de Paquetes de Migración](#6-exportación-de-paquetes-de-migración)
- [7. Restauración y Reasignación de Rutas entre Equipos](#7-restauración-y-reasignación-de-rutas-entre-equipos)
- [Instantánea de Seguridad Previa a la Restauración](#-instantánea-de-seguridad-previa-a-la-restauración)

---

## 🛡️ Principios Fundamentales del Motor de Respaldo

1. **Consistencia WAL en Caliente:** Utiliza la API nativa de copias en línea de SQLite (`sqlite3.backup()`). Las instantáneas son 100% consistentes y nunca sufren escrituras corruptas ni bloqueos de concurrencia.
2. **Paquetes Unificados en un Solo Archivo:** Todo lo necesario para reconstruir el estado de tu biblioteca (base de datos, perfil de gustos, historial de descargas, huellas de carpetas y manifiesto) se empaqueta en un **único archivo `.tar.gz`**.
3. **Cero Copias Redundantes:** Si el contenido de la base de datos no ha cambiado desde la última instantánea, las escrituras innecesarias en disco se omiten automáticamente.
4. **Restauración Autocurativa:** ¿Te mudas a un nuevo PC con otro nombre de usuario o diferente ruta de música? El motor de restauración reescribe automáticamente las rutas de los archivos en la base de datos.

---

## 1. Arquitectura de Paquete Unificado en un Solo Archivo

Cada paquete de copia de seguridad `.tar.gz` contiene:

```text
music_engine_backup_20261012_143000.tar.gz
├── conveyor_state.sqlite           # Instantánea limpia en caliente de la base de datos
├── manifest.json                   # Metadatos: timestamp, versión, SHA-256, rutas y etiquetas
└── auxiliary/                      # Estado auxiliar imprescindible en tiempo de ejecución
    ├── taste_profile.json          # Perfil de gustos del curador de IA
    ├── download_archive.txt        # Histórico de IDs descargados con yt-dlp
    └── playlist_folder_state.json  # Huellas de cambio de listas de reproducción
```

---

## 2. Instantáneas SQLite en Caliente (Sin Inactividad)

Copiar archivos de manera tradicional (`cp conveyor_state.sqlite ...`) puede generar bases de datos corruptas o bloqueadas cuando SQLite opera en modo WAL (Write-Ahead Logging).

Music Engine utiliza la API interna de Python `sqlite3.backup()`:
- Vuelca de manera segura los diarios WAL activos.
- Bloquea páginas de forma atómica en memoria.
- Genera una copia independiente e impoluta sin interrumpir descargas ni reproducciones en curso.

---

## 3. Deduplicación por Hash SHA-256

Para evitar llenar el disco con copias diarias idénticas cuando no se han añadido ni escuchado canciones nuevas:
1. Antes de escribir una instantánea, el motor calcula el hash SHA-256 de la base de datos actual.
2. Lo compara contra el marcador guardado en `data/.last_backup_hash`.
3. Si el hash coincide, la copia se omite:
   ```text
   [i] State unchanged since last snapshot. Deduplication skipped redundant backup.
   ```
4. Puedes anular la deduplicación en cualquier momento con el modificador `--force`.

---

## 4. Retención y Rotación Automáticas

Configurado en `config/config.yaml`:

```yaml
backup:
  auto_backup: true      # Se ejecuta automáticamente en cada ciclo del motor
  dir: "data/backups"    # Directorio de destino
  max_backups: 10        # Límite rotativo de instantáneas a conservar
  format: "bundle"       # "bundle" (.tar.gz unificado) o "db_only" (.sqlite.gz)
  dedup_by_hash: true    # Activar deduplicación por SHA-256
```

Cuando el número de instantáneas supera `max_backups`, los archivos más antiguos se eliminan automáticamente.

---

## 5. Creación Manual de Instantáneas

### Crear una Instantánea
```bash
python main.py backup
```

### Etiquetar una Instantánea con una Descripción
```bash
python main.py backup --tag "antes_de_llenado_masivo"
```

### Forzar una Instantánea Omitiendo la Deduplicación
```bash
python main.py backup --force
```

### Listar las Instantáneas Disponibles
```bash
python main.py backup --list
```

*Ejemplo de salida:*
```text
=======================================================
 AVAILABLE SNAPSHOTS (3 in /home/usuario/Music_Engine/data/backups)
=======================================================
 • music_engine_backup_20261012_143000 [manual]
    Date: 2026-10-12 14:30:00 | Size: 412.5 KB | Format: bundle
 • music_engine_backup_20261011_040000 [auto]
    Date: 2026-10-11 04:00:00 | Size: 410.2 KB | Format: bundle
=======================================================
```

---

## 6. Exportación de Paquetes de Migración

Para trasladar el estado completo de tu motor a otro ordenador o servidor doméstico:

```bash
# Exportar al directorio predeterminado (data/backups/):
python main.py export-backup

# Exportar a una ubicación específica (ej. pendrive USB o escritorio):
python main.py export-backup -o ~/Desktop/music_engine_migracion.tar.gz
```

*Salida:*
```text
[✓] Migration bundle exported successfully: /home/usuario/Desktop/music_engine_migracion.tar.gz
    You can copy this file to another machine and run:
    python main.py restore-backup music_engine_migracion.tar.gz
```

---

## 7. Restauración y Reasignación de Rutas entre Equipos

Al restaurar una copia de seguridad en otro equipo, los nombres de usuario y rutas suelen diferir:
- **PC Antiguo:** `/home/aitor/Music/Songs/...`
- **PC Nuevo:** `/home/servidor/Media/Music/...`

El comando `restore-backup` detecta automáticamente estas discrepancias y reescribe todas las rutas de archivos de audio guardadas en la base de datos para que apunten a la nueva ubicación.

### Restaurar en el Mismo Equipo
```bash
python main.py restore-backup data/backups/music_engine_backup_20261012_143000.tar.gz
```

### Restaurar en un Nuevo Equipo con Otra Carpeta de Música
```bash
python main.py restore-backup ~/music_engine_migracion.tar.gz --target-base-dir ~/Media/Music
```

*Resumen de salida:*
```text
=======================================================
 RESTORE SUMMARY
=======================================================
 - Total tracks in database: 1416
 - Rebased path references:  1416
 - Components restored:      database, taste_profile.json, download_archive.txt, playlist_folder_state.json
 - Base directory rebased:   '/home/aitor/Music/Songs' -> '/home/servidor/Media/Music'
=======================================================
```

---

## 🛡️ Instantánea de Seguridad Previa a la Restauración

Antes de alterar cualquier base de datos activa o extraer archivos durante un proceso de restauración, Music Engine **crea automáticamente una instantánea de seguridad de emergencia** de tu estado actual:

```text
data/backups/pre_restore_safety_backup_YYYYMMDD_HHMMSS.sqlite.gz
```

Si una operación de restauración se interrumpe de forma accidental o se apunta por error a un archivo equivocado, tus datos previos se mantienen 100% a salvo y recuperables.

---

<p align="center">
  <a href="metadata-and-lyrics.md"><b>⬅ Metadatos y Letras</b></a> • <a href="troubleshooting.md"><b>Siguiente: Solución de Problemas y FAQ ➡</b></a>
</p>
