# Motor de Música (Music Conveyor Engine)

¡Bienvenido al ecosistema musical 100% offline y gestionado por IA!

## Pasos Universales:
1. Asegúrate de tener Python 3.10 o superior instalado.
2. Abre una terminal/consola en esta carpeta.
3. Ejecuta: `pip install -r requirements.txt`
4. Copia `config.yaml.template` a `config/config.yaml`.
5. Copia `env.template` a `config/.env` e introduce tus claves de Gemini y ListenBrainz dentro de ese archivo `.env`.
6. Ejecuta: `python init_db.py` para crear la base de datos inicial.
7. Ejecuta: `python main.py run` para iniciar el motor por primera vez.

## Estructura de carpetas:
- **storage/Cinta**: Aquí irán las canciones efímeras.
- **storage/Permanente**: Tu biblioteca intocable.
- **storage/Antojos**: Para peticiones manuales, escribe en `storage/Antojos/antojos.txt`.
- **storage/Playlists**: Las listas de reproducción m3u8.

## Instalación Específica para LINUX
1. Instala FFmpeg si no lo tienes: `sudo apt install ffmpeg`.
2. Para automatizar el motor en segundo plano, añade esto a tu Cronjob (`crontab -e`):
   `0 * * * * cd /ruta/absoluta/a/esta/carpeta && python3 main.py run`
3. Instala Syncthing y comparte la carpeta `storage/` con tu móvil Android.
