from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('my-shift/', views.MyShiftReportView.as_view(), name='my-shift'),
    path('branch-daily/', views.BranchDailySummaryView.as_view(), name='branch-daily'),
    path('operations/', views.OperationsReportView.as_view(), name='operations'),
]
