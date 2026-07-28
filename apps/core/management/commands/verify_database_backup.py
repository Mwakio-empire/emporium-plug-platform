from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from core.backup_services import DatabaseBackupVerifier


class Command(BaseCommand):
    help = 'Download and verify an encrypted off-site PostgreSQL archive without restoring it.'

    def add_arguments(self, parser):
        parser.add_argument('--object-key', required=True)

    def handle(self, *args, **options):
        try:
            result = DatabaseBackupVerifier.verify_s3_archive(options['object_key'])
        except (ImproperlyConfigured, RuntimeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Backup verified: {result['object_key']} ({result['bytes']} bytes)"
        ))
