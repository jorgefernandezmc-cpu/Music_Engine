# 📱 Buzón de Control Remoto (`peticiones.txt` / `requests.txt`)

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/mailbox-commands.md">🇬🇧 English</a> | <b>🇪🇸 Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/caracteristica-buzon_remoto-purple?style=for-the-badge&logo=fastapi&logoColor=white" alt="Buzón Remoto">
  <img src="https://img.shields.io/badge/bilingue-Espanol%20y%20Ingles-orange?style=for-the-badge" alt="Bilingüe">
</p>

El **Buzón de Control Remoto** te permite enviar instrucciones, descargar álbumes completos, pegar enlaces directos de YouTube o Spotify, arreglar canciones con audio erróneo, gestionar listas de reproducción o consultar información técnica directamente desde tu smartphone, sin necesidad de abrir una terminal ni conectarte por SSH.

---

## 📑 Tabla de Contenidos

- [Cómo Funciona el Buzón](#-cómo-funciona-el-buzón)
- [Tabla Resumen de Sintaxis de Comandos](#-tabla-resumen-de-sintaxis-de-comandos)
- [1. Descarga de Álbumes de Estudio Completos](#1-descarga-de-álbumes-de-estudio-completos)
- [2. Descarga de Pistas Individuales](#2-descarga-de-pistas-individuales)
- [3. Descarga Directa por Enlaces (YouTube, YT Music, Spotify)](#3-descarga-directa-por-enlaces-youtube-yt-music-spotify)
- [4. Búfer de Antojos Temporales (Cravings)](#4-búfer-de-antojos-temporales-cravings)
- [5. Reparación y Sustitución de Audio (Fix Automático y Enlace Manual)](#5-reparación-y-sustitución-de-audio-fix-automático-y-enlace-manual)
- [6. Promoción y Blindaje a Permanente](#6-promoción-y-blindaje-a-permanente)
- [7. Descarte y Purga de Canciones (Cinta y Colección Permanente)](#7-descarte-y-purga-de-canciones-cinta-y-colección-permanente)
- [8. Reasignación de Metadatos, Álbumes y Artistas](#8-reasignación-de-metadatos-álbumes-y-artistas)
- [9. Gestión de Listas de Reproducción Propias](#9-gestión-de-listas-de-reproducción-propias)
- [10. Consulta e Inspección de Información de Pistas](#10-consulta-e-inspección-de-información-de-pistas)
- [11. Forzar Re-descarga Limpia de Pistas](#11-forzar-re-descarga-limpia-de-pistas)
- [12. Corrección de Géneros Musicales](#12-corrección-de-géneros-musicales)
- [13. Búsqueda y Actualización de Letras Sincronizadas](#13-búsqueda-y-actualización-de-letras-sincronizadas)
- [14. Radios Temáticas de Descubrimiento](#14-radios-temáticas-de-descubrimiento)
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
                                            deja comentarios de error o info
```

1. Dentro de tu directorio base de música (`storage.base_dir`), abre el archivo `requests.txt` (o `peticiones.txt`) utilizando cualquier editor de notas en tu móvil.
2. Añade tus instrucciones al final del archivo (debajo de la cabecera comentada con `#`).
3. Guarda el archivo. **Syncthing** lo sincroniza al instante con tu ordenador.
4. En el siguiente ciclo de ejecución (mediante `systemd` o ejecutando manualmente `python main.py run`), el motor interpreta las órdenes, las ejecuta, borra las completadas, añade respuestas de información y reporta explicaciones en caso de error.

> [!TIP]
> **Adaptación Automática del Idioma de la Cabecera:** La cabecera explicativa de ayuda en `requests.txt` (o `peticiones.txt`) se adapta automáticamente al ajuste `system.language` (`"en"` o `"es"` en `config/config.yaml`). Si cambias de idioma, el motor actualiza la cabecera en la siguiente ejecución manteniendo intactas todas tus órdenes y notas pendientes.

---

## 📋 Tabla Resumen de Sintaxis de Comandos

El buzón admite indistintamente la sintaxis en **español** y en **inglés**:

| Operación | Sintaxis en Español | Sintaxis en Inglés | Destino / Efecto |
| :--- | :--- | :--- | :--- |
| **Álbum Permanente** | `disco: Artista - Disco`<br>`permanente album: Artista - Disco` | `album: Artist - Album`<br>`permanent album: Artist - Album` | `Permanent/<Artista>/<Disco>/` |
| **Álbum en Antojos** | `antojo album: Artista - Disco` | `craving album: Artist - Album` | `Cravings/<Artista>/<Disco>/` |
| **Tema Permanente** | `permanente: Artista - Tema`<br>`Descargar "Tema" de Artista` | `permanent: Artist - Track`<br>`Download "Track" by Artist` | `Permanent/<Artista>/<Disco>/` |
| **Tema en Antojos** | `antojo: Artista - Tema` | `craving: Artist - Track` | `Cravings/<Artista>/<Disco>/` |
| **Enlace Directo URL** | `https://music.youtube.com/...`<br>`url: https://...` | `https://music.youtube.com/...`<br>`url: https://...` | Descarga directa de pista o playlist |
| **Enlace URL Antojo** | `antojo: https://...` | `craving: https://...` | Descarga a carpeta temporal de Antojos |
| **Reparar (Auto)** | `reparar: Artista - Tema`<br>`arreglar: Tema` | `fix: Artist - Track`<br>`repair: Track` | Busca versión oficial de estudio en YT Music |
| **Reparar (URL Manual)** | `reparar: Tema -> URL`<br>`fix: Tema -> URL` | `fix: Track -> URL`<br>`repair: Track -> URL` | Sustituye el audio por el enlace exacto indicado |
| **Promocionar Tema** | `favorita: Tema`<br>`blindar: Artista - Tema` | `favorite: Track`<br>`shield: Artist - Track` | Promueve de Cinta/Antojos a Permanente |
| **Purgar de Cinta/Antojos** | `borrar: Tema`<br>`eliminar: Tema` | `purge: Track`<br>`delete: Track` | Borra audio y `.lrc` + marca `PURGED` |
| **Purgar de Permanente** | `borrar permanente: Artista - Tema`<br>`eliminar permanente: Tema` | `purge permanent: Artist - Track`<br>`delete permanent: Track` | Borra de `Permanent/`, limpia carpetas y marca `PURGED` |
| **Reasignar Álbum** | `album: Tema -> Nuevo Álbum` | `album: Track -> New Album` | Mueve archivos y etiquetas al nuevo álbum |
| **Reasignar Artista** | `artista: Tema -> Nuevo Artista` | `artist: Track -> New Artist` | Mueve archivos y actualiza etiquetas de artista |
| **Añadir a Playlist** | `lista: NombreLista += Tema` | `playlist: Name += Track` | Añade pista a lista de reproducción M3U8 |
| **Quitar de Playlist** | `lista: NombreLista -= Tema` | `playlist: Name -= Track` | Elimina pista de lista de reproducción M3U8 |
| **Forzar Re-descarga** | `redescargar: Artista - Tema` | `redownload: Artist - Track` | Borra caché y vuelve a descargar limpia |
| **Consultar Información** | `info: Artista - Tema`<br>`informacion: Tema` | `info: Artist - Track`<br>`information: Track` | Inserta ficha técnica comentada en el buzón |
| **Corregir Género** | `genero: Tema -> Nuevo Género`<br>`genero: Tema` (auto IA) | `genre: Track -> New Genre`<br>`genre: Track` | Inyecta etiqueta en archivo y SQLite |
| **Refrescar Letra** | `letra: Tema` | `lyrics: Track` | Vuelve a buscar y guarda el `.lrc` sincronizado |
| **Radio Temática** | `radio: Descripción de Estilo` | `radio: Vibe Description` | Llena la Cinta con temas del estilo indicado |

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

---

## 2. Descarga de Pistas Individuales

Descarga canciones sueltas directamente a la colección permanente, con soporte de desambiguación estricta de artista:

```text
# Sintaxis estructurada con artista y título:
permanente: Daft Punk - Get Lucky
permanente: Kendrick Lamar - Not Like Us

# Lenguaje natural:
Descargar "Starboy" de The Weeknd
Download "Ojitos Lindos" by Bad Bunny
```

---

## 3. Descarga Directa por Enlaces (YouTube, YT Music, Spotify)

Puedes pulsar **"Compartir enlace"** en tu móvil y pegar la URL directamente en el buzón:

```text
# Enlace de YouTube Music a Colección Permanente:
https://music.youtube.com/watch?v=5NV6Rdv1a3I

# Enlace de YouTube convencional o formato corto:
https://youtu.be/5NV6Rdv1a3I

# Enlace explícito como Antojo temporal:
antojo: https://music.youtube.com/watch?v=5NV6Rdv1a3I

# Playlist completa de YouTube Music:
https://music.youtube.com/playlist?list=PLw-VjHDlEOgvtnnnqWlTqByAtC7tXBg6D

# Enlace de Spotify (extrae artista y título y descarga la mejor versión):
https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT
```

---

## 4. Búfer de Antojos Temporales (Cravings)

Canciones o éxitos de temporada que quieres disfrutar durante unas semanas sin llenar tu biblioteca permanente:

```text
# Antojo de tema individual:
antojo: Charli xcx - Apple
craving: Quevedo - Columbia

# Antojo de disco completo:
antojo album: Arctic Monkeys - AM
craving album: C. Tangana - El Madrileño
```

> [!NOTE]
> Los antojos se limpian automáticamente tras cumplir el periodo de retención (`cravings.retention_days`, por defecto 30 días). Si te gusta un antojo, puedes promoverlo a permanente en cualquier momento con `favorita: Tema`.

---

## 5. Reparación y Sustitución de Audio (Fix Automático y Enlace Manual)

Si una canción descargada tiene los metadatos correctos pero el audio corresponde a un directo, un rip de baja calidad, un remix o una pista incorrecta:

### Opción A: Búsqueda Automática de Versión de Estudio
El motor busca la pista oficial descartando explícitamente el audio erróneo actual:

```text
reparar: Pink Floyd - Comfortably Numb
fix: Hotel California
arreglar: Daft Punk - Get Lucky
```

### Opción B: Sustitución Precisa Mediante Enlace Manual de YouTube
Si quieres garantizar el 100% de exactitud con un vídeo o pista específica de YouTube Music:

```text
reparar: Daft Punk - Get Lucky -> https://music.youtube.com/watch?v=5NV6Rdv1a3I
fix: Starboy -> https://youtu.be/34Na4j8AVgA
```

*Acción interna*: El motor borra el audio local viejo y el archivo `.lrc`, elimina la clave de la caché de descargas (`data/download_archive.txt`), asigna el nuevo identificador y encola la descarga limpia de la versión deseada.

---

## 6. Promoción y Blindaje a Permanente

Si descubres una joya en tu Cinta (`Conveyor`) o en `Antojos` que deseas conservar de por vida:

```text
favorita: Midnight City
blindar: M83 - Midnight City
shield: Daft Punk - Instant Crush
```

El motor resuelve el álbum de estudio canónico, traslada los archivos y el `.lrc` a `Permanent/<Artista>/<Álbum>/`, limpia directorios vacíos y regenera las listas.

---

## 7. Descarte y Purga de Canciones (Cinta y Colección Permanente)

### Descartar de Cinta o Antojos
```text
borrar: Nombre de Canción
eliminar: Nombre de Canción
purge: Track Name
```
Borra el archivo y marca el tema como `PURGED` para que el curador de IA no vuelva a sugerirlo.

### Purgar de la Colección Permanente
Para evitar borrados accidentales, la biblioteca permanente requiere el comando específico:

```text
borrar permanente: Queen - Bohemian Rhapsody
eliminar permanente: Daft Punk - One More Time
purge permanent: Artist - Track
```
Elimina físicamente el audio y la letra de `Permanent/`, limpia la carpeta del álbum/artista si quedan vacías y actualiza todas las listas permanentes.

---

## 8. Reasignación de Metadatos, Álbumes y Artistas

### Reasignar Álbum
```text
album: Instant Crush -> Random Access Memories (10th Anniversary)
disco: Bohemian Rhapsody -> A Night at the Opera
```

### Reasignar Artista Principal
Si una canción fue catalogada con un artista erróneo o deseas mover una colaboración a la carpeta del artista principal:

```text
artista: Save Your Tears -> The Weeknd
artist: Cuica -> Rosalía
```
Mueve físicamente la pista a `Permanent/<Nuevo Artista>/<Álbum>/`, actualiza las etiquetas del archivo (`artist` / `©ART`) y reorganiza la biblioteca.

---

## 9. Gestión de Listas de Reproducción Propias

Añade o quita canciones de tus listas de reproducción personalizadas (`Listas Propias/`):

```text
# Añadir a lista:
lista: Gym += Eye of the Tiger
playlist: Favoritas 2024 += Daft Punk - Get Lucky

# Quitar de lista:
lista: Gym -= Eye of the Tiger
playlist: Favoritas 2024 -= Get Lucky
```

---

## 10. Consulta e Inspección de Información de Pistas

Escribe `info:` para que el motor consulte la base de datos y las etiquetas físicas del archivo, insertando una ficha técnica en el propio archivo:

```text
info: Daft Punk - Get Lucky
informacion: Bohemian Rhapsody
```

El motor responderá al final del archivo comentando los detalles técnicos:
```text
# --- INFORMACIÓN DE PISTAS (Resultados) ---
# [INFO] Daft Punk - Get Lucky | Álbum: Random Access Memories (2013) #8 | Género: Disco / Funk | Estado: PERMANENTE | Duración: 4:09 | Archivo: OPUS (5.2 MB) | Letra: Sincronizada (.lrc)
```

---

## 11. Forzar Re-descarga Limpia de Pistas

Si un archivo de audio descargado sufrió algún corte o quieres renovarlo:

```text
redescargar: Daft Punk - One More Time
redownload: Queen - Don't Stop Me Now
```
Borra el audio existente y su letra, limpia la caché de descargas y vuelve a bajarlo en la mejor calidad.

---

## 12. Corrección de Géneros Musicales

```text
# Asignación manual directa:
genero: Midnight City -> Synthwave / Dream Pop

# Reanálisis mediante IA:
genero: Midnight City
genre: Bohemian Rhapsody
```

---

## 13. Búsqueda y Actualización de Letras Sincronizadas

Fuerza la descarga o actualización de letras sincronizadas en tiempo real:

```text
letra: Daft Punk - One More Time
lyrics: Queen - Don't Stop Me Now
```

---

## 14. Radios Temáticas de Descubrimiento

Genera recomendaciones inmediatas adaptadas a un ambiente o estilo musical específico:

```text
radio: Grunge de los 90 y Rock Alternativo
radio: Lo-Fi Synthwave nocturno para programar
radio: Indie Rock español de los 2000
```

---

## 🔄 Bucle de Retroalimentación y Gestión de Errores

Cuando el motor procesa el buzón:
1. **Órdenes correctas**: Se eliminan del archivo para mantenerlo limpio.
2. **Consultas `info:`**: Se escriben al final del archivo bajo `# --- INFORMACIÓN DE PISTAS (Resultados) ---`.
3. **Órdenes fallidas**: Se muestran bajo `# --- ÓRDENES NO COMPLETADAS (Ver detalles abajo) ---` con el motivo exacto del fallo (`# ERROR:` o `# NOTICE:`).

---

<p align="center">
  <a href="cli-reference.md"><b>⬅ Referencia de CLI</b></a> • <a href="mobile-and-sync.md"><b>Siguiente: Ecosistema Móvil y Sincronización ➡</b></a>
</p>
