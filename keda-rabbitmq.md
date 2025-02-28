
# Deploy RabbitMQ on a VM with AKS, KEDA, Windows Node Autoscaling, and a Local Producer

This guide demonstrates how to set up an event-driven autoscaling environment using Azure Kubernetes Service (AKS) and KEDA. You will:

- Create an Azure resource group.
- Deploy RabbitMQ on an Ubuntu VM in Azure.
- Create an AKS cluster with a fixed Linux system node (for core components) and add an autoscaling Windows node pool.
- Install KEDA (Kubernetes Event-Driven Autoscaling) to monitor RabbitMQ metrics.
- Run a message producer locally using Docker Desktop to simulate load.
- Deploy a Windows-based consumer in AKS that is scaled automatically by KEDA based on the RabbitMQ queue load.
- Learn about additional configuration parameters available in the latest [KEDA RabbitMQ Queue Scaler (v2.16)](https://kedacore.github.io/keda-docs/v2.16/scalers/rabbitmq-queue/).

---

## Table of Contents

- [Deploy RabbitMQ on a VM with AKS, KEDA, Windows Node Autoscaling, and a Local Producer](#deploy-rabbitmq-on-a-vm-with-aks-keda-windows-node-autoscaling-and-a-local-producer)
  - [Table of Contents](#table-of-contents)
  - [1. Create Resource Group](#1-create-resource-group)
  - [2. Deploy RabbitMQ on an Ubuntu VM](#2-deploy-rabbitmq-on-an-ubuntu-vm)
    - [2.1 Create the Ubuntu VM](#21-create-the-ubuntu-vm)
    - [2.2 Open Required Ports](#22-open-required-ports)
    - [2.3 Install and Configure RabbitMQ](#23-install-and-configure-rabbitmq)
  - [3. Create Minimal AKS Cluster (Linux Only, with Windows Credentials)](#3-create-minimal-aks-cluster-linux-only-with-windows-credentials)
  - [4. Retrieve AKS Credentials \& Verify the Cluster](#4-retrieve-aks-credentials--verify-the-cluster)
  - [5. Add Windows Node Pool (Autoscaling)](#5-add-windows-node-pool-autoscaling)
    - [Verify the Node Pools](#verify-the-node-pools)
  - [6. Install KEDA on AKS](#6-install-keda-on-aks)
    - [6.1 Add and Update the KEDA Helm Repository](#61-add-and-update-the-keda-helm-repository)
    - [6.2 Install KEDA](#62-install-keda)
    - [6.3 Verify KEDA Installation](#63-verify-keda-installation)
  - [7. Run the Producer Locally Using Docker Desktop](#7-run-the-producer-locally-using-docker-desktop)
    - [7.1 Prepare the Producer Script](#71-prepare-the-producer-script)
    - [7.2 Create a Dockerfile for the Producer](#72-create-a-dockerfile-for-the-producer)
    - [7.3 Build and Run the Producer Locally](#73-build-and-run-the-producer-locally)
  - [8. Deploy the Windows Consumer + KEDA ScaledObject](#8-deploy-the-windows-consumer--keda-scaledobject)
    - [8.1 Create the Windows Consumer Deployment and ScaledObject](#81-create-the-windows-consumer-deployment-and-scaledobject)
  - [9. Simulate \& Observe Autoscaling](#9-simulate--observe-autoscaling)
  - [10. Additional Notes on KEDA’s RabbitMQ Scaler](#10-additional-notes-on-kedas-rabbitmq-scaler)
  - [Congratulations!](#congratulations)

---

## 1. Create Resource Group

Create a resource group to hold all your Azure resources.

```bash
az group create --name keda-sample-rg --location eastus
```

---

## 2. Deploy RabbitMQ on an Ubuntu VM

### 2.1 Create the Ubuntu VM

Deploy an Ubuntu 22.04 VM in Azure:

```bash
az vm create \
  --resource-group keda-sample-rg \
  --name keda-rabbitmq \
  --image Ubuntu2204 \
  --admin-username azureuser \
  --generate-ssh-keys
```

### 2.2 Open Required Ports

Open ports 5672 (AMQP) and 15672 (Management UI):

```bash
az vm open-port \
  --resource-group keda-sample-rg \
  --name keda-rabbitmq \
  --port "5672,15672"
```

### 2.3 Install and Configure RabbitMQ

1. **SSH into the VM:**  
   Replace `<PUBLIC_IP_OF_VM>` with your VM’s public IP.
   ```bash
   ssh azureuser@<PUBLIC_IP_OF_VM>
   ```

2. **Install Erlang and RabbitMQ:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y erlang
   sudo apt-get install -y rabbitmq-server
   sudo rabbitmq-plugins enable rabbitmq_management
   sudo systemctl enable rabbitmq-server
   sudo systemctl start rabbitmq-server
   ```

3. **(Optional) Create a Custom RabbitMQ User:**  
   This step secures your RabbitMQ instance.
   ```bash
   sudo rabbitmqctl add_user YOUR_USERNAME YOUR_PASSWORD
   sudo rabbitmqctl set_user_tags YOUR_USERNAME administrator
   sudo rabbitmqctl set_permissions -p / YOUR_USERNAME ".*" ".*" ".*"
   ```

4. **Record Your RabbitMQ Credentials:**  
   - **AMQP URL:** `amqp://YOUR_USERNAME:YOUR_PASSWORD@<PUBLIC_IP_OF_VM>:5672/`  
   - **Management UI:** `http://<PUBLIC_IP_OF_VM>:15672`

---

## 3. Create Minimal AKS Cluster (Linux Only, with Windows Credentials)

Create an AKS cluster with one Linux node and supply Windows credentials so that you can add Windows node pools later.

```bash
az aks create \
  --resource-group keda-sample-rg \
  --name keda-cluster \
  --node-count 1 \
  --vm-set-type VirtualMachineScaleSets \
  --windows-admin-username azureuser \
  --windows-admin-password "YOUR_WINDOWS_PASSWORD" \
  --generate-ssh-keys
```

- This creates a fixed Linux node pool with 1 node.
- Replace `YOUR_WINDOWS_PASSWORD` with your desired Windows admin password.

---

## 4. Retrieve AKS Credentials & Verify the Cluster

1. **Download the cluster credentials:**
   ```bash
   az aks get-credentials --resource-group keda-sample-rg --name keda-cluster
   ```

2. **Verify the nodes:**
   ```bash
   kubectl get nodes
   ```
   You should see one Linux node in the "Ready" state.

---

## 5. Add Windows Node Pool (Autoscaling)

Add a Windows node pool named `winnp` that autoscale from 2 to 5 nodes.

```bash
az aks nodepool add \
  --resource-group keda-sample-rg \
  --cluster-name keda-cluster \
  --name winnp \
  --os-type Windows \
  --node-count 2 \
  --min-count 2 \
  --max-count 5 \
  --enable-cluster-autoscaler \
  --vm-set-type VirtualMachineScaleSets
```

### Verify the Node Pools

```bash
az aks show --resource-group keda-sample-rg --name keda-cluster --query agentPoolProfiles
kubectl get nodes -o wide
```

- You should see one Linux node and two Windows nodes.

---

## 6. Install KEDA on AKS

KEDA enables event-driven autoscaling based on external metrics.

### 6.1 Add and Update the KEDA Helm Repository

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
```

### 6.2 Install KEDA

```bash
helm install keda kedacore/keda --namespace keda --create-namespace
```

### 6.3 Verify KEDA Installation

```bash
kubectl get pods -n keda
```

- You should see pods like `keda-operator` and `keda-metrics-apiserver` running.

---

## 7. Run the Producer Locally Using Docker Desktop

Instead of deploying the producer to AKS, you can run it locally using Docker Desktop.

### 7.1 Prepare the Producer Script

Create a file named **producer.py** with the following content:

```python
import os
import time
import pika
import uuid

rabbit_host = os.getenv("RABBITMQ_HOST", "localhost")
rabbit_user = os.getenv("RABBITMQ_USER", "YOUR_USERNAME")
rabbit_pass = os.getenv("RABBITMQ_PASS", "YOUR_PASSWORD")
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
```

### 7.2 Create a Dockerfile for the Producer

Create a file named **Dockerfile** with the following content:

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY producer.py /app
RUN pip install pika
CMD ["python", "producer.py"]
```

### 7.3 Build and Run the Producer Locally

1. **Build the Docker image:**

   ```bash
   docker build -t rabbitmq-producer:latest .
   ```

2. **Run the Producer Container:**

   Replace `<PUBLIC_IP_OF_VM>` with your RabbitMQ VM’s public IP.
   
   ```bash
   docker run --rm \
     -e RABBITMQ_HOST=<PUBLIC_IP_OF_VM> \
     -e RABBITMQ_USER=YOUR_USERNAME \
     -e RABBITMQ_PASS="YOUR_PASSWORD" \
     -e RABBITMQ_QUEUE=test-queue \
     -e PUBLISH_INTERVAL=1 \
     rabbitmq-producer:latest
   ```

This container will continuously send messages to your RabbitMQ instance.

---

## 8. Deploy the Windows Consumer + KEDA ScaledObject

Deploy a dummy Windows consumer in AKS that is scaled by KEDA based on the RabbitMQ queue load.

### 8.1 Create the Windows Consumer Deployment and ScaledObject

Create a file named **consumer-scaledobject.yaml** with the following content:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: windows-consumer
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: windows-consumer
  template:
    metadata:
      labels:
        app: windows-consumer
    spec:
      nodeSelector:
        kubernetes.io/os: windows
      containers:
      - name: dummy-consumer
        image: mcr.microsoft.com/dotnet/framework/samples:aspnetapp
        env:
        - name: RABBITMQ_HOST
          value: "<PUBLIC_IP_OF_VM>"
        - name: RABBITMQ_USER
          value: "YOUR_USERNAME"
        - name: RABBITMQ_PASS
          value: "YOUR_PASSWORD"
        - name: RABBITMQ_QUEUE
          value: "test-queue"

---
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: windows-consumer-scaledobject
  namespace: default
spec:
  scaleTargetRef:
    name: windows-consumer
  pollingInterval: 5
  cooldownPeriod: 30
  minReplicaCount: 1
  maxReplicaCount: 10
  triggers:
  - type: rabbitmq
    metadata:
      queueName: test-queue
      protocol: amqp
      host: "amqp://YOUR_USERNAME:YOUR_PASSWORD@<PUBLIC_IP_OF_VM>:5672/"
      mode: QueueLength
      value: "5"
      # activationValue: "2"  # Optional: uncomment to enable scaling from 0
```

Replace `<PUBLIC_IP_OF_VM>`, `YOUR_USERNAME`, and `YOUR_PASSWORD` with your RabbitMQ VM details.

Apply the deployment:

```bash
kubectl apply -f consumer-scaledobject.yaml
```

This creates a Windows consumer deployment that is pinned to Windows nodes, and a KEDA ScaledObject that scales the consumer based on the RabbitMQ queue length.

---

## 9. Simulate & Observe Autoscaling

1. **Producer Operation:**  
   The locally run producer continuously sends messages to the `test-queue`.

2. **Monitor Scaling:**  
   Open a terminal and run:
   ```bash
   kubectl get pods -w
   kubectl get hpa
   ```
   KEDA will automatically create an HPA for the "windows-consumer" deployment. When the queue length exceeds 5 messages, the consumer pods will scale up.

3. **Observe Windows Node Pool Autoscaling:**  
   Check the node status with:
   ```bash
   kubectl get nodes -o wide
   az aks show --resource-group keda-sample-rg --name keda-cluster --query agentPoolProfiles
   ```
   If the consumer pods exceed the capacity of the existing Windows nodes, the AKS autoscaler will add more Windows nodes (up to 5). The Linux node remains fixed at 1.

4. **Scale-Down Behavior:**  
   If you stop the producer (for example, by terminating the Docker container) or if the queue drains, after the cooldown period (30 seconds) KEDA scales the consumer pods down, and the Windows node pool scales back down to the minimum (2 nodes) if no demand remains.

---

## 10. Additional Notes on KEDA’s RabbitMQ Scaler

The latest [KEDA RabbitMQ Queue Scaler (v2.16)](https://kedacore.github.io/keda-docs/v2.16/scalers/rabbitmq-queue/) supports several modes:

- **QueueLength (default):** Scales based on the number of pending messages.
- **MessageRate:** Scales based on the rate of incoming messages (msgs/sec).
- **MessageSize:** Scales based on the total size (bytes) of pending messages.

**Key properties:**

- **value:** The threshold for scaling. For example, if `mode` is set to `QueueLength` and `value` is "5", scaling is triggered when there are more than 5 messages.
- **activationValue (optional):** Useful for scaling from 0 (set `minReplicaCount: 0`) by defining a lower threshold.
- **pollingInterval:** The frequency (in seconds) at which KEDA checks RabbitMQ metrics.
- **cooldownPeriod:** The time (in seconds) to wait after the last scale event before scaling down.

Adjust these parameters to fine-tune autoscaling behavior for your workload.

---

## Congratulations!

You now have a complete event-driven autoscaling setup that includes:

- A **RabbitMQ** instance running on an Ubuntu VM in Azure.
- An **AKS** cluster with a fixed Linux system node and an autoscaling Windows node pool (2–5 nodes).
- A **locally run producer** (via Docker Desktop) that continuously publishes messages to RabbitMQ.
- A **KEDA-driven Windows consumer** deployment that scales based on the RabbitMQ queue load.
- Detailed insights into how KEDA’s RabbitMQ scaler parameters (mode, value, activationValue) can be configured.

When the RabbitMQ queue is busy, the consumer pods scale out—and if needed, additional Windows nodes are provisioned automatically. When the load decreases, both pods and nodes scale down accordingly.