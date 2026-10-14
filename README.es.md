# 🎵 Music Engine — La Cinta Transportadora Musical Autónoma

<p align="right">
  <b>Language / Idioma:</b>
  <a href="README.md">🇬🇧 English</a> | <b>🇪🇸 Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/database-SQLite_WAL-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/AI-Google_Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Google Gemini">
  <img src="https://img.shields.io/badge/downloader-yt--dlp-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="yt-dlp">
  <img src="https://img.shields.io/badge/sync-Syncthing-16A085?style=for-the-badge&logo=syncthing&logoColor=white" alt="Syncthing">
  <img src="https://img.shields.io/badge/docs-modular_v2.0-blueviolet?style=for-the-badge" alt="Docs Modulares">
</p>

> **Music Engine** es un ecosistema de gestión musical autónomo, auto-alojado (*self-hosted*) y 100% privado. Mantiene una biblioteca local de audio en alta fidelidad (`.opus` / `.m4a`), descubre y descarga nueva música de forma autónoma mediante Inteligencia Artificial (Google Gemini) y radios de YouTube Music, prioriza de manera estricta versiones oficiales de álbum de estudio frente a sencillos sueltos, y se sincroniza bidireccionalmente con dispositivos móviles Android.

---

## 🚀 El Modelo de "Cinta Transportadora" (*Conveyor Belt*)

Music Engine reemplaza las listas de reproducción estáticas por una **cinta transportadora musical automatizada**:

```text
       [ Curador IA (Gemini) / YouTube Music ]
                          │
                          ▼
              📦 Búfer "Cinta" (Conveyor/)
                 (Descubrimientos rotativos)
                 │                   │
      ¿Escuchada repetidamente?    ¿Sin reproducir / Omitida?
          (≥15 reproducciones)       │
               o                     ▼
        ¿Marcada con ❤️?        🗑️ Purgada (Guillotina)
                 │             (Eliminada del disco automáticamente)
                 ▼
     ⭐ Biblioteca Permanente (Permanent/)
      Permanent/<Artista>/<Álbum>/<Pista>.opus
```

1. **Descubrimiento Continuo (`Conveyor/`)**: Analiza tu perfil de gustos y llena un búfer rotativo con canciones nuevas.
2. **Promoción a Permanente (`Permanent/`)**: Si escuchas un tema de forma repetida ($\ge 15$ reproducciones) o pulsas ❤️ (*Favorito*) en tu reproductor móvil, se guarda de forma permanente en la carpeta oficial de su álbum de estudio.
3. **Guillotina Automatizada**: Las canciones no escuchadas tras el periodo de gracia (150 días) o con alta tasa de saltos se eliminan automáticamente del disco para optimizar el almacenamiento.
4. **Antojos Temporales (`Cravings/`)**: Descarga canciones de moda o temas veraniegos que caducan automáticamente tras 30 días sin reproducir, sin ensuciar tu biblioteca permanente.
5. **Letras Sincronizadas Integradas (`.lrc`)**: Extrae letras de karaoke sincronizadas con precisión de milisegundos desde LRCLIB, syncedlyrics y YouTube Music.

---

## ✨ Características Principales

- 🧠 **Curación con Inteligencia Artificial**: Utiliza Google Gemini para equilibrar familiaridad (60%), artistas adyacentes (25%) y exploración de nuevos géneros (15%).
- 💿 **Integridad de Álbum de Estudio**: Aplica una jerarquía estricta `Permanent/<Artista_Principal>/<Álbum>/`. Descarta sencillos sueltos, directos o versiones piratas.
- 📱 **Buzón de Control Remoto**: Pide canciones, descarga álbumes enteros, corrige géneros o purga pistas directamente desde el móvil editando un archivo de texto sincronizado (`requests.txt` / `peticiones.txt`).
- 📲 **Sincronización Móvil Impecable**: Sincronización P2P bidireccional con Android mediante Syncthing. Compatibilidad nativa con reproductores como **Lune**, **Auxio**, **Symfonium** y **Poweramp**.
- 🎧 **Telemetría Offline-First**: El registro de reproducciones (*scrobbling*) local mediante **Pano Scrobbler** + **ListenBrainz** cierra el bucle: las reproducciones y favoritos del móvil guían las promociones en el ordenador.
- 💾 **Copias de Seguridad Inteligentes y Migración entre PCs**: Instantáneas en caliente de SQLite con deduplicación por hash SHA-256 y paquetes de migración portables (`.tar.gz`) con reasignación automática de rutas (*path rebasing*).
- ⏰ **Automatización Desatendida**: Ejecución diaria totalmente automática mediante temporizadores de usuario de Linux systemd sin necesidad de privilegios root.
- 🌐 **Experiencia de Usuario Bilingüe**: La cabecera del buzón (`requests.txt` / `peticiones.txt`) y las notificaciones de escritorio se adaptan a inglés o español (`system.language`) con actualización inteligente de cabeceras al vuelo.

