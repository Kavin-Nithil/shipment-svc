import pika
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    """
    RabbitMQ Publisher for shipping events
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

            logger.info(f"Connected to RabbitMQ at {settings.RABBITMQ_HOST}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {str(e)}")
            return False

    def publish(self, routing_key, message):
        """
        Publish message to RabbitMQ

        Args:
            routing_key: Event routing key (e.g., 'shipment.delivered')
            message: Dictionary message to publish
        """
        try:
            if not self.connection or self.connection.is_closed:
                if not self.connect():
                    logger.error("Cannot publish: RabbitMQ connection failed")
                    return False

            # Convert message to JSON
            message_body = json.dumps(message, default=str)

            # Publish message
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent message
                    content_type='application/json'
                )
            )

            logger.info(f"Published event: {routing_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish message: {str(e)}")
            self.close()
            return False

    def close(self):
        """Close RabbitMQ connection"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                logger.info("RabbitMQ connection closed")
        except Exception as e:
            logger.error(f"Error closing connection: {str(e)}")


# Singleton instance
_publisher = None


def get_publisher():
    """Get or create RabbitMQ publisher instance"""
    global _publisher
    if _publisher is None:
        _publisher = RabbitMQPublisher()
    return _publisher


def publish_event(event_type, data):
    """
    Convenience function to publish events

    Args:
        event_type: Event type (e.g., 'shipment.delivered')
        data: Event data dictionary
    """
    if not settings.RABBITMQ_ENABLED:
        logger.info(f"RabbitMQ disabled, skipping event: {event_type}")
        return False

    publisher = get_publisher()
    return publisher.publish(event_type, data)


def close_publisher():
    """Close publisher connection"""
    global _publisher
    if _publisher:
        _publisher.close()
        _publisher = None
