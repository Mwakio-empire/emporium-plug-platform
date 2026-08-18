from django.test import SimpleTestCase

from catalog.stock_presentation import (
    IN_STOCK,
    LOW_STOCK,
    OUT_OF_STOCK,
    public_stock_label,
    public_stock_status,
)


class PublicStockPresentationTests(SimpleTestCase):
    def test_public_status_reveals_state_not_quantity(self):
        self.assertEqual(public_stock_status(0, 3), OUT_OF_STOCK)
        self.assertEqual(public_stock_status(3, 3), LOW_STOCK)
        self.assertEqual(public_stock_status(4, 3), IN_STOCK)

    def test_public_labels_are_customer_facing(self):
        self.assertEqual(public_stock_label(OUT_OF_STOCK), 'Out of stock')
        self.assertEqual(public_stock_label(LOW_STOCK), 'Low stock - order soon')
        self.assertEqual(public_stock_label(IN_STOCK), 'In stock')
