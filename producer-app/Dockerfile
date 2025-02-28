FROM python:3.13-slim
WORKDIR /app
COPY producer.py /app
RUN pip install pika
CMD ["python", "producer.py"]