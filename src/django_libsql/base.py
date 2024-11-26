import logging
from collections.abc import Mapping
from itertools import chain, tee
from django.utils.regex_helper import _lazy_re_compile
import libsql_experimental as libsql_client

from django.db.backends.sqlite3._functions import register as register_functions
from django.db.backends.sqlite3.base import DatabaseWrapper as SQLite3DatabaseWrapper
from django.utils.asyncio import async_unsafe

from .creation import DatabaseCreation

log = logging.getLogger(__name__)


SQL_PARAM_PLACEHOLDER_REGEX = _lazy_re_compile(r"(?<!%)%s")


class CustomCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, query, params=None):
        """
        Execute a single query with optional parameters.
        Handles the conversion of query placeholders based on parameter style.
        """
        if params is None:
            return self.cursor.execute(query)

        param_names = list(params) if isinstance(params, Mapping) else None
        converted_query = self.convert_query(query, param_names=param_names)
        return self.cursor.execute(converted_query, params)

    def executemany(self, query, param_list):
        """
        Execute the same query with multiple parameter sets.
        Handles the conversion of query placeholders for batch execution.
        """
        peekable, param_list = tee(iter(param_list))
        param_names = list(next(peekable, {})) if isinstance(next(peekable, {}), Mapping) else None
        converted_query = self.convert_query(query, param_names=param_names)
        return self.cursor.executemany(converted_query, param_list)

    def convert_query(self, query, param_names=None):
        """
        Convert query placeholders to the desired format.
        - If `param_names` is None, replace '%s' with '?' (for positional style).
        - If `param_names` is provided, convert to named style (e.g., ':param_name').
        """
        import re
        query = re.sub(r'\bREM\b', '--', query)  # Handle REM keyword conflicts

        if param_names is None:
            # Replace unescaped `%s` with `?` for positional parameter style.
            return SQL_PARAM_PLACEHOLDER_REGEX.sub("?", query).replace("%%", "%")
        else:
            # Convert to named style (e.g., ":param_name").
            return query % {name: f":{name}" for name in param_names}

    def close(self):
        """
        Close the cursor to release database resources.
        """
        if hasattr(self.cursor, "close"):
            return self.cursor.close()
        raise NotImplementedError("Underlying cursor does not support closing.")

    def __getattr__(self, attr):
        """
        Delegate attribute access and method calls to the wrapped cursor.
        """
        return getattr(self.cursor, attr)


class DatabaseWrapper(SQLite3DatabaseWrapper):
    vendor = "libsql"
    display_name = "libSQL"
    creation_class = DatabaseCreation

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
        # TODO: https://github.com/libsql/libsql-experimental-python/issues/7
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
        try:
            if autocommit:
                if self.connection.in_transaction:  # Check if a transaction is active
                    try:
                        self.connection.commit()  # Commit the transaction to enable autocommit
                        log.info("Committed active transaction to enable autocommit.")
                    except Exception as e:
                        log.warning(f"Failed to commit transaction during autocommit enable: {e}")
            else:
                if not self.connection.in_transaction:  # Start a transaction if none is active
                    try:
                        self.connection.execute("BEGIN")
                        log.info("Started transaction for autocommit disable.")
                    except Exception as e:
                        log.warning(f"Failed to start transaction: {e}")
        except Exception as e:
            log.error(f"Unexpected error in _set_autocommit: {e}")
            raise

    def _start_transaction_under_autocommit(self):
        """
        Start a transaction explicitly in autocommit mode.
        """
        with self.wrap_database_errors:
            if self.connection.in_transaction:  # Check if already in a transaction
                self.connection.execute("COMMIT")
            self.connection.execute("BEGIN")

    def create_cursor(self, name=None):
        """
          File "/Users/pete/projects/lincolnloop/django-libsql/django/django/db/backends/sqlite3/base.py", line 190, in create_cursor
            return self.connection.cursor(factory=SQLiteCursorWrapper)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        TypeError: Connection.cursor() takes no keyword arguments
        """
        return CustomCursorWrapper(self.connection.cursor())

    def disable_constraint_checking(self):
        """
          File "/Users/pete/projects/lincolnloop/django-libsql/django/django/db/backends/sqlite3/base.py", line 227, in disable_constraint_checking
            enabled = cursor.execute("PRAGMA foreign_keys").fetchone()[0]
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        ValueError: invalid column type
        https://github.com/libsql/sqld/issues/287
        """
        with self.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF")
        return True
