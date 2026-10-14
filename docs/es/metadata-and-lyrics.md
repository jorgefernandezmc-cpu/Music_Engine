# 🎶 Metadatos, Géneros y Letras Sincronizadas

<p align="right">
  <b>Language / Idioma:</b>
  <a href="../en/metadata-and-lyrics.md">English</a> | <b>Español</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/letras-sincronizadas_.lrc-blue?style=for-the-badge&logo=music&logoColor=white" alt="Letras Sincronizadas">
  <img src="https://img.shields.io/badge/generos-IA_%2B_MusicBrainz-orange?style=for-the-badge&logo=google&logoColor=white" alt="Géneros IA MusicBrainz">
  <img src="https://img.shields.io/badge/metadatos-albumes_estudio-green?style=for-the-badge" alt="Álbumes de Estudio">
</p>

Music Engine mantiene estándares de calidad audiófila impecables. En lugar de conformarse con sencillos sueltos, etiquetas incompletas o versiones de baja fidelidad, el motor cuenta con un completo pipeline de enriquecimiento que garantiza metadatos oficiales de estudio, géneros granulares y letras sincronizadas con precisión de milisegundos.

---

## 📑 Tabla de Contenidos

- [El Pipeline de Enriquecimiento](#-el-pipeline-de-enriquecimiento)
- [1. Cascada de Letras Sincronizadas](#1-cascada-de-letras-sincronizadas)
  - [Jerarquía de Proveedores](#jerarquía-de-proveedores)
  - [Doble Etiquetado: Vorbis/MP4 Incrustado y Archivos .lrc Sidecar](#doble-etiquetado-vorbismp4-incrustado-y-archivos-lrc-sidecar)
  - [Escanear y Mejorar Letras](#escanear-y-mejorar-letras)
- [2. Clasificación Inteligente de Géneros Musicales](#2-clasificación-inteligente-de-géneros-musicales)
  - [Estrategia de Clasificación por Niveles](#estrategia-de-clasificación-por-niveles)
  - [Caché Local en `artist_genres`](#la-tabla-de-caché-artist_genres)
  - [Comandos CLI para Géneros](#comandos-cli-para-géneros)
- [3. Números de Pista y Fechas de Lanzamiento](#3-números-de-pista-y-fechas-de-lanzamiento)
- [4. Resolución Heurística de Álbumes de Estudio](#4-resolución-heurística-de-álbumes-de-estudio)
  - [Priorización de Álbumes de Estudio sobre Sencillos](#priorización-de-álbumes-de-estudio-sobre-sencillos)
  - [Filtro de Exclusión de Palabras Clave Antagónicas](#filtro-de-exclusión-de-palabras-clave-antagónicas)
- [5. Auditoría y Reparación de Pistas Dudosas (`fix-metadata`)](#5-auditoría-y-reparación-de-pistas-dudosas-fix-metadata)

---

## 🔄 El Pipeline de Enriquecimiento

```text
 Archivo de Audio Descargado (.opus / .m4a)
                 │
                 ├──▶ 1. Cascada de Letras ────▶ [LRCLIB] ──▶ [syncedlyrics] ──▶ [YTMusic]
                 │                                │
                 │                                ├──▶ Incrusta etiquetas Vorbis/MP4
                 │                                └──▶ Genera sidecar contiguo <Pista>.lrc
                 │
                 ├──▶ 2. Clasificador Géneros ─▶ [MusicBrainz] ──▶ [Deezer] ──▶ [IA Gemini]
                 │                                │
                 │                                └──▶ Escribe etiqueta de género y actualiza SQLite
                 │
                 └──▶ 3. Pistas y Fechas ──────▶ [API de Listas de Álbumes de YTMusic]
                                                  │
                                                  └──▶ Escribe tracknumber, fecha y actualiza SQLite
```

---

## 1. Cascada de Letras Sincronizadas

La obtención de letras se realiza mediante una cascada de respaldo multifuente implementada en [`src/lyrics_provider.py`](../../src/lyrics_provider.py):

### Jerarquía de Proveedores

1. **API de LRCLIB (Primaria):** Base de datos abierta de letras sincronizadas con marcas de tiempo en milisegundos (`[mm:ss.xx]`).
2. **`syncedlyrics` (Secundaria):** Scraper automatizado que consulta NetEase, Musixmatch, Megalobiz y Deezer.
3. **API de Letras de YouTube Music (Terciaria):** Letras oficiales obtenidas del endpoint `get_watch_playlist` / `get_lyrics` de YouTube Music.
4. **lyrics.ovh (Respaldo final):** Letras en texto plano sin sincronizar cuando ninguna fuente temporizada está disponible.

---

### Doble Etiquetado: Vorbis/MP4 Incrustado y Archivos `.lrc` Sidecar

Music Engine almacena las letras en dos ubicaciones complementarias para lograr una compatibilidad universal absoluta:

1. **Etiquetas Físicas Incrustadas en el Archivo:**
   - **Opus (Comentarios Vorbis):** Se inyectan en las etiquetas `LYRICS`, `SYNCEDLYRICS` y `UNSYNCEDLYRICS` utilizando Mutagen.
   - **M4A / AAC (Átomos MP4):** Se inyectan en el átomo `©lyr`.
2. **Archivos Sidecar `.lrc`:**
   - Se guardan exactamente al lado del archivo de audio con idéntico nombre base:
     ```text
     Permanent/Arctic Monkeys/AM/Arctic Monkeys - Do I Wanna Know.opus
     Permanent/Arctic Monkeys/AM/Arctic Monkeys - Do I Wanna Know.lrc
     ```
   - Formato estándar de karaoke:
     ```text
     [00:15.20] Have you got colour in your cheeks?
     [00:18.45] Do you ever get that fear that you can't shift the type...
     ```
   - Reconocido y mostrado de forma inmediata por **Lune**, **Auxio**, **Symfonium**, **Poweramp** y reproductores de escritorio.

---

### Escanear y Mejorar Letras

Para auditar tu biblioteca y convertir letras en texto plano en archivos sincronizados `.lrc`:

```bash
# Procesar un lote de 50 pistas:
python main.py enrich-lyrics

# Escanear la colección entera sin límite:
python main.py enrich-lyrics --all

# Descargar solo letras ausentes sin intentar mejorar las no sincronizadas:
python main.py enrich-lyrics --no-upgrade
```

---

## 2. Clasificación Inteligente de Géneros Musicales

Implementado en [`src/genre_resolver.py`](../../src/genre_resolver.py).

### Estrategia de Clasificación por Niveles

1. **Paso 1: Caché Local en SQLite (tabla `artist_genres`)**
   - Si el género del artista ya ha sido consultado previamente, se resuelve de forma instantánea (0 ms) sin llamadas de red.
2. **Paso 2: API Abierta de MusicBrainz**
   - Consulta etiquetas y clasificaciones comunitarias de MusicBrainz.
3. **Paso 3: IA Semántica de Google Gemini**
   - Cuando las bases de datos abiertas no disponen de etiquetas o categorizan de forma vaga (ej. *"Music"*), Gemini analiza la discografía del artista y asigna géneros precisos y estandarizados (ej. *"Synthwave"*, *"Indie Rock"*, *"Neo-Soul"*).

### La Tabla de Caché `artist_genres`

Almacenada dentro de `data/conveyor_state.sqlite`:
```sql
CREATE TABLE artist_genres (
    artist TEXT PRIMARY KEY,
    genre TEXT NOT NULL,
    source TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Comandos CLI para Géneros

```bash
# Procesar un lote de 50 temas pendientes:
python main.py enrich-genres

# Reclasificar todas las pistas de la biblioteca completa:
python main.py enrich-genres --all --force-all

# Clasificar géneros sin usar IA (únicamente con MusicBrainz / Deezer):
python main.py enrich-genres --all --no-ai
```

---

## 3. Números de Pista y Fechas de Lanzamiento

Los álbumes de la colección Permanente se completan con los números de pista oficiales del disco y el año original de publicación a través de [`src/enrich_track_meta.py`](../../src/enrich_track_meta.py):

- Recupera la secuencia oficial de pistas directamente del catálogo de YouTube Music.
- Etiqueta los archivos con `tracknumber` y `date` / `year`.
- Actualiza los campos `track_number` y `release_date` en la tabla `tracks` de SQLite.

```bash
# Enriquecer pistas sin número o fecha:
python main.py enrich-metadata

# Forzar reanálisis en toda la biblioteca:
python main.py enrich-metadata --force-all
```

---

## 4. Resolución Heurística de Álbumes de Estudio

Implementado en [`src/album_resolver.py`](../../src/album_resolver.py).

### Priorización de Álbumes de Estudio sobre Sencillos

Los sencillos sueltos a menudo incluyen carátulas promocionales efímeras, títulos confusos o carecen del contexto del disco. Al descubrir o descargar temas, Music Engine:

1. Detecta si un lanzamiento es un álbum de estudio mediante `is_studio_album()`.
2. Busca en YouTube Music dentro del catálogo oficial de álbumes del artista.
3. Otorga una **bonificación heurística de +100 puntos** a las pistas pertenecientes a álbumes oficiales frente a sencillos independientes.

### Filtro de Exclusión de Palabras Clave Antagónicas

Un problema frecuente en descargadores automatizados es confundir canciones con nombres muy similares dentro del mismo álbum. Music Engine incluye un riguroso **filtro de palabras clave antagónicas**:

| Búsqueda Solicitada | Versión de Álbum Descartada | Motivo del Descarte |
| :--- | :--- | :--- |
| *"Nuestro Primer Baile"* | *"Nuestro Último Baile"* | Antónimos `Primer` frente a `Último` |
| *"Track Title (Original)"* | *"Track Title (Remix)"* | Tipo incompatible `Original` frente a `Remix` |
| *"Song (Intro)"* | *"Song (Outro)"* | Posición incompatible `Intro` frente a `Outro` |

Esto elimina los falsos positivos y asegura que siempre obtengas la pista exacta solicitada.

---

## 5. Auditoría y Reparación de Pistas Dudosas (`fix-metadata`)

Con el tiempo, las búsquedas algorítmicas pueden coincidir ocasionalmente con grabaciones no oficiales, versiones karaoke, tributos acústicos o reinterpretaciones en 8 bits.

El comando `fix-metadata` audita tu colección cotejándola contra patrones conflictivos conocidos (`FORBIDDEN_WORDS`):
- `karaoke`, `cover`, `instrumental cover`, `tribute`, `8-bit`, `slowed + reverb`, `live at...`

```bash
# Auditoría y autorreparación heurística:
python main.py fix-metadata

# Auditoría utilizando la IA de Gemini como desempate final:
python main.py fix-metadata --use-ai
```

Cuando se detecta una pista subsanable, el motor:
1. Localiza la versión canónica de estudio en YouTube Music.
2. Sustituye el identificador de video en SQLite.
3. Elimina el archivo de audio antiguo y su `.lrc`.
4. Encola la versión oficial limpia para descarga inmediata.

---

<p align="center">
  <a href="automation.md"><b>⬅ Automatización en Segundo Plano</b></a> • <a href="backup-and-migration.md"><b>Siguiente: Copias de Seguridad y Migración ➡</b></a>
</p>
