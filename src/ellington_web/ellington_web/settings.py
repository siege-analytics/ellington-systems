"""Django settings for the Ellington web layer.

This is the presentation + confirmation-workflow layer that sits on top of
the pure engine library in `src/ellington_systems/`. The engine remains
importable without Django; this package is only pulled in when
`ellington-systems[web]` is installed.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "ELLINGTON_SECRET_KEY",
    "dev-only-not-for-production-set-ELLINGTON_SECRET_KEY",
)

DEBUG = os.environ.get("ELLINGTON_DEBUG", "1") == "1"

ALLOWED_HOSTS = os.environ.get("ELLINGTON_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ellington_web.roster",
    "ellington_web.confirmations",
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

ROOT_URLCONF = "ellington_web.ellington_web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "ellington_web" / "templates"],
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

WSGI_APPLICATION = "ellington_web.ellington_web.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get(
            "ELLINGTON_DB_PATH",
            str(BASE_DIR.parent.parent / "ellington.sqlite3"),
        ),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/admin/login/"

EMAIL_BACKEND = os.environ.get(
    "ELLINGTON_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get(
    "ELLINGTON_DEFAULT_FROM_EMAIL", "no-reply@ellington.local"
)
ELLINGTON_PUBLIC_BASE_URL = os.environ.get(
    "ELLINGTON_PUBLIC_BASE_URL", "http://localhost:8000"
)
