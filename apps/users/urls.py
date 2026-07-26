# apps/users/urls.py
from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # API auth
    path('api/register/', views.CustomerRegistrationAPIView.as_view(), name='api-register'),
    path('api/register/verify/', views.SignupOTPVerificationAPIView.as_view(), name='api-register-verify'),
    path('api/login/', views.CustomerTokenObtainPairView.as_view(), name='api-login'),
    path('api/logout/', views.APILogoutView.as_view(), name='api-logout'),
    path('api/token/refresh/', views.VersionedTokenRefreshView.as_view(), name='api-token-refresh'),
    path('api/profile/', views.UserProfileAPIView.as_view(), name='api-profile'),
    path('api/staff/', views.StaffAccountProvisionAPIView.as_view(), name='api-staff-create'),
    path('api/staff/invite/activate/', views.StaffInviteActivationAPIView.as_view(), name='api-staff-invite-activate'),
    path('api/staff/<int:user_id>/invite/resend/', views.StaffInviteResendAPIView.as_view(), name='api-staff-invite-resend'),
]
