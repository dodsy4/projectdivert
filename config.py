import os

# Grabs the folder where the script runs.
basedir = os.path.abspath(os.path.dirname(__file__))


def _bool_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _int_env(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default


DEBUG = _bool_env('FLASK_DEBUG', False)

# Never use a randomly generated key in production; set SECRET_KEY in env.
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-only-change-me')

def _clean_env_url(value):
    """Trim whitespace and accidental surrounding quotes from env URLs."""
    if not value:
        return value
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1].strip()
    return value


# Prefer explicit SQLALCHEMY_DATABASE_URI when both are present.
database_url = _clean_env_url(os.getenv('SQLALCHEMY_DATABASE_URI')) or _clean_env_url(os.getenv('DATABASE_URL'))
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

SQLALCHEMY_DATABASE_URI = database_url or 'postgresql://louisdods@localhost:5432/pd'
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Session/cookie hardening
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = _bool_env('SESSION_COOKIE_SECURE', True)
SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

# Forms and URL behavior
WTF_CSRF_ENABLED = True
PREFERRED_URL_SCHEME = os.getenv('PREFERRED_URL_SCHEME', 'https')

# External service keys
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '')
MAIL_PROVIDER = os.getenv('MAIL_PROVIDER', 'console')
MAIL_FROM_EMAIL = os.getenv('MAIL_FROM_EMAIL', 'noreply@example.com')
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY', '')
REQUEST_NOTIFICATION_EMAIL = os.getenv('REQUEST_NOTIFICATION_EMAIL', '')
WASTE_REMOVAL_NOTIFICATION_EMAIL = os.getenv('WASTE_REMOVAL_NOTIFICATION_EMAIL', '') or REQUEST_NOTIFICATION_EMAIL
APP_BASE_URL = os.getenv('APP_BASE_URL', '')

# API auth
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
JWT_EXP_HOURS = _int_env('JWT_EXP_HOURS', 24)
