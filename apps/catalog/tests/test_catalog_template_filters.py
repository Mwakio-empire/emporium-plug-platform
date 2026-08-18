from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.catalog.templatetags.catalog_extras import storefront_image_url


class StorefrontImageUrlTests(SimpleTestCase):
    def test_adds_bounded_cloudinary_delivery_transform(self):
        image = SimpleNamespace(
            url='https://res.cloudinary.com/demo/image/upload/v1/catalog/kettle.png'
        )

        result = storefront_image_url(image, 640)

        self.assertEqual(
            result,
            'https://res.cloudinary.com/demo/image/upload/'
            'f_auto,q_auto,c_fill,g_auto,w_640,h_640/v1/catalog/kettle.png',
        )

    def test_leaves_non_cloudinary_storage_url_unchanged(self):
        image = SimpleNamespace(url='/media/catalog/kettle.png')

        self.assertEqual(storefront_image_url(image, 640), image.url)

    def test_upgrades_cloudinary_delivery_to_https(self):
        image = SimpleNamespace(
            url='http://res.cloudinary.com/demo/image/upload/catalog/kettle.png'
        )

        self.assertTrue(storefront_image_url(image, 384).startswith('https://'))

    def test_returns_empty_string_for_missing_image(self):
        self.assertEqual(storefront_image_url(None), '')