---

## ⚡ Inicio Rápido (3 Pasos)

Puesta en marcha en menos de 2 minutos:

```bash
# 1. Clonar el repositorio e instalar dependencias
git clone https://github.com/your-username/Music_Engine.git && cd Music_Engine
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configuración y claves secretas
cp config/config.yaml.template config/config.yaml
cp config/.env.template config/.env
# Editar config/.env y añadir tu GEMINI_API_KEY (Gratuita en https://aistudio.google.com/)

# 3. Inicializar la base de datos y verificar estado
python database/init_db.py
python main.py status
```

> [!TIP]
> ¿Buscas instrucciones detalladas de instalación para tu distribución, solución de problemas o parámetros de configuración? Consulta las guías a continuación.

---

## 📚 Portal de Documentación

La documentación completa está organizada modularmente en el directorio [`docs/es/`](docs/es/):

| Guía | Descripción | Destinatarios |
| :--- | :--- | :--- |
| 📦 **[Guía de Instalación](docs/es/installation.md)** | Paquetes del sistema (`ffmpeg`, `python3-venv`), entorno virtual en Linux/macOS/WSL2. | *Nuevos usuarios, Sysadmins* |
| ⚙️ **[Guía de Configuración](docs/es/configuration.md)** | Análisis detallado de `config.yaml`, tokens en `.env`, perfil de gustos y auth de YouTube. | *Todos los usuarios* |
| 💻 **[Referencia de CLI](docs/es/cli-reference.md)** | Manual exhaustivo de comandos de `main.py`, modificadores (`--fill`, etc.) y ejemplos prácticos. | *Usuarios avanzados, Desarrolladores* |
| 📱 **[Manual del Buzón Remoto](docs/es/mailbox-commands.md)** | Sintaxis completa para controlar el motor desde el móvil mediante `peticiones.txt` (EN y ES). | *Oyentes diarios* |
| 📲 **[Ecosistema Móvil y Sincronización](docs/es/mobile-and-sync.md)** | Configuración de Syncthing, `.stignore`, reproductores Lune/Auxio, ListenBrainz y Pano Scrobbler. | *Usuarios de Android* |
| ⏰ **[Automatización en Segundo Plano](docs/es/automation.md)** | Servicios y temporizadores de usuario de `systemd`, modo *lingering* y gestión de logs. | *Sysadmins, Self-hosters* |
| 🎶 **[Metadatos, Géneros y Letras](docs/es/metadata-and-lyrics.md)** | Cascada de letras `.lrc`, etiquetas Vorbis, clasificación de géneros por IA y reparación de álbumes. | *Audiófilos* |
| 💾 **[Copias de Seguridad y Migración](docs/es/backup-and-migration.md)** | Instantáneas SQLite en caliente, deduplicación SHA-256, paquetes portables y reescritura de rutas. | *Todos los usuarios* |
| ❓ **[Solución de Problemas y Preguntas Frecuentes](docs/es/troubleshooting.md)** | Diagnósticos, errores frecuentes (bloqueos, API keys, ffmpeg) y soluciones probadas. | *Cualquier incidencia* |
| 🏗️ **[Arquitectura e Internos del Sistema](docs/es/architecture.md)** | Guía técnica profunda: máquina de estados, esquema SQLite, catálogo de módulos y directrices. | *Colaboradores, Desarrolladores* |

👉 **[Explorar el Índice Completo de Documentación (docs/README.md)](docs/README.md)**

---

## 💻 Comandos CLI Esenciales

```bash
# Consultar el estado de la biblioteca y uso de disco:
python main.py status

# Ejecutar el ciclo regular del motor (telemetría, curación, purgas y descargas):
python main.py run

# Llenar por completo el búfer de descubrimiento (Conveyor) en una sola pasada:
python main.py run --fill

# Importar una lista de YouTube Music a la biblioteca Permanente:
python main.py import-playlist "https://music.youtube.com/playlist?list=..." --download

# Enriquecer la biblioteca con letras sincronizadas (.lrc):
python main.py enrich-lyrics --all

# Crear una instantánea de copia de seguridad del estado de la biblioteca:
python main.py backup --tag "mi_copia"
```

