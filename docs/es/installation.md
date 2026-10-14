# 📦 Guía de Instalación Paso a Paso

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/installation.md">English</a> | <b>Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/guia-instalacion-blue?style=for-the-badge&logo=git&logoColor=white" alt="Guía de Instalación">
  <img src="https://img.shields.io/badge/python-3.10%20a%203.14-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10 a 3.14">
  <img src="https://img.shields.io/badge/plataformas-Linux%20|%20macOS%20|%20WSL2-555?style=for-the-badge" alt="Plataformas">
</p>

Esta guía te guiará en la configuración de **Music Engine** desde cero en cualquier distribución moderna de Linux, macOS o entorno Windows WSL2.

---

## 📑 Tabla de Contenidos

- [Requisitos Previos del Sistema](#-requisitos-previos-del-sistema)
- [1. Paquetes del Sistema Operativo](#1-paquetes-del-sistema-operativo)
- [2. Clonar el Repositorio](#2-clonar-el-repositorio)
- [3. Entorno Virtual de Python (.venv)](#3-entorno-virtual-de-python-venv)
- [4. Instalar Dependencias de Python](#4-instalar-dependencias-de-python)
- [5. Verificar la Configuración del Sistema](#5-verificar-la-configuración-del-sistema)
- [6. Siguientes Pasos: Configuración](#6-siguientes-pasos-configuración)
- [Problemas Comunes de Instalación](#-problemas-comunes-de-instalación)

---

## 🛠️ Requisitos Previos del Sistema

Music Engine requiere:
1. **Python 3.10 o superior** (probado en 3.10, 3.11, 3.12, 3.13 y 3.14).
2. **ffmpeg** instalado en el sistema anfitrión (requerido por `yt-dlp` para extraer y transcodificar audio a Opus/M4A).
3. **Git** para el control de versiones.
4. **Conexión a Internet** para la configuración inicial y la descarga de audio, letras y metadatos.

---

## 1. Paquetes del Sistema Operativo

Instala Python, pip, herramientas de entornos virtuales y ffmpeg mediante el gestor de paquetes de tu distribución:

### 🐧 Debian / Ubuntu / Linux Mint / Pop!_OS
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git
```
> [!IMPORTANT]
> En sistemas Debian y Ubuntu, `python3-venv` se distribuye como un paquete independiente de Python. Asegúrate de instalarlo explícitamente para evitar errores con `ensurepip`.

### 🏹 Arch Linux / Manjaro / EndeavourOS
```bash
sudo pacman -Syu --needed python python-pip ffmpeg git
```

### 🎩 Fedora / RHEL / AlmaLinux / Rocky Linux
```bash
sudo dnf install -y python3 python3-pip ffmpeg ffmpeg-free git
```

### 🦎 openSUSE (Tumbleweed / Leap)
```bash
sudo zypper refresh
sudo zypper install -y python3 python3-pip ffmpeg git
```

### 🏔️ Alpine Linux
```bash
apk update
apk add python3 py3-pip ffmpeg git
```

### 🍎 macOS (Homebrew)
```bash
brew install python ffmpeg git
```

### 🪟 Windows (WSL2)
Music Engine está diseñado para entornos POSIX. En Windows, instala **WSL2** con Ubuntu:
```powershell
# En PowerShell (Administrador):
wsl --install -d Ubuntu
```
Una vez dentro del terminal de Ubuntu, sigue las [instrucciones de Debian / Ubuntu](#-debian--ubuntu--linux-mint--pop_os) anteriores.

---

## 2. Clonar el Repositorio

Clona el repositorio del proyecto en la ubicación deseada (por ejemplo, dentro de `~/Projects` o `~/Music_Engine`):

```bash
git clone https://github.com/your-username/Music_Engine.git
cd Music_Engine
```

---

## 3. Entorno Virtual de Python (`.venv`)

Aísla siempre las dependencias del motor dentro de un entorno virtual dedicado:

```bash
# 1. Crear el entorno virtual
python3 -m venv .venv

# 2. Activar el entorno virtual
source .venv/bin/activate
```

> [!TIP]
> Tras la activación, el indicador de tu terminal mostrará `(.venv)`. Siempre que abras una nueva terminal para ejecutar comandos manualmente, recuerda ejecutar `source .venv/bin/activate` o invocar `.venv/bin/python main.py <comando>`.

---

## 4. Instalar Dependencias de Python

Con el entorno virtual activado, actualiza pip e instala todas las librerías necesarias:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Resumen de Dependencias Principales

| Paquete | Versión Mínima | Propósito |
| :--- | :--- | :--- |
| `yt-dlp` | `>=2024.08.06` | Extracción y streaming de audio en alta fidelidad. |
| `ytmusicapi` | `>=1.7.0` | Búsqueda en catálogo de YouTube Music, heurísticas de álbumes y listas de pistas. |
| `google-genai` | `>=0.3.0` | SDK de Google Gemini para curación musical y análisis de géneros. |
| `mutagen` | `>=1.47.0` | Inyección de etiquetas de audio (Vorbis, ID3, MP4) y carátulas. |
| `thefuzz` | `>=0.22.1` | Coincidencia difusa (*fuzzy matching*) para reconciliación de scrobbles y comandos del buzón. |
| `filelock` | `>=3.15.4` | Sincronización de procesos y seguridad ante concurrencia (`engine.lock`). |
| `syncedlyrics`| `>=1.0.1` | Extractor de letras sincronizadas multifuente. |
| `pyyaml` | `>=6.0.1` | Analizador de configuración YAML (`config.yaml`). |
| `python-dotenv` | `>=1.0.1` | Cargador seguro de variables de entorno (`.env`). |

---

## 5. Verificar la Configuración del Sistema

Ejecuta estas comprobaciones rápidas para verificar que los binarios y librerías externas están correctamente configurados:

### Comprobar ffmpeg
```bash
ffmpeg -version | head -n 1
```
*Salida esperada: Información de la versión (por ejemplo, `ffmpeg version 6.x` o `7.x`).*

### Comprobar Python y el Entorno Virtual
```bash
python -c "import mutagen, yt_dlp, ytmusicapi; print('✓ Módulos principales cargados con éxito')"
```
*Salida esperada: `✓ Módulos principales cargados con éxito`.*

---

## 6. Siguientes Pasos: Configuración

¡Tu entorno está listo! Continúa configurando las rutas de almacenamiento, las credenciales de API y tu perfil de gustos inicial:

👉 **[Ir a la Guía de Configuración](configuration.md)**

---

## ❓ Problemas Comunes de Instalación

### `ModuleNotFoundError: No module named 'venv'`
- **Causa:** En Debian/Ubuntu, `python3-venv` es un paquete separado.
- **Solución:** Ejecuta `sudo apt install python3-venv`.

### `externally-managed-environment` (PEP 668)
- **Causa:** Las distribuciones modernas de Linux bloquean la ejecución de `pip install` directamente en el Python del sistema para no romper paquetes del SO.
- **Solución:** Nunca utilices `sudo pip install`. Crea y activa siempre un entorno virtual (`python3 -m venv .venv` y `source .venv/bin/activate`).

### `ffmpeg not found in PATH`
- **Causa:** ffmpeg no está instalado o se encuentra en una ruta personalizada que no forma parte de la variable `$PATH` del sistema.
- **Solución:** Comprueba dónde está instalado ffmpeg (`which ffmpeg`) e instálalo a través del gestor de paquetes de tu sistema operativo.

---

<p align="center">
  <a href="README.md"><b>⬅ Portal de Documentación</b></a> • <a href="configuration.md"><b>Siguiente: Guía de Configuración ➡</b></a>
</p>
