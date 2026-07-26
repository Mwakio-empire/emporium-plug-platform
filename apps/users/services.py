from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from analytics.models import AuditLog
from analytics.services import AuditTrackingService

from .identifiers import normalize_phone_number, phone_lookup
from .models import OTPVerification, User
from .otp_services import OTPService


class StaffAccountProvisioningService:
    """Authorization and lifecycle rules for manager-created staff accounts."""

    SUPER_ADMIN_CREATABLE_ROLES = {
        User.Role.STAFF,
        User.Role.INVENTORY_MANAGER,
        User.Role.BRANCH_MANAGER,
    }

    @classmethod
    @transaction.atomic
    def create_invited_account(
        cls, *, actor, phone_number, email, first_name, last_name, role, branch, ip_address=None,
    ):
        if not actor.is_active:
            raise ValidationError('Inactive accounts cannot provision staff.', code='forbidden_staff_role')
        if actor.role == User.Role.BRANCH_MANAGER:
            if role != User.Role.STAFF or branch.pk != actor.branch_id:
                raise ValidationError(
                    'Branch managers may create only STAFF accounts for their own branch.',
                    code='forbidden_staff_scope',
                )
        elif actor.role == User.Role.SUPER_ADMIN:
            if role not in cls.SUPER_ADMIN_CREATABLE_ROLES:
                raise ValidationError('This role cannot be provisioned.', code='forbidden_staff_role')
        else:
            raise ValidationError('You are not allowed to create staff accounts.', code='forbidden_staff_role')

        phone = normalize_phone_number(phone_number)
        normalized_email = User.objects.normalize_email(email).lower() if email else None
        if User.objects.filter(phone_lookup(phone)).exists():
            raise ValidationError({'phone_number': 'An account with this phone number already exists.'})
        if normalized_email and User.objects.filter(email__iexact=normalized_email).exists():
            raise ValidationError({'email': 'An account with this email already exists.'})

        user = User(
            username=phone.removeprefix('+'),
            phone_number=phone,
            email=normalized_email,
            first_name=first_name,
            last_name=last_name,
            role=role,
            branch=branch,
            is_active=False,
            activated_at=None,
        )
        user.set_unusable_password()
        try:
            with transaction.atomic():
                user.save()
        except IntegrityError:
            raise ValidationError('A staff account with these identifiers already exists.')
        OTPService.generate_and_send(user, purpose=OTPVerification.Purpose.STAFF_INVITE)
        AuditTrackingService.log_action(
            user=actor,
            action_type=AuditLog.ActionTypes.STAFF_ACCOUNT_CREATED,
            description=(
                f'Created inactive staff account user_id={user.pk}, role={user.role}, '
                f'branch_id={user.branch_id}; activation OTP issued.'
            ),
            ip_address=ip_address,
        )
        return user

    @classmethod
    @transaction.atomic
    def resend_invitation(cls, *, actor, invited_user, ip_address=None):
        if not actor.is_active:
            raise ValidationError('Inactive accounts cannot resend invitations.')
        if invited_user.is_active or invited_user.activated_at is not None:
            raise ValidationError('This account has already been activated.')
        if invited_user.role not in User.PRIVILEGED_ROLES:
            raise ValidationError('This is not a staff invitation.')
        if actor.role == User.Role.BRANCH_MANAGER:
            if invited_user.role != User.Role.STAFF or invited_user.branch_id != actor.branch_id:
                raise ValidationError('This staff account is outside your authorization scope.')
        elif actor.role != User.Role.SUPER_ADMIN:
            raise ValidationError('You are not allowed to resend this invitation.')

        OTPService.generate_and_send(invited_user, purpose=OTPVerification.Purpose.STAFF_INVITE)
        AuditTrackingService.log_action(
            user=actor,
            action_type=AuditLog.ActionTypes.STAFF_INVITE_RESENT,
            description=f'Resent activation OTP for staff user_id={invited_user.pk}.',
            ip_address=ip_address,
        )

    @classmethod
    @transaction.atomic
    def activate_invited_account(cls, *, user, code, new_password, ip_address=None):
        locked = User.objects.select_for_update().get(pk=user.pk)
        if locked.is_active or locked.activated_at is not None or locked.role not in User.PRIVILEGED_ROLES:
            raise ValidationError('Invalid or expired staff invitation.')
        OTPService.verify(locked, code, purpose=OTPVerification.Purpose.STAFF_INVITE)
        locked.set_password(new_password)
        locked.is_active = True
        locked.activated_at = timezone.now()
        locked.last_password_change_at = locked.activated_at
        locked.save(update_fields=[
            'password', 'is_active', 'activated_at', 'last_password_change_at',
        ])
        AuditTrackingService.log_action(
            user=locked,
            action_type=AuditLog.ActionTypes.STAFF_ACCOUNT_ACTIVATED,
            description=f'Staff account user_id={locked.pk} completed invitation activation.',
            ip_address=ip_address,
        )
        return locked
