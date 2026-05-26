import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------
# SEGURIDAD
# ---------------------------
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-dev-key')
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get(
    'ALLOWED_HOSTS',
    '127.0.0.1,localhost'
).split(',')

# ---------------------------
# APLICACIONES
# ---------------------------
INSTALLED_APPS = [
    'unfold',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'analisis',
]

# ---------------------------
# MIDDLEWARE
# ---------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ---------------------------
# URLS
# ---------------------------
ROOT_URLCONF = 'config.urls'

# ---------------------------
# TEMPLATES
# ---------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------
# DATABASE
# ---------------------------
# Por defecto usa SQLite (desarrollo). Para PostgreSQL, configura variables de entorno:
# DATABASE_ENGINE=postgresql
# DATABASE_NAME=MICROBIANA
# DATABASE_USER=postgres
# DATABASE_PASSWORD=tu_password
# DATABASE_HOST=localhost
# DATABASE_PORT=5432

DB_ENGINE = os.environ.get('DATABASE_ENGINE', 'sqlite3')

if DB_ENGINE == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DATABASE_NAME', 'MICROBIANA'),
            'USER': os.environ.get('DATABASE_USER', 'postgres'),
            'PASSWORD': os.environ.get('DATABASE_PASSWORD', ''),
            'HOST': os.environ.get('DATABASE_HOST', 'localhost'),
            'PORT': os.environ.get('DATABASE_PORT', '5432'),
        }
    }
else:
    # SQLite por defecto (seguro y fácil para desarrollo)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ---------------------------
# PASSWORDS
# ---------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------
# INTERNACIONALIZACIÓN
# ---------------------------
LANGUAGE_CODE = 'es-ec'
TIME_ZONE = 'America/Guayaquil'
USE_I18N = True
USE_TZ = True

# ---------------------------
# STATIC FILES
# ---------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ---------------------------
# MEDIA FILES
# Necesario para ArchivoMolecular.archivo (FileField)
# README: "Ingesta de Datos: carga de archivos 16S e ITS"
# ---------------------------
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------
# LOGIN / LOGOUT
# ---------------------------
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'analisis:dashboard'
LOGOUT_REDIRECT_URL = 'login'

# ---------------------------
# USUARIO PERSONALIZADO
# README: Roles → Administrador, Analista Especialista, Técnico Agrícola
# ---------------------------
AUTH_USER_MODEL = 'analisis.Usuario'

# ---------------------------
# DEFAULT PRIMARY KEY
# ---------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


UNFOLD = {

    "SITE_TITLE": "TerraBioLab",
    "SITE_HEADER": "TerraBioLab UTC",
    "SITE_SUBHEADER": "Sistema Inteligente de Análisis Microbiológico",
    "SITE_SYMBOL": "biotech",

    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,

    "COLORS": {
        "primary": {
            "50": "240 253 250",
            "100": "204 251 241",
            "200": "153 246 228",
            "300": "94 234 212",
            "400": "45 212 191",
            "500": "20 184 166",
            "600": "13 148 136",
            "700": "15 118 110",
            "800": "17 94 89",
            "900": "19 78 74",
        },
    },

    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
    },
}