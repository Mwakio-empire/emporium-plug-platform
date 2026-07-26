from django.urls import path
from . import views
app_name = 'notifications'
urlpatterns = [
    path('operations/', views.NotificationOperationsView.as_view(), name='operations'),
    path('sms/inbound/', views.sms_inbound_webhook, name='sms_inbound'),
]
