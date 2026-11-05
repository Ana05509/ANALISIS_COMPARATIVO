import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
from django.urls import reverse_lazy
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# ---------------------------
# SEGURIDAD
# ---------------------------
_INSECURE_SECRET_KEY = 'django-insecure-dev-key'
SECRET_KEY = os.environ.get('SECRET_KEY', _INSECURE_SECRET_KEY)
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.environ.get(
    'ALLOWED_HOSTS',
    '127.0.0.1,localhost'
).split(',')

# Railway inyecta el dominio público asignado en esta variable — se agrega
# solo si existe, así el mismo settings.py sirve para local y para Railway
# sin tener que copiar el dominio a mano en ALLOWED_HOSTS cada vez que
# Railway lo regenera.
_railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
if _railway_domain:
    ALLOWED_HOSTS.append(_railway_domain)

# Django exige CSRF_TRUSTED_ORIGINS con esquema explícito (https://) para
# aceptar POST desde un dominio distinto al de desarrollo — sin esto, el
# login y cualquier formulario fallan con "CSRF verification failed" en
# producción aunque ALLOWED_HOSTS esté bien.
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()
]
if _railway_domain:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_railway_domain}')

# Política de sesión: como en la mayoría de plataformas establecidas (banca,
# sistemas universitarios, admin de SaaS) — dura mientras la persona sigue
# activa (se renueva en cada request), pero expira sola tras 8h de inactividad
# y también al cerrar el navegador, sin necesidad de "recordarme" porque esta
# app no ofrece esa opción. Antes no había ningún límite explícito y Django
# usaba su default de 2 semanas fijas, lo que hacía que el módulo de
# Auditoría > Eventos de Acceso pareciera "no actualizarse": con la sesión
# viva tanto tiempo, nadie volvía a autenticarse (y por lo tanto no se
# generaba un evento nuevo) aunque sí estuviera usando el sistema a diario.
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 horas
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ---------------------------
# ENDURECIMIENTO PARA PRODUCCIÓN (HTTPS/HSTS)
# Todo esto queda inactivo con DEBUG=True para no romper el entorno local
# (cookies "secure" y redirección HTTPS no funcionan sobre http://localhost).
# ---------------------------
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

# ---------------------------
# CONTENT SECURITY POLICY
# Lista de orígenes desde los que el navegador puede cargar scripts, estilos,
# fuentes e imágenes. Las plantillas tienen scripts y atributos onclick/style
# en línea, y el admin (Unfold) usa Alpine.js, que necesita eval: por eso se
# permiten 'unsafe-inline' y 'unsafe-eval'. Aun así la política impide cargar
# scripts de dominios no listados, plugins (<object>), cambiar la URL base,
# incrustar el sitio en otra página y enviar formularios a sitios ajenos.
#
# CSP_MODO=reporte  (por defecto) el navegador solo avisa; cada aviso queda
#                   en el log del servidor como "CSP {...}" (ver /csp-report/).
# CSP_MODO=bloquear el navegador bloquea lo que no cumpla. Pasar a este modo
#                   cuando el log lleve unos días sin avisos inesperados.
# CSP_MODO=off      sin cabecera.
# ---------------------------
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

# ---------------------------
# APLICACIONES
# ---------------------------
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

    "unfold.contrib.import_export", 
    "import_export",
    
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',  # Proveedor específico de Google
    # Historial de cambios (Cultivo, MuestraSuelo, Catálogo, Usuario).
    # unfold.contrib.simple_history (arriba) debe ir antes que simple_history
    # para que sus plantillas (tema Unfold) tengan prioridad sobre las de simple_history.
    'simple_history',

    'analisis',
    'bioquimica',
    'portal',

]

# ---------------------------
# MIDDLEWARE
# ---------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',

    # Cabecera Content-Security-Policy (configuración en SECURE_CSP más abajo)
    'django.middleware.csp.ContentSecurityPolicyMiddleware',

    # Sirve los estáticos directamente desde la app en producción (Railway
    # no tiene un servidor web aparte tipo nginx delante) — debe ir
    # inmediatamente después de SecurityMiddleware, antes de cualquier otro.
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
# Railway (y la mayoría de hosts) inyectan la conexión completa en
# DATABASE_URL cuando se agrega un plugin de Postgres — si existe, se usa
# esa; si no (desarrollo local), se cae a las credenciales de siempre.
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

