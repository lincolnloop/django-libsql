import logging

import libsql_experimental as libsql_client

from django.db.backends.sqlite3._functions import register as register_functions
from django.db.backends.sqlite3.base import DatabaseWrapper as SQLite3DatabaseWrapper
from django.utils.asyncio import async_unsafe

log = logging.getLogger(__name__)


class DatabaseWrapper(SQLite3DatabaseWrapper):
    vendor = "libsql"
    display_name = "libSQL"

    def connection_params(self) -> dict:
        """Return a dict of connection parameters"""

        return {
            "database": self.settings_dict["NAME"],
            "sync_url": self.settings_dict["SYNC_URL"],
            "auth_token": self.settings_dict["AUTH_TOKEN"],
        }

    @async_unsafe
    def get_new_connection(self, conn_params):
        """Connect to the database"""
        conn = libsql_client.connect(**self.connection_params())
        # TODO: AttributeError: 'builtins.Connection' object has no attribute 'create_function'
        # register_functions(conn)

        conn.execute("PRAGMA foreign_keys = ON")
        # The macOS bundled SQLite defaults legacy_alter_table ON, which
        # prevents atomic table renames.
        # conn.execute("PRAGMA legacy_alter_table = OFF")
        return conn

    def _set_autocommit(self, autocommit):
        """
          File "/Users/pete/projects/lincolnloop/django-libsql/django/django/db/backends/sqlite3/base.py", line 219, in _set_autocommit
            self.connection.isolation_level = level
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        AttributeError: 'builtins.Connection' object has no attribute 'isolation_level'
        https://github.com/libsql/libsql-experimental-python/issues/1
        """
        pass

    def create_cursor(self, name=None):
        """
          File "/Users/pete/projects/lincolnloop/django-libsql/django/django/db/backends/sqlite3/base.py", line 190, in create_cursor
            return self.connection.cursor(factory=SQLiteCursorWrapper)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        TypeError: Connection.cursor() takes no keyword arguments
        """
        return self.connection.cursor()

    def disable_constraint_checking(self):
        """
          File "/Users/pete/projects/lincolnloop/django-libsql/django/django/db/backends/sqlite3/base.py", line 227, in disable_constraint_checking
            enabled = cursor.execute("PRAGMA foreign_keys").fetchone()[0]
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        ValueError: invalid column type
        """
        with self.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF")
        return True
