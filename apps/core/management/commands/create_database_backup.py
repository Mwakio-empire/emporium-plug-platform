from django.core.management.base import BaseCommand

from core.backup_services import DatabaseBackupManager


class Command(BaseCommand):
    help = 'Create an encrypted off-site PostgreSQL custom-format backup.'

    def handle(self, *args, **options):
        result = DatabaseBackupManager.execute_backup()
        self.stdout.write(self.style.SUCCESS(
            f"Backup uploaded: {result['object_key']} ({result['bytes']} bytes)"
        ))
