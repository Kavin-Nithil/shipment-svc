import pika
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    """
    RabbitMQ Consumer for order events
    """

    def __init__(self):
        self.connection = None
        self.channel = None
        self.exchange = settings.RABBITMQ_EXCHANGE

    def connect(self):
        """Establish connection to RabbitMQ"""
        try:
            credentials = pika.PlainCredentials(
                settings.RABBITMQ_USER,
                settings.RABBITMQ_PASSWORD
            )
            parameters = pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                port=settings.RABBITMQ_PORT,
                virtual_host=settings.RABBITMQ_VHOST,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare exchange
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type='topic',
                durable=True
            )

            logger.info(f"Consumer connected to RabbitMQ at {settings.RABBITMQ_HOST}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {str(e)}")
            return False

    def setup_queue(self, queue_name, routing_keys):
        """
        Setup queue and bind to routing keys

        Args:
            queue_name: Name of the queue
            routing_keys: List of routing keys to bind (e.g., ['order.confirmed', 'order.cancelled'])
        """
        try:
            # Declare queue
            self.channel.queue_declare(queue=queue_name, durable=True)

            # Bind queue to routing keys
            for routing_key in routing_keys:
                self.channel.queue_bind(
                    exchange=self.exchange,
                    queue=queue_name,
                    routing_key=routing_key
                )
                logger.info(f"Queue {queue_name} bound to {routing_key}")

            return True
        except Exception as e:
            logger.error(f"Failed to setup queue: {str(e)}")
            return False

    def start_consuming(self, queue_name, callback):
        """
        Start consuming messages from queue

        Args:
            queue_name: Name of the queue to consume from
            callback: Callback function to process messages
        """
        try:
            self.channel.basic_qos(prefetch_count=1)
            self.channel.basic_consume(
                queue=queue_name,
                on_message_callback=callback,
                auto_ack=False
            )

            logger.info(f"Started consuming from queue: {queue_name}")
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Consumer stopped by user")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"Error consuming messages: {str(e)}")
            self.stop_consuming()

    def stop_consuming(self):
        """Stop consuming messages"""
        try:
            if self.channel:
                self.channel.stop_consuming()
            self.close()
        except Exception as e:
            logger.error(f"Error stopping consumer: {str(e)}")

    def close(self):
        """Close RabbitMQ connection"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                logger.info("Consumer connection closed")
        except Exception as e:
            logger.error(f"Error closing connection: {str(e)}")


def handle_order_confirmed(ch, method, properties, body):
    """
    Handle order.confirmed event
    Creates a shipment for the confirmed order
    """
    try:
        from .models import Shipment
        import random

        message = json.loads(body)
        logger.info(f"Received order.confirmed event: {message}")

        order_id = message.get('order_id')

        # Check if shipment already exists for this order
        if Shipment.objects.filter(order_id=order_id, status__in=['PENDING', 'PICKED_UP', 'IN_TRANSIT']).exists():
            logger.info(f"Shipment already exists for order {order_id}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Create shipment
        tracking_no = f"TRK{random.randint(1000, 9999)}"
        while Shipment.objects.filter(tracking_no=tracking_no).exists():
            tracking_no = f"TRK{random.randint(1000, 9999)}"

        shipment = Shipment.objects.create(
            order_id=order_id,
            tracking_no=tracking_no,
            carrier='DHL',  # Default carrier
            status='PENDING',
            shipping_address=message.get('shipping_address', ''),
        )

        logger.info(f"Created shipment {shipment.id} for order {order_id}")

        # Publish shipment created event
        from .rabbitmq_publisher import publish_event
        publish_event('shipment.created', {
            'shipment_id': shipment.id,
            'order_id': shipment.order_id,
            'tracking_no': shipment.tracking_no,
            'carrier': shipment.carrier,
            'status': shipment.status,
        })

        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error handling order.confirmed: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def handle_order_cancelled(ch, method, properties, body):
    """
    Handle order.cancelled event
    Cancels shipments for the cancelled order
    """
    try:
        from .models import Shipment

        message = json.loads(body)
        logger.info(f"Received order.cancelled event: {message}")

        order_id = message.get('order_id')

        # Find pending/in-transit shipments for this order
        shipments = Shipment.objects.filter(
            order_id=order_id,
            status__in=['PENDING', 'PICKED_UP', 'IN_TRANSIT']
        )

        for shipment in shipments:
            shipment.status = 'CANCELLED'
            shipment.save()

            logger.info(f"Cancelled shipment {shipment.id} for order {order_id}")

            # Publish shipment cancelled event
            from .rabbitmq_publisher import publish_event
            publish_event('shipment.cancelled', {
                'shipment_id': shipment.id,
                'order_id': shipment.order_id,
                'tracking_no': shipment.tracking_no,
                'reason': 'order_cancelled',
            })

        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error handling order.cancelled: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


# Event handler mapping
EVENT_HANDLERS = {
    'order.confirmed': handle_order_confirmed,
    'order.cancelled': handle_order_cancelled,
}


def message_callback(ch, method, properties, body):
    """
    Main message callback router
    Routes messages to appropriate handlers based on routing key
    """
    routing_key = method.routing_key
    handler = EVENT_HANDLERS.get(routing_key)

    if handler:
        handler(ch, method, properties, body)
    else:
        logger.warning(f"No handler for routing key: {routing_key}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
