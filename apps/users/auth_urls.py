from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.CustomerLoginView.as_view(), name='login'),
    path('signup/', views.CustomerSignupView.as_view(), name='signup'),
    path('logout/', views.CustomerLogoutView.as_view(), name='logout'),
    path('profile/', views.CustomerProfileView.as_view(), name='profile'),
    path('password/change/', views.AuthenticatedPasswordChangeView.as_view(), name='password-change'),
    path('verify-otp/', views.OTPVerifyView.as_view(), name='verify-otp'),
    path('verify-otp/resend/', views.OTPResendView.as_view(), name='resend-otp'),
    path('verify-staff-otp/', views.StaffOTPVerifyView.as_view(), name='verify-staff-otp'),
    path('verify-staff-otp/resend/', views.StaffOTPResendView.as_view(), name='resend-staff-otp'),
    path('forgot-password/', views.PasswordResetRequestView.as_view(), name='forgot-password'),
    path('reset-password/', views.PasswordResetConfirmView.as_view(), name='reset-password-confirm'),
    path('staff/invite/', views.StaffAccountProvisionView.as_view(), name='staff-invite'),
    path('staff/activate/', views.StaffInviteActivationView.as_view(), name='staff-activate'),
    path('privacy/', views.PrivacyNoticeView.as_view(), name='privacy'),
    path('privacy/request/', views.CustomerPrivacyRequestView.as_view(), name='privacy-request'),
    path('privacy/export/', views.CustomerPrivacyExportView.as_view(), name='privacy-export'),
    path('privacy/operations/', views.PrivacyOperationsView.as_view(), name='privacy-operations'),
]