# WhiteNoise sirve STATIC_ROOT directamente desde la app (sin nginx
# delante) con hash en el nombre de archivo + cache larga — mismo efecto
# que el cache-busting manual que ya hace UNFOLD["STYLES"]/["SCRIPTS"]
# vía _static_con_version(), pero para TODO estático, no solo esos dos
# archivos. Solo en producción: en local, collectstatic no siempre se ha
# corrido, y Django ya sirve estáticos directo con runserver.
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
SOCIALACCOUNT_ADAPTER = 'analisis.adapter.CustomSocialAccountAdapter'

# Solo se pueden crear cuentas nuevas (formulario o Google) con correos de
# estos dominios; también se aceptan sus subdominios (p. ej. est.utc.edu.ec).
# No afecta a las cuentas que ya existen: siguen entrando y recuperando su
# contraseña aunque su correo sea de otro dominio. Vacío = registro sin
# restricción de dominio.
REGISTRO_DOMINIOS_PERMITIDOS = [
    d.strip().lower().lstrip('@')
    for d in os.environ.get('REGISTRO_DOMINIOS_PERMITIDOS', 'utc.edu.ec').split(',')
    if d.strip()
]

# Respaldo del limitador de allauth alineado con el bloqueo propio de
# analisis.seguridad (3 intentos fallidos por correo → 15 minutos). Solo se
# sobrescribe esta clave; allauth conserva sus demás límites por defecto.
ACCOUNT_RATE_LIMITS = {"login_failed": "10/m/ip,3/15m/key"}

# Detrás del proxy de Railway, REMOTE_ADDR es la IP del proxy, no la del
# cliente: sin esto el limitador de intentos de login (consume_or_429 en
# views/auth.py) metía a TODOS los usuarios en el mismo contador. Con 1
# proxy de confianza se toma la última IP de X-Forwarded-For (la que
# agregó el proxy), no la primera (que la escribe el cliente y es falsificable).
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

# ---------------------------
# CONFIGURACIÓN INTERFAZ UNFOLD
# ---------------------------
def _static_con_version(nombre_relativo):
    """
    static("admin_personalizado.css") + "?v=<mtime>": sin esto, el
    navegador puede quedarse sirviendo una versión vieja del CSS/JS desde
    caché aunque el archivo en el servidor ya haya cambiado, y un
    Ctrl+Shift+R no siempre alcanza para forzarlo. Al cambiar la fecha de
    modificación del archivo, cambia la URL completa, así que el
    navegador SIEMPRE la trata como un recurso nuevo.
    """
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

    # ─── TRADUCCIONES INTERNAS DE UNFOLD ──────────────────────────────────
    "LIST_EMPTY_TITLE": "No se encontraron resultados",
    "LIST_EMPTY_DESCRIPTION": "Esta sección no contiene registros aún. Crea un nuevo elemento o restablece los filtros.",
}

# ---------------------------
# CONFIGURACIÓN DE CORREO ELECTRÓNICO
# ---------------------------
EMAIL_HOST      = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT      = int(os.environ.get('EMAIL_PORT', '587'))
# 587 = STARTTLS (EMAIL_USE_TLS); 465 = SSL directo (EMAIL_USE_SSL). Nunca los dos.
EMAIL_USE_TLS   = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL   = os.environ.get('EMAIL_USE_SSL', 'False') == 'True'
# Sin esto, smtplib no tiene timeout (None) y se queda esperando
# indefinidamente si el puerto SMTP saliente está lento/filtrado en
# producción (Railway) — el worker de gunicorn quedaba colgado hasta su
# propio timeout de 180s en vez de fallar rápido y dejar que
# CustomAccountAdapter.send_mail() (analisis/adapter.py) lo capture.
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

ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https' if not DEBUG else 'http'