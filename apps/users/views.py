# apps/users/views.py
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model, login as django_login, logout as django_logout, authenticate
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
import json
import hashlib
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from .serializers import (
    CustomerTokenObtainPairSerializer,
    SignupOTPVerificationSerializer,
    StaffAccountProvisionSerializer,
    StaffAccountSerializer,
    StaffInviteActivationSerializer,
    UserRegistrationSerializer,
    UserProfileSerializer,
)
from .jwt import issue_tokens, VersionedTokenRefreshSerializer
from .security import AuthenticationSecurityService
from .forms import (
    CustomerLoginForm, CustomerSignupForm, OTPVerifyForm,
    PasswordResetRequestForm, PasswordResetConfirmForm,
    StaffAccountProvisionForm, StaffInviteActivationForm,
    PrivacyRequestForm, PrivacyExportForm, CustomerProfileForm,
)
from .otp_services import OTPService
from .models import OTPVerification, PrivacyRequest
from .privacy_services import PersonalDataExportService, PrivacyRequestReviewService
from .rate_limit import check_rate_limit
from .identifiers import resolve_user_identifier
from .permissions import IsBranchManagerOrAbove
from .services import StaffAccountProvisioningService
from analytics.models import AuditLog
from analytics.services import AuditTrackingService

User = get_user_model()

PENDING_AUTH_TTL_SECONDS = 10 * 60


# ------------------------------------------------------------------
# JWT / API views (unchanged from Phase 0)
# ------------------------------------------------------------------
class CustomerRegistrationAPIView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    throttle_scope = 'signup'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        OTPService.generate_and_send(user, purpose=OTPVerification.Purpose.SIGNUP)
        return Response(
            {
                'user': UserProfileSerializer(user).data,
                'verification_required': True,
            },
            status=status.HTTP_201_CREATED,
        )


class SignupOTPVerificationAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = 'otp'

    def post(self, request):
        serializer = SignupOTPVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        return Response({
            'user': UserProfileSerializer(user).data,
            'tokens': issue_tokens(user),
        })


class CustomerTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomerTokenObtainPairSerializer
    throttle_scope = 'login'


class VersionedTokenRefreshView(TokenRefreshView):
    serializer_class = VersionedTokenRefreshSerializer


class APILogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_value = request.data.get('refresh', '')
        if not refresh_value:
            return Response({'refresh': ['This field is required.']}, status=status.HTTP_400_BAD_REQUEST)
        try:
            refresh = RefreshToken(refresh_value)
            if str(refresh.get('user_id')) != str(request.user.pk):
                return Response(
                    {'refresh': ['Token does not belong to the authenticated user.']},
                    status=status.HTTP_403_FORBIDDEN,
                )
            refresh.blacklist()
        except TokenError:
            return Response({'refresh': ['Invalid or expired token.']}, status=status.HTTP_400_BAD_REQUEST)
        User.objects.filter(pk=request.user.pk).update(token_version=F('token_version') + 1)
        AuditTrackingService.log_action(
            user=request.user,
            action_type=AuditLog.ActionTypes.LOGOUT,
            description="API logout completed; existing tokens invalidated.",
            ip_address=_client_ip(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserProfileAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class StaffAccountProvisionAPIView(APIView):
    permission_classes = [IsBranchManagerOrAbove]

    def post(self, request):
        serializer = StaffAccountProvisionSerializer(
            data=request.data, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except ValidationError as exc:
            response_status = (
                status.HTTP_403_FORBIDDEN
                if getattr(exc, 'code', None) in {'forbidden_staff_scope', 'forbidden_staff_role'}
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({'detail': exc.message_dict if hasattr(exc, 'message_dict') else exc.messages}, status=response_status)
        return Response(StaffAccountSerializer(user).data, status=status.HTTP_201_CREATED)


class StaffInviteActivationAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = 'otp'

    def post(self, request):
        serializer = StaffInviteActivationSerializer(
            data=request.data, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            'user': StaffAccountSerializer(user).data,
            'message': 'Staff account activated. Sign in to complete two-factor authentication.',
        })


class StaffInviteResendAPIView(APIView):
    permission_classes = [IsBranchManagerOrAbove]
    throttle_scope = 'otp'

    def post(self, request, user_id):
        invited_user = User.objects.filter(pk=user_id).first()
        if invited_user is None:
            return Response({'detail': 'Staff invitation not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            StaffAccountProvisioningService.resend_invitation(
                actor=request.user,
                invited_user=invited_user,
                ip_address=_client_ip(request),
            )
        except ValidationError as exc:
            return Response({'detail': exc.messages}, status=status.HTTP_403_FORBIDDEN)
        return Response({'message': 'A new staff activation code has been sent.'})


# ------------------------------------------------------------------
# HTML AUTH VIEWS
# ------------------------------------------------------------------
def _client_ip(request):
    return request.META.get('REMOTE_ADDR', 'unknown')


def _safe_next(request, value):
    """Return a local redirect target or an empty string."""
    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return ''


def _set_pending_session(request, key, user, next_url=''):
    request.session.cycle_key()
    request.session[key] = user.pk
    request.session[f'{key}_created_at'] = timezone.now().timestamp()
    next_key = f'{key.removesuffix("_user_id")}_next'
    request.session.pop(next_key, None)
    if next_url:
        request.session[next_key] = _safe_next(request, next_url)


def _pending_session_is_current(request, key):
    created_at = request.session.get(f'{key}_created_at')
    if created_at is None:
        return False
    try:
        age = timezone.now().timestamp() - float(created_at)
    except (TypeError, ValueError):
        return False
    return 0 <= age <= PENDING_AUTH_TTL_SECONDS


def _clear_pending_session(request, key):
    request.session.pop(key, None)
    request.session.pop(f'{key}_created_at', None)
    request.session.pop(f'{key.removesuffix("_user_id")}_next', None)


class CustomerLoginView(View):
    template_name = 'users/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('/')
        next_url = _safe_next(request, request.GET.get('next', ''))
        return render(request, self.template_name, {'form': CustomerLoginForm(), 'next': next_url})

    def post(self, request):
        form = CustomerLoginForm(request.POST)
        next_url = _safe_next(request, request.POST.get('next', ''))
        if not form.is_valid():
            return render(request, self.template_name, {'form': form, 'next': next_url})

        identifier = form.cleaned_data['identifier']
        password = form.cleaned_data['password']
        ip = _client_ip(request)

        try:
            check_rate_limit(f"ratelimit:login_ip:{ip}", limit=20, window_seconds=300)
            identifier_key = hashlib.sha256(identifier.lower().encode('utf-8')).hexdigest()
            check_rate_limit(f"ratelimit:login_id:{ip}:{identifier_key}", limit=5, window_seconds=300)
        except ValidationError as e:
            form.add_error(None, str(e))
            return render(request, self.template_name, {'form': form, 'next': next_url})

        candidate = resolve_user_identifier(User, identifier)
        if candidate and AuthenticationSecurityService.is_locked(candidate):
            form.add_error(None, "Sign-in is temporarily locked. Try again later.")
            return render(request, self.template_name, {'form': form, 'next': next_url})

        user = authenticate(request, username=identifier, password=password)

        if user is not None:
            AuthenticationSecurityService.clear_failures(user)
            if user.role in User.PRIVILEGED_ROLES:
                AuditTrackingService.log_action(
                    user=user, action_type=AuditLog.ActionTypes.LOGIN,
                    description="Password verified; awaiting staff 2FA OTP.",
                    ip_address=ip,
                )
                try:
                    OTPService.generate_and_send(user, purpose=OTPVerification.Purpose.STAFF_LOGIN)
                except ValidationError:
                    pass  # cooldown active -- an unexpired code already exists
                _set_pending_session(request, 'pending_staff_login_user_id', user, next_url)
                return redirect('accounts:verify-staff-otp')

            django_login(request, user)
            from copy import deepcopy
            from orders.cart_services import (
                STOREFRONT_CART_BRANCH_KEY,
                STOREFRONT_CART_KEY,
                UnifiedSessionCartService,
            )
            guest_cart = deepcopy(request.session.get(STOREFRONT_CART_KEY, {}))
            guest_branch_id = request.session.get(STOREFRONT_CART_BRANCH_KEY)
            UnifiedSessionCartService(request).merge_authenticated_cart(
                guest_cart,
                guest_branch_id,
            )
            AuditTrackingService.log_action(
                user=user, action_type=AuditLog.ActionTypes.LOGIN,
                description="Successful customer login.",
                ip_address=ip,
            )
            return redirect(next_url or '/')

        if (
            candidate
            and candidate.role == User.Role.CUSTOMER
            and not candidate.is_active
            and candidate.check_password(password)
        ):
            AuthenticationSecurityService.clear_failures(candidate)
            _set_pending_session(request, 'pending_verification_user_id', candidate, next_url)
            return redirect('accounts:verify-otp')

        AuthenticationSecurityService.record_failure(candidate)

        AuditTrackingService.log_action(
            user=candidate, action_type=AuditLog.ActionTypes.LOGIN_FAILED,
            description="Failed login attempt.",
            ip_address=ip,
        )
        form.add_error(None, "Invalid phone/email or password.")
        return render(request, self.template_name, {'form': form, 'next': next_url})


class CustomerSignupView(View):
    template_name = 'users/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('/')
        next_url = _safe_next(request, request.GET.get('next', ''))
        return render(request, self.template_name, {'form': CustomerSignupForm(), 'next': next_url})

    def post(self, request):
        form = CustomerSignupForm(request.POST)
        next_url = _safe_next(request, request.POST.get('next', ''))
        ip = _client_ip(request)
        try:
            check_rate_limit(f"ratelimit:signup:{ip}", limit=5, window_seconds=3600)
        except ValidationError as e:
            form.add_error(None, str(e))
            return render(request, self.template_name, {'form': form, 'next': next_url})

        if form.is_valid():
            phone = form.cleaned_data['phone_number']
            generated_username = phone.replace('+', '').replace(' ', '')
            user = User.objects.create_user(
                username=generated_username,
                phone_number=phone,
                email=form.cleaned_data.get('email') or None,
                first_name=form.cleaned_data.get('first_name', ''),
                last_name=form.cleaned_data.get('last_name', ''),
                password=form.cleaned_data['password'],
                role=User.Role.CUSTOMER,
                is_active=False,
            )
            OTPService.generate_and_send(user)
            _set_pending_session(request, 'pending_verification_user_id', user, next_url)
            return redirect('accounts:verify-otp')
        return render(request, self.template_name, {'form': form, 'next': next_url})


class CustomerLogoutView(View):
    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        if user:
            AuditTrackingService.log_action(
                user=user,
                action_type=AuditLog.ActionTypes.LOGOUT,
                description="User logged out.",
                ip_address=_client_ip(request),
            )
        django_logout(request)
        return redirect('/')


class CustomerProfileView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'users/profile.html'

    def test_func(self):
        return self.request.user.role == User.Role.CUSTOMER

    def get(self, request):
        return render(request, self.template_name, {
            'form': CustomerProfileForm(instance=request.user),
            'recent_orders': request.user.customer_orders.order_by('-created_at')[:5],
        })

    def post(self, request):
        form = CustomerProfileForm(request.POST, instance=request.user)
        if not form.is_valid():
            return render(request, self.template_name, {
                'form': form,
                'recent_orders': request.user.customer_orders.order_by('-created_at')[:5],
            }, status=400)
        form.save()
        AuditTrackingService.log_action(
            user=request.user,
            action_type=AuditLog.ActionTypes.IDENTITY_UPDATED,
            description='Customer updated profile name fields.',
            ip_address=_client_ip(request),
        )
        messages.success(request, 'Your profile has been updated.')
        return redirect('accounts:profile')


class OTPVerifyView(View):
    """Signup verification -- flips is_active True on success."""
    template_name = 'users/verify_otp.html'

    def _pending_user(self, request):
        if not _pending_session_is_current(request, 'pending_verification_user_id'):
            _clear_pending_session(request, 'pending_verification_user_id')
            return None
        user_id = request.session.get('pending_verification_user_id')
        return User.objects.filter(
            id=user_id, role=User.Role.CUSTOMER, is_active=False,
        ).first() if user_id else None

    def get(self, request):
        user = self._pending_user(request)
        if user is None:
            return redirect('accounts:signup')
        return render(request, self.template_name, {'form': OTPVerifyForm(), 'phone': user.phone_number})

    def post(self, request):
        user = self._pending_user(request)
        if user is None:
            return redirect('accounts:signup')
        ip = _client_ip(request)
        try:
            check_rate_limit(f"ratelimit:otp_verify_ip:{ip}", limit=20, window_seconds=300)
        except ValidationError as e:
            form = OTPVerifyForm(request.POST)
            form.add_error(None, str(e))
            return render(request, self.template_name, {'form': form, 'phone': user.phone_number})

        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            try:
                OTPService.verify(user, form.cleaned_data['code'])
            except ValidationError as e:
                form.add_error('code', str(e))
                return render(request, self.template_name, {'form': form, 'phone': user.phone_number})
            django_login(request, user, backend='users.backends.PhoneOrEmailBackend')
            AuditTrackingService.log_action(
                user=user, action_type=AuditLog.ActionTypes.LOGIN,
                description="Customer signup verified; login completed.",
                ip_address=ip,
            )
            next_url = request.session.pop('pending_verification_next', '')
            _clear_pending_session(request, 'pending_verification_user_id')
            return redirect(_safe_next(request, next_url) or '/')
        return render(request, self.template_name, {'form': form, 'phone': user.phone_number})


class OTPResendView(View):
    def post(self, request):
        if not _pending_session_is_current(request, 'pending_verification_user_id'):
            _clear_pending_session(request, 'pending_verification_user_id')
            return redirect('accounts:signup')
        user_id = request.session.get('pending_verification_user_id')
        user = User.objects.filter(
            id=user_id, role=User.Role.CUSTOMER, is_active=False,
        ).first() if user_id else None
        if user is None:
            return redirect('accounts:signup')
        try:
            OTPService.generate_and_send(user)
            messages.success(request, "A new code has been sent.")
        except ValidationError as e:
            messages.error(request, str(e))
        return redirect('accounts:verify-otp')


class StaffOTPVerifyView(View):
    """Mandatory 2FA for STAFF/INVENTORY_MANAGER/BRANCH_MANAGER/SUPER_ADMIN. Never touches is_active."""
    template_name = 'users/verify_staff_otp.html'

    def _pending_user(self, request):
        if not _pending_session_is_current(request, 'pending_staff_login_user_id'):
            _clear_pending_session(request, 'pending_staff_login_user_id')
            return None
        user_id = request.session.get('pending_staff_login_user_id')
        return User.objects.filter(id=user_id, is_active=True).first() if user_id else None

    def get(self, request):
        user = self._pending_user(request)
        if user is None:
            return redirect('accounts:login')
        return render(request, self.template_name, {'form': OTPVerifyForm(), 'phone': user.phone_number})

    def post(self, request):
        user = self._pending_user(request)
        if user is None:
            return redirect('accounts:login')
        ip = _client_ip(request)
        try:
            check_rate_limit(f"ratelimit:staff_otp_ip:{ip}", limit=20, window_seconds=300)
        except ValidationError as e:
            form = OTPVerifyForm(request.POST)
            form.add_error(None, str(e))
            return render(request, self.template_name, {'form': form, 'phone': user.phone_number})

        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            try:
                OTPService.verify(user, form.cleaned_data['code'], purpose=OTPVerification.Purpose.STAFF_LOGIN)
            except ValidationError as e:
                form.add_error('code', str(e))
                return render(request, self.template_name, {'form': form, 'phone': user.phone_number})
            django_login(request, user, backend='users.backends.PhoneOrEmailBackend')
            AuditTrackingService.log_action(
                user=user, action_type=AuditLog.ActionTypes.LOGIN,
                description="Staff 2FA verified; login completed.",
                ip_address=ip,
            )
            next_url = request.session.pop('pending_staff_login_next', '')
            _clear_pending_session(request, 'pending_staff_login_user_id')
            return redirect(_safe_next(request, next_url) or self._default_redirect_for(user))
        return render(request, self.template_name, {'form': form, 'phone': user.phone_number})

    @staticmethod
    def _default_redirect_for(user):
        if user.role == User.Role.SUPER_ADMIN:
            return '/management/dashboard/'
        if user.role in [User.Role.STAFF, User.Role.BRANCH_MANAGER]:
            return '/pos-desk/'
        return '/'


class StaffOTPResendView(View):
    def post(self, request):
        if not _pending_session_is_current(request, 'pending_staff_login_user_id'):
            _clear_pending_session(request, 'pending_staff_login_user_id')
            return redirect('accounts:login')
        user_id = request.session.get('pending_staff_login_user_id')
        user = User.objects.filter(id=user_id, is_active=True).first() if user_id else None
        if user is None:
            return redirect('accounts:login')
        try:
            OTPService.generate_and_send(user, purpose=OTPVerification.Purpose.STAFF_LOGIN)
            messages.success(request, "A new code has been sent.")
        except ValidationError as e:
            messages.error(request, str(e))
        return redirect('accounts:verify-staff-otp')


class PasswordResetRequestView(View):
    """Enumeration-safe: always shows the same success message regardless of whether the account exists."""
    template_name = 'users/forgot_password.html'

    def get(self, request):
        return render(request, self.template_name, {'form': PasswordResetRequestForm()})

    def post(self, request):
        form = PasswordResetRequestForm(request.POST)
        ip = _client_ip(request)
        if form.is_valid():
            try:
                check_rate_limit(f"ratelimit:pwreset:{ip}", limit=5, window_seconds=600)
            except ValidationError as e:
                form.add_error(None, str(e))
                return render(request, self.template_name, {'form': form})

            identifier = form.cleaned_data['identifier']
            _clear_pending_session(request, 'pending_reset_user_id')
            user = resolve_user_identifier(User, identifier)
            if user is not None and user.is_active:
                try:
                    OTPService.generate_and_send(user, purpose=OTPVerification.Purpose.PASSWORD_RESET)
                    _set_pending_session(request, 'pending_reset_user_id', user)
                except ValidationError:
                    _set_pending_session(request, 'pending_reset_user_id', user)
            messages.success(request, "If an account exists for that phone/email, a reset code has been sent.")
            return redirect('accounts:reset-password-confirm')
        return render(request, self.template_name, {'form': form})


class PasswordResetConfirmView(View):
    template_name = 'users/reset_password.html'

    def get(self, request):
        return render(request, self.template_name, {'form': PasswordResetConfirmForm()})

    def post(self, request):
        form = PasswordResetConfirmForm(request.POST)
        if not _pending_session_is_current(request, 'pending_reset_user_id'):
            _clear_pending_session(request, 'pending_reset_user_id')
            form.add_error('code', "Invalid or expired code. Please request a new one.")
            return render(request, self.template_name, {'form': form})
        user_id = request.session.get('pending_reset_user_id')
        if not user_id:
            form.add_error('code', "Invalid or expired code. Please request a new one.")
            return render(request, self.template_name, {'form': form})
        if form.is_valid():
            user = User.objects.filter(id=user_id, is_active=True).first()
            if user is None:
                form.add_error('code', "Invalid or expired code. Please request a new one.")
                return render(request, self.template_name, {'form': form})
            try:
                OTPService.verify(user, form.cleaned_data['code'], purpose=OTPVerification.Purpose.PASSWORD_RESET)
            except ValidationError as e:
                form.add_error('code', "Invalid or expired code. Please request a new one.")
                return render(request, self.template_name, {'form': form})
            user.set_password(form.cleaned_data['new_password'])
            user.token_version += 1
            user.last_password_change_at = timezone.now()
            user.save(update_fields=['password', 'token_version', 'last_password_change_at'])
            AuthenticationSecurityService.clear_failures(user)
            AuditTrackingService.log_action(
                user=user,
                action_type=AuditLog.ActionTypes.PASSWORD_RESET,
                description="Password reset completed; existing tokens invalidated.",
                ip_address=_client_ip(request),
            )
            _clear_pending_session(request, 'pending_reset_user_id')
            messages.success(request, "Password reset successful. Please sign in.")
            return redirect('accounts:login')
        return render(request, self.template_name, {'form': form})


class StaffAccountProvisionView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'users/staff_invite.html'

    def test_func(self):
        return self.request.user.role in (User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN)

    def get(self, request):
        return render(request, self.template_name, {
            'form': StaffAccountProvisionForm(actor=request.user),
        })

    def post(self, request):
        form = StaffAccountProvisionForm(request.POST, actor=request.user)
        if form.is_valid():
            try:
                StaffAccountProvisioningService.create_invited_account(
                    actor=request.user,
                    phone_number=form.cleaned_data['phone_number'],
                    email=form.cleaned_data.get('email'),
                    first_name=form.cleaned_data.get('first_name', ''),
                    last_name=form.cleaned_data.get('last_name', ''),
                    role=form.cleaned_data['role'],
                    branch=form.cleaned_data['branch'],
                    ip_address=_client_ip(request),
                )
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                messages.success(request, 'Staff invitation created and activation code sent.')
                return redirect('accounts:staff-invite')
        return render(request, self.template_name, {'form': form})


class StaffInviteActivationView(View):
    template_name = 'users/activate_staff.html'

    def get(self, request):
        return render(request, self.template_name, {'form': StaffInviteActivationForm()})

    def post(self, request):
        form = StaffInviteActivationForm(request.POST)
        if form.is_valid():
            user = resolve_user_identifier(User, form.cleaned_data['identifier'])
            if user is None:
                form.add_error('code', 'Invalid or expired staff invitation.')
            else:
                try:
                    StaffAccountProvisioningService.activate_invited_account(
                        user=user,
                        code=form.cleaned_data['code'],
                        new_password=form.cleaned_data['new_password'],
                        ip_address=_client_ip(request),
                    )
                except ValidationError:
                    form.add_error('code', 'Invalid or expired staff invitation.')
                else:
                    messages.success(request, 'Staff account activated. Sign in to continue with 2FA.')
                    return redirect('accounts:login')
        return render(request, self.template_name, {'form': form})


class PrivacyNoticeView(View):
    template_name = 'users/privacy.html'

    def get(self, request):
        is_customer = (
            request.user.is_authenticated
            and request.user.role == User.Role.CUSTOMER
        )
        request_form = PrivacyRequestForm(user=request.user) if is_customer else None
        if request_form and request.GET.get('request_type') in PrivacyRequest.RequestType.values:
            request_form.initial['request_type'] = request.GET['request_type']
        return render(request, self.template_name, {
            'controller_name': settings.PRIVACY_CONTROLLER_NAME or 'Emporium Plug',
            'privacy_contact': settings.PRIVACY_CONTACT_EMAIL,
            'privacy_notice_approved': settings.PRIVACY_NOTICE_APPROVED,
            'request_form': request_form,
            'export_form': PrivacyExportForm(user=request.user) if is_customer else None,
            'privacy_requests': (
                request.user.privacy_requests.all()[:20] if is_customer else []
            ),
        })


class CustomerPrivacyRequestView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.role == User.Role.CUSTOMER

    def post(self, request):
        form = PrivacyRequestForm(request.POST, user=request.user)
        if not form.is_valid():
            messages.error(request, 'Privacy request not submitted. Check the form and password.')
            return render(request, 'users/privacy.html', {
                'controller_name': settings.PRIVACY_CONTROLLER_NAME or 'Emporium Plug',
                'privacy_contact': settings.PRIVACY_CONTACT_EMAIL,
                'privacy_notice_approved': settings.PRIVACY_NOTICE_APPROVED,
                'request_form': form,
                'export_form': PrivacyExportForm(user=request.user),
                'privacy_requests': request.user.privacy_requests.all()[:20],
            }, status=400)
        try:
            with transaction.atomic():
                privacy_request = PrivacyRequest.objects.create(
                    user=request.user,
                    request_type=form.cleaned_data['request_type'],
                    details=form.cleaned_data['details'],
                )
        except IntegrityError:
            messages.error(request, 'An open request of this type already exists.')
            return redirect('accounts:privacy')
        AuditTrackingService.log_action(
            user=request.user,
            action_type=AuditLog.ActionTypes.PRIVACY_REQUEST,
            description=f'Privacy request {privacy_request.pk} submitted.',
            ip_address=_client_ip(request),
        )
        messages.success(request, 'Your privacy request has been recorded for review.')
        return redirect('accounts:privacy')


class CustomerPrivacyExportView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.role == User.Role.CUSTOMER

    def post(self, request):
        form = PrivacyExportForm(request.POST, user=request.user)
        if not form.is_valid():
            messages.error(request, 'Password confirmation failed; no data was exported.')
            return redirect('accounts:privacy')
        payload = PersonalDataExportService.build(request.user)
        AuditTrackingService.log_action(
            user=request.user,
            action_type=AuditLog.ActionTypes.PRIVACY_DATA_EXPORT,
            description='Customer downloaded a scoped personal-data export.',
            ip_address=_client_ip(request),
        )
        response = HttpResponse(
            json.dumps(payload, cls=DjangoJSONEncoder, indent=2),
            content_type='application/json; charset=utf-8',
        )
        response['Content-Disposition'] = 'attachment; filename="emporium-plug-personal-data.json"'
        response['Cache-Control'] = 'private, no-store'
        return response


class PrivacyOperationsView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'users/privacy_operations.html'

    def test_func(self):
        return self.request.user.role == User.Role.SUPER_ADMIN

    def get(self, request):
        return render(request, self.template_name, {
            'open_requests': PrivacyRequest.objects.filter(
                status__in=[PrivacyRequest.Status.SUBMITTED, PrivacyRequest.Status.IN_REVIEW],
            ).select_related('user')[:100],
            'recent_requests': PrivacyRequest.objects.filter(
                status__in=[PrivacyRequest.Status.COMPLETED, PrivacyRequest.Status.REJECTED],
            ).select_related('user', 'handled_by')[:100],
        })

    def post(self, request):
        try:
            privacy_request = PrivacyRequestReviewService.resolve(
                request_id=request.POST.get('request_id'),
                actor=request.user,
                password=request.POST.get('manager_password'),
                outcome=request.POST.get('outcome'),
                response_note=request.POST.get('response_note'),
            )
        except (ValidationError, PrivacyRequest.DoesNotExist) as exc:
            messages.error(request, str(exc))
            return redirect('accounts:privacy-operations')
        AuditTrackingService.log_action(
            user=request.user,
            action_type=AuditLog.ActionTypes.PRIVACY_REQUEST,
            description=f'Privacy request {privacy_request.pk} resolved as {privacy_request.status}.',
            ip_address=_client_ip(request),
        )
        messages.success(request, 'Privacy request outcome recorded.')
        return redirect('accounts:privacy-operations')
