from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import Stock
from orders.models import Order, OrderItem, OrderStatusHistory
from orders.transitions import OrderTransitionService
from users.models import User


class DomainIntegrityTestDataMixin:
    def setUp(self):
        self.branch = Branch.objects.create(name='Integrity Branch', location='Nakuru')
        self.actor = User.objects.create_user(
            username='integrity_actor',
            phone_number='+254700990001',
            email='integrity@example.test',
            password='StrongPass123!',
            role=User.Role.CUSTOMER,
        )
        self.category = Category.objects.create(name='Integrity', slug='integrity')
        self.product = Product.objects.create(
            name='Integrity Product', slug='integrity-product',
            category=self.category, price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, attribute_name='Size', attribute_value='One',
        )

    def make_order(self, order_type=Order.OrderType.ONLINE_DELIVERY, status=Order.Status.PROCESSING):
        return Order.objects.create(
            branch=self.branch,
            order_type=order_type,
            customer=self.actor,
            customer_phone=self.actor.phone_number,
            payment_method=Order.PaymentMethod.COD,
            processed_by=self.actor,
            status=status,
            subtotal=Decimal('100.00'),
            total_payable=Decimal('100.00'),
        )


class OrderTransitionPolicyTests(DomainIntegrityTestDataMixin, TestCase):
    def test_valid_transition_is_persisted_and_audited_once(self):
        order = self.make_order(status=Order.Status.PROCESSING)

        packing = OrderTransitionService.transition(
            order=order,
            to_status=Order.Status.PACKING,
            changed_by=self.actor,
            note='Packing started.',
        )
        transitioned = OrderTransitionService.transition(
            order=packing,
            to_status=Order.Status.PACKED,
            changed_by=self.actor,
            note='Packing checklist complete.',
        )

        self.assertEqual(transitioned.status, Order.Status.PACKED)
        self.assertEqual(
            OrderStatusHistory.objects.filter(
                order=order,
                old_status=Order.Status.PACKING,
                new_status=Order.Status.PACKED,
            ).count(),
            1,
        )

    def test_delivery_order_cannot_enter_pickup_state(self):
        order = self.make_order(order_type=Order.OrderType.ONLINE_DELIVERY)
        with self.assertRaises(ValidationError):
            OrderTransitionService.transition(
                order=order,
                to_status=Order.Status.READY_FOR_PICKUP,
                changed_by=self.actor,
            )

    def test_pickup_order_cannot_enter_delivery_state(self):
        order = self.make_order(order_type=Order.OrderType.ONLINE_PICKUP)
        with self.assertRaises(ValidationError):
            OrderTransitionService.transition(
                order=order,
                to_status=Order.Status.OUT_FOR_DELIVERY,
                changed_by=self.actor,
            )

    def test_terminal_order_cannot_be_reopened(self):
        order = self.make_order(status=Order.Status.DELIVERED)
        with self.assertRaises(ValidationError):
            OrderTransitionService.transition(
                order=order,
                to_status=Order.Status.PROCESSING,
                changed_by=self.actor,
            )


class DatabaseConstraintTests(DomainIntegrityTestDataMixin, TestCase):
    def test_database_rejects_discount_above_subtotal(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.create(
                branch=self.branch,
                order_type=Order.OrderType.WALK_IN,
                customer_phone=self.actor.phone_number,
                payment_method=Order.PaymentMethod.CASH,
                processed_by=self.actor,
                subtotal=Decimal('10.00'),
                discount_amount=Decimal('11.00'),
                total_payable=Decimal('0.00'),
            )

    def test_database_rejects_order_item_with_both_product_and_variant(self):
        order = self.make_order()
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderItem.objects.create(
                order=order,
                product=self.product,
                variant=self.variant,
                quantity=1,
                unit_price=Decimal('100.00'),
                total_price=Decimal('100.00'),
            )

    def test_database_rejects_stock_without_catalog_item(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Stock.objects.create(branch=self.branch, quantity=1)
