import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
from django.urls import reverse_lazy
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# SEGURIDAD
_INSECURE_SECRET_KEY = 'django-insecure-dev-key'
SECRET_KEY = os.environ.get('SECRET_KEY', _INSECURE_SECRET_KEY)
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.environ.get(
    'ALLOWED_HOSTS',
    '127.0.0.1,localhost'
).split(',')

# Dominio público que asigna Railway (solo si existe).
_railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
if _railway_domain:
    ALLOWED_HOSTS.append(_railway_domain)

# Necesario para aceptar POST (login, formularios) en producción.
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()
]
if _railway_domain:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_railway_domain}')

# Sesión: se renueva con la actividad, expira tras 8 h inactiva o al cerrar el navegador.
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 horas
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Seguridad HTTPS/HSTS (solo en producción, con DEBUG=False).
if not DEBUG:
    if SECRET_KEY == _INSECURE_SECRET_KEY:
        raise ImproperlyConfigured(
            "SECRET_KEY sigue en su valor de desarrollo con DEBUG=False. "
            "Define la variable de entorno SECRET_KEY antes de desplegar "
            "(python -c \"from django.core.management.utils import get_random_secret_key; "
            "print(get_random_secret_key())\")."
        )

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'True') == 'True'
    # Necesario cuando Django corre detrás de un proxy (nginx, etc.) que termina el TLS:
    # así sabe que el request original fue HTTPS aunque le llegue como HTTP interno.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', 31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# CONTENT SECURITY POLICY
# Se permiten 'unsafe-inline' y 'unsafe-eval' por los scripts en línea y Alpine.js (Unfold).
# CSP_MODO: reporte (por defecto, solo avisa en el log) | bloquear | off
from django.utils.csp import CSP  # noqa: E402

_CDN_SCRIPTS = ["https://cdn.plot.ly", "https://cdn.jsdelivr.net"]
_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.UNSAFE_INLINE, CSP.UNSAFE_EVAL, *_CDN_SCRIPTS],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE, "https://fonts.googleapis.com", "https://cdn.jsdelivr.net"],
    "font-src": [CSP.SELF, "https://fonts.gstatic.com", "https://cdn.jsdelivr.net", "data:"],
    # https: porque los cultivos pueden tener una imagen externa (Cultivo.imagen_url)
    "img-src": [CSP.SELF, "data:", "blob:", "https:"],
    # data:/blob: para las descargas PNG/SVG de los gráficos (fetch de un data URL)
    "connect-src": [CSP.SELF, "data:", "blob:"],
    "media-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    # El login con Google redirige el formulario a accounts.google.com
    "form-action": [CSP.SELF, "https://accounts.google.com"],
    "report-uri": "/csp-report/",
}
CSP_MODO = os.environ.get('CSP_MODO', 'reporte').strip().lower()
SECURE_CSP = _CSP if CSP_MODO == 'bloquear' else {}
SECURE_CSP_REPORT_ONLY = _CSP if CSP_MODO == 'reporte' else {}

# APLICACIONES
INSTALLED_APPS = [
    'unfold',  # Interfaz avanzada para el administrador
    'unfold.contrib.simple_history',  # Plantillas de Unfold para la pestaña "Historial"

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Mapeado aquí para no estorbar a Unfold
    'django.contrib.postgres',  # ArrayField de analisis.BloqueoLogin

    "unfold.contrib.import_export", 
    "import_export",
    
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',  # Proveedor específico de Google
    # Historial de cambios; debe ir después de unfold.contrib.simple_history.
    'simple_history',

    'analisis',
    'bioquimica',
    'portal',

]

