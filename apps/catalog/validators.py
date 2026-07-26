from pathlib import Path

from PIL import Image, UnidentifiedImageError
from django.core.exceptions import ValidationError


MAX_CATALOG_IMAGE_BYTES = 5 * 1024 * 1024
MAX_CATALOG_IMAGE_DIMENSION = 8000
ALLOWED_CATALOG_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
ALLOWED_CATALOG_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def validate_catalog_image(upload):
    """Validate actual image content before an admin upload reaches storage."""
    if not hasattr(upload, 'read'):
        return
    size = getattr(upload, 'size', 0) or 0
    if size > MAX_CATALOG_IMAGE_BYTES:
        raise ValidationError('Catalog images must be 5 MB or smaller.')
    extension = Path(getattr(upload, 'name', '')).suffix.lower()
    if extension not in ALLOWED_CATALOG_IMAGE_EXTENSIONS:
        raise ValidationError('Use a JPEG, PNG or WebP catalog image.')
    try:
        upload.seek(0)
        with Image.open(upload) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
        if image_format not in ALLOWED_CATALOG_IMAGE_FORMATS:
            raise ValidationError('The uploaded file is not an approved image format.')
        if width > MAX_CATALOG_IMAGE_DIMENSION or height > MAX_CATALOG_IMAGE_DIMENSION:
            raise ValidationError('Catalog images may not exceed 8000 pixels on either side.')
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValidationError('The uploaded file is not a valid image.') from exc
    finally:
        upload.seek(0)
