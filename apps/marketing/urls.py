from django.urls import path
from . import views
from . import workspace_views
app_name = 'marketing'
urlpatterns = [
    path('reviews/', views.ProductReviewListCreateView.as_view(), name='reviews'),
    path('reviews/moderation/', views.ReviewModerationQueueView.as_view(), name='review-moderation'),
    path('reviews/<int:review_id>/moderate/', views.ReviewModerationDecisionView.as_view(), name='review-moderate'),
    path('returns/', views.MyReturnRequestListCreateView.as_view(), name='returns'),
    path('returns/branch/', views.BranchReturnRequestListView.as_view(), name='returns-branch'),
    path('returns/<int:return_id>/decide/', views.ReturnRequestDecisionView.as_view(), name='return-decide'),
    path('my-returns/', workspace_views.CustomerReturnsPageView.as_view(), name='my-returns'),
    path('my-returns/create/', workspace_views.CustomerReturnCreateView.as_view(), name='customer-return-create'),
    path('products/<int:product_id>/review/', workspace_views.CustomerReviewCreateView.as_view(), name='customer-review-create'),
    path('operations/', workspace_views.MarketingWorkspaceView.as_view(), name='operations-workspace'),
    path('operations/reviews/<int:review_id>/decide/', workspace_views.WorkspaceReviewDecisionView.as_view(), name='workspace-review-decide'),
    path('operations/returns/<int:return_id>/decide/', workspace_views.WorkspaceReturnDecisionView.as_view(), name='workspace-return-decide'),
]
