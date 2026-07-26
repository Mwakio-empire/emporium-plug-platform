# apps/logistics/models.py

import uuid
from decimal import Decimal, ROUND_CEILING
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import F, Q


class KenyaCounty(models.Model):
    """Official Kenyan county used to group customer parcel destinations."""

    code = models.CharField(max_length=2, primary_key=True)
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['code']
        verbose_name_plural = 'Kenya counties'

    def __str__(self):
        return self.name


class ParcelDestination(models.Model):
    """A verified matatu/bus parcel collection route from Nairobi."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    county = models.ForeignKey(
        KenyaCounty, on_delete=models.PROTECT, related_name='parcel_destinations',
    )
    town = models.CharField(max_length=100)
    collection_point = models.CharField(
        max_length=160,
        help_text='Where the recipient collects the parcel at the destination.',
    )
    operator_name = models.CharField(
        max_length=120,
        help_text='Approved matatu, bus or parcel-office operator.',
    )
    nairobi_dispatch_point = models.CharField(
        max_length=160,
        help_text='Internal Nairobi stage or parcel office used by staff.',
    )
    fee = models.DecimalField(max_digits=10, decimal_places=2)
    included_weight_kg = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('5.00'),
    )
    additional_kg_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        help_text='Charge for each started kilogram above the included weight.',
    )
    estimated_days_min = models.PositiveSmallIntegerField(default=1)
    estimated_days_max = models.PositiveSmallIntegerField(default=2)
    collection_instructions = models.TextField(blank=True)
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['county__name', 'town', 'collection_point']
        constraints = [
            models.UniqueConstraint(
                fields=['county', 'town', 'collection_point', 'operator_name'],
                name='unique_parcel_destination_operator',
            ),
            models.CheckConstraint(
                condition=Q(fee__gte=0), name='parcel_destination_fee_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(included_weight_kg__gt=0),
                name='parcel_destination_included_weight_positive',
            ),
            models.CheckConstraint(
                condition=Q(additional_kg_fee__gte=0),
                name='parcel_destination_extra_fee_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(estimated_days_max__gte=F('estimated_days_min')),
                name='parcel_destination_eta_ordered',
            ),
            models.CheckConstraint(
                condition=Q(effective_until__isnull=True) | Q(effective_until__gte=F('effective_from')),
                name='parcel_destination_rate_dates_ordered',
            ),
        ]

    def __str__(self):
        return f'{self.town} - {self.collection_point} ({self.operator_name})'

    def fee_for_weight(self, weight_kg):
        """Return the configured fee, charging each started excess kilogram."""
        weight = Decimal(str(weight_kg))
        if weight <= 0:
            raise ValidationError('Parcel weight must be greater than zero.')
        excess = max(Decimal('0.00'), weight - self.included_weight_kg)
        extra_units = excess.quantize(Decimal('1'), rounding=ROUND_CEILING)
        return self.fee + (extra_units * self.additional_kg_fee)


class DeliveryZone(models.Model):
    """
    Delivery zone per branch with flat fee and estimated time.
    Admin defines zones (e.g. Nakuru Town, Milimani, Pipeline).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='delivery_zones',
    )
    name = models.CharField(max_length=100)
    fee = models.DecimalField(max_digits=8, decimal_places=2)
    estimated_minutes = models.PositiveIntegerField(
        help_text="Estimated delivery time in minutes.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Delivery Zone"
        verbose_name_plural = "Delivery Zones"
        ordering = ['branch', 'name']
        unique_together = [['branch', 'name']]

    def __str__(self):
        return f"{self.name} ({self.branch.name}) — KES {self.fee}"


class PickupSlot(models.Model):
    """
    Available pickup time slots per branch.
    Admin defines these; customers select one at checkout.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='pickup_slots',
    )
    label = models.CharField(
        max_length=50,
        help_text="e.g. '9:00 AM – 11:00 AM'",
    )
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['branch', 'label']
        unique_together = [['branch', 'label']]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(starts_at__isnull=True, ends_at__isnull=True)
                    | Q(
                        starts_at__isnull=False,
                        ends_at__isnull=False,
                        ends_at__gt=F('starts_at'),
                    )
                ),
                name='pickup_slot_time_window_valid',
            ),
        ]

    def __str__(self):
        return f"{self.label} @ {self.branch.name}"


class RiderProfile(models.Model):
    """
    Extends the user system for delivery personnel.
    OneToOne with User — a rider has exactly one profile.
    Riders are identified by the existence of this profile,
    NOT by a dedicated role value in User.Role.
    """
    class DutyStatus(models.TextChoices):
        OFFLINE = 'OFFLINE', 'Offline'
        AVAILABLE = 'AVAILABLE', 'Available / On Duty'
        BUSY = 'BUSY', 'On Active Delivery'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rider_profile',
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='riders',
        db_index=True,
    )
    status = models.CharField(
        max_length=15,
        choices=DutyStatus.choices,
        default=DutyStatus.OFFLINE,
        db_index=True,
    )
    vehicle_registration = models.CharField(max_length=30, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.user_id:
            if self.user.role != 'STAFF':
                raise ValidationError({'user': 'A rider account must use the branch STAFF role.'})
            if self.user.branch_id != self.branch_id:
                raise ValidationError({'branch': 'Rider profile and user must belong to the same branch.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Rider: {self.user.get_full_name() or self.user.username} ({self.branch.name})"


class DeliveryAssignment(models.Model):
    """
    State machine governing the lifecycle of a physical delivery.

    Design rules:
    - OneToOne to Order — one assignment per order
    - clean() enforces rider.branch must match order.branch
    - save() calls full_clean() — validation always runs
    - VALID_TRANSITIONS enforced in views before any status update
    - GPS coordinates stored per update; DeliveryLocationLog tracks full history
    - last_location_updated_at tells you how fresh the coordinates are
    """

    class DeliveryStatus(models.TextChoices):
        PENDING_ASSIGNMENT = 'PENDING', 'Pending Rider Assignment'
        ASSIGNED = 'ASSIGNED', 'Rider Assigned'
        PICKED_UP = 'PICKED_UP', 'Picked Up from Branch'
        OUT_FOR_DELIVERY = 'IN_TRANSIT', 'Out for Delivery'
        DELIVERED = 'DELIVERED', 'Delivered Safely'
        FAILED = 'FAILED', 'Delivery Attempt Failed'
        RETURNED = 'RETURNED', 'Returned to Branch'

    # Valid state machine transitions
    VALID_TRANSITIONS = {
        'ASSIGNED': ['PICKED_UP', 'FAILED'],
        'PICKED_UP': ['IN_TRANSIT', 'FAILED'],
        'IN_TRANSIT': ['DELIVERED', 'FAILED'],
        'FAILED': ['ASSIGNED', 'RETURNED'],
    }

    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.PROTECT,
        related_name='delivery_assignment',
    )
    rider = models.ForeignKey(
        RiderProfile,
        on_delete=models.PROTECT,
        related_name='assignments',
        null=True,
        blank=True,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING_ASSIGNMENT,
        db_index=True,
    )

    # GPS — current position (overwritten each update)
    # Full location history stored in DeliveryLocationLog
    current_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
    )
    current_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
    )
    last_location_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the most recent GPS coordinate update.",
    )

    # Audit timestamps
    assigned_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    delivery_notes = models.TextField(blank=True, null=True)
    customer_confirmed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp when customer replied YES to the delivery confirmation SMS.",
    )
    customer_disputed = models.BooleanField(
        default=False, db_index=True,
        help_text="True if customer replied to the delivery confirmation SMS with anything other than YES.",
    )
    dispute_note = models.TextField(
        blank=True, default='',
        help_text="Raw text of the customer's non-YES reply.",
    )
    class Meta:
        verbose_name = "Delivery Assignment"
        verbose_name_plural = "Delivery Assignments"
        ordering = ['-assigned_at']

    def clean(self):
        """Branch guard — rider and order must belong to the same branch."""
        if self.order_id and self.order.order_type != 'ONLINE_DELIVERY':
            raise ValidationError({'order': 'Delivery assignments require an online delivery order.'})
        if self.rider and self.order_id:
            if self.order.branch_id != self.rider.branch_id:
                raise ValidationError({
                    'rider': (
                        f"Cannot assign rider from '{self.rider.branch.name}' "
                        f"to an order belonging to '{self.order.branch.name}'."
                    )
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Delivery for {self.order} — {self.get_status_display()}"


class DeliveryLocationLog(models.Model):
    """
    Immutable GPS history for a delivery assignment.
    Every location update inserts a new row — never overwrites.
    Enables route playback and audit trail in Phase 3.
    """
    assignment = models.ForeignKey(
        DeliveryAssignment,
        on_delete=models.CASCADE,
        related_name='location_logs',
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        return (
            f"Assignment {self.assignment_id} | "
            f"({self.latitude}, {self.longitude}) | {self.recorded_at}"
        ) 


class PackingChecklist(models.Model):
    """Auditable packing session for one online order."""

    order = models.OneToOneField(
        'orders.Order', on_delete=models.PROTECT, related_name='packing_checklist',
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='packing_checklists_started',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='packing_checklists_completed', null=True, blank=True,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default='')

    def __str__(self):
        return f"Packing checklist for {self.order.order_number}"


class PackingChecklistItem(models.Model):
    """One checked order line; retained as fulfilment evidence."""

    checklist = models.ForeignKey(
        PackingChecklist, on_delete=models.PROTECT, related_name='lines',
    )
    order_item = models.OneToOneField(
        'orders.OrderItem', on_delete=models.PROTECT,
        related_name='packing_check',
    )
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='packing_lines_checked', null=True, blank=True,
    )
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['order_item_id']

    @property
    def is_checked(self):
        return self.checked_at is not None

    def clean(self):
        super().clean()
        if (
            self.checklist_id and self.order_item_id
            and self.checklist.order_id != self.order_item.order_id
        ):
            raise ValidationError({'order_item': 'Packing line must belong to the checklist order.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ParcelDispatch(models.Model):
    """Auditable handoff of a paid order to a matatu/bus parcel operator."""

    order = models.OneToOneField(
        'orders.Order', on_delete=models.PROTECT, related_name='parcel_dispatch',
    )
    parcel_reference = models.CharField(max_length=100)
    vehicle_registration = models.CharField(max_length=30, blank=True)
    operator_contact = models.CharField(max_length=30, blank=True)
    actual_transport_cost = models.DecimalField(max_digits=10, decimal_places=2)
    dispatch_note = models.TextField(blank=True)
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='parcel_dispatches_recorded',
    )
    dispatched_at = models.DateTimeField(auto_now_add=True)
    arrived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='parcel_arrivals_recorded',
    )
    arrived_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='parcel_collections_recorded',
    )
    collected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-dispatched_at']
        constraints = [
            models.CheckConstraint(
                condition=Q(actual_transport_cost__gte=0),
                name='parcel_dispatch_cost_nonnegative',
            ),
        ]

    def clean(self):
        super().clean()
        if self.order_id:
            if self.order.order_type != 'ONLINE_DELIVERY' or not self.order.parcel_destination_id:
                raise ValidationError('Parcel dispatch requires a parcel-to-town order.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.order.order_number} - {self.parcel_reference}'
