web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn config.wsgi --log-file - --access-logfile - --bind 0.0.0.0:$PORT --timeout 180
