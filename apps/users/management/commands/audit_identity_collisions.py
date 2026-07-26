from collections import defaultdict

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from users.identifiers import normalize_phone_number
from users.models import User


class Command(BaseCommand):
    help = 'Fail if multiple users resolve to the same normalized phone or email identity.'

    def handle(self, *args, **options):
        phones = defaultdict(list)
        emails = defaultdict(list)
        for user in User.objects.only('id', 'phone_number', 'email', 'role', 'is_active'):
            try:
                phones[normalize_phone_number(user.phone_number)].append(user)
            except ValidationError:
                raise CommandError(f'User id={user.pk} has an invalid phone format.')
            if user.email:
                emails[user.email.strip().lower()].append(user)

        collisions = [group for group in phones.values() if len(group) > 1]
        collisions.extend(group for group in emails.values() if len(group) > 1)
        if collisions:
            summaries = []
            for group in collisions:
                summaries.append(', '.join(
                    f'user_id={user.pk} role={user.role} active={user.is_active}'
                    for user in group
                ))
            raise CommandError(
                'Identity collisions require manual resolution: ' + ' | '.join(summaries)
            )
        self.stdout.write(self.style.SUCCESS('No normalized phone or email collisions found.'))