*Para conocer todos los comandos y modificadores, consulta la **[Referencia de CLI](docs/es/cli-reference.md)**.*

---

## 📱 Control Remoto desde el Móvil (`peticiones.txt` / `requests.txt`)

Controla tu colección musical desde el teléfono escribiendo comandos naturales en `requests.txt` o `peticiones.txt`:

```text
# Descargar álbumes de estudio completos:
disco: Pink Floyd - The Dark Side of the Moon
antojo album: Arctic Monkeys - AM

# Descargar canciones sueltas:
permanente: Daft Punk - Get Lucky
antojo: Charli xcx - Apple

# Promover o descartar canciones:
favorita: Midnight City
borrar: Canción No Deseada

# Reasignar álbum o corregir géneros:
album: Título Canción -> Disco Correcto
genero: Título Canción -> Synthwave
```

*Tanto la sintaxis en español (`disco:`, `antojo:`, `permanente:`, `favorita:`, `borrar:`, `genero:`) como en inglés (`album:`, `craving:`, `permanent:`, `favorite:`, `purge:`, `genre:`) son completamente intercambiables. Consulta la **[Guía del Buzón Remoto](docs/es/mailbox-commands.md)**.*

---

## 📐 Arquitectura del Sistema

```text
 +-----------------------------------------------------------------------+
 |                          DISPOSITIVO MÓVIL                            |
 |   [ Reproductor Lune ] ----> [ Pano Scrobbler ] ----> [ ListenBrainz ]|
 |             ^                         |                      |        |
 +-------------|-------------------------|----------------------|--------+
               | (Audio y .lrc)          |                      |
               v                         |                      |
      === [ SYNCTHING ] ===              |                      |
               ^                         |                      |
 +-------------|-------------------------|----------------------|--------+
 |             v                         v                      v        |
 |      Almacén de Música          Feedback Corazón       Reproducciones |
 |        (Canciones/)                   │                      │        |
 |             │                         +-----------┬----------+        |
 |             ▼                                     ▼                   |
 |  +-----------------------------------------------------------------+  |
 |  |                        MUSIC ENGINE (PC)                        |  |
 |  |  • StoragePaths    : Resolución dinámica de directorios         |  |
 |  |  • AlbumResolver   : Resolución de versiones de álbum de estudio|  |
 |  |  • TelemetryEngine : Sincronización de scrobbles y favoritos    |  |
 |  |  • CuratorLLM      : Curación con IA Gemini + radios de YTM     |  |
 |  |  • Downloader      : Descarga por lotes con yt-dlp y etiquetas  |  |
 |  |  • LyricsProvider  : Cascada multifuente de letras (.lrc)       |  |
 |  |  • PlaylistGen     : Generador de listas .m3u8 y copias de Lune |  |
 |  |  • BackupManager   : Instantáneas en caliente WAL y deduplicación| |
 |  |                                                                 |  |
 |  |                  Base de Datos SQLite (Modo WAL)                |  |
 |  |                    (data/conveyor_state.sqlite)                 |  |
 |  +-----------------------------------------------------------------+  |
 +-----------------------------------------------------------------------+
```

---

## 🔒 Privacidad y Almacenamiento Local

- **100% Local y Auto-alojado**: Todos los archivos de audio, listas de reproducción, letras sincronizadas y metadatos residen exclusivamente en tus discos personales.
- **Sin Dependencia de Plataformas Privativas**: Formatos abiertos y estándar (`.opus`, `.m4a`, `.lrc`, `.m3u8` en UTF-8, SQLite) garantizan compatibilidad universal con cualquier reproductor.
- **Cero Fuga de Datos**: Tu historial de escucha, claves de API, cookies y colecciones están estrictamente excluidos en `.gitignore` y nunca se comparten de forma externa.

---

<p align="center">
  <b>Music Engine</b> — Diseñado para amantes de la privacidad y coleccionistas apasionados de música.<br>
  <a href="docs/es/README.md"><b>📖 Explorar el Portal de Documentación</b></a> • <a href="README.md"><b>🇬🇧 English Version</b></a>
</p>
