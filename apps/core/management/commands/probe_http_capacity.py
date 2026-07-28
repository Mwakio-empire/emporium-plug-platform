import json

from django.core.management.base import BaseCommand, CommandError

from core.load_testing import run_capacity_probe


class Command(BaseCommand):
    help = 'Run a bounded, GET-only HTTP capacity probe against an authorized target.'

    def add_arguments(self, parser):
        parser.add_argument('--base-url', required=True)
        parser.add_argument('--path', action='append', dest='paths', required=True)
        parser.add_argument('--requests', type=int, default=100)
        parser.add_argument('--concurrency', type=int, default=10)
        parser.add_argument('--timeout-seconds', type=float, default=10)
        parser.add_argument('--max-failure-rate', type=float, default=0.01)
        parser.add_argument('--max-p95-ms', type=float, default=1500)
        parser.add_argument('--allow-remote', action='store_true')
        parser.add_argument('--expected-host')

    def handle(self, *args, **options):
        if not 0 <= options['max_failure_rate'] <= 1:
            raise CommandError('Maximum failure rate must be between 0 and 1.')
        if options['max_p95_ms'] <= 0:
            raise CommandError('Maximum p95 latency must be positive.')
        try:
            summary = run_capacity_probe(
                base_url=options['base_url'],
                paths=options['paths'],
                total_requests=options['requests'],
                concurrency=options['concurrency'],
                timeout_seconds=options['timeout_seconds'],
                allow_remote=options['allow_remote'],
                expected_host=options['expected_host'],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
        if summary['failure_rate'] > options['max_failure_rate']:
            raise CommandError('Capacity probe exceeded the maximum failure rate.')
        if summary['latency_ms']['p95'] > options['max_p95_ms']:
            raise CommandError('Capacity probe exceeded the maximum p95 latency.')
        self.stdout.write(self.style.SUCCESS('Capacity probe passed configured thresholds.'))
