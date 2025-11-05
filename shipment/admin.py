from django.contrib import admin
from .models import Shipment, ShipmentHistory


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'tracking_no', 'order_id', 'carrier',
        'status', 'shipped_at', 'delivered_at', 'created_at'
    ]
    list_filter = ['status', 'carrier', 'created_at', 'shipped_at']
    search_fields = ['tracking_no', 'order_id']
    readonly_fields = ['created_at', 'updated_at', 'shipped_at', 'delivered_at']
    ordering = ['-created_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('order_id', 'tracking_no', 'carrier', 'status')
        }),
        ('Shipping Details', {
            'fields': ('shipping_address', 'estimated_delivery', 'actual_weight', 'notes')
        }),
        ('Timestamps', {
            'fields': ('shipped_at', 'delivered_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        """Make tracking_no readonly after creation"""
        if obj:  # Editing existing object
            return self.readonly_fields + ('tracking_no',)
        return self.readonly_fields


@admin.register(ShipmentHistory)
class ShipmentHistoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'shipment', 'status', 'location', 'timestamp']
    list_filter = ['status', 'timestamp']
    search_fields = ['shipment__tracking_no', 'location', 'description']
    readonly_fields = ['timestamp']
    ordering = ['-timestamp']

    def has_add_permission(self, request):
        """Prevent manual creation of history entries"""
        return False