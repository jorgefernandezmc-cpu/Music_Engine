# ⏰ Automatización en Segundo Plano (Systemd)

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/automation.md">English</a> | <b>Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/servicio-systemd_usuario-teal?style=for-the-badge&logo=linux&logoColor=white" alt="Systemd de Usuario">
  <img src="https://img.shields.io/badge/automatizacion-desatendida-brightgreen?style=for-the-badge" alt="Automatización Desatendida">
</p>

Music Engine está diseñado para funcionar de forma autónoma en segundo plano en tu PC con Linux. Mediante **servicios y temporizadores de usuario de systemd**, el motor puede ejecutar ciclos de mantenimiento diario, sincronizar la telemetría móvil, descargar canciones solicitadas, rotar el búfer de descubrimientos y purgar temas no reproducidos sin requerir privilegios de superusuario (*root*) ni intervención manual.

---

## 📑 Tabla de Contenidos

- [¿Por qué Unidades de Usuario de Systemd?](#por-qué-unidades-de-usuario-de-systemd)
- [1. Crear la Unidad de Servicio (`music-engine.service`)](#1-crear-la-unidad-de-servicio-music-engineservice)
- [2. Crear la Unidad de Temporizador (`music-engine.timer`)](#2-crear-la-unidad-de-temporizador-music-enginetimer)
- [3. Habilitar y Activar la Automatización](#3-habilitar-y-activar-la-automatización)
- [4. Gestión y Monitorización de Ejecuciones](#4-gestión-y-monitorización-de-ejecuciones)
- [5. Modo Persistente Lingering (Ejecución sin Sesión Gráfica)](#5-modo-persistente-lingering-ejecución-sin-sesión-gráfica)
- [6. Gestión y Rotación de Logs (Logrotate)](#6-gestión-y-rotación-de-logs-logrotate)
- [Alternativa: Configuración Clásica con Tareas Cron](#alternativa-configuración-clásica-con-tareas-cron)

---

## ¿Por qué Unidades de Usuario de Systemd?

- **Ejecución sin Root:** Se ejecuta bajo tu cuenta de usuario habitual; los archivos se crean con la propiedad y permisos correctos.
- **Notificaciones de Escritorio:** Se comunica fácilmente con las sesiones gráficas de usuario para emitir avisos no bloqueantes con `notify-send`.
- **Aislamiento de Entorno:** Invoca de forma segura el entorno virtual de Python (`.venv`).
- **Temporizadores Persistentes:** Si tu ordenador estaba suspendido o apagado a la hora programada, systemd ejecuta la tarea atrasada inmediatamente al despertar.

---

## 1. Crear la Unidad de Servicio (`music-engine.service`)

Crea la carpeta para las unidades de usuario si todavía no existe:

```bash
mkdir -p ~/.config/systemd/user
```

Crea el archivo `~/.config/systemd/user/music-engine.service`:

```ini
[Unit]
Description=Music Engine Autonomous Cycle Runner
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
# Ajusta WorkingDirectory a la ruta absoluta de tu repositorio:
WorkingDirectory=/home/TU_USUARIO/Projects/Music_Engine

# Invoca directamente el binario de Python dentro de tu entorno virtual:
ExecStart=/home/TU_USUARIO/Projects/Music_Engine/.venv/bin/python main.py run

# Registro de salidas y auditoría:
StandardOutput=append:/home/TU_USUARIO/Projects/Music_Engine/logs/systemd.log
StandardError=append:/home/TU_USUARIO/Projects/Music_Engine/logs/systemd.log

[Install]
WantedBy=default.target
```

> [!IMPORTANT]
> Sustituye `/home/TU_USUARIO/Projects/Music_Engine` por la ruta absoluta real de instalación de `Music_Engine` (ejecuta `pwd` dentro de la carpeta del proyecto para comprobarla).

---

## 2. Crear la Unidad de Temporizador (`music-engine.timer`)

Crea el archivo `~/.config/systemd/user/music-engine.timer`:

```ini
[Unit]
Description=Daily autonomous execution timer for Music Engine

[Timer]
# Se ejecuta cada mañana a las 04:00 AM hora local:
OnCalendar=*-*-* 04:00:00

# Recupera ejecuciones perdidas si el ordenador estaba apagado:
Persistent=true

# Añade un retardo aleatorio de cortesía para no saturar APIs a horas exactas:
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
```

> [!TIP]
> **¿Deseas múltiples ejecuciones al día?** Puedes configurar `OnCalendar=*-*-* 04,16:00:00` para ejecutar dos veces al día (a las 4:00 AM y a las 4:00 PM), o `OnCalendar=hourly` para comprobar el buzón de peticiones cada hora.

---

## 3. Habilitar y Activar la Automatización

Recarga el demonio de usuario de systemd e inicia el temporizador:

```bash
# 1. Recargar el demonio de usuario de systemd
systemctl --user daemon-reload

# 2. Habilitar e iniciar el temporizador de inmediato
systemctl --user enable --now music-engine.timer
```

Verifica que el temporizador está armado y activo:

```bash
systemctl --user list-timers --all | grep music-engine
```

*Salida esperada:*
```text
NEXT                         LEFT          LAST PASSED UNIT                ACTIVATES
Tue 2026-10-13 04:00:00 CEST 8h left       n/a  n/a    music-engine.timer  music-engine.service
```

---

## 4. Gestión y Monitorización de Ejecuciones

### Disparar una Ejecución Manual
Puedes probar el servicio de systemd en cualquier momento sin esperar al temporizador:

```bash
systemctl --user start music-engine.service
```

### Comprobar el Estado del Servicio
```bash
systemctl --user status music-engine.service
```

### Seguir los Registros en Tiempo Real
```bash
# Ver la salida combinada de systemd:
tail -f logs/systemd.log

# Ver los logs de componentes específicos:
tail -f logs/engine.log
tail -f logs/downloader.log
tail -f logs/curator.log
```

---

## 5. Modo Persistente Lingering (Ejecución sin Sesión Gráfica)

Si ejecutas Music Engine en un servidor doméstico, Raspberry Pi o equipo multimedia donde no mantienes una sesión gráfica abierta continuamente, activa el modo **lingering** para tu usuario:

```bash
sudo loginctl enable-linger $USER
```

Esto ordena a systemd mantener el gestor de servicios de tu usuario en funcionamiento las 24 horas del día, desde el arranque del equipo hasta su apagado.

---

## 6. Gestión y Rotación de Logs (Logrotate)

Para evitar que los archivos en `logs/` crezcan indefinidamente con el paso de los meses, puedes configurar una regla de logrotate de usuario:

Crea `~/.config/logrotate.d/music-engine`:

```text
/home/TU_USUARIO/Projects/Music_Engine/logs/*.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

---

## 🔄 Alternativa: Configuración Clásica con Tareas Cron

Si tu entorno Linux no utiliza systemd (por ejemplo Alpine Linux, contenedores Docker o entornos BSD minimalistas), puedes programar el motor mediante el cron tradicional de usuario:

```bash
crontab -e
```

Añade la siguiente línea:

```cron
0 4 * * * cd /home/TU_USUARIO/Projects/Music_Engine && .venv/bin/python main.py run >> logs/systemd.log 2>&1
```

---

<p align="center">
  <a href="mobile-and-sync.md"><b>⬅ Ecosistema Móvil y Sincronización</b></a> • <a href="metadata-and-lyrics.md"><b>Siguiente: Metadatos, Géneros y Letras ➡</b></a>
</p>
