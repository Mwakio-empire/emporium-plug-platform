from django.urls import path

from .views import OperationsReportCSVView, OperationsReportWorkspaceView


app_name = 'report_workspace'

urlpatterns = [
    path('', OperationsReportWorkspaceView.as_view(), name='operations'),
    path('export.csv', OperationsReportCSVView.as_view(), name='operations-csv'),
]
