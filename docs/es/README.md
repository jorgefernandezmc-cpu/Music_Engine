# 📚 Portal de Documentación de Music Engine

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/README.md">🇬🇧 English</a> | <b>🇪🇸 Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/docs-v2.0-blue?style=for-the-badge" alt="Versión de Documentación">
  <img src="https://img.shields.io/badge/cobertura-completa-brightgreen?style=for-the-badge" alt="Cobertura Completa">
  <img src="https://img.shields.io/badge/audiencia-todos_los_usuarios-orange?style=for-the-badge" alt="Audiencia Todos los Usuarios">
</p>

Bienvenido al portal exhaustivo de documentación de **Music Engine** — el ecosistema de gestión musical autónomo, auto-alojado (*self-hosted*) y 100% privado.

Tanto si estás configurando el sistema por primera vez, consultando los comandos de la interfaz de terminal (CLI), integrando la reproducción y registro de canciones en Android, o contribuyendo al código base del motor, a continuación encontrarás guías detalladas y enfocadas a cada necesidad.

---

## 🗺️ Directorio de Documentación

```text
docs/es/
├── README.md               # 📍 Estás aquí: Índice y mapa de navegación
├── installation.md         # 📦 Requisitos previos, paquetes del SO (Linux/macOS/WSL2), venv y dependencias
├── configuration.md        # ⚙️ Referencia de config.yaml, secretos .env, perfil de gustos e init de BD
├── cli-reference.md        # 💻 Manual exhaustivo de comandos CLI, argumentos, opciones y ejemplos reales
├── mailbox-commands.md     # 📱 Sintaxis del buzón de control remoto peticiones.txt / requests.txt (ES y EN)
├── mobile-and-sync.md      # 📲 Sincronización P2P con Syncthing, reproductores Android y telemetría ListenBrainz
├── automation.md           # ⏰ Automatización en segundo plano mediante servicios de usuario y timers de systemd
├── metadata-and-lyrics.md  # 🎶 Cascada de letras sincronizadas .lrc, géneros con IA y reparación de álbumes
├── backup-and-migration.md # 💾 Instantáneas en caliente de SQLite, deduplicación SHA-256 y migración entre PCs
├── troubleshooting.md      # ❓ Preguntas frecuentes, errores comunes, diagnósticos y recuperación
└── architecture.md         # 🏗️ Internos técnicos, modelo de datos SQLite y catálogo de módulos
```

---

## 🎯 Documentación según tu Perfil

Elige la ruta que mejor se adapte a tu objetivo actual:

| Perfil de Usuario | Ruta de Lectura Recomendada |
| :--- | :--- |
| **🚀 Primeros Pasos** | 1. [Guía de Instalación](installation.md)<br>2. [Guía de Configuración](configuration.md)<br>3. [Ecosistema Móvil y Sincronización](mobile-and-sync.md) |
| **🎧 Oyente Diario** | 1. [Comandos del Buzón Remoto](mailbox-commands.md)<br>2. [Ecosistema Móvil y Sincronización](mobile-and-sync.md)<br>3. [Referencia de CLI](cli-reference.md) |
| **🛠️ Administrador / Sysadmin** | 1. [Automatización en Segundo Plano (Systemd)](automation.md)<br>2. [Copias de Seguridad y Migración](backup-and-migration.md)<br>3. [Solución de Problemas y FAQ](troubleshooting.md) |
| **🎵 Audiófilo y Curador de Etiquetas** | 1. [Metadatos, Géneros y Letras](metadata-and-lyrics.md)<br>2. [Guía de Configuración](configuration.md) (códecs y heurísticas) |
| **💻 Desarrollador y Colaborador** | 1. [Arquitectura del Sistema e Internos](architecture.md)<br>2. [Referencia de CLI](cli-reference.md)<br>3. [CONTEXT.md del Proyecto](../../CONTEXT.md) |

---

## 📑 Resumen de las Guías

