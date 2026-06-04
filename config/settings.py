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
    'unfold',  # Interfaz avanzada para el administrador (debe ir antes de admin)
    'django.contrib.sites',  # Requerido obligatoriamente por django-allauth
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Aplicaciones de autenticación de django-allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',  # Proveedor específico de Google
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
    
    # Middleware requerido por allauth para gestionar sesiones de cuentas sociales
    'allauth.account.middleware.AccountMiddleware',
]

# ---------------------------
# URLS Y WSGI
# ---------------------------
ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'analisis' / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',  # Requerido por allauth
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------
# DATABASE (PostgreSQL)
# ---------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'MICROBIANA',
        'USER': 'postgres',
        'PASSWORD': 'ABCDE',  
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# ---------------------------
# PASSWORDS VALIDATORS
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
# STATIC FILES (CSS, JS, Images)
# ---------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ---------------------------
# MEDIA FILES (Cargas de archivos 16S e ITS)
# ---------------------------
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------
# USUARIO PERSONALIZADO (Roles)
# ---------------------------
AUTH_USER_MODEL = 'analisis.Usuario'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------
# CONFIGURACIÓN DE AUTENTICACIÓN (Allauth + Django)
# ---------------------------
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',             # Autenticación tradicional
    'allauth.account.auth_backends.AuthenticationBackend',   # Autenticación vía Google/Social
]

# URLs de redirección unificadas utilizando nombres de rutas mutuas
LOGIN_URL = 'analisis:login'
LOGIN_REDIRECT_URL = 'analisis:dashboard'  # Redirige al dashboard de tu app tras loguearse
LOGOUT_REDIRECT_URL = 'analisis:login'     # Redirige al login al salir

# Configuración del proveedor de Google OAuth2
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'OAUTH_PKCE_ENABLED': True,
    }
}

# ---------------------------
# CONFIGURACIÓN INTERFAZ UNFOLD
# ---------------------------
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