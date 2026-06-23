import os
from pathlib import Path
from django.templatetags.static import static

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
    'unfold',  # Interfaz avanzada para el administrador
    
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Mapeado aquí para no estorbar a Unfold

    "unfold.contrib.import_export", 
    "import_export",
    
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
    'django.middleware.locale.LocaleMiddleware',
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
        'NAME': 'Proyect',
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
LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Guayaquil'
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

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

# URLs de redirección unificadas utilizando nombres de rutas mutuas con namespace
LOGIN_URL = 'analisis:login'
LOGIN_REDIRECT_URL = 'analisis:dashboard'  # Redirige al dashboard de tu app tras loguearse
LOGOUT_REDIRECT_URL = 'analisis:login'

ACCOUNT_LOGOUT_REDIRECT_URL = 'analisis:login'
ACCOUNT_AUTHENTICATED_LOGIN_REDIRECTS = True    # Redirige al login al salir
ACCOUNT_SIGNUP_FORM_CLASS = 'analisis.signup_form.CustomSignupForm'
ACCOUNT_ADAPTER = 'analisis.adapter.CustomAccountAdapter'
ACCOUNT_PREVENT_ENUMERATION = False

# Configuración del proveedor de Google OAuth2
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': 'TU_CLIENT_ID_DE_GOOGLE_CLOUD.apps.googleusercontent.com',
            'secret': 'TU_SECRET_KEY_DE_GOOGLE_CLOUD',
            'key': ''
        },
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
    
    "STYLES": [
        lambda request: static("admin_personalizado.css"),
    ],

"COLORS": {
        "primary": {
            "50": "239 246 255",
            "100": "219 234 254",
            "200": "191 219 254",
            "300": "147 197 253",
            "400": "96 165 250",
            "500": "59 130 246",  # Azul principal
            "600": "37 99 235",
            "700": "29 78 216",
            "800": "30 64 175",
            "900": "30 58 138",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
    },
    
    # ─── TRADUCCIONES INTERNAS DE UNFOLD ──────────────────────────────────
    "LIST_EMPTY_TITLE": "No se encontraron resultados",
    "LIST_EMPTY_DESCRIPTION": "Esta sección no contiene registros aún. Crea un nuevo elemento o restablece los filtros.",
}

# ---------------------------
# CONFIGURACIÓN DE CORREO ELECTRÓNICO
# ---------------------------
# Muestra los correos en la consola/terminal para pruebas de desarrollo
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
USE_DJANGO_JQUERY = True