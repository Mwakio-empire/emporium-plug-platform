import base64
import io
import uuid
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cloudinary import config as cloudinary_config
from cloudinary import uploader


SYNTHETIC_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)
MAX_VERIFICATION_RESPONSE_BYTES = 1024 * 1024


class MediaVerificationError(RuntimeError):
    pass


def verify_cloudinary_round_trip(*, timeout_seconds: float = 20) -> dict:
    """Upload, fetch and remove a synthetic image without exposing credentials."""
    active_config = cloudinary_config()
    if not all((active_config.cloud_name, active_config.api_key, active_config.api_secret)):
        raise MediaVerificationError('Cloudinary credentials are incomplete.')
    if not 1 <= timeout_seconds <= 60:
        raise MediaVerificationError('Timeout must be between 1 and 60 seconds.')

    public_id = f'emporium-plug/verification/{uuid.uuid4().hex}'
    verification_error = None
    summary = None
    uploaded = False
    try:
        response = uploader.upload(
            io.BytesIO(SYNTHETIC_PNG),
            public_id=public_id,
            resource_type='image',
            format='png',
            overwrite=False,
            tags=['emporium-plug-storage-verification'],
        )
        uploaded = True
        secure_url = response.get('secure_url', '')
        parsed_url = urlparse(secure_url)
        if parsed_url.scheme != 'https' or not parsed_url.hostname:
            raise MediaVerificationError('Cloudinary did not return a secure delivery URL.')

        request = Request(
            secure_url,
            headers={'User-Agent': 'EmporiumPlug-MediaVerification/1.0'},
        )
        with urlopen(request, timeout=timeout_seconds) as delivered:  # nosec B310
            status = delivered.status
            content_type = delivered.headers.get_content_type()
            body = delivered.read(MAX_VERIFICATION_RESPONSE_BYTES + 1)
        if status != 200 or not content_type.startswith('image/') or not body:
            raise MediaVerificationError('The uploaded verification image was not delivered correctly.')
        if len(body) > MAX_VERIFICATION_RESPONSE_BYTES:
            raise MediaVerificationError('The verification delivery response exceeded the safety limit.')
        summary = {
            'cloud_name': active_config.cloud_name,
            'delivery_host': parsed_url.hostname,
            'delivered_bytes': len(body),
        }
    except Exception as exc:  # cleanup must still run after provider/network failures
        verification_error = exc

    cleanup_error = None
    if uploaded:
        try:
            deletion = uploader.destroy(public_id, resource_type='image', invalidate=True)
            if deletion.get('result') not in {'ok', 'not found'}:
                raise MediaVerificationError('Cloudinary did not confirm verification-asset deletion.')
        except Exception as exc:
            cleanup_error = exc

    if cleanup_error:
        raise MediaVerificationError(
            'Cloudinary media verification could not remove its synthetic asset.'
        ) from cleanup_error
    if verification_error:
        if isinstance(verification_error, MediaVerificationError):
            raise verification_error
        raise MediaVerificationError('Cloudinary media verification failed.') from verification_error
    return summary
