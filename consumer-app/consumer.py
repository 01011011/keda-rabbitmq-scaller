import os
import time
import pika

def callback(ch, method, properties, body):
    print(f"Received message: {body.decode()}")
    # Simulate processing that takes X amount of seconds per message
    time.sleep(int(os.getenv("RABBITMQ_WAIT_TIME", "WAIT_TIME_NOT_SET")))
    ch.basic_ack(delivery_tag=method.delivery_tag)
    print("Processed message.")

rabbit_host = os.getenv("RABBITMQ_HOST", "localhost")
rabbit_user = os.getenv("RABBITMQ_USER", "YOUR_USERNAME")
rabbit_pass = os.getenv("RABBITMQ_PASS", "YOUR_PASSWORD")
rabbit_queue = os.getenv("RABBITMQ_QUEUE", "test-queue")

credentials = pika.PlainCredentials(rabbit_user, rabbit_pass)
parameters = pika.ConnectionParameters(host=rabbit_host, credentials=credentials)
connection = pika.BlockingConnection(parameters)
channel = connection.channel()
channel.queue_declare(queue=rabbit_queue)

# Ensure only one message is processed at a time
channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue=rabbit_queue, on_message_callback=callback)

print("Starting consumer. Waiting for messages...")
channel.start_consuming()