# MIDDLEWARE
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',

    # Cabecera Content-Security-Policy (configuración en SECURE_CSP más abajo)
    'django.middleware.csp.ContentSecurityPolicyMiddleware',

    # Sirve los estáticos en producción; debe ir justo después de SecurityMiddleware.
    'whitenoise.middleware.WhiteNoiseMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Middleware requerido por allauth para gestionar sesiones de cuentas sociales
    'allauth.account.middleware.AccountMiddleware',

    # Auditoría: adjunta el usuario autenticado a cada registro histórico,
    # sin importar si el cambio vino del admin, de una vista o de la API
    'simple_history.middleware.HistoryRequestMiddleware',

    # Pide aceptar los Términos de uso y la Política de privacidad vigentes
    # a quien aún no lo hizo (va después de AuthenticationMiddleware)
    'analisis.middleware.TerminosMiddleware',
]

# URLS Y WSGI
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
                'analisis.permisos.contexto_permisos',  # variable {{ puede_cargar }}
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# DATABASE (PostgreSQL): usa DATABASE_URL si existe, si no las credenciales locales.
if os.environ.get('DATABASE_URL'):
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.config(
            env='DATABASE_URL',
            conn_max_age=600,
            ssl_require=not DEBUG,
        )
    }
else:
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

# CACHÉ. LocMemCache (por defecto) vive en la memoria de cada proceso: con
# WEB_CONCURRENCY > 1 cada worker tiene el suyo. CACHE_BACKEND=db lo comparte
# entre procesos (tabla biomicro_cache, la crea "createcachetable"). Lo usa el
# limitador por IP de allauth; el bloqueo por cuenta ya está en la base
# (analisis.BloqueoLogin) y no depende de esto.
if os.environ.get('CACHE_BACKEND', 'local').strip().lower() == 'db':
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
                          'LOCATION': 'biomicro_cache'}}
else:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# PASSWORDS VALIDATORS
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# INTERNACIONALIZACIÓN
LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Guayaquil'
USE_I18N = True
USE_TZ = True
LANGUAGES = [('es', 'Español')]   # Solo español: ignora Accept-Language del navegador
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# STATIC FILES (CSS, JS, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise con hash en el nombre de archivo (solo en producción).
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG else
            "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}

# MEDIA FILES (Cargas de archivos 16S e ITS)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# USUARIO PERSONALIZADO (Roles)
AUTH_USER_MODEL = 'analisis.Usuario'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Catálogos grandes en el admin superan el límite por defecto (1000 campos).
# 10 000 cubre hasta ~5 000 filas con checkboxes; ajustar si crece más.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10_000

# CONFIGURACIÓN DE AUTENTICACIÓN (Allauth + Django)
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
# "Olvidé mi contraseña" responde igual exista o no la cuenta, y no escribe a
# direcciones no registradas. El registro sigue avisando "ya existe una cuenta":
# ocultarlo exige verificación de correo obligatoria (cambiaría el flujo de alta).
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']  # sin username; email=username
ACCOUNT_LOGIN_METHODS = {'email'}                               # login con correo (username = email auto)
ACCOUNT_UNIQUE_EMAIL = True         # un correo = una cuenta
SOCIALACCOUNT_ADAPTER = 'analisis.adapter.CustomSocialAccountAdapter'

# Dominios permitidos para registrar cuentas nuevas (incluye subdominios).
# Vacío = sin restricción.
REGISTRO_DOMINIOS_PERMITIDOS = [
    d.strip().lower().lstrip('@')
    for d in os.environ.get('REGISTRO_DOMINIOS_PERMITIDOS', 'utc.edu.ec').split(',')
    if d.strip()
]

# Igual que analisis.seguridad: 3 intentos fallidos por correo → 15 minutos.
ACCOUNT_RATE_LIMITS = {"login_failed": "10/m/ip,3/15m/key"}

# Railway usa 1 proxy: se toma la última IP de X-Forwarded-For.
ALLAUTH_TRUSTED_PROXY_COUNT = int(
    os.environ.get('ALLAUTH_TRUSTED_PROXY_COUNT', '1' if _railway_domain else '0')
)

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

