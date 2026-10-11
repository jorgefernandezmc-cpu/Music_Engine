#!/bin/bash
cd "$(dirname "$0")"
echo 'Ejecutando motor...'
python3 main.py run
read -p 'Presiona Enter para salir...'
