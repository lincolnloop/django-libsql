import http.client
import multiprocessing
import os
import shutil
import sqlite3
import sys
from functools import cached_property
from urllib.parse import urlparse

from django.db import NotSupportedError
from django.db.backends.sqlite3.creation import DatabaseCreation as SQLite3DatabaseCreation
from django.conf import settings

class DatabaseCreation(SQLite3DatabaseCreation):

    def _libsql_admin_conn(self) -> http.client.HTTPConnection:
        parsed = urlparse(self.connection.settings_dict["ADMIN_URL"])
        conn_kwargs = {"host": f"{parsed.hostname}:{parsed.port}", "timeout": 5}
        if parsed.scheme == "https":
            return http.client.HTTPSConnection(**conn_kwargs)
        elif parsed.scheme == "http":
            return http.client.HTTPConnection(**conn_kwargs)
        else:
            raise Exception(f"Unsupported scheme: {parsed.scheme}")

    @cached_property
    def libsql_namespace(self) -> str:
        parsed = urlparse(self.connection.settings_dict["SYNC_URL"])
        return parsed.hostname.split(".")[0]

    @cached_property
    def libsql_test_namespace(self) -> str:
        parsed = urlparse(self.connection.settings_dict["TEST"]["SYNC_URL"])
        return parsed.hostname.split(".")[0]

    def _libsql_admin_request(self, method: str, path: str, body: str = None):
        conn = self._libsql_admin_conn()
        conn.request(
            method,
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                # "Authorization": f"Bearer {self.connection.settings_dict['AUTH_TOKEN']}"
            },
        )
        resp = conn.getresponse()
        conn.close()
        return resp

    def create_libsql_database(self, host: str) -> None:
        parsed = urlparse(host)
        database_name = parsed.hostname.split(".")[0]
        if self.libsql_database_exists(database_name):
            return
        response = self._libsql_admin_request("POST", f"/v1/namespaces/{database_name}/create", body="{}")
        if response.status != 200:
            raise Exception(f"Failed to create database: {response.status} {response.reason}")

    def destroy_libsql_database(self, host: str) -> None:
        parsed = urlparse(host)
        database_name = parsed.hostname.split(".")[0]
        breakpoint()
        if not self.libsql_database_exists(database_name):
            return
        response = self._libsql_admin_request("DELETE", f"/v1/namespaces/{database_name}")
        if response.status != 200:
            raise Exception(f"Failed to destroy database: {response.status} {response.reason}")

    def libsql_database_exists(self, database_name: str) -> bool:
        response = self._libsql_admin_request("GET", f"/v1/namespaces/{database_name}/stats")
        if response.status == 400:
            return False
        if response.status == 200:
            return True
        raise Exception(f"Failed to check if database exists: {response.status} {response.reason}")

    @staticmethod
    def is_in_memory_db(database_name):
        # return not isinstance(database_name, Path) and (
        #     database_name == ":memory:" or "mode=memory" in database_name
        # )
        return False

    def _get_test_db_name(self):
        test_database_name = self.connection.settings_dict["TEST"]["NAME"]
        return test_database_name

    def _get_test_db_sync_url(self):
        test_database_sync_url = self.connection.settings_dict["TEST"]["SYNC_URL"]
        return test_database_sync_url

    def create_test_db(
        self, verbosity=1, autoclobber=False, serialize=True, keepdb=False
    ):
        """
        Create a test database, prompting the user for confirmation if the
        database already exists. Return the name of the test database created.
        """
        # Don't import django.core.management if it isn't needed.
        from django.core.management import call_command

        test_database_name = self._get_test_db_name()
        test_database_sync_url = self._get_test_db_sync_url()

        if verbosity >= 1:
            action = "Creating"
            if keepdb:
                action = "Using existing"

            self.log(
                "%s test database for alias %s..."
                % (
                    action,
                    self._get_database_display_str(verbosity, f"{test_database_sync_url} {test_database_name}"),
                )
            )

        # We could skip this call if keepdb is True, but we instead
        # give it the keepdb param. This is to handle the case
        # where the test DB doesn't exist, in which case we need to
        # create it, then just not destroy it. If we instead skip
        # this, we will get an exception.
        self._create_test_db(verbosity, autoclobber, keepdb)

        self.connection.close()
        settings.DATABASES[self.connection.alias]["NAME"] = test_database_name
        settings.DATABASES[self.connection.alias]["SYNC_URL"] = test_database_sync_url
        self.connection.settings_dict["NAME"] = test_database_name
        self.connection.settings_dict["SYNC_URL"] = test_database_sync_url

        try:
            if self.connection.settings_dict["TEST"]["MIGRATE"] is False:
                # Disable migrations for all apps.
                old_migration_modules = settings.MIGRATION_MODULES
                settings.MIGRATION_MODULES = {
                    app.label: None for app in apps.get_app_configs()
                }
            # We report migrate messages at one level lower than that
            # requested. This ensures we don't get flooded with messages during
            # testing (unless you really ask to be flooded).
            call_command(
                "migrate",
                verbosity=max(verbosity - 1, 0),
                interactive=False,
                database=self.connection.alias,
                run_syncdb=True,
            )
        finally:
            if self.connection.settings_dict["TEST"]["MIGRATE"] is False:
                settings.MIGRATION_MODULES = old_migration_modules

        # We then serialize the current state of the database into a string
        # and store it on the connection. This slightly horrific process is so people
        # who are testing on databases without transactions or who are using
        # a TransactionTestCase still get a clean database on every test run.
        if serialize:
            self.connection._test_serialized_contents = self.serialize_db_to_string()

        call_command("createcachetable", database=self.connection.alias)

        # Ensure a connection for the side effect of initializing the test database.
        self.connection.ensure_connection()

        if os.environ.get("RUNNING_DJANGOS_TEST_SUITE") == "true":
            self.mark_expected_failures_and_skips()

        return test_database_name

    def _create_test_db(self, verbosity, autoclobber, keepdb=False):
        test_database_name = self._get_test_db_name()
        test_database_sync_url = self._get_test_db_sync_url()

        if keepdb:
            self.create_libsql_database(self.libsql_test_namespace)
            return test_database_name
        if not self.is_in_memory_db(test_database_name):
            # Erase the old test database
            if verbosity >= 1:
                self.log(
                    "Destroying old test database for alias %s..."
                    % (self._get_database_display_str(verbosity, f"{test_database_sync_url} {test_database_name}"),)
                )
            if os.access(test_database_name, os.F_OK):
                if not autoclobber:
                    confirm = input(
                        "Type 'yes' if you would like to try deleting the test "
                        "database '%s', or 'no' to cancel: " % test_database_name
                    )
                if autoclobber or confirm == "yes":

                    self.destroy_libsql_database(test_database_sync_url)
                    try:
                        os.remove(test_database_name)
                    except Exception as e:
                        self.log("Got an error deleting the old test database: %s" % e)
                        sys.exit(2)
                else:
                    self.log("Tests cancelled.")
                    sys.exit(1)

        self.create_libsql_database(test_database_sync_url)
        return test_database_name

    def get_test_db_clone_settings(self, suffix):
        orig_settings_dict = self.connection.settings_dict
        source_database_name = orig_settings_dict["NAME"] or ":memory:"
        source_database_sync_url = orig_settings_dict["SYNC_URL"]

        if not self.is_in_memory_db(source_database_name):
            root, ext = os.path.splitext(source_database_name)
            parsed = urlparse(source_database_sync_url)
            return {
                **orig_settings_dict,
                "NAME": f"{root}_{suffix}{ext}",
                "SYNC_URL": f"{parsed.scheme}://{suffix}{parsed.hostname}:{parsed.port}",
            }

        start_method = multiprocessing.get_start_method()
        if start_method == "fork":
            return orig_settings_dict
        raise NotSupportedError(
            f"Cloning with start method {start_method!r} is not supported."
        )

    def _clone_test_db(self, suffix, verbosity, keepdb=False):
        """
        Internal implementation - duplicate the test db tables.
        """
        raise NotImplementedError(
            "The database backend doesn't support cloning databases. "
            "Disable the option to run tests in parallel processes."
        )

    def _destroy_test_db(self, test_database_name, verbosity):
        if test_database_name and not self.is_in_memory_db(test_database_name):
            # Remove the SQLite database file
            os.remove(test_database_name)
            self.destroy_libsql_database(self.libsql_test_namespace)

    def test_db_signature(self):
        """
        Return a tuple that uniquely identifies a test database.

        This takes into account the special cases of ":memory:" and "" for
        SQLite since the databases will be distinct despite having the same
        TEST NAME. See https://www.sqlite.org/inmemorydb.html
        """
        test_database_name = self._get_test_db_name()
        test_database_sync_url = self._get_test_db_sync_url()
        sig = [self.connection.settings_dict["SYNC_URL"], self.connection.settings_dict["NAME"]]
        if self.is_in_memory_db(test_database_name):
            sig.append(self.connection.alias)
        else:
            sig.extend([test_database_sync_url, test_database_name])
        return tuple(sig)

    def setup_worker_connection(self, _worker_id):
        settings_dict = self.get_test_db_clone_settings(_worker_id)
        # connection.settings_dict must be updated in place for changes to be
        # reflected in django.db.connections. Otherwise new threads would
        # connect to the default database instead of the appropriate clone.
        start_method = multiprocessing.get_start_method()
        self.connection.settings_dict.update(settings_dict)
        self.connection.close()
        # if start_method == "fork":
        #     # Update settings_dict in place.
        #     self.connection.settings_dict.update(settings_dict)
        #     self.connection.close()
        # elif start_method == "spawn":
        #     alias = self.connection.alias
        #     connection_str = (
        #         f"file:memorydb_{alias}_{_worker_id}?mode=memory&cache=shared"
        #     )
        #     source_db = self.connection.Database.connect(
        #         f"file:{alias}_{_worker_id}.sqlite3?mode=ro", uri=True
        #     )
        #     target_db = sqlite3.connect(connection_str, uri=True)
        #     source_db.backup(target_db)
        #     source_db.close()
        #     # Update settings_dict in place.
        #     self.connection.settings_dict.update(settings_dict)
        #     self.connection.settings_dict["NAME"] = connection_str
        #     # Re-open connection to in-memory database before closing copy
        #     # connection.
        #     self.connection.connect()
        #     target_db.close()
        #     if os.environ.get("RUNNING_DJANGOS_TEST_SUITE") == "true":
        #         self.mark_expected_failures_and_skips()