web: python manage.py migrate --noinput && python manage.py createcachetable && python manage.py collectstatic --noinput && gunicorn config.wsgi -c gunicorn.conf.py
