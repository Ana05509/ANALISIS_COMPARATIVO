#!/usr/bin/env bash
# Respaldo de la base de datos y de media/ de BioMicro.
# Guarda en /var/backups/biomicro y borra los de más de 28 días.
# Programarlo todos los días a las 02:00:
#   echo "0 2 * * * root bash /opt/biomicro/app/deploy/scripts/respaldo.sh" | sudo tee /etc/cron.d/biomicro-respaldo
set -euo pipefail

APP=/opt/biomicro/app
DESTINO=/var/backups/biomicro
DIAS=28
FECHA=$(date +%Y-%m-%d_%H%M)

mkdir -p $DESTINO
chmod 700 $DESTINO

# DATABASE_URL se lee del .env sin cargar el resto en el entorno.
DATABASE_URL=$(grep -E '^DATABASE_URL=' $APP/.env | cut -d= -f2-)

pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" \
    --file=$DESTINO/bd_$FECHA.dump
tar -czf $DESTINO/media_$FECHA.tar.gz -C $APP media

find $DESTINO -type f -mtime +$DIAS -delete
echo "Respaldo listo: $DESTINO/bd_$FECHA.dump y media_$FECHA.tar.gz"
