"""
Management command to consume RabbitMQ events
Usage: python manage.py consume_events
"""
from django.core.management.base import BaseCommand
from shipment.management.commands.rabbitmq_consumer import RabbitMQConsumer, message_callback
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Consume events from RabbitMQ'

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            type=str,
            default='shipping_queue',
            help='Queue name to consume from'
        )

    def handle(self, *args, **options):
        queue_name = options['queue']

        self.stdout.write(self.style.SUCCESS(f'Starting RabbitMQ consumer for queue: {queue_name}'))

        consumer = RabbitMQConsumer()

        # Connect to RabbitMQ
        if not consumer.connect():
            self.stdout.write(self.style.ERROR('Failed to connect to RabbitMQ'))
            return

        # Setup queue and bind routing keys
        routing_keys = ['order.confirmed', 'order.cancelled']
        if not consumer.setup_queue(queue_name, routing_keys):
            self.stdout.write(self.style.ERROR('Failed to setup queue'))
            return

        self.stdout.write(self.style.SUCCESS(f'Listening for events: {", ".join(routing_keys)}'))

        try:
            # Start consuming
            consumer.start_consuming(queue_name, message_callback)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nStopping consumer...'))
            consumer.stop_consuming()
            self.stdout.write(self.style.SUCCESS('Consumer stopped'))