### 1. 📦 [Guía de Instalación](installation.md)
Instrucciones paso a paso para Debian, Ubuntu, Arch Linux, Fedora, openSUSE, Alpine, macOS y Windows WSL2. Cubre los paquetes del sistema (`python3-venv`, `ffmpeg`), clonación del repositorio, configuración del entorno virtual de Python y comandos de verificación.

### 2. ⚙️ [Guía de Configuración](configuration.md)
Explicación detallada de cada parámetro de `config/config.yaml`: rutas de almacenamiento, límites de rotación de la Cinta, ponderación de descubrimiento de la IA de Gemini, parámetros de descarga y políticas de copia de seguridad. Detalla las credenciales en `config/.env`, inicialización del perfil de gustos en `data/taste_profile.json`, creación de la base de datos y cookies/cabeceras opcionales de YouTube.

### 3. 💻 [Referencia de CLI](cli-reference.md)
Manual completo para `main.py` con sintaxis, comandos disponibles, modificadores (`--fill`, `--download`, `--force-all`, `--use-ai`, `--no-rebase`, etc.) y recetas prácticas para el mantenimiento diario.

### 4. 📱 [Comandos del Buzón Remoto (`peticiones.txt`)](mailbox-commands.md)
Aprende a controlar el motor desde tu smartphone editando un sencillo archivo de texto sincronizado. Cubre la sintaxis en español e inglés para solicitar temas individuales, álbumes de estudio completos, antojos temporales, marcar canciones favoritas, reclasificar géneros, refrescar letras y purgar temas.

### 5. 📲 [Ecosistema Móvil y Sincronización](mobile-and-sync.md)
Cómo configurar una experiencia musical offline impecable: sincronización bidireccional con Syncthing mediante reglas optimizadas en `.stignore`, configuración de reproductores locales (**Lune**, **Auxio**, **Symfonium**, **VLC**), exportación de listas de usuario creadas en el móvil y registro de reproducciones y favoritos con **Pano Scrobbler** y **ListenBrainz**.

### 6. ⏰ [Automatización en Segundo Plano (Systemd)](automation.md)
Automatiza la ejecución de Music Engine en Linux mediante unidades de usuario no privilegiadas de `systemd`. Incluye archivos listos para usar de `.service` y `.timer`, soporte para activaciones persistentes tras apagados, gestión de logs y alternativas con tareas cron.

### 7. 🎶 [Metadatos, Géneros y Letras](metadata-and-lyrics.md)
Profundización en el pipeline de enriquecimiento: cascada multifuente de letras sincronizadas (LRCLIB, syncedlyrics, YouTube Music, lyrics.ovh), inyección de etiquetas Vorbis/ID3, categorización inteligente de géneros con Gemini y MusicBrainz, y reparación de temas para asegurar versiones oficiales de álbum.

### 8. 💾 [Copias de Seguridad, Instantáneas y Migración](backup-and-migration.md)
Descubre cómo el motor protege el estado de tu biblioteca: instantáneas en caliente de SQLite sin tiempo de inactividad utilizando la API de WAL, deduplicación mediante hashes SHA-256, paquetes unificados de migración en un solo archivo `.tar.gz` y restauración en otro ordenador con reasignación automática de rutas (*path rebasing*).

### 9. ❓ [Solución de Problemas y Preguntas Frecuentes (FAQ)](troubleshooting.md)
Respuestas y soluciones a las incidencias más frecuentes: claves de API no encontradas, fallos de extracción de audio con `ffmpeg`, bloqueos de base de datos en modo WAL, limitaciones de tasa (*rate-limiting*) de YouTube, retrasos en la telemetría móvil y purgas accidentales.

### 10. 🏗️ [Arquitectura del Sistema e Internos](architecture.md)
Visión técnica exhaustiva para desarrolladores: máquina de estados del ciclo de vida de las pistas, esquema relacional de SQLite con índices, jerarquía de directorios en disco y catálogo de módulos detallando cada clase en `src/`.

---

<p align="center">
  <a href="../../README.es.md"><b>⬅ Volver al README del Proyecto</b></a> • <a href="installation.md"><b>Siguiente: Guía de Instalación ➡</b></a>
</p>
