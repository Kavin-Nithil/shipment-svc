from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Shipment, ShipmentHistory
from .serializers import (
    ShipmentSerializer,
    ShipmentCreateSerializer,
    ShipmentUpdateSerializer,
    ShipmentListSerializer,
    ShipmentHistorySerializer
)
from .rabbitmq_publisher import publish_event


class ShipmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Shipment CRUD operations

    list: Get all shipments
    create: Create new shipment (POST /v1/shipments)
    retrieve: Get shipment by ID (GET /v1/shipments/{id})
    update: Full update shipment
    partial_update: Update shipment status (PATCH /v1/shipments/{id})
    destroy: Delete shipment
    """
    queryset = Shipment.objects.all().prefetch_related('history')
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'carrier', 'order_id']
    search_fields = ['tracking_no', 'order_id']
    ordering_fields = ['created_at', 'shipped_at', 'delivered_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ShipmentListSerializer
        elif self.action == 'create':
            return ShipmentCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ShipmentUpdateSerializer
        return ShipmentSerializer

    def create(self, request, *args, **kwargs):
        """Create a new shipment"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shipment = serializer.save()

        # Publish shipment created event
        publish_event('shipment.created', {
            'shipment_id': shipment.id,
            'order_id': shipment.order_id,
            'tracking_no': shipment.tracking_no,
            'carrier': shipment.carrier,
            'status': shipment.status,
            'created_at': shipment.created_at.isoformat()
        })

        # Return full shipment details
        output_serializer = ShipmentSerializer(shipment)
        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        """Update shipment (full update)"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        old_status = instance.status

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        shipment = serializer.save()

        # Publish status change events
        if old_status != shipment.status:
            self._publish_status_event(shipment, old_status)

        output_serializer = ShipmentSerializer(shipment)
        return Response(output_serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """Update shipment status (partial update)"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def _publish_status_event(self, shipment, old_status):
        """Publish RabbitMQ events based on status changes"""
        event_data = {
            'shipment_id': shipment.id,
            'order_id': shipment.order_id,
            'tracking_no': shipment.tracking_no,
            'carrier': shipment.carrier,
            'old_status': old_status,
            'new_status': shipment.status,
            'updated_at': shipment.updated_at.isoformat()
        }

        # Publish specific events based on status
        if shipment.status == 'PICKED_UP':
            publish_event('shipment.picked_up', event_data)
        elif shipment.status == 'IN_TRANSIT':
            publish_event('shipment.in_transit', event_data)
        elif shipment.status == 'OUT_FOR_DELIVERY':
            publish_event('shipment.out_for_delivery', event_data)
        elif shipment.status == 'DELIVERED':
            event_data['delivered_at'] = shipment.delivered_at.isoformat() if shipment.delivered_at else None
            publish_event('shipment.delivered', event_data)
        elif shipment.status == 'CANCELLED':
            publish_event('shipment.cancelled', event_data)
        elif shipment.status == 'FAILED':
            publish_event('shipment.failed', event_data)

        # Always publish generic status update
        publish_event('shipment.status_updated', event_data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Get shipment history"""
        shipment = self.get_object()
        history = shipment.history.all()
        serializer = ShipmentHistorySerializer(history, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_tracking(self, request):
        """Get shipment by tracking number
        GET /v1/shipments/by_tracking/?tracking_no=TRK1234
        """
        tracking_no = request.query_params.get('tracking_no')
        if not tracking_no:
            return Response(
                {'error': 'tracking_no parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        shipment = get_object_or_404(Shipment, tracking_no=tracking_no)
        serializer = ShipmentSerializer(shipment)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_order(self, request):
        """Get all shipments for an order
        GET /v1/shipments/by_order/?order_id=123
        """
        order_id = request.query_params.get('order_id')
        if not order_id:
            return Response(
                {'error': 'order_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            order_id = int(order_id)
        except ValueError:
            return Response(
                {'error': 'order_id must be an integer'},
                status=status.HTTP_400_BAD_REQUEST
            )

        shipments = Shipment.objects.filter(order_id=order_id)
        serializer = ShipmentListSerializer(shipments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get shipment statistics"""
        from django.db.models import Count

        stats = Shipment.objects.values('status').annotate(count=Count('id'))
        carrier_stats = Shipment.objects.values('carrier').annotate(count=Count('id'))

        return Response({
            'status_distribution': list(stats),
            'carrier_distribution': list(carrier_stats),
            'total_shipments': Shipment.objects.count()
        })
