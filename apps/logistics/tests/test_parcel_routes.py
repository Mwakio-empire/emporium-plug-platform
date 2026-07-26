from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.orders.tests.test_online_checkout import OnlineCheckoutTestDataMixin
from logistics.fulfilment_services import FulfilmentService
from logistics.models import ParcelDispatch
from logistics.parcel_services import ParcelPricingService
from orders.models import Order
from orders.online_services import OnlineOrderService


class ParcelPricingTests(OnlineCheckoutTestDataMixin, TestCase):
    def test_started_excess_kilograms_are_charged(self):
        request = self._get_request_with_session()
        self.product_simple.weight = Decimal('3.10')
        self.product_simple.save(update_fields=['weight'])
        self._build_cart_with_product(request, quantity=2)

        destination, weight, fee = ParcelPricingService.quote(
            destination_id=self.parcel_destination.pk,
            cart=ParcelPricingServiceCart(request),
        )

        self.assertEqual(destination, self.parcel_destination)
        self.assertEqual(weight, Decimal('6.20'))
        self.assertEqual(fee, Decimal('210.00'))

    def test_missing_product_weight_blocks_parcel_quote(self):
        request = self._get_request_with_session()
        self.product_simple.weight = Decimal('0.00')
        self.product_simple.save(update_fields=['weight'])
        self._build_cart_with_product(request)

        with self.assertRaisesMessage(ValidationError, 'weight is configured'):
            ParcelPricingService.cart_weight(ParcelPricingServiceCart(request))


class ParcelFulfilmentTests(OnlineCheckoutTestDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        request = self._get_request_with_session()
        self._build_cart_with_product(request)
        self.order = OnlineOrderService.create_order(
            request=request,
            branch=self.branch,
            customer=self.customer,
            order_type=Order.OrderType.ONLINE_DELIVERY,
            customer_phone='+254700111111',
            customer_name='Parcel Recipient',
            parcel_destination=self.parcel_destination,
            payment_method=Order.PaymentMethod.MPESA_STK,
        )
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.PACKED)
        self.order.refresh_from_db()

    def test_dispatch_arrival_and_collection_are_audited(self):
        dispatch, order = FulfilmentService.dispatch_parcel(
            order_id=self.order.pk,
            actor=self.customer.__class__.get_system_account(),
            parcel_reference='KAK-1234',
            actual_transport_cost=Decimal('150.00'),
            vehicle_registration='KDA 123A',
        )
        self.assertEqual(order.status, Order.Status.DISPATCHED)
        self.assertEqual(dispatch.parcel_reference, 'KAK-1234')

        order = FulfilmentService.mark_parcel_arrived(
            order_id=order.pk, actor=self.customer.__class__.get_system_account(),
        )
        self.assertEqual(order.status, Order.Status.ARRIVED_AT_DESTINATION)

        order = FulfilmentService.mark_parcel_collected(
            order_id=order.pk,
            actor=self.customer.__class__.get_system_account(),
            confirmation_note='Recipient confirmed collection by phone.',
        )
        self.assertEqual(order.status, Order.Status.COLLECTED)
        dispatch.refresh_from_db()
        self.assertIsNotNone(dispatch.arrived_at)
        self.assertIsNotNone(dispatch.collected_at)

    def test_same_parcel_cannot_be_dispatched_twice(self):
        actor = self.customer.__class__.get_system_account()
        FulfilmentService.dispatch_parcel(
            order_id=self.order.pk, actor=actor,
            parcel_reference='KAK-1234', actual_transport_cost=Decimal('150.00'),
        )
        with self.assertRaises(ValidationError):
            FulfilmentService.dispatch_parcel(
                order_id=self.order.pk, actor=actor,
                parcel_reference='KAK-5678', actual_transport_cost=Decimal('150.00'),
            )
        self.assertEqual(ParcelDispatch.objects.filter(order=self.order).count(), 1)


class ParcelPricingServiceCart:
    """Use the real cart service while keeping these tests explicit."""

    def __new__(cls, request):
        from orders.cart_services import UnifiedSessionCartService
        return UnifiedSessionCartService(request)
