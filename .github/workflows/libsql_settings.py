import os
import uuid

DATABASES = {
    "default": {
        "ENGINE": "django_libsql",
        "NAME": "/tmp/default.db",
        "SYNC_URL": os.environ["LIBSQL_SYNC_URL"],
        "AUTH_TOKEN": os.environ["LIBSQL_AUTH_TOKEN"],
        "TEST": {
            # libsql does not like django's default in-memory database name
            # file:memorydb_default?mode=memory&cache=shared
            "NAME": "/tmp/testdefault.db",
            "SYNC_URL": "test" + os.environ["LIBSQL_SYNC_URL"]
        },
    },
    "other": {
        "ENGINE": "django_libsql",
        "NAME": "/tmp/other.db",
        "SYNC_URL": os.environ["OTHER_LIBSQL_SYNC_URL"],
        "AUTH_TOKEN": os.environ["LIBSQL_AUTH_TOKEN"],
        "TEST": {
            # libsql does not like django's default in-memory database name
            # file:memorydb_default?mode=memory&cache=shared
            "NAME": "/tmp/testother.db",
            "SYNC_URL": "test" + os.environ["OTHER_LIBSQL_SYNC_URL"]
        },
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
PASSWORD_HASHERS = ("django.contrib.auth.hashers.MD5PasswordHasher",)
SECRET_KEY = "django_tests_secret_key"
USE_TZ = False
