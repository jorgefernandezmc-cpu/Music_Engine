# 📚 Music Engine Documentation Portal / Portal de Documentación

<p align="center">
  <img src="https://img.shields.io/badge/docs-multilingual-blue?style=for-the-badge" alt="Documentation Version">
  <img src="https://img.shields.io/badge/languages-English%20%7C%20Español-brightgreen?style=for-the-badge" alt="Languages">
  <img src="https://img.shields.io/badge/architecture-scalable_i18n-orange?style=for-the-badge" alt="Scalable i18n">
</p>

<p align="center">
  <a href="en/README.md">🇬🇧 <b>English Documentation</b></a> &nbsp;&nbsp;•&nbsp;&nbsp;
  <a href="es/README.md">🇪🇸 <b>Documentación en Español</b></a>
</p>

---

Welcome to the documentation portal for **Music Engine** — the autonomous, self-hosted, and 100% private music management ecosystem.

Bienvenido al portal de documentación de **Music Engine** — el ecosistema de gestión musical autónomo, auto-alojado y 100% privado.

---

## 🗺️ Documentation Structure / Estructura de Documentación

The documentation follows a clean, modular, and scalable multi-language hierarchy:

La documentación sigue una jerarquía multilingüe limpia, modular y escalable:

```text
docs/
├── README.md               # 🌐 Multilingual index portal (You are here)
├── en/                     # 🇬🇧 English Documentation
│   ├── README.md           # English portal index & user pathways
│   ├── installation.md     # Installation & prerequisites
│   ├── configuration.md    # Configuration reference & environment secrets
│   ├── cli-reference.md    # Complete CLI manual & options
│   ├── mailbox-commands.md # Remote control requests.txt syntax
│   ├── mobile-and-sync.md  # Syncthing, Android players & telemetry
│   ├── automation.md       # Linux systemd background automation
│   ├── metadata-and-lyrics.md # Synced lyrics (.lrc), tags & genres
│   ├── backup-and-migration.md # SQLite snapshots & cross-PC migration
│   ├── troubleshooting.md  # Troubleshooting & FAQ
│   └── architecture.md     # Deep technical internals & data model
└── es/                     # 🇪🇸 Documentación en Español
    ├── README.md           # Índice del portal en español y rutas de usuario
    ├── installation.md     # Instalación y requisitos previos
    ├── configuration.md    # Referencia de configuración y secretos .env
    ├── cli-reference.md    # Manual exhaustivo de CLI y opciones
    ├── mailbox-commands.md # Sintaxis del buzón remoto peticiones.txt
    ├── mobile-and-sync.md  # Syncthing, reproductores Android y telemetría
    ├── automation.md       # Automatización en segundo plano con systemd
    ├── metadata-and-lyrics.md # Letras sincronizadas (.lrc), etiquetas y géneros
    ├── backup-and-migration.md # Instantáneas SQLite y migración entre PCs
    ├── troubleshooting.md  # Solución de problemas y preguntas frecuentes
    └── architecture.md     # Arquitectura interna técnica y modelo de datos
```

> [!TIP]
> **Scalability for future languages:** To add a new language (e.g., French, German), contributors simply create a new directory (e.g., `docs/fr/`, `docs/de/`) containing matching filenames. The application code and commands remain exclusively in English.

---

## 📑 Complete Document Index / Índice Completo de Documentos

| Topic / Tema | 🇬🇧 English | 🇪🇸 Español | Target Audience / Destinatarios |
| :--- | :--- | :--- | :--- |
| **Portal Index** | [English Portal](en/README.md) | [Portal en Español](es/README.md) | All users / Todos |
| **📦 Installation** | [Installation Guide](en/installation.md) | [Guía de Instalación](es/installation.md) | New users, Sysadmins |
| **⚙️ Configuration** | [Configuration Guide](en/configuration.md) | [Guía de Configuración](es/configuration.md) | All users / Todos |
| **💻 CLI Reference** | [CLI Reference](en/cli-reference.md) | [Referencia de CLI](es/cli-reference.md) | Power users, Developers |
| **📱 Remote Mailbox** | [Mailbox Commands](en/mailbox-commands.md) | [Comandos del Buzón Remoto](es/mailbox-commands.md) | Daily listeners / Móvil |
| **📲 Mobile & Sync** | [Mobile Ecosystem & Sync](en/mobile-and-sync.md) | [Ecosistema Móvil y Sincronización](es/mobile-and-sync.md) | Android users / Móvil |
| **⏰ Automation** | [Background Automation](en/automation.md) | [Automatización en Segundo Plano](es/automation.md) | Sysadmins, Self-hosters |
| **🎶 Metadata & Lyrics** | [Metadata, Genres & Lyrics](en/metadata-and-lyrics.md) | [Metadatos, Géneros y Letras](es/metadata-and-lyrics.md) | Audiophiles / Curadores |
| **💾 Backups & Migration** | [Backups & PC Migration](en/backup-and-migration.md) | [Copias de Seguridad y Migración](es/backup-and-migration.md) | All users / Todos |
| **❓ Troubleshooting** | [Troubleshooting & FAQ](en/troubleshooting.md) | [Solución de Problemas y FAQ](es/troubleshooting.md) | Diagnostics / Ayuda |
| **🏗️ Architecture** | [Architecture & Internals](en/architecture.md) | [Arquitectura e Internos](es/architecture.md) | Contributors, Developers |

---

<p align="center">
  <a href="../README.md"><b>⬅ English README</b></a> &nbsp;•&nbsp;
  <a href="../README.es.md"><b>🇪🇸 README en Español</b></a>
</p>
