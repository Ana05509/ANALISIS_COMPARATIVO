#!/usr/bin/env bash
# Publica la última versión de main en el servidor (equivale a un deploy de Railway).
# Uso: sudo bash /opt/biomicro/app/deploy/scripts/actualizar.sh
set -euo pipefail

APP=/opt/biomicro/app
VENV=/opt/biomicro/venv

# Respaldo antes de tocar nada: si una migración falla, se puede volver atrás.
bash $APP/deploy/scripts/respaldo.sh

cd $APP
sudo -u biomicro git pull --ff-only
sudo -u biomicro $VENV/bin/pip install -r requirements.txt
sudo -u biomicro $VENV/bin/python manage.py migrate --noinput
sudo -u biomicro $VENV/bin/python manage.py collectstatic --noinput
systemctl restart biomicro

sleep 3
systemctl is-active --quiet biomicro && echo "BioMicro actualizado y en marcha." \
    || { echo "El servicio no arrancó. Revisa: journalctl -u biomicro -n 50"; exit 1; }
