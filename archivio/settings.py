"""Archivio chat — impostazioni.

Gira solo in locale (127.0.0.1). I dati stanno in data/archivio.sqlite3.
La cartella dell'export ChatGPT si imposta con la variabile EXPORT_CHATGPT
oppure nel file data/config.json ({"export_chatgpt": "/percorso/export"}).
"""

import json
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# chiave segreta generata al primo avvio e conservata in locale
_key_file = DATA_DIR / "secret_key.txt"
if not _key_file.exists():
    _key_file.write_text(secrets.token_urlsafe(50), encoding="utf-8")
SECRET_KEY = _key_file.read_text(encoding="utf-8").strip()

DEBUG = os.environ.get("ARCHIVIO_DEBUG") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

_config_file = DATA_DIR / "config.json"
_config = {}
if _config_file.exists():
    _config = json.loads(_config_file.read_text(encoding="utf-8"))

EXPORT_CHATGPT = Path(
    os.environ.get("EXPORT_CHATGPT")
    or _config.get("export_chatgpt")
    or Path.home() / "Dev" / "scrapemychats" / "export"
).expanduser()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "chats",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "archivio.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "archivio.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "archivio.sqlite3",
        "OPTIONS": {"timeout": 30},
    }
}

LANGUAGE_CODE = "it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20000  # spostamenti multipli di molte chat
