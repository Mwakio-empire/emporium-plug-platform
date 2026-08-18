# apps/logistics/urls.py

from django.urls import path
from . import views
from . import workspace_views

app_name = 'logistics'

urlpatterns = [
    path('towns/', views.TownListView.as_view(), name='towns'),
    path('workspace/', workspace_views.FulfilmentWorkspaceView.as_view(), name='fulfilment-workspace'),
    path('workspace/orders/<int:order_id>/packing/start/', workspace_views.PackingStartView.as_view(), name='packing-start'),
    path('workspace/packing/<int:checklist_id>/lines/<int:line_id>/check/', workspace_views.PackingLineCheckView.as_view(), name='packing-line-check'),
    path('workspace/packing/<int:checklist_id>/complete/', workspace_views.PackingCompleteView.as_view(), name='packing-complete'),
    path('workspace/orders/<int:order_id>/ready-pickup/', workspace_views.PickupReadyView.as_view(), name='pickup-ready'),
    path('workspace/orders/<str:order_number>/assign-rider/', workspace_views.RiderAssignWorkspaceView.as_view(), name='workspace-assign-rider'),
    path('workspace/pickups/confirm/', workspace_views.PickupConfirmWorkspaceView.as_view(), name='workspace-confirm-pickup'),
    path('workspace/orders/<int:order_id>/parcel/dispatch/', workspace_views.ParcelDispatchWorkspaceView.as_view(), name='parcel-dispatch'),
    path('workspace/orders/<int:order_id>/parcel/arrived/', workspace_views.ParcelArrivedWorkspaceView.as_view(), name='parcel-arrived'),
    path('workspace/orders/<int:order_id>/parcel/collected/', workspace_views.ParcelCollectedWorkspaceView.as_view(), name='parcel-collected'),
    path('zones/', views.DeliveryZoneListView.as_view(), name='zones'),
    path('pickup-slots/', views.PickupSlotListView.as_view(), name='pickup-slots'),
    path('my-deliveries/', views.RiderDeliveryQueueView.as_view(), name='rider-queue'),
    path('delivery/<int:assignment_id>/update/', views.RiderUpdateDeliveryStatusView.as_view(), name='update-delivery'),
    path('assign-rider/', views.AssignRiderView.as_view(), name='assign-rider'),
    path('confirm-pickup/', views.ConfirmPickupView.as_view(), name='confirm-pickup'),
]
