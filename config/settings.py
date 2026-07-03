import os
from pathlib import Path
from django.templatetags.static import static
from django.urls import reverse_lazy

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
    'bioquimica',

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
            BASE_DIR / 'bioquimica' / 'templates',
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
        'NAME': os.environ.get('DB_NAME', 'Proyect'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'ABCDE'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
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
LANGUAGES = [('es', 'Español')]   # Solo español: ignora Accept-Language del navegador
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

# Catálogos grandes en el admin superan el límite por defecto (1000 campos).
# 10 000 cubre hasta ~5 000 filas con checkboxes; ajustar si crece más.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10_000

# ---------------------------
# CONFIGURACIÓN DE AUTENTICACIÓN (Allauth + Django)
# ---------------------------
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'analisis.backends.EmailOrUsernameBackend',              # username o email → funciona para admin y usuarios nuevos
    'allauth.account.auth_backends.AuthenticationBackend',   # Google / Social
]

# URLs de redirección unificadas utilizando nombres de rutas mutuas con namespace
LOGIN_URL = 'analisis:login'
LOGIN_REDIRECT_URL = 'analisis:dashboard'  # Redirige al dashboard de tu app tras loguearse
LOGOUT_REDIRECT_URL = 'analisis:login'

ACCOUNT_LOGOUT_REDIRECT_URL = 'analisis:login'
ACCOUNT_AUTHENTICATED_LOGIN_REDIRECTS = True
ACCOUNT_SIGNUP_FORM_CLASS = 'analisis.signup_form.CustomSignupForm'
ACCOUNT_ADAPTER = 'analisis.adapter.CustomAccountAdapter'
ACCOUNT_PREVENT_ENUMERATION = False
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']  # sin username; email=username
ACCOUNT_LOGIN_METHODS = {'email'}                               # login con correo (username = email auto)
ACCOUNT_UNIQUE_EMAIL = True         # un correo = una cuenta

# Configuración del proveedor de Google OAuth2
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
            'secret': os.environ.get('GOOGLE_CLIENT_SECRET', ''),
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
    "SITE_TITLE": "BioSuelo",
    "SITE_HEADER": "BioSuelo",
    "SITE_SUBHEADER": "Procesamiento y visualización de resultados microbiológicos",
    "SITE_SYMBOL": "biotech",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "DASHBOARD_CALLBACK": "analisis.admin.dashboard_callback",
    
    "STYLES": [
        lambda request: static("admin_personalizado.css"),
    ],

    "COLORS": {
        "primary": {
            "50":  "oklch(97% 0.020 165)",
            "100": "oklch(94% 0.042 165)",
            "200": "oklch(90% 0.072 165)",
            "300": "oklch(84% 0.104 165)",
            "400": "oklch(74% 0.124 165)",
            "500": "oklch(62% 0.136 165)",  # #1D9E75 verde principal
            "600": "oklch(54% 0.130 165)",
            "700": "oklch(46% 0.120 165)",
            "800": "oklch(37% 0.100 165)",
            "900": "oklch(28% 0.080 165)",
            "950": "oklch(20% 0.060 165)",
        },
    },

    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Secuenciación Molecular",
                "separator": True,
                "items": [
                    {
                        "title": "Catálogo de Microorganismos",
                        "icon": "menu_book",
                        "link": reverse_lazy("admin:analisis_catalogomicroorganismo_changelist"),
                    },
                    {
                        "title": "Archivos Moleculares",
                        "icon": "upload_file",
                        "link": reverse_lazy("admin:analisis_archivomolecular_changelist"),
                    },
                    {
                        "title": "Resultados Taxonómicos",
                        "icon": "science",
                        "link": reverse_lazy("admin:analisis_resultadotaxonomico_changelist"),
                    },
                ],
            },
            {
                "title": "Muestras de Campo",
                "separator": True,
                "items": [
                    {
                        "title": "Muestras de Suelo",
                        "icon": "landscape",
                        "link": reverse_lazy("admin:analisis_muestrasuelo_changelist"),
                    },
                    {
                        "title": "Cultivos",
                        "icon": "agriculture",
                        "link": reverse_lazy("admin:analisis_cultivo_changelist"),
                    },
                    {
                        "title": "Variedades / Clones",
                        "icon": "eco",
                        "link": reverse_lazy("admin:analisis_variedadclon_changelist"),
                    },
                ],
            },
            {
                "title": "Microbiología Clásica",
                "separator": True,
                "items": [
                    {
                        "title": "Ensayos (Recuento / Aislamiento)",
                        "icon": "science",
                        "link": reverse_lazy("admin:bioquimica_ensayomicrobiologico_changelist"),
                    },
                    {
                        "title": "Microorganismos Aislados",
                        "icon": "biotech",
                        "link": reverse_lazy("admin:bioquimica_microorganismoaislado_changelist"),
                    },
                ],
            },
            {
                "title": "Gestión",
                "separator": True,
                "items": [
                    {
                        "title": "Usuarios",
                        "icon": "group",
                        "link": reverse_lazy("admin:analisis_usuario_changelist"),
                    },
                ],
            },
        ],
    },

    # ─── TRADUCCIONES INTERNAS DE UNFOLD ──────────────────────────────────
    "LIST_EMPTY_TITLE": "No se encontraron resultados",
    "LIST_EMPTY_DESCRIPTION": "Esta sección no contiene registros aún. Crea un nuevo elemento o restablece los filtros.",
}

# ---------------------------
# CONFIGURACIÓN DE CORREO ELECTRÓNICO
# ---------------------------
# Desarrollo: muestra los correos en la terminal
# Producción: cambiar a smtp.EmailBackend con las credenciales reales
EMAIL_BACKEND   = 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST      = 'smtp.gmail.com'
EMAIL_PORT      = 587
EMAIL_USE_TLS   = True
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL  = 'BioSoil Analytics <terraBioLab@gmail.com>'

USE_DJANGO_JQUERY = True