import uuid

from django.shortcuts import render
from django.http import FileResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Q
from django.utils import timezone
from django.views.generic import TemplateView
from branches.models import Branch
from logistics.models import PickupSlot
from core.context_processors import build_whatsapp_url
from .document_services import CommercialDocumentGenerator
from .models import Order
from .cart_services import UnifiedSessionCartService
from users.permissions import has_role, is_rider

User = get_user_model()


@login_required
def download_invoice_pdf_view(request, order_id):
    """
    Secure controller view dispatching processed stream buffers cleanly back 
    to authenticated requests as an unalterable binary attachment.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        from django.http import Http404
        raise Http404("Target transaction record missing.")


    # Guardrail: branch staff/managers/inventory managers can download
    # invoices for orders belonging to their own branch; customers can
    # only download their own; super admins bypass entirely.
    user = request.user
    if not user.is_superuser and user.role != User.Role.SUPER_ADMIN:
        is_branch_staff = user.role in [
            User.Role.STAFF, User.Role.INVENTORY_MANAGER, User.Role.BRANCH_MANAGER,
        ] and not is_rider(user)
        if is_branch_staff:
            if user.branch_id != order.branch_id:
                raise PermissionDenied(
                    "Security Boundary Violation: Cannot review multi-branch external financials."
                )
        elif order.customer_id != user.id:
            raise PermissionDenied(
                "Access Control Rule: Cannot view secondary consumer accounts data."
            )
    # Fetch processed memory stream safely out of Document Engine
    pdf_buffer = CommercialDocumentGenerator.generate_invoice_pdf_stream(order_id)
    
    return FileResponse(
        pdf_buffer, 
        as_attachment=True, 
        filename=f"Invoice_Receipt_INV_{order.id:06d}.pdf",
        content_type='application/pdf'
    )


class CheckoutPageView(UserPassesTestMixin, TemplateView):
    """Customer and guest checkout page backed by the checkout APIs."""

    template_name = 'orders/checkout.html'

    def test_func(self):
        return (
            not self.request.user.is_authenticated
            or has_role(self.request.user, User.Role.CUSTOMER)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart = UnifiedSessionCartService(self.request)
        cart_branch = Branch.objects.filter(
            pk=cart.cart_branch_id,
            is_active=True,
        ).first()
        cart_items = cart.get_cart_items_extended()
        cart_total = cart.get_total_financial_cost()
        cart_regular_total = sum(
            item['regular_price'] * item['quantity'] for item in cart_items
        )
        pickup_slots = list(
            PickupSlot.objects.filter(
                is_active=True,
                branch_id=cart.cart_branch_id,
                branch__offers_customer_pickup=True,
            ).filter(
                Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now())
            ).values(
                'id', 'branch_id', 'label', 'starts_at', 'ends_at',
            )
        )
        cart_lines = [
            f"- {item['product'].name} x{item['quantity']} — KES {item['total_price']}"
            for item in cart_items[:10]
        ]
        if len(cart_items) > 10:
            cart_lines.append(f"- Plus {len(cart_items) - 10} more cart item(s)")
        delivery_message = '\n'.join([
            'Hello Emporium Plug, I would like this cart sent to my town.',
            '',
            'Cart:',
            *cart_lines,
            f"Subtotal: KES {cart.get_total_financial_cost()}",
            '',
            'Please confirm the destination collection point, transport fee, final total and expected arrival before I pay.',
            'I understand this WhatsApp message does not reserve stock.',
        ])
        context.update({
            'cart_items': cart_items,
            'cart_total': cart_total,
            'cart_regular_total': cart_regular_total,
            'cart_product_discount': max(0, cart_regular_total - cart_total),
            'cart_branch_id': cart.cart_branch_id,
            'pickup_available': bool(
                cart_branch and cart_branch.offers_customer_pickup and pickup_slots
            ),
            'pickup_slots': pickup_slots,
            'delivery_whatsapp_url': build_whatsapp_url(delivery_message),
            'hide_global_whatsapp': True,
            'checkout_idempotency_key': str(uuid.uuid4()),
            'customer_phone': (
                str(self.request.user.phone_number)
                if self.request.user.is_authenticated else ''
            ),
            'customer_name': (
                self.request.user.get_full_name()
                if self.request.user.is_authenticated else ''
            ),
            'customer_email': (
                self.request.user.email
                if self.request.user.is_authenticated else ''
            ),
        })
        return context


class OrderTrackingPageView(TemplateView):
    """Public shell; order data is loaded only through the protected API."""

    template_name = 'orders/tracking.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['order_number'] = self.kwargs['order_number']
        return context


class DeliveryQuotePageView(TemplateView):
    """Public shell; protected quote data is loaded through the owner-only API."""

    template_name = 'orders/delivery_quote_status.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['quote_reference'] = self.kwargs['reference']
        return context
