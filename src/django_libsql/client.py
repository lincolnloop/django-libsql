import subprocess

from django.db.backends.base.client import BaseDatabaseClient


class DatabaseClient(BaseDatabaseClient):
    executable_name = "turso"

    def runshell(self):
        args = [self.executable_name, "db", "shell", self.connection.settings_dict["SYNC_URL"]]

        subprocess.check_call(args, env={"TURSO_API_TOKEN": self.connection.settings_dict["AUTH_TOKEN"]})
