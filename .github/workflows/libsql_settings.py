import os
import uuid

DATABASES = {
    "default": {
        "ENGINE": "django_libsql",
        "NAME": "/tmp/test.db",
        "SYNC_URL": os.environ["LIBSQL_SYNC_URL"],
        "AUTH_TOKEN": os.environ["LIBSQL_AUTH_TOKEN"],
        "TEST": {"SYNC_URL": "test" + os.environ["LIBSQL_SYNC_URL"]},
    },
    "other": {
        "ENGINE": "django_libsql",
        "NAME": "/tmp/test.db",
        "SYNC_URL": os.environ["OTHER_LIBSQL_SYNC_URL"],
        "AUTH_TOKEN": os.environ["LIBSQL_AUTH_TOKEN"],
        "TEST": {"SYNC_URL": "test" + os.environ["OTHER_LIBSQL_SYNC_URL"]},
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
PASSWORD_HASHERS = ("django.contrib.auth.hashers.MD5PasswordHasher",)
SECRET_KEY = "django_tests_secret_key"
USE_TZ = False
