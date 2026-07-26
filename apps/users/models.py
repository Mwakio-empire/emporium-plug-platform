# Create your models here.
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models.functions import Lower
from django.utils import timezone
from datetime import timedelta
from branches.models import Branch
from .identifiers import normalize_phone_number


class CustomUserManager(BaseUserManager):
    """
    Enterprise Manager ensuring unique identifiers for both phone numbers 
    and email fields are fully validated upon account generation.
    """
    def create_user(self, username, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("The unique phone number identifier must be supplied.")
        phone_number = normalize_phone_number(phone_number)
        if extra_fields.get('email'):
            extra_fields['email'] = self.normalize_email(extra_fields['email']).lower()
        extra_fields.setdefault("role", User.Role.CUSTOMER)
        if extra_fields.get('is_active', True) and not extra_fields.get('activated_at'):
            extra_fields['activated_at'] = timezone.now()
        user = self.model(username=username, phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.SUPER_ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must be assigned is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must be assigned is_superuser=True.")

        return self.create_user(username, phone_number, password, **extra_fields)

SYSTEM_ACCOUNT_USERNAME = 'system_automation'
class User(AbstractUser):
    """
    System User Entity implementing role-based boundaries and scoping constraints.
    """
    class Role(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer'
        STAFF = 'STAFF', 'Branch Staff'
        INVENTORY_MANAGER = 'INVENTORY_MANAGER', 'Inventory Manager'
        BRANCH_MANAGER = 'BRANCH_MANAGER', 'Branch Manager'
        SUPER_ADMIN = 'SUPER_ADMIN', 'Super Admin'

    PRIVILEGED_ROLES = (
        Role.STAFF,
        Role.INVENTORY_MANAGER,
        Role.BRANCH_MANAGER,
        Role.SUPER_ADMIN,
    )

    phone_number = models.CharField(
        max_length=15, 
        unique=True, 
        help_text="Primary unique operational identifier (E.164 format recommended)."
    )
    email = models.EmailField(
        unique=True, 
        blank=True, 
        null=True, 
        help_text="Optional customer contact email or mandatory administrator address."
    )
    role = models.CharField(
        max_length=25, 
        choices=Role.choices, 
        default=Role.CUSTOMER,
        help_text="Defines system-wide capabilities and functional context."
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members',
        help_text="Ties branch level personnel to their distinct isolation environment."
    )
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_failed_login_at = models.DateTimeField(null=True, blank=True)
    token_version = models.PositiveIntegerField(default=0)
    last_password_change_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    objects = CustomUserManager()

    # Reconfigure authentication mapping fields
    REQUIRED_FIELDS = ['phone_number']

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        role__in=['STAFF', 'INVENTORY_MANAGER', 'BRANCH_MANAGER'],
                        branch__isnull=False,
                    )
                    | models.Q(
                        role__in=['CUSTOMER', 'SUPER_ADMIN'],
                        branch__isnull=True,
                    )
                ),
                name='user_role_branch_scope_consistent',
            ),
            models.UniqueConstraint(
                Lower('email'),
                name='user_email_case_insensitive_unique',
            ),
        ]

    def clean(self):
        super().clean()
        
        # Operational Guard Rails: Staff must be anchored to an explicit branch
        branch_dependent_roles = [
            self.Role.STAFF,
            self.Role.INVENTORY_MANAGER,
            self.Role.BRANCH_MANAGER,
        ]
        if self.role in branch_dependent_roles and not self.branch:
            raise ValidationError({
                'branch': f"Users assigned the role '{self.get_role_display()}' must be bound to a specific physical branch."
            })
        
        # Non-branch workers should not skew branch metric logs
        if self.role in [self.Role.CUSTOMER, self.Role.SUPER_ADMIN] and self.branch:
            self.branch = None

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    @classmethod
    def get_system_account(cls):
        """
        Non-loggable placeholder actor for automated stock/order mutations
        that have no natural human actor -- e.g. auto-cancelling a GUEST
        checkout order (customer=None, phone-only per Business Context §1)
        where StockAuditLog.triggered_by and OrderStatusHistory.changed_by
        are both required (non-null) FKs. is_active=False permanently --
        this account must never be able to authenticate.
        Lazily created on first use; safe to call from any Celery task.
        NOTE: cannot use get_or_create(defaults=...) here -- AbstractBaseUser
        .password is a required (non-blank) CharField, and get_or_create
        never calls set_password(), so full_clean() inside User.save()
        raises ValidationError on the blank password and the account is
        never created. set_unusable_password() populates a valid (but
        unusable-for-login) hashed value, satisfying full_clean().
        """
        account = cls.objects.filter(username=SYSTEM_ACCOUNT_USERNAME).first()
        if account is not None:
            return account
        try:
            # The savepoint keeps a simultaneous first-use insert from
            # breaking the checkout transaction that requested this actor.
            with transaction.atomic():
                account = cls(
                    username=SYSTEM_ACCOUNT_USERNAME,
                    phone_number='+254000000000',
                    email='system@internal.dynamicretail.local',
                    first_name='System',
                    last_name='Automation',
                    role=cls.Role.SUPER_ADMIN,
                    is_active=False,
                    is_staff=False,
                )
                account.set_unusable_password()
                account.save()
                return account
        except IntegrityError:
            return cls.objects.get(username=SYSTEM_ACCOUNT_USERNAME)
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    

class OTPVerification(models.Model):
    class Purpose(models.TextChoices):
        SIGNUP = 'SIGNUP', 'Signup Verification'
        STAFF_LOGIN = 'STAFF_LOGIN', 'Staff 2FA Login'
        PASSWORD_RESET = 'PASSWORD_RESET', 'Password Reset'
        STAFF_INVITE = 'STAFF_INVITE', 'Staff Account Invitation'

    MAX_ATTEMPTS = 5
    EXPIRY_MINUTES = 10
    RESEND_COOLDOWN_SECONDS = 60

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_codes')
    code = models.CharField(
        max_length=128,
        help_text="One-way password hash of the OTP; the raw code is never persisted.",
    )
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.SIGNUP)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"OTP for {self.user.phone_number} ({self.purpose})"


class PrivacyRequest(models.Model):
    class RequestType(models.TextChoices):
        ACCESS = 'ACCESS', 'Access my personal data'
        CORRECTION = 'CORRECTION', 'Correct my personal data'
        DELETION = 'DELETION', 'Delete or anonymise my personal data'
        OBJECTION = 'OBJECTION', 'Object to or restrict processing'

    class Status(models.TextChoices):
        SUBMITTED = 'SUBMITTED', 'Submitted'
        IN_REVIEW = 'IN_REVIEW', 'In review'
        COMPLETED = 'COMPLETED', 'Completed'
        REJECTED = 'REJECTED', 'Rejected with reason'

    user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='privacy_requests',
    )
    request_type = models.CharField(max_length=20, choices=RequestType.choices)
    details = models.TextField(blank=True, max_length=2000)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SUBMITTED,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    handled_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='privacy_requests_handled',
    )
    response_note = models.TextField(blank=True, max_length=4000)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'request_type'],
                condition=models.Q(status__in=['SUBMITTED', 'IN_REVIEW']),
                name='one_open_privacy_request_per_type',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status__in=['SUBMITTED', 'IN_REVIEW'], handled_at__isnull=True)
                    | models.Q(status__in=['COMPLETED', 'REJECTED'], handled_at__isnull=False)
                ),
                name='privacy_request_resolution_time_consistent',
            ),
        ]

    def __str__(self):
        return f'{self.get_request_type_display()} for user {self.user_id}'
