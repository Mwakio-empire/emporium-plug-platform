from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class ImmutableAuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Audit records are immutable.')

    def delete(self):
        raise ValidationError('Audit records are immutable.')


class AuditLog(models.Model):
    """
    Immutable system register recording critical operational changes, 
    security modifications, and high-privilege management actions.
    """
    class ActionTypes(models.TextChoices):
            LOGIN = 'LOGIN', 'User Session Login'
            LOGIN_FAILED = 'LOGIN_FAILED', 'Failed Login Attempt'
            LOGOUT = 'LOGOUT', 'User Session Logout'
            PASSWORD_RESET = 'PASSWORD_RESET', 'Password Reset Completed'
            STAFF_ACCOUNT_CREATED = 'STAFF_ACCOUNT_CREATED', 'Staff Account Created'
            STAFF_ACCOUNT_ACTIVATED = 'STAFF_ACCOUNT_ACTIVATED', 'Staff Account Activated'
            STAFF_INVITE_RESENT = 'STAFF_INVITE_RESENT', 'Staff Invitation Resent'
            IDENTITY_UPDATED = 'IDENTITY_UPDATED', 'User Identity Updated'
            IMPERSONATION_START = 'IMPERSONATION_START', 'Troubleshooting Impersonation Started'
            IMPERSONATION_STOP = 'IMPERSONATION_STOP', 'Troubleshooting Impersonation Stopped'
            STOCK_VOID = 'STOCK_VOID', 'Inventory Void Adjustment'
            PRICE_CHANGE = 'PRICE_CHANGE', 'Product Unit Price Alteration'
            DISCOUNT_APPLIED = 'DISCOUNT_APPLIED', 'Manager Discount Authorization'
            MANUAL_PAYMENT_CONFIRMATION = (
                'MANUAL_PAYMENT_CONFIRMATION',
                'Manual Payment Confirmation',
            )
            PAYMENT_WEBHOOK_REVIEW = 'PAYMENT_WEBHOOK_REVIEW', 'Payment Webhook Review'
            PROMOTION_REDEMPTION = 'PROMOTION_REDEMPTION', 'Promotion Redemption'
            PROMOTION_CHANGE = 'PROMOTION_CHANGE', 'Promotion Configuration Change'
            REVIEW_MODERATION = 'REVIEW_MODERATION', 'Review Moderation'
            RETURN_DECISION = 'RETURN_DECISION', 'Return Decision'
            PARCEL_ROUTE_CHANGE = 'PARCEL_ROUTE_CHANGE', 'Parcel Route Configuration Change'
            PRIVACY_REQUEST = 'PRIVACY_REQUEST', 'Privacy Request Submitted'
            PRIVACY_DATA_EXPORT = 'PRIVACY_DATA_EXPORT', 'Personal Data Exported'
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='audit_logs',
        db_index=True
    )
    action_type = models.CharField(
        max_length=30,
        choices=ActionTypes.choices,
        db_index=True
    )
    description = models.TextField(help_text="Detailed context capturing prior state vs updated state values.")
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "System Audit Trail Log"
        verbose_name_plural = "System Audit Trail Logs"

    objects = ImmutableAuditLogQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Audit records are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Audit records are immutable.')

    def __str__(self):
        return f"[{self.timestamp}] {self.action_type} - Initiated by User ID: {self.user_id}"
