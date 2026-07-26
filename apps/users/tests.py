# apps/users/tests.py
#
# Django built-in test runner (APITestCase, unittest-style).
# Placed as a single tests.py -- matches your confirmed structure
# (users/ has tests.py, not a tests/ folder like catalog/ does).
#
# Field references traced to verified users/models.py:
#   User extends AbstractUser -- username, first_name, last_name,
#   date_joined, get_full_name() all inherited, not custom.
#   phone_number: CharField(unique=True) -- the required field
#   email: EmailField(unique=True, blank=True, null=True) -- optional
#   role: Role.CUSTOMER / STAFF / INVENTORY_MANAGER / BRANCH_MANAGER / SUPER_ADMIN
#   USERNAME_FIELD = 'username' (default, not overridden)
#   CustomUserManager.create_user(username, phone_number, password, **extra)
#
# URL names traced to apps/users/urls.py as applied:
#   users:api-register, users:api-login, users:api-token-refresh, users:api-profile
#   (full paths are /api/users/api/register/ etc. -- the redundant prefix
#   is a known structural quirk, not something these tests need to change)
#
# Uniqueness discipline: every test that creates a User uses a distinct
# phone_number/email/username suffix so an unrelated uniqueness constraint
# never crashes a test that isn't testing uniqueness itself. The one test
# that DOES test duplicate email deliberately reuses an email on purpose --
# that is the single case where the constraint is the point of the test.

from decimal import Decimal
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.contrib.auth.hashers import check_password
from django.test import Client
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch
from branches.models import Branch
from .forms import PasswordResetConfirmForm, PasswordResetRequestForm
from users.models import OTPVerification
from users.otp_services import OTPService
from users.tasks import purge_unverified_accounts
from analytics.models import AuditLog

User = get_user_model()


