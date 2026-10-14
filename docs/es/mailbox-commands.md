# 📱 Buzón de Control Remoto (`peticiones.txt` / `requests.txt`)

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/mailbox-commands.md">English</a> | <b>Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/caracteristica-buzon_remoto-purple?style=for-the-badge&logo=fastapi&logoColor=white" alt="Buzón Remoto">
  <img src="https://img.shields.io/badge/bilingue-Espanol%20y%20Ingles-orange?style=for-the-badge" alt="Bilingüe">
</p>

El **Buzón de Control Remoto** te permite enviar instrucciones, descargar álbumes completos, encolar antojos temporales, promocionar pistas a la biblioteca permanente o corregir metadatos directamente desde tu smartphone, sin necesidad de abrir una terminal ni conectarte por SSH.

---

## 📑 Tabla de Contenidos

- [Cómo Funciona el Buzón](#-cómo-funciona-el-buzón)
- [Tabla Resumen de Sintaxis de Comandos](#-tabla-resumen-de-sintaxis-de-comandos)
- [1. Descarga de Álbumes de Estudio Completos](#1-descarga-de-álbumes-de-estudio-completos)
- [2. Descarga de Pistas Individuales](#2-descarga-de-pistas-individuales)
- [3. Búfer de Antojos Temporales (Cravings)](#3-búfer-de-antojos-temporales-cravings)
- [4. Promoción y Blindaje a Permanente](#4-promoción-y-blindaje-a-permanente)
- [5. Descarte y Purga de Canciones](#5-descarte-y-purga-de-canciones)
- [6. Reasignación de Metadatos y Álbumes](#6-reasignación-de-metadatos-y-álbumes)
- [7. Corrección de Géneros Musicales](#7-corrección-de-géneros-musicales)
- [8. Búsqueda y Actualización de Letras Sincronizadas](#8-búsqueda-y-actualización-de-letras-sincronizadas)
- [9. Radios Temáticas de Descubrimiento](#9-radios-temáticas-de-descubrimiento)
- [10. Reparación Automática de Pistas](#10-reparación-automática-de-pistas)
- [Bucle de Retroalimentación y Gestión de Errores](#-bucle-de-retroalimentación-y-gestión-de-errores)

---

## 📬 Cómo Funciona el Buzón

```text
 ┌────────────────┐          Syncthing          ┌────────────────┐
 │ Dispositivo    │  ─────────────────────────▶ │  Music Engine  │
 │ Móvil (Notas)  │  ◀───────────────────────── │  (PC en fondo) │
 └────────────────┘                             └────────────────┘
         │                                              │
         ▼                                              ▼
 Editas requests.txt o                      Lee líneas en cada ciclo,
 peticiones.txt en la                       descarga audio/letras,
 carpeta sincronizada                       limpia órdenes finalizadas y
                                            deja comentarios de error
```

1. Dentro de tu directorio base de música (`storage.base_dir`), abre el archivo `requests.txt` (o `peticiones.txt`) utilizando cualquier editor de notas en tu móvil.
2. Añade tus instrucciones al final del archivo (debajo de la cabecera comentada con `#`).
3. Guarda el archivo. **Syncthing** lo sincroniza al instante con tu ordenador.
4. En el siguiente ciclo de ejecución (mediante `systemd` o ejecutando manualmente `python main.py run`), el motor interpreta las órdenes, las ejecuta, borra las completadas y añade explicaciones en caso de error.

---

## 📋 Tabla Resumen de Sintaxis de Comandos

El buzón admite indistintamente la sintaxis en **español** y en **inglés**:

| Operación | Sintaxis en Español | Sintaxis en Inglés | Destino |
| :--- | :--- | :--- | :--- |
| **Álbum Permanente** | `disco: Artista - Disco`<br>`permanente album: Artista - Disco` | `album: Artist - Album`<br>`permanent album: Artist - Album` | `Permanent/<Artista>/<Disco>/` |
| **Álbum en Antojos** | `antojo album: Artista - Disco` | `craving album: Artist - Album` | `Cravings/<Artista>/<Disco>/` |
| **Tema Permanente** | `permanente: Artista - Tema`<br>`Descargar "Tema" de Artista` | `permanent: Artist - Track`<br>`Download "Track" by Artist` | `Permanent/<Artista>/<Disco>/` |
| **Tema en Antojos** | `antojo: Artista - Tema` | `craving: Artist - Track` | `Cravings/<Artista>/<Disco>/` |
| **Promocionar Tema** | `permanente: Tema`<br>`favorita: Tema`<br>`blindar: Tema` | `permanent: Track`<br>`favorite: Track`<br>`shield: Track` | Se mueve a `Permanent/` |
| **Purgar Tema** | `borrar: Tema`<br>`eliminar: Tema` | `purge: Track`<br>`delete: Track` | Borra archivo + `.lrc` + marca `PURGED` |
| **Reasignar Álbum** | `album: Tema -> Nuevo Álbum` | `album: Track -> New Album` | Mueve archivos y etiquetas al nuevo álbum |
| **Corregir Género** | `genero: Tema -> Nuevo Género`<br>`genero: Tema` (reanálisis IA) | `genre: Track -> New Genre`<br>`genre: Track` | Inyecta etiqueta en archivo y SQLite |
| **Refrescar Letra** | `letra: Tema` | `lyrics: Track` | Vuelve a buscar y guarda el `.lrc` sincronizado |
| **Radio Temática** | `radio: Descripción de Estilo` | `radio: Vibe Description` | Llena la Cinta con temas del estilo indicado |
| **Reparar Pista** | `reparar: Tema`<br>`arreglar: Tema` | `fix: Track`<br>`repair: Track` | Sustituye por la versión oficial de estudio |

---

## 1. Descarga de Álbumes de Estudio Completos

Descarga listas completas oficiales de temas directamente desde YouTube Music:

```text
# Descarga el álbum completo The Dark Side of the Moon a Permanente:
disco: Pink Floyd - The Dark Side of the Moon

# Sintaxis explícita de álbum permanente:
permanente album: Rosalía - Motomami

# Lenguaje natural:
Descargar el disco "Random Access Memories" de Daft Punk
```

El motor:
- Obtiene números oficiales de pista y año de lanzamiento.
- Descarga cada pista directamente en `Permanent/<Artista_Principal>/<Álbum>/`.
- Incrusta carátula en alta resolución y metadatos limpios.
- Descarga archivos sidecar `.lrc` sincronizados para cada pista.
- Añade las canciones a `Permanent.m3u8` y actualiza la copia para Lune.

---

## 2. Descarga de Pistas Individuales

Descarga canciones sueltas directamente a la colección permanente:

```text
# Sintaxis estructurada:
permanente: Daft Punk - Get Lucky
permanente: Kendrick Lamar - Not Like Us

# Lenguaje natural:
Descargar "Starboy" de The Weeknd
Download "Ojitos Lindos" by Bad Bunny
```

---

## 3. Búfer de Antojos Temporales (Cravings)

¿Te apetece una canción del verano, un éxito viral o una banda sonora puntual que no deseas conservar para siempre en tu biblioteca permanente? Añádela como **Antojo**:

```text
# Antojo de tema individual:
antojo: Charli xcx - Apple
antojo: Quevedo - Columbia

# Antojo de disco completo:
antojo album: Arctic Monkeys - AM
antojo album: C. Tangana - El Madrileño
```

> [!NOTE]
> - Los antojos se guardan en `storage.cravings_dir` (ej. `Cravings/` o `Antojos/`).
> - Se incluyen automáticamente en la lista de reproducción `Cravings.m3u8`.
> - Las canciones en Antojos se eliminan automáticamente del disco cuando superan `cravings.retention_days` (por defecto: 30 días) sin necesidad de mantenimiento manual.
> - Si te enamoras de un antojo, ¡puedes promocionarlo a permanente en cualquier momento con `favorita: Nombre del Tema`!

---

## 4. Promoción y Blindaje a Permanente

Si descubres una joya en tu búfer de **Conveyor** (la Cinta) o en tu carpeta de **Antojos** que deseas conservar de por vida:

```text
favorita: Midnight City
permanente: Midnight City
blindar: Midnight City
shield: Midnight City
```

El motor al instante:
1. Localiza el archivo de audio y su letra `.lrc`.
2. Identifica el álbum de estudio canónico de la pista.
3. Mueve físicamente los archivos a `Permanent/<Artista_Principal>/<Álbum>/`.
4. Actualiza su registro en base de datos a `PERMANENT` con `is_permanent = 1`.
5. Elimina directorios de origen vacíos y regenera las listas.

---

## 5. Descarte y Purga de Canciones

Si no te gusta una pista que se encuentra actualmente en la Cinta o en Antojos:

```text
borrar: Nombre de la Canción
eliminar: Nombre de la Canción
purge: Nombre de la Canción
delete: Nombre de la Canción
```

El motor borra de inmediato el archivo de audio y su sidecar `.lrc` del disco, marca la pista como `PURGED` en SQLite y garantiza que el curador de IA **nunca** volverá a sugerirla ni a descargarla.

---

## 6. Reasignación de Metadatos y Álbumes

En ocasiones, una pista se descargó con un nombre de álbum incorrecto o pertenece a una edición especial o recopilatorio. Puedes corregirla sin tocar archivos manualmente:

```text
# Formato: album: <canción> -> <álbum_destino>
album: Instant Crush -> Random Access Memories (10th Anniversary)
disco: Bohemian Rhapsody -> A Night at the Opera

# Sintaxis en lenguaje natural:
Mueve la canción "Around the World" al álbum "Homework"
Move the song "Starboy" to album "Starboy"
```

El motor actualiza las etiquetas del archivo, renombra carpetas, traslada los archivos `.lrc` y limpia directorios vacíos remanentes.

---

## 7. Corrección de Géneros Musicales

Si un tema fue etiquetado con un género demasiado genérico (ej. `Pop`) y prefieres una categoría más precisa:

```text
# Asignación manual directa:
genero: Midnight City -> Synthwave / Dream Pop
genero: Master of Puppets -> Thrash Metal

# Reanálisis mediante IA (omitir el género de destino):
genero: Midnight City
genero: Bohemian Rhapsody
```

---

## 8. Búsqueda y Actualización de Letras Sincronizadas

Fuerza una búsqueda inmediata en LRCLIB, syncedlyrics y YouTube Music para descargar o actualizar letras sincronizadas:

```text
letra: Daft Punk - One More Time
letra: Queen - Don't Stop Me Now
lyrics: Daft Punk - One More Time
```

---

## 9. Radios Temáticas de Descubrimiento

Inyecta un lote de temas novedosos que encajan con un ambiente o estilo musical específico en tu búfer de la Cinta:

```text
radio: Grunge de los 90 y Rock Alternativo
radio: Lo-Fi Synthwave nocturno para programar
radio: Indie Rock español de los 2000
```

---

## 10. Reparación Automática de Pistas

Sustituye una versión en directo de baja calidad, un remix o un cover pirata por la versión oficial de estudio:

```text
reparar: Hotel California
reparar: Pink Floyd - Comfortably Numb
fix: Rosalía - Malamente
```

---

## 🔄 Bucle de Retroalimentación y Gestión de Errores

Cuando el motor procesa `requests.txt` o `peticiones.txt`:

1. **Las órdenes completadas con éxito se eliminan automáticamente** del archivo para mantenerlo limpio.
2. La cabecera informativa inicial se conserva intacta en la parte superior.
3. Si una orden falla (por ejemplo, si no se encuentra el álbum en YouTube Music o si la pista no existe en la Cinta), la línea se conserva al final con un comentario explicativo `# ERROR:`:

```text
# Ejemplo de feedback del buzón tras un ciclo de ejecución:
# --- UNCOMPLETED ORDERS (See details below) ---
permanente album: Grupo Desconocido - Disco Inexistente  # ERROR: Album not found on YouTube Music
```

Puedes corregir cualquier errata tipográfica o borrar las líneas fallidas cuando lo desees.

---

<p align="center">
  <a href="cli-reference.md"><b>⬅ Referencia de CLI</b></a> • <a href="mobile-and-sync.md"><b>Siguiente: Ecosistema Móvil y Sincronización ➡</b></a>
</p>
