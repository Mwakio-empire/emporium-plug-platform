from rest_framework import serializers
from .models import (
    StockAuditLog, StockCount, StockCountLine, StockIntake, StockIntakeLine,
    TransferReceipt, TransferRequest,
)


class TransferRequestSerializer(serializers.ModelSerializer):
    item_name = serializers.SerializerMethodField()
    from_branch_name = serializers.CharField(source='from_branch.name', read_only=True)
    to_branch_name = serializers.CharField(source='to_branch.name', read_only=True)
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True)
    remaining_quantity = serializers.IntegerField(read_only=True)
    receipts = serializers.SerializerMethodField()

    class Meta:
        model = TransferRequest
        fields = [
            'id', 'item_name', 'quantity', 'from_branch_name', 'to_branch_name',
            'status', 'requested_by_name', 'requested_at', 'approved_at',
            'dispatched_at', 'confirmed_at', 'received_quantity',
            'remaining_quantity', 'rejection_reason', 'cancellation_reason',
            'notes', 'receipts',
        ]

    def get_item_name(self, obj):
        return str(obj.variant) if obj.variant else obj.product.name

    def get_receipts(self, obj):
        return TransferReceiptSerializer(obj.receipts.all(), many=True).data


class TransferReceiptSerializer(serializers.ModelSerializer):
    received_by_name = serializers.CharField(source='received_by.get_full_name', read_only=True)

    class Meta:
        model = TransferReceipt
        fields = ['id', 'quantity', 'received_by_name', 'received_at', 'note']


class TransferRequestCreateSerializer(serializers.Serializer):
    to_branch_id = serializers.IntegerField()
    from_branch_id = serializers.IntegerField(required=False)  # SUPER_ADMIN only
    product_id = serializers.IntegerField(required=False)
    variant_id = serializers.IntegerField(required=False)
    quantity = serializers.IntegerField(min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, data):
        if bool(data.get('product_id')) == bool(data.get('variant_id')):
            raise serializers.ValidationError("Provide exactly one of product_id or variant_id.")
        return data


class TransferReceiptCreateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, default='')


class StockIntakeLineCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(required=False)
    variant_id = serializers.IntegerField(required=False)
    quantity = serializers.IntegerField(min_value=1)

    def validate(self, data):
        if bool(data.get('product_id')) == bool(data.get('variant_id')):
            raise serializers.ValidationError("Provide exactly one of product_id or variant_id.")
        return data


class StockIntakeCreateSerializer(serializers.Serializer):
    branch_id = serializers.IntegerField(required=False)
    supplier_name = serializers.CharField(max_length=150)
    delivery_reference = serializers.CharField(max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    lines = StockIntakeLineCreateSerializer(many=True, allow_empty=False)


class StockIntakeLineSerializer(serializers.ModelSerializer):
    item_name = serializers.SerializerMethodField()

    class Meta:
        model = StockIntakeLine
        fields = ['id', 'item_name', 'quantity']

    def get_item_name(self, obj):
        return str(obj.variant or obj.product)


class StockIntakeSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    received_by_name = serializers.CharField(source='received_by.get_full_name', read_only=True)
    lines = StockIntakeLineSerializer(many=True, read_only=True)

    class Meta:
        model = StockIntake
        fields = [
            'id', 'branch_name', 'supplier_name', 'delivery_reference',
            'received_by_name', 'received_at', 'notes', 'lines',
        ]


class ManualStockAdjustmentSerializer(serializers.Serializer):
    branch_id = serializers.IntegerField(required=False)
    product_id = serializers.IntegerField(required=False)
    variant_id = serializers.IntegerField(required=False)
    change_amount = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=[
        StockAuditLog.Reason.CORRECTION,
        StockAuditLog.Reason.DAMAGE,
        StockAuditLog.Reason.THEFT,
    ])
    reference_number = serializers.CharField(max_length=100)
    note = serializers.CharField(max_length=1000)

    def validate(self, data):
        if bool(data.get('product_id')) == bool(data.get('variant_id')):
            raise serializers.ValidationError("Provide exactly one of product_id or variant_id.")
        if data['change_amount'] == 0:
            raise serializers.ValidationError("change_amount cannot be zero.")
        return data


class StockCountLineSerializer(serializers.ModelSerializer):
    item_name = serializers.SerializerMethodField()
    variance = serializers.IntegerField(read_only=True)

    class Meta:
        model = StockCountLine
        fields = ['id', 'item_name', 'expected_quantity', 'counted_quantity', 'variance']

    def get_item_name(self, obj):
        return str(obj.variant or obj.product)


class StockCountSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    lines = StockCountLineSerializer(many=True, read_only=True)

    class Meta:
        model = StockCount
        fields = [
            'id', 'branch_name', 'status', 'started_at', 'completed_at',
            'cancelled_at', 'notes', 'cancellation_reason', 'lines',
        ]


class StockCountCreateSerializer(serializers.Serializer):
    branch_id = serializers.IntegerField(required=False)
    stock_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, allow_empty=False,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class StockCountQuantitySerializer(serializers.Serializer):
    counted_quantity = serializers.IntegerField(min_value=0)
