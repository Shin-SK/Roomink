web: gunicorn config.wsgi --log-file -
release: python3 manage.py migrate --noop || python3 manage.py migrate
