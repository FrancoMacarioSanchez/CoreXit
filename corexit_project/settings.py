"""
Settings de CoreX Hub (portal de clientes, staff y panel de desarrolladores).

Todo lo sensible se lee de variables de entorno (o de un archivo .env en la raíz).
Ver .env.example.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env(ruta):
    """Carga un .env simple (CLAVE=valor) sin dependencias externas."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding='utf-8').splitlines():
        linea = linea.strip()
        if not linea or linea.startswith('#') or '=' not in linea:
            continue
        clave, valor = linea.split('=', 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env(BASE_DIR / '.env')


def env(clave, default=None):
    return os.environ.get(clave, default)


def env_bool(clave, default=False):
    return str(env(clave, default)).lower() in ('1', 'true', 'yes', 'si', 'on')


def env_list(clave, default=''):
    return [x.strip() for x in env(clave, default).split(',') if x.strip()]


SECRET_KEY = env('DJANGO_SECRET_KEY', 'dev-inseguro-cambiar-en-produccion')
DEBUG = env_bool('DJANGO_DEBUG', True)
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS', '')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    # Núcleo: modelos, autenticación, integración con los SaaS y API
    'dashboard.apps.DashboardConfig',
    # Áreas separadas por rol
    'portal',     # clientes
    'staff',      # equipo comercial / administración / soporte
    'devpanel',   # desarrolladores (tenants y métricas de cada SaaS)
    'landing',
    'monitoreo',  # métricas del servidor y actividad del staff
    'igportal',   # portal de Instagram
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'monitoreo.middleware.MetricasRequestMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'monitoreo.middleware.ActividadMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'corexit_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'dashboard.context_processors.roles',
            ],
        },
    },
]

WSGI_APPLICATION = 'corexit_project.wsgi.application'

if env('DB_ENGINE', 'postgres') == 'sqlite':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env('DB_NAME', 'corex_db'),
            'USER': env('DB_USER', 'corex_user'),
            'PASSWORD': env('DB_PASSWORD', 'corex_password'),
            'HOST': env('DB_HOST', '127.0.0.1'),
            'PORT': env('DB_PORT', '5433'),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Los PDF de facturas NO se sirven públicamente: se entregan por vistas que
# controlan que el usuario sea el dueño (o staff).
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / env('MEDIA_DIR', 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cookies con nombre propio: en 127.0.0.1 las cookies NO se separan por puerto y
# el Hub, FacturAR y GestionAR se pisarían la sesión entre sí.
SESSION_COOKIE_NAME = env('SESSION_COOKIE_NAME', 'corexhub_sessionid')
CSRF_COOKIE_NAME = env('CSRF_COOKIE_NAME', 'corexhub_csrftoken')

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'redirect_post_login'
LOGOUT_REDIRECT_URL = 'landing-home'

# --- Integración con los SaaS -------------------------------------------------
# Timeout (segundos) para las llamadas HTTP salientes a la API de cada SaaS.
COREX_SAAS_TIMEOUT = int(env('COREX_SAAS_TIMEOUT', '10'))
# Alta de tenant: el SaaS crea y migra un schema completo, puede tardar
COREX_SAAS_TIMEOUT_ALTA = int(env('COREX_SAAS_TIMEOUT_ALTA', '120'))
# Dominio base sugerido para los tenants nuevos (ej. gestionar-mitienda.corexit.tech)
COREX_DOMINIO_BASE = env('COREX_DOMINIO_BASE', 'corexit.tech')
# URL pública de este hub (se le envía a los SaaS para que sepan a dónde empujar métricas)
COREX_HUB_URL = env('COREX_HUB_URL', 'http://127.0.0.1:8000')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'corex': {'handlers': ['console'], 'level': env('COREX_LOG_LEVEL', 'INFO')},
    },
}
