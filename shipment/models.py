from django.db import models
from django.utils import timezone


class Shipment(models.Model):
    """
    Shipment model to track order shipments
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PICKED_UP', 'Picked Up'),
        ('IN_TRANSIT', 'In Transit'),
        ('OUT_FOR_DELIVERY', 'Out for Delivery'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
        ('FAILED', 'Failed'),
    ]

    CARRIER_CHOICES = [
        ('DHL', 'DHL'),
        ('Bluedart', 'Bluedart'),
        ('FedEx', 'FedEx'),
        ('DTDC', 'DTDC'),
    ]

    # Primary fields
    order_id = models.IntegerField(db_index=True, help_text="Reference to order in Order Service")
    tracking_no = models.CharField(max_length=50, unique=True, db_index=True)
    carrier = models.CharField(max_length=50, choices=CARRIER_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)

    # Timestamps
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Shipping details
    shipping_address = models.TextField(null=True, blank=True)
    estimated_delivery = models.DateTimeField(null=True, blank=True)
    actual_weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                        help_text="Weight in kg")

    # Additional metadata
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'shipments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_id', 'status']),
            models.Index(fields=['tracking_no']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Shipment #{self.id} - Order {self.order_id} - {self.tracking_no}"

    def save(self, *args, **kwargs):
        # Auto-set shipped_at when status changes to shipped states
        if self.status in ['PICKED_UP', 'IN_TRANSIT'] and not self.shipped_at:
            self.shipped_at = timezone.now()

        # Auto-set delivered_at when status is delivered
        if self.status == 'DELIVERED' and not self.delivered_at:
            self.delivered_at = timezone.now()

        super().save(*args, **kwargs)


class ShipmentHistory(models.Model):
    """
    Track shipment status history for audit trail
    """
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='history')
    status = models.CharField(max_length=20)
    location = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'shipment_history'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['shipment', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.shipment.tracking_no} - {self.status} at {self.timestamp}"