# CONFIGURACIÓN INTERFAZ UNFOLD
def _static_con_version(nombre_relativo):
    """Agrega ?v=<mtime> a la URL del estático para evitar la caché del navegador."""
    ruta = BASE_DIR / "static" / nombre_relativo
    try:
        version = int(os.path.getmtime(ruta))
    except OSError:
        version = 0
    url_base = static(nombre_relativo)
    return f"{url_base}?v={version}"


UNFOLD = {
    "SITE_TITLE": "BioMicro",
    "SITE_HEADER": "BioMicro",
    "SITE_SUBHEADER": "Procesamiento y visualización de resultados microbiológicos",
    "SITE_SYMBOL": "biotech",
    "SITE_ICON": lambda request: _static_con_version("logo.png"),
    "SITE_LOGO": lambda request: _static_con_version("logo.png"),
    "SITE_FAVICONS": [
        {
            "rel": "icon",
            "type": "image/png",
            "href": lambda request: _static_con_version("logo.png"),
        },
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "DASHBOARD_CALLBACK": "analisis.admin.dashboard_callback",

    "STYLES": [
        lambda request: _static_con_version("admin_personalizado.css"),
    ],
    "SCRIPTS": [
        lambda request: _static_con_version("admin_sidebar_fijo.js"),
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
        "show_search": False,
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
            {
                "title": "Auditoría",
                "separator": True,
                "items": [
                    {
                        "title": "Eventos de Acceso",
                        "icon": "shield_lock",
                        "link": reverse_lazy("admin:analisis_eventoacceso_changelist"),
                    },
                    {
                        "title": "Registro de Acciones",
                        "icon": "history",
                        "link": reverse_lazy("admin:admin_logentry_changelist"),
                    },
                ],
            },
            {
                "title": "Ayuda",
                "separator": True,
                "items": [
                    {
                        "title": "Manual del Administrador",
                        "icon": "menu_book",
                        "link": reverse_lazy("admin-manual"),
                    },
                ],
            },
        ],
    },

    # TRADUCCIONES INTERNAS DE UNFOLD
    "LIST_EMPTY_TITLE": "No se encontraron resultados",
    "LIST_EMPTY_DESCRIPTION": "Esta sección no contiene registros aún. Crea un nuevo elemento o restablece los filtros.",
}

# CONFIGURACIÓN DE CORREO ELECTRÓNICO
EMAIL_HOST      = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT      = int(os.environ.get('EMAIL_PORT', '587'))
# 587 = STARTTLS (EMAIL_USE_TLS); 465 = SSL directo (EMAIL_USE_SSL). Nunca los dos.
EMAIL_USE_TLS   = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL   = os.environ.get('EMAIL_USE_SSL', 'False') == 'True'
# Timeout SMTP para no colgar el worker si el servidor de correo no responde.
EMAIL_TIMEOUT   = 10
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
# Remitente que ven los usuarios. Si no se define, usa la cuenta SMTP.
# Con el correo de la UTC, por ejemplo: BioMicro UTC <biomicro@utc.edu.ec>
DEFAULT_FROM_EMAIL  = os.environ.get('DEFAULT_FROM_EMAIL') or 'BioMicro <{}>'.format(
    os.environ.get('EMAIL_HOST_USER') or 'noreply@biomicro.ec'
)
SERVER_EMAIL        = DEFAULT_FROM_EMAIL

# Si hay credenciales en .env usa SMTP real; si no, imprime en consola
if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

USE_DJANGO_JQUERY = True

# LOGS: todo a la consola (Railway los recoge de stdout/stderr).
# Sin esto, con DEBUG=False Django descarta los errores 500: su manejador de
# consola solo actúa con DEBUG=True y mail_admins no tiene ADMINS.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'biomicro': {'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'biomicro'},
    },
    'root': {'handlers': ['console'], 'level': os.environ.get('LOG_LEVEL', 'INFO')},
    'loggers': {
        'django': {'level': 'INFO'},
        'django.db.backends': {'level': 'WARNING'},
    },
}

ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https' if not DEBUG else 'http'