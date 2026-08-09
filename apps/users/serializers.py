# apps/users/serializers.py

from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .jwt import issue_tokens
from .models import OTPVerification
from .otp_services import OTPService
from .security import AuthenticationSecurityService
from .identifiers import normalize_phone_number, phone_lookup, resolve_user_identifier
from branches.models import Branch
from .services import StaffAccountProvisioningService

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Customer self-registration.
    Role is always hardcoded to CUSTOMER — never accepted from client.
    """
    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value
    password = serializers.CharField(
        write_only=True,
        min_length=settings.PASSWORD_MINIMUM_LENGTH,
        max_length=128,
    )
    confirm_password = serializers.CharField(write_only=True)

    def validate_phone_number(self, value):
        try:
            normalized = normalize_phone_number(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        if User.objects.filter(phone_lookup(normalized)).exists():
            raise serializers.ValidationError('An account with this phone number already exists.')
        return normalized

    def validate_email(self, value):
        if not value:
            return None
        normalized = User.objects.normalize_email(value).lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return normalized

    class Meta:
        model = User
        fields = [
            'id', 'email', 'phone_number', 'first_name',
            'last_name', 'password', 'confirm_password',
        ]
        read_only_fields = ['id']

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError(
                {'confirm_password': 'Passwords do not match.'}
            )
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
 
        # AbstractUser requires a unique 'username' internally, but this
        # serializer never collects one from the customer -- phone_number
        # is the actual user-facing identifier. Auto-generate a username
        # from phone_number (stripped of '+' and spaces) so
        # User.objects.create_user() has the positional arg it requires.
        phone_number = validated_data.get('phone_number', '')
        generated_username = phone_number.replace('+', '').replace(' ', '')
 
        return User.objects.create_user(
            username=generated_username,
            role=User.Role.CUSTOMER,
            is_active=False,
            **validated_data,
        )


class SignupOTPVerificationSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    code = serializers.RegexField(r'^\d{6}$')

    def validate(self, attrs):
        identifier = attrs['identifier'].strip()
        user = resolve_user_identifier(User, identifier)
        if user is not None and (
            user.role != User.Role.CUSTOMER or user.is_active
        ):
            user = None
        if user is None:
            raise serializers.ValidationError('Invalid or expired verification request.')
        try:
            OTPService.verify(
                user, attrs['code'], purpose=OTPVerification.Purpose.SIGNUP,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'code': list(exc.messages)})
        attrs['user'] = user
        return attrs


class CustomerTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['token_version'] = user.token_version
        return token

    def validate(self, attrs):
        identifier = attrs.get(self.username_field, '')
        candidate = resolve_user_identifier(User, identifier)
        if candidate and AuthenticationSecurityService.is_locked(candidate):
            raise AuthenticationFailed('Sign-in is temporarily locked. Try again later.')
        try:
            data = super().validate(attrs)
        except AuthenticationFailed:
            AuthenticationSecurityService.record_failure(candidate)
            raise
        AuthenticationSecurityService.clear_failures(self.user)
        if self.user.role != User.Role.CUSTOMER:
            raise PermissionDenied(
                'Staff token login is disabled. Use the staff sign-in flow with 2FA.'
            )
        return data

class UserProfileSerializer(serializers.ModelSerializer):
    """Read/update own profile. Email and role are read-only."""

    class Meta:
        model = User
        fields = [
            'id', 'email', 'phone_number',
            'first_name', 'last_name', 'role',
            'date_joined',
        ]
        read_only_fields = ['id', 'email', 'role', 'date_joined']


class StaffAccountSerializer(serializers.ModelSerializer):
    branch_id = serializers.IntegerField(source='branch.id', read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'phone_number', 'email', 'first_name', 'last_name',
            'role', 'branch_id', 'is_active', 'activated_at',
        )
        read_only_fields = fields


class StaffAccountProvisionSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=32)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=(
        User.Role.STAFF,
        User.Role.INVENTORY_MANAGER,
        User.Role.BRANCH_MANAGER,
    ))
    branch_id = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True), source='branch',
    )

    def create(self, validated_data):
        request = self.context['request']
        return StaffAccountProvisioningService.create_invited_account(
            actor=request.user,
            phone_number=validated_data['phone_number'],
            email=validated_data.get('email'),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=validated_data['role'],
            branch=validated_data['branch'],
            ip_address=request.META.get('REMOTE_ADDR'),
        )


class StaffInviteActivationSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    code = serializers.RegexField(r'^\d{6}$')
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        user = resolve_user_identifier(User, attrs['identifier'])
        if user is None or user.role not in User.PRIVILEGED_ROLES or user.is_active or user.activated_at:
            raise serializers.ValidationError('Invalid or expired staff invitation.')
        try:
            validate_password(attrs['new_password'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)})
        attrs['user'] = user
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        try:
            return StaffAccountProvisioningService.activate_invited_account(
                user=validated_data['user'],
                code=validated_data['code'],
                new_password=validated_data['new_password'],
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'code': list(exc.messages)})
