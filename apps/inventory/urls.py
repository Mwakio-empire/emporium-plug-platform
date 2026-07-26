from django.urls import path

from . import views
from . import workspace_views


app_name = 'inventory'
urlpatterns = [
    path('workspace/', workspace_views.InventoryWorkspaceView.as_view(), name='inventory-workspace'),
    path('workspace/intakes/', workspace_views.SupplierIntakeWorkspaceView.as_view(), name='workspace-intake'),
    path('workspace/transfers/', workspace_views.TransferRequestWorkspaceView.as_view(), name='workspace-transfer-request'),
    path('workspace/transfers/<int:transfer_id>/approve/', workspace_views.TransferApproveWorkspaceView.as_view(), name='workspace-transfer-approve'),
    path('workspace/transfers/<int:transfer_id>/dispatch/', workspace_views.TransferDispatchWorkspaceView.as_view(), name='workspace-transfer-dispatch'),
    path('workspace/transfers/<int:transfer_id>/receive/', workspace_views.TransferReceiveWorkspaceView.as_view(), name='workspace-transfer-receive'),
    path('workspace/transfers/<int:transfer_id>/reject/', workspace_views.TransferRejectWorkspaceView.as_view(), name='workspace-transfer-reject'),
    path('workspace/transfers/<int:transfer_id>/cancel/', workspace_views.TransferCancelWorkspaceView.as_view(), name='workspace-transfer-cancel'),
    path('workspace/adjustments/', workspace_views.ManualAdjustmentWorkspaceView.as_view(), name='workspace-adjustment'),
    path('workspace/counts/start/', workspace_views.StockCountStartWorkspaceView.as_view(), name='workspace-count-start'),
    path('workspace/counts/<int:stock_count_id>/complete/', workspace_views.StockCountCompleteWorkspaceView.as_view(), name='workspace-count-complete'),
    path('workspace/counts/<int:stock_count_id>/cancel/', workspace_views.StockCountCancelWorkspaceView.as_view(), name='workspace-count-cancel'),
    path('intakes/', views.StockIntakeListCreateView.as_view(), name='intake-list-create'),
    path('adjustments/', views.ManualStockAdjustmentView.as_view(), name='manual-adjustment'),
    path('counts/', views.StockCountListCreateView.as_view(), name='stock-count-list-create'),
    path('counts/<int:stock_count_id>/lines/<int:line_id>/', views.StockCountLineUpdateView.as_view(), name='stock-count-line-update'),
    path('counts/<int:stock_count_id>/complete/', views.StockCountCompleteView.as_view(), name='stock-count-complete'),
    path('counts/<int:stock_count_id>/cancel/', views.StockCountCancelView.as_view(), name='stock-count-cancel'),
    path('transfers/', views.TransferRequestListCreateView.as_view(), name='transfer-list-create'),
    path('transfers/<int:transfer_id>/approve/', views.TransferApproveView.as_view(), name='transfer-approve'),
    path('transfers/<int:transfer_id>/dispatch/', views.TransferDispatchView.as_view(), name='transfer-dispatch'),
    path('transfers/<int:transfer_id>/receive/', views.TransferReceiveView.as_view(), name='transfer-receive'),
    path('transfers/<int:transfer_id>/confirm/', views.TransferConfirmView.as_view(), name='transfer-confirm'),
    path('transfers/<int:transfer_id>/reject/', views.TransferRejectView.as_view(), name='transfer-reject'),
    path('transfers/<int:transfer_id>/cancel/', views.TransferCancelView.as_view(), name='transfer-cancel'),
]
