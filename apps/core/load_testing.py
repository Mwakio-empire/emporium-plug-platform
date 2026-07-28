import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


LOCAL_HOSTS = {'127.0.0.1', 'localhost', '::1'}


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


HTTP_OPENER = build_opener(_NoRedirectHandler)


@dataclass(frozen=True)
class RequestResult:
    latency_ms: float
    status_code: int | None
    succeeded: bool


def validate_target(base_url: str, *, allow_remote: bool, expected_host: str | None) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('Base URL must be an absolute HTTP or HTTPS URL.')
    if parsed.username or parsed.password:
        raise ValueError('Credentials must not be embedded in the load-test URL.')
    host = parsed.hostname.lower()
    if host not in LOCAL_HOSTS:
        if not allow_remote:
            raise ValueError('Remote load tests require explicit authorization flags.')
        if not expected_host or expected_host.lower() != host:
            raise ValueError('The expected remote host must exactly match the target host.')
    return base_url.rstrip('/') + '/'


def _request_once(url: str, timeout_seconds: float) -> RequestResult:
    started = time.perf_counter()
    request = Request(url, headers={'User-Agent': 'EmporiumPlug-AuthorizedCapacityProbe/1.0'})
    try:
        with HTTP_OPENER.open(request, timeout=timeout_seconds) as response:
            status_code = response.status
            response.read(1)
        succeeded = 200 <= status_code < 400
    except HTTPError as exc:
        status_code = exc.code
        succeeded = False
    except (TimeoutError, URLError):
        status_code = None
        succeeded = False
    return RequestResult(
        latency_ms=(time.perf_counter() - started) * 1000,
        status_code=status_code,
        succeeded=succeeded,
    )


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil((percentile / 100) * len(ordered)) - 1)
    return ordered[index]


def run_capacity_probe(
    *,
    base_url: str,
    paths: list[str],
    total_requests: int,
    concurrency: int,
    timeout_seconds: float,
    allow_remote: bool = False,
    expected_host: str | None = None,
) -> dict:
    normalized_base = validate_target(
        base_url,
        allow_remote=allow_remote,
        expected_host=expected_host,
    )
    if not paths or any(not path.startswith('/') or path.startswith('//') for path in paths):
        raise ValueError('At least one root-relative path is required.')
    if not 1 <= total_requests <= 10_000:
        raise ValueError('Total requests must be between 1 and 10,000.')
    if not 1 <= concurrency <= min(100, total_requests):
        raise ValueError('Concurrency must be between 1 and 100 and not exceed requests.')
    if not 0.1 <= timeout_seconds <= 60:
        raise ValueError('Request timeout must be between 0.1 and 60 seconds.')

    urls = [urljoin(normalized_base, paths[index % len(paths)]) for index in range(total_requests)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(lambda url: _request_once(url, timeout_seconds), urls))
    duration_seconds = max(time.perf_counter() - started, 0.000001)
    latencies = [result.latency_ms for result in results]
    successes = sum(result.succeeded for result in results)
    failures = total_requests - successes
    status_counts = {}
    for result in results:
        key = str(result.status_code) if result.status_code is not None else 'network_error'
        status_counts[key] = status_counts.get(key, 0) + 1
    return {
        'target_host': urlparse(normalized_base).hostname,
        'requests': total_requests,
        'concurrency': concurrency,
        'successes': successes,
        'failures': failures,
        'failure_rate': failures / total_requests,
        'duration_seconds': round(duration_seconds, 3),
        'requests_per_second': round(total_requests / duration_seconds, 2),
        'latency_ms': {
            'p50': round(_percentile(latencies, 50), 2),
            'p95': round(_percentile(latencies, 95), 2),
            'p99': round(_percentile(latencies, 99), 2),
        },
        'status_counts': status_counts,
    }
