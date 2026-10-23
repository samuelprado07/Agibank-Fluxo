import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.6-flash')

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ValueError("Defina DJANGO_SECRET_KEY quando DJANGO_DEBUG=false.")
    SECRET_KEY = "local-demo-only-not-for-production"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

# The Vite development proxy preserves the browser's local origin.
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"] if DEBUG else []

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "core.apps.CoreConfig",
    "finance.apps.FinanceConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = []
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3",
    # Acquire SQLite's writer lock before reading data used by an atomic update.
    "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 5},
    "TEST": {"NAME": BASE_DIR / "test.sqlite3"},
}}
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