class PasswordResetFormTests(APITestCase):

    def test_request_form_normalizes_identifier(self):
        form = PasswordResetRequestForm({'identifier': '  customer@example.com  '})

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['identifier'], 'customer@example.com')

    def test_confirm_form_rejects_mismatched_passwords(self):
        form = PasswordResetConfirmForm({
            'code': '123456',
            'new_password': 'StrongResetPass123!',
            'confirm_new_password': 'DifferentResetPass123!',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('confirm_new_password', form.errors)

    def test_confirm_form_applies_password_validation(self):
        form = PasswordResetConfirmForm({
            'code': '123456',
            'new_password': '12345678',
            'confirm_new_password': '12345678',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('new_password', form.errors)


class CustomerRegistrationTests(APITestCase):

    def setUp(self):
        cache.clear()

    def _valid_payload(self, suffix):
        """Builds a registration payload with a unique phone/email per call."""
        return {
            'email': f'customer{suffix}@test.com',
            'phone_number': f'+25470000{suffix}',
            'first_name': 'Test',
            'last_name': f'User{suffix}',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
        }

    @patch('users.otp_services.secrets.randbelow', return_value=123456)
    def test_registration_requires_otp_before_tokens_are_issued(self, _randbelow):
        """
        WHAT: POST valid registration data
        EXPECT: 201, no tokens, inactive customer pending OTP verification
                of anything the client might try to send
        """
        url = reverse('users:api-register')
        response = self.client.post(url, self._valid_payload('0001'), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('tokens', response.data)
        self.assertTrue(response.data['verification_required'])
        self.assertEqual(response.data['user']['role'], User.Role.CUSTOMER)
        user = User.objects.get(phone_number='+254700000001')
        self.assertFalse(user.is_active)
        otp = OTPVerification.objects.get(user=user, purpose=OTPVerification.Purpose.SIGNUP)
        self.assertNotEqual(otp.code, '123456')
        self.assertTrue(check_password('123456', otp.code))

        verification = self.client.post(reverse('users:api-register-verify'), {
            'identifier': user.phone_number,
            'code': '123456',
        }, format='json')
        self.assertEqual(verification.status_code, status.HTTP_200_OK)
        self.assertIn('access', verification.data['tokens'])
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_registration_auto_generates_username_from_phone(self):
        """
        WHAT: Register without ever supplying a username (not exposed by
              the serializer at all)
        EXPECT: User is created successfully -- this is the exact bug
                that was crashing before the create() fix
        """
        url = reverse('users:api-register')
        payload = self._valid_payload('0002')
        response = self.client.post(url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(phone_number=payload['phone_number'])
        self.assertTrue(created_user.username)  # non-empty, auto-generated

    def test_role_cannot_be_overridden_by_client(self):
        """
        WHAT: Client attempts to smuggle role=SUPER_ADMIN into the payload
        EXPECT: Serializer has no 'role' field at all -- ignored entirely,
                account is still created as CUSTOMER
        """
        url = reverse('users:api-register')
        payload = self._valid_payload('0003')
        payload['role'] = User.Role.SUPER_ADMIN
        response = self.client.post(url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['role'], User.Role.CUSTOMER)

    def test_mismatched_passwords_rejected(self):
        """
        WHAT: password != confirm_password
        EXPECT: 400, confirm_password error -- no account created
        """
        url = reverse('users:api-register')
        payload = self._valid_payload('0004')
        payload['confirm_password'] = 'DifferentPassword123!'
        response = self.client.post(url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirm_password', response.data)
        self.assertFalse(User.objects.filter(phone_number=payload['phone_number']).exists())

    def test_weak_password_rejected_by_django_validators(self):
        """
        WHAT: A common, all-numeric, too-short password
        EXPECT: 400 -- validate_password() runs Django's built-in validators
        """
        url = reverse('users:api-register')
        payload = self._valid_payload('0005')
        payload['password'] = '12345678'
        payload['confirm_password'] = '12345678'
        response = self.client.post(url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_duplicate_phone_number_rejected(self):
        """
        WHAT: A phone_number that already belongs to another account
        EXPECT: 400 -- DRF's auto-generated UniqueValidator on the
                unique=True model field catches this before create()
                is ever called, so it never reaches create_user()
        """
        url = reverse('users:api-register')
        first_payload = self._valid_payload('0006')
        self.client.post(url, first_payload, format='json')

        second_payload = self._valid_payload('0007')
        second_payload['phone_number'] = first_payload['phone_number']  # deliberate clash
        response = self.client.post(url, second_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number', response.data)

    def test_duplicate_email_rejected(self):
        """
        WHAT: An email that already belongs to another account
        EXPECT: 400 -- this is the ONE test that deliberately reuses an
                email, because uniqueness is exactly what's being tested.
                Every other test in this file uses a distinct email so
                this constraint never interferes with unrelated behaviour.
        """
        url = reverse('users:api-register')
        first_payload = self._valid_payload('0008')
        self.client.post(url, first_payload, format='json')

        second_payload = self._valid_payload('0009')
        second_payload['email'] = first_payload['email']  # deliberate clash
        response = self.client.post(url, second_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)


class LoginTests(APITestCase):

    def setUp(self):
        """
        Creates a user directly via the manager -- bypassing the
        registration endpoint -- so login tests are isolated from
        registration behaviour.
        """
        self.known_password = 'LoginTestPass123!'
        self.user = User.objects.create_user(
            username='loginuser0001',
            phone_number='+254711000001',
            email='loginuser0001@test.com',
            first_name='Login',
            last_name='Tester',
            password=self.known_password,
            role=User.Role.CUSTOMER,
        )

    def test_login_with_correct_credentials_returns_tokens(self):
        """
        WHAT: POST username + correct password
        EXPECT: 200, access and refresh tokens present
        NOTE: USERNAME_FIELD is 'username' (verified, not overridden to
              email) -- login payload uses 'username', not 'email'.
        """
        url = reverse('users:api-login')
        response = self.client.post(url, {
            'username': self.user.username,
            'password': self.known_password,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_login_accepts_phone_number(self):
        response = self.client.post(reverse('users:api-login'), {
            'username': self.user.phone_number,
            'password': self.known_password,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_accepts_email_case_insensitively(self):
        response = self.client.post(reverse('users:api-login'), {
            'username': self.user.email.upper(),
            'password': self.known_password,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_with_wrong_password_returns_401(self):
        """
        WHAT: POST correct username, wrong password
        EXPECT: 401
        """
        url = reverse('users:api-login')
        response = self.client.post(url, {
            'username': self.user.username,
            'password': 'WrongPassword999!',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_customer_cannot_obtain_jwt(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = self.client.post(reverse('users:api-login'), {
            'username': self.user.username,
            'password': self.known_password,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_repeated_failures_persistently_lock_account(self):
        url = reverse('users:api-login')
        for _ in range(5):
            self.client.post(url, {
                'username': self.user.username,
                'password': 'WrongPassword999!',
            }, format='json')

        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 5)
        self.assertGreater(self.user.locked_until, timezone.now())
        response = self.client.post(url, {
            'username': self.user.username,
            'password': self.known_password,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_staff_cannot_bypass_two_factor_with_jwt_login(self):
        branch = Branch.objects.create(name='JWT Staff Branch', location='Nakuru')
        staff = User.objects.create_user(
            username='jwtstaff', phone_number='+254711000099',
            email='jwtstaff@test.com', password='StaffPass123!',
            role=User.Role.STAFF, branch=branch,
        )
        response = self.client.post(reverse('users:api-login'), {
            'username': staff.username,
            'password': 'StaffPass123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_token_refresh_returns_new_access_token(self):
        """
        WHAT: POST a valid refresh token to the refresh endpoint
        EXPECT: 200, new access token returned
        """
        login_url = reverse('users:api-login')
        login_response = self.client.post(login_url, {
            'username': self.user.username,
            'password': self.known_password,
        }, format='json')
        refresh_token = login_response.data['refresh']

        refresh_url = reverse('users:api-token-refresh')
        response = self.client.post(refresh_url, {'refresh': refresh_token}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_api_logout_revokes_current_access_and_refresh_tokens(self):
        login = self.client.post(reverse('users:api-login'), {
            'username': self.user.username,
            'password': self.known_password,
        }, format='json')
        access = login.data['access']
        refresh = login.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        response = self.client.post(
            reverse('users:api-logout'), {'refresh': refresh}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            self.client.get(reverse('users:api-profile')).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.client.post(
                reverse('users:api-token-refresh'), {'refresh': refresh}, format='json',
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class OTPAttemptLimitTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='otpuser', phone_number='+254722909090',
            email='otpuser@test.com', password='OTPUserPass123!',
            role=User.Role.CUSTOMER, is_active=False,
        )

    @patch('users.otp_services.secrets.randbelow', return_value=123456)
    def test_otp_is_hashed_and_locks_after_five_wrong_attempts(self, _randbelow):
        otp = OTPService.generate_and_send(self.user)
        self.assertNotEqual(otp.code, '123456')
        for _ in range(5):
            with self.assertRaises(ValidationError):
                OTPService.verify(self.user, '000000')
        with self.assertRaisesMessage(ValidationError, 'Too many incorrect attempts'):
            OTPService.verify(self.user, '123456')

    @patch('users.otp_services.secrets.randbelow', return_value=123456)
    def test_expired_otp_is_rejected(self, _randbelow):
        otp = OTPService.generate_and_send(self.user)
        OTPVerification.objects.filter(pk=otp.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        with self.assertRaisesMessage(ValidationError, 'expired'):
            OTPService.verify(self.user, '123456')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    @patch('users.otp_services.secrets.randbelow', return_value=123456)
    def test_verified_otp_cannot_be_reused(self, _randbelow):
        OTPService.generate_and_send(self.user)
        OTPService.verify(self.user, '123456')
        with self.assertRaisesMessage(ValidationError, 'No pending verification code'):
            OTPService.verify(self.user, '123456')

    @patch('users.otp_services.secrets.randbelow', return_value=123456)
    def test_resend_cooldown_is_enforced(self, _randbelow):
        OTPService.generate_and_send(self.user)
        with self.assertRaisesMessage(ValidationError, 'Please wait'):
            OTPService.generate_and_send(self.user)


class UserProfileTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='profileuser0001',
            phone_number='+254722000001',
            email='profileuser0001@test.com',
            first_name='Profile',
            last_name='Owner',
            password='ProfilePass123!',
            role=User.Role.CUSTOMER,
        )

    def test_unauthenticated_request_rejected(self):
        """
        WHAT: GET /profile/ with no auth token
        EXPECT: 401
        """
        url = reverse('users:api-profile')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_sees_own_profile(self):
        """
        WHAT: GET /profile/ authenticated as the owner
        EXPECT: 200, correct phone_number and email returned
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('users:api-profile')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['phone_number'], str(self.user.phone_number))
        self.assertEqual(response.data['email'], self.user.email)

    def test_patch_updates_first_name(self):
        """
        WHAT: PATCH first_name
        EXPECT: 200, first_name updated in DB
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('users:api-profile')
        response = self.client.patch(url, {'first_name': 'Updated'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')

    def test_patch_cannot_change_role(self):
        """
        WHAT: PATCH attempts to escalate role to SUPER_ADMIN
        EXPECT: role field is read_only -- request succeeds but role
                is silently ignored, user remains CUSTOMER
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('users:api-profile')
        response = self.client.patch(url, {'role': User.Role.SUPER_ADMIN}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.CUSTOMER)

    def test_patch_cannot_change_email(self):
        """
        WHAT: PATCH attempts to change email
        EXPECT: email field is read_only -- silently ignored
        """
        self.client.force_authenticate(user=self.user)
        original_email = self.user.email
        url = reverse('users:api-profile')
        response = self.client.patch(url, {'email': 'hacked@test.com'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, original_email)


class InventoryManagerBranchScopeTests(APITestCase):
    def test_inventory_manager_requires_branch(self):
        with self.assertRaises(ValidationError):
            User.objects.create_user(
                username='unscoped_inventory_manager',
                phone_number='+254700889999',
                email='unscoped.inventory@example.test',
                role=User.Role.INVENTORY_MANAGER,
            )

    def test_inventory_manager_with_branch_is_valid(self):
        branch = Branch.objects.create(name='Inventory Scope Branch', location='Nakuru')
        manager = User.objects.create_user(
            username='scoped_inventory_manager',
            phone_number='+254700889998',
            email='scoped.inventory@example.test',
            role=User.Role.INVENTORY_MANAGER,
            branch=branch,
        )
        self.assertEqual(manager.branch, branch)


class HTMLAuthenticationSecurityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.branch = Branch.objects.create(name='Auth Branch', location='Nakuru')
        self.staff = User.objects.create_user(
            username='authstaff', phone_number='+254733000001',
            email='authstaff@test.com', password='StaffPass123!',
            role=User.Role.STAFF, branch=self.branch,
        )

    @patch('users.otp_services.secrets.randbelow', return_value=654321)
    def test_staff_password_does_not_create_session_before_otp(self, _randbelow):
        response = self.client.post(reverse('accounts:login'), {
            'identifier': self.staff.username,
            'password': 'StaffPass123!',
        })
        self.assertRedirects(response, reverse('accounts:verify-staff-otp'))
        self.assertNotIn('_auth_user_id', self.client.session)

        response = self.client.post(reverse('accounts:verify-staff-otp'), {'code': '654321'})
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.staff.pk)

    @patch('users.otp_services.secrets.randbelow', return_value=111222)
    def test_external_next_redirect_is_rejected(self, _randbelow):
        response = self.client.post(reverse('accounts:login'), {
            'identifier': self.staff.username,
            'password': 'StaffPass123!',
            'next': 'https://attacker.example/steal',
        })
        self.assertRedirects(response, reverse('accounts:verify-staff-otp'))
        response = self.client.post(reverse('accounts:verify-staff-otp'), {'code': '111222'})
        self.assertEqual(response.url, '/pos-desk/')

    def test_login_post_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(reverse('accounts:login'), {
            'identifier': self.staff.username,
            'password': 'StaffPass123!',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_html_logout_flushes_authenticated_session_and_is_audited(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, '/')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertTrue(AuditLog.objects.filter(
            user=self.staff, action_type=AuditLog.ActionTypes.LOGOUT,
        ).exists())

    def test_inactive_staff_cannot_enter_customer_activation_flow(self):
        self.staff.is_active = False
        self.staff.save(update_fields=['is_active'])
        response = self.client.post(reverse('accounts:login'), {
            'identifier': self.staff.username,
            'password': 'StaffPass123!',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('pending_verification_user_id', self.client.session)
        self.assertNotIn('pending_staff_login_user_id', self.client.session)

    def test_expired_pending_staff_session_is_rejected(self):
        session = self.client.session
        session['pending_staff_login_user_id'] = self.staff.pk
        session['pending_staff_login_user_id_created_at'] = (
            timezone.now().timestamp() - 601
        )
        session.save()
        response = self.client.get(reverse('accounts:verify-staff-otp'))
        self.assertRedirects(response, reverse('accounts:login'))


class StaffProvisioningTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.branch = Branch.objects.create(name='Provision Branch', location='Nakuru')
        self.other_branch = Branch.objects.create(name='Other Provision Branch', location='Nairobi')
        self.manager = User.objects.create_user(
            username='provisionmanager', phone_number='+254755100001',
            email='provisionmanager@test.com', password='ManagerPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.super_admin = User.objects.create_superuser(
            username='provisionsuper', phone_number='+254755100002',
            email='provisionsuper@test.com', password='SuperPass123!',
        )

    def _payload(self, **overrides):
        payload = {
            'phone_number': '0755100003',
            'email': 'New.Staff@Test.com',
            'first_name': 'New',
            'last_name': 'Staff',
            'role': User.Role.STAFF,
            'branch_id': self.branch.pk,
        }
        payload.update(overrides)
        return payload

    @patch('users.otp_services.secrets.randbelow', return_value=246810)
    def test_branch_manager_creates_inactive_staff_invitation(self, _randbelow):
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            reverse('users:api-staff-create'), self._payload(), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        staff = User.objects.get(phone_number='+254755100003')
        self.assertFalse(staff.is_active)
        self.assertFalse(staff.has_usable_password())
        self.assertEqual(staff.email, 'new.staff@test.com')
        self.assertTrue(OTPVerification.objects.filter(
            user=staff, purpose=OTPVerification.Purpose.STAFF_INVITE,
        ).exists())

    def test_branch_manager_cannot_create_staff_for_other_branch(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(reverse('users:api-staff-create'), self._payload(
            branch_id=self.other_branch.pk,
        ), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_branch_manager_cannot_create_elevated_role(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(reverse('users:api-staff-create'), self._payload(
            role=User.Role.BRANCH_MANAGER,
        ), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_cannot_provision_staff(self):
        customer = User.objects.create_user(
            username='provisioncustomer', phone_number='+254755100004',
            email='provisioncustomer@test.com', password='CustomerPass123!',
        )
        self.client.force_authenticate(user=customer)
        response = self.client.post(
            reverse('users:api-staff-create'), self._payload(), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('users.otp_services.secrets.randbelow', return_value=246810)
    def test_invited_staff_sets_password_then_still_requires_login_2fa(self, _randbelow):
        self.client.force_authenticate(user=self.manager)
        created = self.client.post(
            reverse('users:api-staff-create'), self._payload(), format='json',
        )
        self.client.force_authenticate(user=None)
        activation = self.client.post(reverse('users:api-staff-invite-activate'), {
            'identifier': '+254755100003',
            'code': '246810',
            'new_password': 'ActivatedStaffPass123!',
            'confirm_password': 'ActivatedStaffPass123!',
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(activation.status_code, status.HTTP_200_OK)
        staff = User.objects.get(phone_number='+254755100003')
        self.assertTrue(staff.is_active)
        self.assertIsNotNone(staff.activated_at)
        self.assertTrue(staff.check_password('ActivatedStaffPass123!'))
        jwt_login = self.client.post(reverse('users:api-login'), {
            'username': staff.username,
            'password': 'ActivatedStaffPass123!',
        }, format='json')
        self.assertEqual(jwt_login.status_code, status.HTTP_403_FORBIDDEN)

    @patch('users.otp_services.secrets.randbelow', return_value=135790)
    def test_super_admin_can_create_branch_manager_invitation(self, _randbelow):
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.post(reverse('users:api-staff-create'), self._payload(
            phone_number='+254755100005',
            email='new.manager@test.com',
            role=User.Role.BRANCH_MANAGER,
            branch_id=self.other_branch.pk,
        ), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_staff_invitation_page_requires_manager_role(self):
        customer = User.objects.create_user(
            username='staffpagecustomer', phone_number='+254755100006',
            email='staffpagecustomer@test.com', password='CustomerPass123!',
        )
        self.client.force_login(customer)
        response = self.client.get(reverse('accounts:staff-invite'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('users.otp_services.secrets.randbelow', return_value=112233)
    def test_branch_manager_can_invite_and_staff_can_activate_in_browser(self, _randbelow):
        self.client.force_login(self.manager)
        page = self.client.get(reverse('accounts:staff-invite'))
        self.assertEqual(page.status_code, status.HTTP_200_OK)
        response = self.client.post(reverse('accounts:staff-invite'), self._payload(
            phone_number='0755100007',
            email='browser.staff@test.com',
            branch=self.branch.pk,
        ))
        self.assertRedirects(response, reverse('accounts:staff-invite'))
        invited = User.objects.get(phone_number='+254755100007')
        self.assertFalse(invited.is_active)

        self.client.logout()
        activation_page = self.client.get(reverse('accounts:staff-activate'))
        self.assertEqual(activation_page.status_code, status.HTTP_200_OK)
        activated = self.client.post(reverse('accounts:staff-activate'), {
            'identifier': 'browser.staff@test.com',
            'code': '112233',
            'new_password': 'BrowserStaffPass123!',
            'confirm_password': 'BrowserStaffPass123!',
        })
        self.assertRedirects(activated, reverse('accounts:login'))
        invited.refresh_from_db()
        self.assertTrue(invited.is_active)
        self.assertTrue(invited.check_password('BrowserStaffPass123!'))


class UnverifiedAccountCleanupTests(APITestCase):
    def test_cleanup_does_not_delete_a_deactivated_verified_customer(self):
        user = User.objects.create_user(
            username='deactivatedcustomer', phone_number='+254755200001',
            email='deactivated@test.com', password='CustomerPass123!',
            activated_at=timezone.now() - timedelta(days=30),
        )
        User.objects.filter(pk=user.pk).update(
            is_active=False,
            date_joined=timezone.now() - timedelta(days=2),
        )
        purge_unverified_accounts()
        self.assertTrue(User.objects.filter(pk=user.pk).exists())


class PasswordResetRevocationTests(APITestCase):
    def setUp(self):
        cache.clear()

    @patch('users.otp_services.secrets.randbelow', return_value=909090)
    def test_password_reset_invalidates_existing_jwt(self, _randbelow):
        user = User.objects.create_user(
            username='resetuser', phone_number='+254744000001',
            email='resetuser@test.com', password='OriginalPass123!',
            role=User.Role.CUSTOMER,
        )
        login = self.client.post(reverse('users:api-login'), {
            'username': user.username,
            'password': 'OriginalPass123!',
        }, format='json')
        access = login.data['access']

        self.client.post(reverse('accounts:forgot-password'), {'identifier': user.email})
        response = self.client.post(reverse('accounts:reset-password-confirm'), {
            'code': '909090',
            'new_password': 'ReplacementPass123!',
            'confirm_new_password': 'ReplacementPass123!',
        })
        self.assertRedirects(response, reverse('accounts:login'))

        api_client = self.client_class()
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        revoked = api_client.get(reverse('users:api-profile'))
        self.assertEqual(revoked.status_code, status.HTTP_401_UNAUTHORIZED)
