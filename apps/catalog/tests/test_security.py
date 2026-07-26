from io import BytesIO

from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from catalog.validators import validate_catalog_image


class CatalogImageValidationTests(SimpleTestCase):
    def test_rejects_non_image_content_with_image_extension(self):
        upload = SimpleUploadedFile(
            'not-really-an-image.jpg', b'<script>alert(1)</script>',
            content_type='image/jpeg',
        )
        with self.assertRaises(ValidationError):
            validate_catalog_image(upload)

    def test_rejects_unsupported_extension(self):
        upload = SimpleUploadedFile('image.svg', b'<svg></svg>', content_type='image/svg+xml')
        with self.assertRaises(ValidationError):
            validate_catalog_image(upload)

    def test_accepts_verified_png_and_rewinds_stream(self):
        content = BytesIO()
        Image.new('RGB', (20, 20), color='blue').save(content, format='PNG')
        upload = SimpleUploadedFile('product.png', content.getvalue(), content_type='image/png')
        validate_catalog_image(upload)
        self.assertEqual(upload.tell(), 0)
