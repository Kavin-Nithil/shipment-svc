from rest_framework import serializers
from .models import Shipment, ShipmentHistory


class ShipmentHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentHistory
        fields = ['id', 'status', 'location', 'description', 'timestamp']
        read_only_fields = ['id', 'timestamp']


class ShipmentSerializer(serializers.ModelSerializer):
    history = ShipmentHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Shipment
        fields = [
            'id', 'order_id', 'tracking_no', 'carrier', 'status',
            'shipped_at', 'delivered_at', 'created_at', 'updated_at',
            'shipping_address', 'estimated_delivery', 'actual_weight',
            'notes', 'history'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'shipped_at', 'delivered_at']

    def validate_tracking_no(self, value):
        """Ensure tracking number follows expected format"""
        if not value.startswith('TRK'):
            raise serializers.ValidationError("Tracking number must start with 'TRK'")
        return value

    def validate_order_id(self, value):
        """Validate order_id is positive"""
        if value <= 0:
            raise serializers.ValidationError("Order ID must be positive")
        return value


class ShipmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating shipments"""

    class Meta:
        model = Shipment
        fields = [
            'order_id', 'carrier', 'shipping_address',
            'estimated_delivery', 'actual_weight', 'notes'
        ]

    def create(self, validated_data):
        # Auto-generate tracking number
        import random
        tracking_no = f"TRK{random.randint(1000, 9999)}"

        # Ensure unique tracking number
        while Shipment.objects.filter(tracking_no=tracking_no).exists():
            tracking_no = f"TRK{random.randint(1000, 9999)}"

        validated_data['tracking_no'] = tracking_no
        validated_data['status'] = 'PENDING'

        return super().create(validated_data)


class ShipmentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating shipment status"""
    location = serializers.CharField(write_only=True, required=False, allow_blank=True)
    description = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Shipment
        fields = ['status', 'location', 'description', 'notes', 'actual_weight']

    def validate_status(self, value):
        """Validate status transitions"""
        instance = self.instance
        if instance:
            current_status = instance.status

            # Define valid transitions
            valid_transitions = {
                'PENDING': ['PICKED_UP', 'CANCELLED'],
                'PICKED_UP': ['IN_TRANSIT', 'CANCELLED'],
                'IN_TRANSIT': ['OUT_FOR_DELIVERY', 'FAILED'],
                'OUT_FOR_DELIVERY': ['DELIVERED', 'FAILED'],
                'DELIVERED': [],  # Terminal state
                'CANCELLED': [],  # Terminal state
                'FAILED': ['IN_TRANSIT'],  # Can retry
            }

            if value != current_status and value not in valid_transitions.get(current_status, []):
                raise serializers.ValidationError(
                    f"Invalid status transition from {current_status} to {value}"
                )

        return value

    def update(self, instance, validated_data):
        # Extract history data
        location = validated_data.pop('location', None)
        description = validated_data.pop('description', None)

        # Update shipment
        old_status = instance.status
        shipment = super().update(instance, validated_data)

        # Create history entry if status changed
        if old_status != shipment.status:
            ShipmentHistory.objects.create(
                shipment=shipment,
                status=shipment.status,
                location=location or '',
                description=description or f"Status updated to {shipment.status}"
            )

        return shipment


class ShipmentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""

    class Meta:
        model = Shipment
        fields = [
            'id', 'order_id', 'tracking_no', 'carrier', 'status',
            'shipped_at', 'delivered_at', 'created_at'
        ]
