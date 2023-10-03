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
        conn.execute("PRAGMA legacy_alter_table = OFF")
        return conn
