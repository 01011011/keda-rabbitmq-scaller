import os
import time
import pika
import uuid

rabbit_host = os.getenv("RABBITMQ_HOST", "localhost")
rabbit_user = os.getenv("RABBITMQ_USER", "myuser")
rabbit_pass = os.getenv("RABBITMQ_PASS", "mypassword")
rabbit_queue = os.getenv("RABBITMQ_QUEUE", "test-queue")
interval = int(os.getenv("PUBLISH_INTERVAL", "1"))

credentials = pika.PlainCredentials(rabbit_user, rabbit_pass)
connection_params = pika.ConnectionParameters(host=rabbit_host, credentials=credentials)
connection = pika.BlockingConnection(connection_params)
channel = connection.channel()
channel.queue_declare(queue=rabbit_queue)

print(f"Starting producer. Host={rabbit_host}, Queue={rabbit_queue}, Interval={interval}s")

try:
    while True:
        message = f"Hello from producer - {uuid.uuid4()}"
        channel.basic_publish(exchange='', routing_key=rabbit_queue, body=message)
        print(f"Sent: {message}")
        time.sleep(interval)
except KeyboardInterrupt:
    print("Producer stopped.")
finally:
    connection.close()