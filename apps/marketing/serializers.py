#apps/marketing/serializers.py
from rest_framework import serializers
from .models import ProductReview, ReturnRequest
class ProductReviewCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=2000)
class ProductReviewSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    product_name = serializers.CharField(source='product.name', read_only=True)
    class Meta:
        model = ProductReview
        fields = [
            'id', 'product', 'product_name', 'customer_name', 'rating',
            'comment', 'is_verified_purchase', 'is_approved', 'created_at',
        ]
        read_only_fields = fields
    def get_customer_name(self, obj):
        return obj.customer.first_name.strip() if obj.customer.first_name else 'Verified customer'
class ReturnRequestCreateSerializer(serializers.Serializer):
    order_number = serializers.CharField()
    order_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(min_length=5, max_length=2000)
class ReturnRequestSerializer(serializers.ModelSerializer):
    item_name = serializers.SerializerMethodField()
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    branch_name = serializers.CharField(source='order.branch.name', read_only=True)
    class Meta:
        model = ReturnRequest
        fields = [
            'id', 'order_number', 'branch_name', 'item_name',
            'quantity', 'reason', 'status', 'item_condition',
            'stock_disposition', 'refund_status', 'decision_reason',
            'decided_at', 'created_at',
        ]
        read_only_fields = fields
    def get_item_name(self, obj):
        item = obj.order_item
        return str(item.variant) if item.variant else item.product.name
class ReturnDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=['APPROVED', 'REJECTED'])
    reason = serializers.CharField(min_length=5, max_length=2000)
    item_condition = serializers.ChoiceField(
        choices=ReturnRequest.ItemCondition.choices,
        required=False,
        default=ReturnRequest.ItemCondition.UNKNOWN,
    )
    stock_disposition = serializers.ChoiceField(
        choices=ReturnRequest.StockDisposition.choices,
        required=False,
        allow_blank=True,
        default='',
    )
    refund_status = serializers.ChoiceField(
        choices=ReturnRequest.RefundStatus.choices,
        required=False,
        default=ReturnRequest.RefundStatus.NOT_REQUIRED,
    )

    def validate(self, attrs):
        if attrs['decision'] == 'APPROVED':
            if attrs['item_condition'] == ReturnRequest.ItemCondition.UNKNOWN:
                raise serializers.ValidationError({'item_condition': 'Assess the item before approval.'})
            if not attrs['stock_disposition']:
                raise serializers.ValidationError({'stock_disposition': 'Choose a stock disposition.'})
        return attrs


class ReviewModerationSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=['APPROVED', 'REJECTED'])
    reason = serializers.CharField(min_length=5, max_length=1000)
