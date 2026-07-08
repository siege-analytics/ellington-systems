import os

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "ellington_web.ellington_web.settings"
)
os.environ.setdefault("ELLINGTON_DB_PATH", ":memory:")
