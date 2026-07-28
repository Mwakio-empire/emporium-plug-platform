import json

from django.core.management.base import BaseCommand, CommandError

from core.media_verification import MediaVerificationError, verify_cloudinary_round_trip


class Command(BaseCommand):
    help = 'Upload, fetch and delete one synthetic image in the configured Cloudinary account.'

    def add_arguments(self, parser):
        parser.add_argument('--confirm-remote-write', action='store_true')
        parser.add_argument('--timeout-seconds', type=float, default=20)

    def handle(self, *args, **options):
        if not options['confirm_remote_write']:
            raise CommandError(
                'Refusing remote write without --confirm-remote-write. '
                'The command creates and then deletes one synthetic Cloudinary image.'
            )
        try:
            summary = verify_cloudinary_round_trip(
                timeout_seconds=options['timeout_seconds'],
            )
        except MediaVerificationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
        self.stdout.write(self.style.SUCCESS('Cloudinary write/delivery/delete verification passed.'))
