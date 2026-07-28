import json

from django.test import SimpleTestCase

from catalog.templatetags.catalog_extras import json_ld


class JsonLdEscapingTests(SimpleTestCase):
    def test_script_termination_and_html_characters_are_unicode_escaped(self):
        payload = {
            'name': '</script><script>alert("xss")</script>&',
            'separator': '\u2028\u2029',
        }

        encoded = str(json_ld(payload))

        self.assertNotIn('</script>', encoded.lower())
        self.assertNotIn('<', encoded)
        self.assertNotIn('>', encoded)
        self.assertNotIn('&', encoded)
        self.assertIn('\\u003c/script\\u003e', encoded.lower())
        self.assertEqual(json.loads(encoded), payload)
