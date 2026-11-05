#!/usr/bin/env bash
# Instalación inicial de BioMicro en Ubuntu Server 24.04.
# Uso (como un usuario con sudo):
#   sudo bash instalar.sh https://github.com/USUARIO/REPO.git biomicro.utc.edu.ec
# Es seguro volver a correrlo: cada paso revisa si ya está hecho.
set -euo pipefail

REPO_URL="${1:?Falta la URL del repositorio}"
DOMINIO="${2:?Falta el dominio, por ejemplo biomicro.utc.edu.ec}"

BASE=/opt/biomicro
APP=$BASE/app
VENV=$BASE/venv
PY=python3.13

echo "==> 1/7 Paquetes del sistema"
apt-get update
apt-get install -y software-properties-common git nginx postgresql postgresql-contrib
# Python 3.13 (el mismo que en desarrollo) desde el PPA deadsnakes.
if ! command -v $PY >/dev/null; then
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update
    apt-get install -y python3.13 python3.13-venv python3.13-dev
fi

echo "==> 2/7 Usuario del sistema 'biomicro'"
if ! id biomicro >/dev/null 2>&1; then
    useradd --system --home-dir $BASE --create-home --shell /bin/bash --gid www-data biomicro
fi
mkdir -p $BASE && chown biomicro:www-data $BASE

echo "==> 3/7 Código"
if [ ! -d $APP/.git ]; then
    sudo -u biomicro git clone "$REPO_URL" $APP
fi
sudo -u biomicro mkdir -p $APP/media

echo "==> 4/7 Entorno virtual y dependencias"
if [ ! -d $VENV ]; then
    sudo -u biomicro $PY -m venv $VENV
fi
sudo -u biomicro $VENV/bin/pip install --upgrade pip
sudo -u biomicro $VENV/bin/pip install -r $APP/requirements.txt

echo "==> 5/7 Archivo .env"
if [ ! -f $APP/.env ]; then
    sudo -u biomicro cp $APP/deploy/env.produccion.ejemplo $APP/.env
    chmod 600 $APP/.env
    sed -i "s/biomicro.utc.edu.ec/$DOMINIO/g" $APP/.env
    echo "    Se creó $APP/.env: complétalo (SECRET_KEY, DATABASE_URL, correo)"
    echo "    y vuelve a correr este script."
    exit 0
fi

echo "==> 6/7 Migraciones y archivos estáticos"
cd $APP
sudo -u biomicro $VENV/bin/python manage.py migrate --noinput
sudo -u biomicro $VENV/bin/python manage.py collectstatic --noinput
sudo -u biomicro $VENV/bin/python manage.py check --deploy

echo "==> 7/7 Servicio y Nginx"
cp $APP/deploy/systemd/biomicro.service /etc/systemd/system/biomicro.service
systemctl daemon-reload
systemctl enable --now biomicro
systemctl restart biomicro

ln -sf /etc/nginx/sites-available/biomicro /etc/nginx/sites-enabled/biomicro
rm -f /etc/nginx/sites-enabled/default
mkdir -p /var/www/certbot

if [ ! -f /etc/letsencrypt/live/$DOMINIO/fullchain.pem ]; then
    # Sin certificado, la config completa no pasa "nginx -t". Se deja solo
    # el puerto 80 para que certbot pueda validar el dominio.
    cat > /etc/nginx/sites-available/biomicro <<EOF
server {
    listen 80;
    server_name $DOMINIO;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 503; }
}
EOF
    nginx -t && systemctl reload nginx
    echo
    echo "Falta el certificado HTTPS para $DOMINIO. Opciones:"
    echo "  a) Let's Encrypt:"
    echo "     sudo apt install -y certbot"
    echo "     sudo certbot certonly --webroot -w /var/www/certbot -d $DOMINIO"
    echo "  b) Certificado de TI: cópialo y ajusta ssl_certificate y"
    echo "     ssl_certificate_key en $APP/deploy/nginx/biomicro.conf"
    echo "Después vuelve a correr este script."
    exit 0
fi

sed "s/biomicro.utc.edu.ec/$DOMINIO/g" $APP/deploy/nginx/biomicro.conf > /etc/nginx/sites-available/biomicro
nginx -t
systemctl reload nginx
echo
echo "Listo. Abre https://$DOMINIO"
