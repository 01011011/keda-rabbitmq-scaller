FROM python:3.13-windowsservercore-1809
WORKDIR /app
COPY consumer.py /app
RUN pip install pika
CMD ["python", "consumer.py"]
