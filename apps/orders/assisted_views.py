import hashlib
import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from branches.models import Branch
from logistics.models import PickupSlot
from users.models import User
from users.permissions import is_rider
from users.rate_limit import check_rate_limit

from .cart_services import UnifiedSessionCartService
from .checkout_access import checkout_request_fingerprint, issue_guest_order_token
from .models import Order
from .online_services import OnlineOrderService


ASSISTED_ROLES = {User.Role.STAFF, User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN}


class WhatsAppAssistedPickupView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Staff intake for a customer order agreed through the business WhatsApp."""

    template_name = 'orders/whatsapp_assisted_pickup.html'

    def test_func(self):
        user = self.request.user
        return user.is_active and user.role in ASSISTED_ROLES and not is_rider(user)

    def _render(self, request, *, form_data=None, status=200):
        cart = UnifiedSessionCartService(request)
        branch = Branch.objects.filter(pk=cart.cart_branch_id, is_active=True).first()
        slots = PickupSlot.objects.none()
        if branch:
            slots = PickupSlot.objects.filter(branch=branch, is_active=True).filter(
                models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=timezone.now())
            ).order_by('starts_at', 'label')
        return render(request, self.template_name, {
            'cart_items': cart.get_cart_items_extended(),
            'cart_total': cart.get_total_financial_cost(),
            'cart_branch': branch,
            'pickup_slots': slots,
            'form_data': form_data or {},
            'idempotency_key': (form_data or {}).get('idempotency_key') or uuid.uuid4(),
        }, status=status)

    def get(self, request):
        return self._render(request)

    def post(self, request):
        cart = UnifiedSessionCartService(request)
        branch = Branch.objects.filter(pk=cart.cart_branch_id, is_active=True).first()
        data = request.POST
        try:
            check_rate_limit(f'whatsapp_assisted_order:{request.user.pk}', limit=20, window_seconds=3600)
            if cart.is_empty() or branch is None:
                raise ValidationError('Add the agreed products to the cart before recording the order.')
            if request.user.role != User.Role.SUPER_ADMIN and request.user.branch_id != branch.pk:
                raise ValidationError('You may only record orders fulfilled by your assigned branch.')
            if not branch.offers_customer_pickup:
                raise ValidationError('This basket is not held at the approved S18 pickup branch. Transfer stock first or use the website checkout flow.')
            slot = PickupSlot.objects.filter(pk=data.get('pickup_slot_id'), branch=branch, is_active=True).first()
            if slot is None or (slot.ends_at and slot.ends_at <= timezone.now()):
                raise ValidationError('Select an active pickup time.')
            if data.get('confirmed') != 'yes':
                raise ValidationError('Confirm that the customer agreed to the products, total and pickup terms.')
            customer_name = data.get('customer_name', '').strip()
            customer_email = data.get('customer_email', '').strip().lower()
            notes = data.get('notes', '').strip()
            if not customer_name or len(customer_name) > 100:
                raise ValidationError('Enter a customer name of 100 characters or fewer.')
            if customer_email:
                validate_email(customer_email)
            if len(notes) > 1000:
                raise ValidationError('Staff notes cannot exceed 1,000 characters.')
            idempotency_key = uuid.UUID(str(data.get('idempotency_key')))
            fingerprint = checkout_request_fingerprint({
                'branch_id': branch.pk,
                'order_type': Order.OrderType.ONLINE_PICKUP,
                'customer_phone': data.get('customer_phone'),
                'customer_name': customer_name,
                'customer_email': customer_email,
                'pickup_slot_id': str(slot.pk),
                'payment_method': Order.PaymentMethod.COD,
                'notes': notes,
                'confirmed': 'yes',
            })
            staff_owner_hash = hashlib.sha256(f'whatsapp-assisted:{request.user.pk}'.encode()).hexdigest()
            order = OnlineOrderService.create_order(
                request=request,
                branch=branch,
                customer=None,
                order_type=Order.OrderType.ONLINE_PICKUP,
                customer_phone=data.get('customer_phone', ''),
                customer_name=customer_name,
                customer_email=customer_email,
                pickup_slot=slot,
                notes=notes,
                payment_method=Order.PaymentMethod.COD,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                guest_session_hash=staff_owner_hash,
                sales_channel=Order.SalesChannel.WHATSAPP_ASSISTED,
                processed_by=request.user,
            )
        except (ValidationError, ValueError) as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, 'messages') else str(exc))
            return self._render(request, form_data=data, status=400)

        token = issue_guest_order_token(order)
        tracking_path = reverse('track-order', kwargs={'order_number': order.order_number})
        tracking_url = request.build_absolute_uri(tracking_path) + f'#{token}'
        return render(request, 'orders/whatsapp_assisted_success.html', {
            'order': order,
            'tracking_url': tracking_url,
        }, status=201)
