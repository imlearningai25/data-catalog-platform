# Data Catalog Platform — Complete Setup & Run Guide
# Written for absolute beginners — every step explained

---

## Table of Contents

1. [What You Are Installing (Plain English)](#1-what-you-are-installing)
2. [System Requirements](#2-system-requirements)
3. [Step 1 — Install Docker Desktop](#3-step-1--install-docker-desktop)
4. [Step 2 — Install Git](#4-step-2--install-git)
5. [Step 3 — Install Python 3.11](#5-step-3--install-python-311)
6. [Step 4 — Install Node.js 20](#6-step-4--install-nodejs-20)
7. [Step 5 — Install Google Cloud SDK](#7-step-5--install-google-cloud-sdk)
8. [Step 6 — Set Up Apache Kafka (Explained for Beginners)](#8-step-6--apache-kafka-explained--setup)
9. [Step 7 — Set Up Google BigQuery](#9-step-7--set-up-google-bigquery)
10. [Step 8 — Set Up DataHub](#10-step-8--set-up-datahub)
11. [Step 9 — Clone & Configure the Project](#11-step-9--clone--configure-the-project)
12. [Step 10 — Run Locally with Docker Compose](#12-step-10--run-locally-with-docker-compose)
13. [Step 11 — Verify Everything Works](#13-step-11--verify-everything-works)
14. [Step 12 — Kubernetes Deployment (Production)](#14-step-12--kubernetes-deployment-production)
15. [Step 13 — Set Up Monitoring (Prometheus + Grafana)](#15-step-13--set-up-monitoring)
16. [Troubleshooting Common Problems](#16-troubleshooting)
17. [Quick Reference — All Ports & URLs](#17-quick-reference)

---

## 1. What You Are Installing

Think of this platform as a **library catalogue for your company's data**, but much more powerful.
Here is what each component does in simple terms:

| Component | What it does | Like... |
|---|---|---|
| **Docker** | Packages each service into a container so it runs the same everywhere | A shipping container for software |
| **Kafka** | A high-speed message bus that carries data between services | A highway between services |
| **Redis** | Ultra-fast temporary storage (used for auth tokens) | A whiteboard that resets |
| **BigQuery** | Google's cloud database — stores your catalog permanently | A very large, fast filing cabinet in the cloud |
| **DataHub** | Tracks where data came from and where it goes | A family tree for your data |
| **Prometheus** | Collects health statistics from every service every 15 seconds | A doctor taking constant readings |
| **Grafana** | Draws charts from Prometheus data so humans can read it | A hospital monitor screen |
| **OPA** | Enforces who is allowed to do what | A security guard with a rulebook |
| **Kubernetes** | Manages all the containers in production, restarts failures, scales up | An airport control tower |
| **React** | The web interface you open in your browser | The cockpit dashboard |

---

## 2. System Requirements

Before starting, make sure your computer has:

| Requirement | Minimum | Recommended |
|---|---|---|
| Operating System | Windows 10 (64-bit), macOS 12, Ubuntu 20.04 | Windows 11, macOS 14, Ubuntu 22.04 |
| RAM | 8 GB | 16 GB or more |
| Free Disk Space | 20 GB | 50 GB |
| CPU Cores | 4 | 8 |
| Internet Connection | Required | Required |

> **Windows users:** Enable WSL 2 (Windows Subsystem for Linux) before installing Docker.
> Open PowerShell as Administrator and run: `wsl --install`
> Then restart your computer.

---

## 3. Step 1 — Install Docker Desktop

Docker is the single most important tool. It runs every service without you needing to install each one manually.

### Windows / macOS

1. Go to: **https://www.docker.com/products/docker-desktop**
2. Click **"Download Docker Desktop"** (it detects your OS automatically).
3. Open the downloaded file (`Docker Desktop Installer.exe` on Windows, `.dmg` on Mac).
4. Follow the installer — click **Next** on every screen, accept the license.
5. When it finishes, **restart your computer**.
6. After restart, Docker Desktop opens automatically. You will see a whale icon in your taskbar/menu bar.

### Ubuntu Linux

Open a terminal (Ctrl+Alt+T) and run these commands **one line at a time**:

```bash
# Remove any old Docker versions
sudo apt-get remove docker docker-engine docker.io containerd runc

# Update package list
sudo apt-get update

# Install required tools
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# Add Docker's official key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine + Compose
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Allow your user to run Docker without sudo
sudo usermod -aG docker $USER

# Log out and back in, then verify:
docker --version
docker compose version
```

### Verify Docker is working

Open a terminal (Command Prompt on Windows, Terminal on Mac/Linux) and type:

```bash
docker run hello-world
```

You should see a message that says **"Hello from Docker!"**. If you do, Docker is working correctly.

---

## 4. Step 2 — Install Git

Git is used to download the project code.

### Windows

1. Go to: **https://git-scm.com/download/win**
2. Download the installer and run it.
3. Click **Next** on every screen (defaults are fine).
4. Open **Git Bash** from the Start menu to use Git.

### macOS

Open Terminal and type:

```bash
git --version
```

If Git is not installed, macOS will prompt you to install it automatically. Click **Install**.

### Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y git
git --version
```

---

## 5. Step 3 — Install Python 3.11

Python runs all the backend FastAPI services. **You need version 3.11 specifically.**

### Windows

1. Go to: **https://www.python.org/downloads/**
2. Click the yellow **"Download Python 3.11.x"** button.
3. Run the installer.
4. ⚠️ **IMPORTANT:** On the first screen, check the box **"Add Python to PATH"** before clicking Install.
5. Click **"Install Now"**.

Verify in Command Prompt:
```bash
python --version
# Should show: Python 3.11.x
```

### macOS

```bash
# Install Homebrew first (if you don't have it)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.11
brew install python@3.11

# Verify
python3.11 --version
```

### Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip
python3.11 --version
```

---

## 6. Step 4 — Install Node.js 20

Node.js runs the React frontend build tools.

### Windows / macOS

1. Go to: **https://nodejs.org/**
2. Download the **LTS version** (it says "Recommended For Most Users").
3. Run the installer — click Next on everything.

### Ubuntu

```bash
# Install Node Version Manager (nvm) — the cleanest way
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

# Reload your terminal profile
source ~/.bashrc

# Install Node.js 20
nvm install 20
nvm use 20

# Verify
node --version    # Should show v20.x.x
npm --version     # Should show 10.x.x
```

---

## 7. Step 5 — Install Google Cloud SDK

This lets you talk to Google BigQuery and Google Kubernetes Engine from your terminal.

### All operating systems

1. Go to: **https://cloud.google.com/sdk/docs/install**
2. Download the installer for your operating system.
3. Run it and follow the steps.

**Or on Mac/Linux, run this in terminal:**

```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL          # Restart shell to load gcloud
gcloud init             # This walks you through logging in
```

### Windows

Download from the link above. After installing, open **Google Cloud SDK Shell** from the Start menu and run:

```bash
gcloud init
```

This opens a browser where you log into your Google account.

### After installation — Authenticate

```bash
# Log in to Google
gcloud auth login

# Set your project (replace with your actual project ID)
gcloud config set project my-data-platform

# Get credentials for BigQuery
gcloud auth application-default login
```

---

## 8. Step 6 — Apache Kafka (Explained & Setup)

### What is Kafka? (Beginner explanation)

Imagine your company has many departments that need to share information. Instead of each department calling every other department directly (which gets chaotic), they all post messages to a central **bulletin board**. Any department that cares about a type of message reads it from the board.

That bulletin board is **Apache Kafka**.

In this platform:
- The **Connector Service** posts: *"I found new tables in Teradata"* → Kafka
- The **Metadata Service** reads that message and enriches it → posts enriched data back to Kafka
- The **Catalog Service** reads the enriched message and saves it to BigQuery

Kafka organises messages into **Topics** (like folders), and each topic can have multiple **Partitions** (for speed).

```
Connector Service
      │
      ▼ publishes to
┌─────────────────────────────────┐
│   Kafka Topic: raw-metadata     │  ← 3 partitions (3 lanes of highway)
└─────────────────────────────────┘
      │
      ▼ consumed by
 Metadata Service
      │
      ▼ publishes to
┌──────────────────────────────────────┐
│   Kafka Topic: enriched-metadata     │
└──────────────────────────────────────┘
      │
      ▼ consumed by
 Catalog Service → BigQuery
```

### Option A: Kafka via Docker Compose (RECOMMENDED — No installation needed)

Kafka is already configured in `docker-compose.yml`. When you run `docker-compose up`, Kafka starts automatically. **No separate installation required.**

### Option B: Install Kafka Standalone (if you want to understand it)

#### Step 1 — Install Java (Kafka requires it)

**Windows:**
1. Go to: **https://adoptium.net/**
2. Download **Temurin 17 (LTS)** for Windows.
3. Run the `.msi` installer. Click Next on everything.
4. Verify: Open Command Prompt → type `java -version`

**macOS:**
```bash
brew install openjdk@17
echo 'export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
java -version
```

**Ubuntu:**
```bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jdk
java -version
```

#### Step 2 — Download Kafka

```bash
# Create a directory for Kafka
mkdir ~/kafka && cd ~/kafka

# Download Kafka 3.7.0 (latest stable)
curl -O https://downloads.apache.org/kafka/3.7.0/kafka_2.13-3.7.0.tgz

# Extract it
tar -xzf kafka_2.13-3.7.0.tgz

# Enter the Kafka directory
cd kafka_2.13-3.7.0
```

#### Step 3 — Start Zookeeper (Kafka's coordinator)

Open a **new terminal window** and run:

```bash
cd ~/kafka/kafka_2.13-3.7.0

# Windows
bin\windows\zookeeper-server-start.bat config\zookeeper.properties

# Mac/Linux
bin/zookeeper-server-start.sh config/zookeeper.properties
```

Wait until you see: `INFO binding to port 0.0.0.0/0.0.0.0:2181`
This means Zookeeper is ready.

#### Step 4 — Start Kafka Broker

Open **another new terminal window**:

```bash
cd ~/kafka/kafka_2.13-3.7.0

# Windows
bin\windows\kafka-server-start.bat config\server.properties

# Mac/Linux
bin/kafka-server-start.sh config/server.properties
```

Wait until you see: `INFO started (kafka.server.KafkaServer)`

#### Step 5 — Create the Topics

Open **another new terminal window**:

```bash
cd ~/kafka/kafka_2.13-3.7.0

# Create the raw metadata topic
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic raw-metadata-events \
  --partitions 3 --replication-factor 1

# Create the enriched metadata topic
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic enriched-metadata-events \
  --partitions 3 --replication-factor 1

# Create the audit events topic
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic audit-events \
  --partitions 3 --replication-factor 1

# Verify topics were created
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

You should see all three topics listed. Kafka is now running!

#### Test Kafka is working (optional)

```bash
# Send a test message (producer)
echo "test message" | bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic raw-metadata-events

# Read messages (consumer) — press Ctrl+C to stop
bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic raw-metadata-events \
  --from-beginning
```

---

## 9. Step 7 — Set Up Google BigQuery

BigQuery stores all catalog data permanently, as the "source of truth".

### Step 1 — Create a Google Cloud Project

1. Go to: **https://console.cloud.google.com/**
2. Click the project dropdown at the top → **"New Project"**
3. Name it: `my-data-platform` (or anything you like)
4. Click **Create**. Wait ~30 seconds.

### Step 2 — Enable Billing

BigQuery requires a billing account (there is a generous free tier — 10GB storage + 1TB queries/month free):

1. In the Cloud Console, go to **Billing** in the left menu.
2. Click **"Link a billing account"**.
3. Add a credit card (you won't be charged for the free tier).

### Step 3 — Enable the BigQuery API

```bash
gcloud services enable bigquery.googleapis.com \
  --project=my-data-platform
```

### Step 4 — Create the BigQuery Dataset

```bash
# Create the data_catalog dataset in the US region
bq mk --dataset \
  --description "Data Catalog Platform storage" \
  --location US \
  my-data-platform:data_catalog
```

### Step 5 — Create the BigQuery Tables

```bash
# Navigate to the project directory
cd data-catalog-platform

# Run the schema creation SQL
bq query --project_id=my-data-platform \
  --use_legacy_sql=false \
  < bigquery/schemas/catalog_schema.sql
```

### Step 6 — Create a Service Account

This gives the platform permission to read/write BigQuery:

```bash
# Create the service account
gcloud iam service-accounts create data-catalog-sa \
  --display-name="Data Catalog Service Account" \
  --project=my-data-platform

# Grant BigQuery permissions
gcloud projects add-iam-policy-binding my-data-platform \
  --member="serviceAccount:data-catalog-sa@my-data-platform.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding my-data-platform \
  --member="serviceAccount:data-catalog-sa@my-data-platform.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Download the key file
gcloud iam service-accounts keys create \
  ./gcp-service-account.json \
  --iam-account=data-catalog-sa@my-data-platform.iam.gserviceaccount.com

echo "Service account key saved to gcp-service-account.json"
```

---

## 10. Step 8 — Set Up DataHub

DataHub is the data lineage engine — it tracks where data comes from and where it goes.

### Option A: DataHub via Docker (RECOMMENDED)

```bash
# Install the DataHub CLI
pip install acryl-datahub

# Verify installation
datahub version

# Start DataHub using its built-in Docker Compose
datahub docker quickstart

# This downloads and starts:
#   - datahub-gms (metadata service)     → port 8080
#   - datahub-frontend (web UI)           → port 9002
#   - datahub-mae-consumer (Kafka bridge)
#   - MySQL (DataHub's own storage)
#   - Elasticsearch (for search)
```

Wait 3–5 minutes for all containers to start. Then open:
**http://localhost:9002** — Username: `datahub`, Password: `datahub`

### Option B: Minimal DataHub GMS only

If you only want the REST API (no web UI):

```bash
docker run -d \
  --name datahub-gms \
  -p 8080:8080 \
  -e EBEAN_DATASOURCE_DRIVER=com.mysql.jdbc.Driver \
  linkedin/datahub-gms:head
```

### Verify DataHub is running

```bash
curl http://localhost:8080/health
# Should return: {"status":"UP"}
```

---

## 11. Step 9 — Clone & Configure the Project

### Clone the repository

```bash
# Navigate to where you want the project
cd ~

# Clone the repo (replace URL with your actual git remote)
git clone https://github.com/your-org/data-catalog-platform.git

# Enter the project folder
cd data-catalog-platform
```

### Create the environment configuration file

```bash
# Copy the example environment file
cp .env.example .env
```

Now open `.env` in a text editor and fill in your values:

```bash
# Windows — open in Notepad
notepad .env

# macOS
open -a TextEdit .env

# Linux
nano .env
```

The `.env` file should contain:

```bash
# ============================================================
# .env — Local development configuration
# NEVER commit this file to Git
# ============================================================

# Google Cloud
GCP_PROJECT=my-data-platform
BQ_DATASET=data_catalog
GOOGLE_APPLICATION_CREDENTIALS=./gcp-service-account.json

# JWT Secret (generate a random one)
JWT_SECRET_KEY=your-256-bit-secret-here

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092

# Redis
REDIS_URL=redis://redis:6379

# DataHub
DATAHUB_GMS_URL=http://datahub-gms:8080
DATAHUB_TOKEN=

# Alertmanager (optional — skip for local dev)
PAGERDUTY_SERVICE_KEY=
SLACK_WEBHOOK_URL=
SMTP_PASSWORD=
```

**Generate a secure JWT secret:**
```bash
# Run this to generate a random 256-bit secret
python3 -c "import secrets; print(secrets.token_hex(32))"
# Copy the output and paste it as JWT_SECRET_KEY in .env
```

### Create the `.env.example` file (for team sharing)

```bash
cat > .env.example << 'EOF'
GCP_PROJECT=my-data-platform
BQ_DATASET=data_catalog
GOOGLE_APPLICATION_CREDENTIALS=./gcp-service-account.json
JWT_SECRET_KEY=REPLACE_ME_generate_with_python_secrets_token_hex_32
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
REDIS_URL=redis://redis:6379
DATAHUB_GMS_URL=http://datahub-gms:8080
DATAHUB_TOKEN=
EOF
```

---

## 12. Step 10 — Run Locally with Docker Compose

This is the easiest way to run everything. One command starts all 9 microservices plus all infrastructure.

### Build all service images

```bash
# Make sure you are in the project directory
cd data-catalog-platform

# Build every Docker image (takes 5–10 minutes the first time)
docker compose build

# You should see output like:
# [+] Building connector-service ... DONE
# [+] Building metadata-service  ... DONE
# ... etc
```

### Start everything

```bash
# Start all services in the background (-d means "detached")
docker compose up -d

# Watch the startup logs (Ctrl+C to stop watching — services keep running)
docker compose logs -f
```

### What starts in what order

Docker Compose respects the dependency chain automatically:

```
Zookeeper → Kafka → [kafka-init creates topics]
Redis
OPA
                    ↓ all ready
connector-service, auth-service, metadata-service,
classification-service, term-service, catalog-service,
audit-service, lineage-service
                    ↓ all healthy
api-gateway, frontend
                    ↓
prometheus → grafana → alertmanager
```

### Check everything is running

```bash
docker compose ps
```

You should see every service showing **"Up"** or **"healthy"**:

```
NAME                   STATUS          PORTS
zookeeper              Up (healthy)    2181/tcp
kafka                  Up (healthy)    0.0.0.0:4444->9092/tcp, 0.0.0.0:4445->9094/tcp
redis                  Up (healthy)    0.0.0.0:4446->6379/tcp
opa                    Up (healthy)    0.0.0.0:4447->8181/tcp
connector-service      Up (healthy)    0.0.0.0:4448->8001/tcp
metadata-service       Up (healthy)    0.0.0.0:4449->8002/tcp
classification-service Up (healthy)    0.0.0.0:4450->8003/tcp
term-service           Up (healthy)    0.0.0.0:4451->8004/tcp
catalog-service        Up (healthy)    0.0.0.0:4452->8005/tcp
auth-service           Up (healthy)    0.0.0.0:4453->8006/tcp
audit-service          Up (healthy)    0.0.0.0:4454->8007/tcp
lineage-service        Up (healthy)    0.0.0.0:4455->8008/tcp
api-gateway            Up (healthy)    0.0.0.0:4456->8000/tcp
frontend               Up              0.0.0.0:4457->8009/tcp
prometheus             Up (healthy)    0.0.0.0:4458->9090/tcp
grafana                Up (healthy)    0.0.0.0:4459->3000/tcp
alertmanager           Up              0.0.0.0:4460->9093/tcp
```

---

## 13. Step 11 — Verify Everything Works

Run through these checks one by one after startup:

### 1. API Gateway health check

```bash
curl http://localhost:4456/health
# Expected: {"status":"healthy","service":"api-gateway"}
```

### 2. Auth service health check

```bash
curl http://localhost:4453/health
# Expected: {"status":"healthy","service":"auth-service"}
```

### 3. Log in and get a JWT token

```bash
curl -X POST http://localhost:4453/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@datacatalog.io","password":"Admin@SecureP@ss1"}'

# Expected response (save the access_token!):
# {
#   "access_token": "<YOUR_ACCESS_TOKEN>",
#   "refresh_token": "<YOUR_REFRESH_TOKEN>",
#   "token_type": "bearer",
#   "expires_in": 900,
#   "role": "admin"
# }
```

Save the `access_token` — you'll need it for the next steps:
```bash
# Store the token (Mac/Linux)
TOKEN=$(curl -s -X POST http://localhost:4453/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@datacatalog.io","password":"Admin@SecureP@ss1"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token saved: ${TOKEN:0:30}..."
```

### 4. Test RBAC — check your permissions

```bash
curl -X POST "http://localhost:4453/authz/check?resource=asset&action=read" \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"allowed":true,"role":"admin","resource":"asset","action":"read"}
```

### 5. Register a test data source

```bash
curl -X POST http://localhost:4448/sources \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "mssql",
    "host": "your-sql-server.database.windows.net",
    "port": 1433,
    "database": "AdventureWorks",
    "username": "your-username",
    "password": "your-password",
    "enable_profiling": true,
    "profile_sample_pct": 5.0
  }'

# Expected: {"source_id":"uuid-here","source_type":"mssql"}
```

### 6. Test the classification service

```bash
curl -X POST http://localhost:4450/classify/column \
  -H "Content-Type: application/json" \
  -d '{
    "column_name": "customer_email",
    "data_type": "VARCHAR",
    "sample_values": ["john@example.com", "jane@test.org"]
  }'

# Expected:
# {
#   "column_name": "customer_email",
#   "classification": "PII",
#   "category": "EMAIL",
#   "sensitivity_level": "CONFIDENTIAL",
#   "confidence": "HIGH"
# }
```

### 7. Test term suggestion

```bash
curl -X POST http://localhost:4451/terms/suggest \
  -H "Content-Type: application/json" \
  -d '{
    "column_name": "customer_id",
    "data_type": "INTEGER",
    "table_name": "customers"
  }'

# Expected: {"column_name":"customer_id","terms":["Customer",...],"suggestions":[...]}
```

### 8. Open the React frontend

Open your browser and go to: **http://localhost:4457**

Log in with:
- Email: `admin@datacatalog.io`
- Password: `Admin@SecureP@ss1`

### 9. Open Prometheus

**http://localhost:4458**

In the search box, type: `up` and press Enter.
You should see all your services listed with value `1` (meaning they are up).

### 10. Open Grafana

**http://localhost:4459**

- Username: `admin`
- Password: `admin123`

Go to **Dashboards → Data Catalog → Platform SLA Dashboard**.

### 11. Open DataHub (if started separately)

**http://localhost:9002**

- Username: `datahub`
- Password: `datahub`

### 12. Check Kafka topics have data

```bash
# List all topics
docker exec kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --list

# Check consumer group lag
docker exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe \
  --group metadata-enrichment-group
```

---

## 14. Step 12 — Kubernetes Deployment (Production)

This deploys the platform to a real Kubernetes cluster (Google GKE).
Skip this section if you only want to run locally with Docker Compose.

### Install kubectl

kubectl is the command-line tool for Kubernetes.

**Windows:**
```powershell
# Run PowerShell as Administrator
choco install kubernetes-cli
# (Install Chocolatey first if needed: https://chocolatey.org/)
```

**macOS:**
```bash
brew install kubectl
kubectl version --client
```

**Ubuntu:**
```bash
sudo apt-get update
sudo apt-get install -y kubectl
kubectl version --client
```

### Install Helm (Kubernetes package manager)

```bash
# macOS
brew install helm

# Windows
choco install kubernetes-helm

# Linux
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verify
helm version
```

### Create a GKE Cluster

```bash
# Enable the GKE API
gcloud services enable container.googleapis.com

# Create a production-grade cluster
gcloud container clusters create data-catalog-prod \
  --project=my-data-platform \
  --region=us-central1 \
  --num-nodes=3 \
  --min-nodes=3 \
  --max-nodes=10 \
  --machine-type=e2-standard-4 \
  --enable-autoscaling \
  --enable-autorepair \
  --enable-autoupgrade \
  --disk-size=50GB \
  --workload-pool=my-data-platform.svc.id.goog

# Get credentials so kubectl can talk to your cluster
gcloud container clusters get-credentials data-catalog-prod \
  --region=us-central1 \
  --project=my-data-platform

# Verify connection
kubectl cluster-info
kubectl get nodes
```

### Install Istio (service mesh for mTLS)

```bash
# Download Istio
curl -L https://istio.io/downloadIstio | sh -
cd istio-1.21.0
export PATH=$PWD/bin:$PATH

# Install Istio on the cluster
istioctl install --set profile=production -y

# Verify Istio is running
kubectl get pods -n istio-system
```

### Deploy the platform

```bash
# Navigate to the project directory
cd data-catalog-platform

# Create the namespace
kubectl apply -f kubernetes/base/namespace.yaml

# Create ConfigMap and Secrets
# First update kubernetes/base/config.yaml with your GCP project ID

# Apply base configs
kubectl apply -f kubernetes/base/config.yaml

# Create secrets (replace values with your real ones)
kubectl create secret generic data-catalog-secrets \
  --namespace=data-catalog \
  --from-literal=JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
  --from-file=GCP_SERVICE_ACCOUNT_KEY=./gcp-service-account.json \
  --from-literal=DATAHUB_TOKEN=""

# Deploy all microservices
kubectl apply -f kubernetes/services/ --namespace=data-catalog

# Deploy security policies (Istio mTLS)
kubectl apply -f kubernetes/security/ --namespace=data-catalog

# Watch the deployments roll out
kubectl rollout status deployment/auth-service -n data-catalog
kubectl rollout status deployment/catalog-service -n data-catalog

# Check all pods are running
kubectl get pods -n data-catalog
```

### Deploy Monitoring Stack

```bash
kubectl apply -f monitoring/kubernetes/monitoring-stack.yaml

# Watch monitoring pods start
kubectl get pods -n monitoring -w

# Port-forward Grafana to your laptop (if no ingress yet)
kubectl port-forward svc/grafana 8010:3000 -n monitoring
# Now open http://localhost:8010
```

### Set up the Ingress (so users can access it via browser)

```bash
# Install nginx ingress controller
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace

# Install cert-manager for automatic HTTPS certificates
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=true

# Apply the ingress rule
kubectl apply -f kubernetes/base/config.yaml  # Contains Ingress definition

# Get the external IP address
kubectl get ingress -n data-catalog
# Wait for ADDRESS to be populated — this is your public URL
```

---

## 15. Step 13 — Set Up Monitoring

### Access Prometheus

```bash
# Local Docker Compose:
open http://localhost:4458

# Kubernetes (port-forward):
kubectl port-forward svc/prometheus 9090:9090 -n monitoring
```

**Useful Prometheus queries to try:**
```
# Are all services up?
up{namespace="data-catalog"}

# Request rate (last 5 min)
sum(rate(http_requests_total[5m])) by (service)

# 30-day SLA percentage
(1 - sum(rate(http_requests_total{status=~"5.."}[30d])) / sum(rate(http_requests_total[30d]))) * 100

# Auth failures
rate(auth_attempts_total{outcome="wrong_password"}[5m])
```

### Access Grafana

```bash
# Local Docker Compose:
open http://localhost:4459
# Username: admin  Password: admin123
```

The **Data Catalog Platform SLA Dashboard** is pre-provisioned. It shows:
- 30-day SLA percentage (target: 99.99%)
- Request rates per service
- p95/p99 latency
- Auth events and RBAC decisions
- Audit event rates

### Configure PagerDuty alerts (optional)

1. Create a free PagerDuty account at **https://www.pagerduty.com**
2. Create a new **Service** → get the **Integration Key**
3. Edit `.env` and set: `PAGERDUTY_SERVICE_KEY=your-key-here`
4. Restart alertmanager: `docker compose restart alertmanager`

### Configure Slack alerts (optional)

1. In Slack, go to **Apps** → search for **"Incoming Webhooks"**
2. Click **"Add to Slack"** → choose your channel
3. Copy the **Webhook URL**
4. Edit `.env`: `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`
5. Restart: `docker compose restart alertmanager`

---

## 16. Troubleshooting

### Problem: `docker compose up` fails with "port already in use"

```bash
# Find what is using the port (example: port 4453)
# Windows:
netstat -ano | findstr :4453

# Mac/Linux:
lsof -i :4453

# Kill the process (replace PID with the number shown)
# Windows:
taskkill /PID <PID> /F

# Mac/Linux:
kill -9 <PID>
```

### Problem: Kafka container keeps restarting

```bash
# Check Kafka logs
docker compose logs kafka --tail=50

# Most common cause: not enough memory
# Solution: Increase Docker Desktop memory to at least 6GB
# Docker Desktop → Settings → Resources → Memory → 6GB
```

### Problem: Services show "unhealthy" in docker compose ps

```bash
# Check the specific service logs
docker compose logs auth-service --tail=100

# Restart a single service
docker compose restart auth-service

# Rebuild a service if code changed
docker compose up -d --build auth-service
```

### Problem: BigQuery permission denied

```bash
# Re-authenticate
gcloud auth application-default login

# Check service account has correct roles
gcloud projects get-iam-policy my-data-platform \
  --flatten="bindings[].members" \
  --filter="bindings.members=serviceAccount:data-catalog-sa@my-data-platform.iam.gserviceaccount.com"
```

### Problem: Frontend cannot connect to API

```bash
# Check API Gateway is running
curl http://localhost:4456/health

# Check frontend environment variable
docker compose exec frontend env | grep VITE

# Check nginx error log
docker compose logs api-gateway --tail=50
```

### Problem: JWT token expired immediately

```bash
# Check your system clock is correct (JWT validation is time-sensitive)
# Windows: Settings → Time & Language → Sync Now
# Mac: System Settings → General → Date & Time → Set automatically
# Linux:
sudo timedatectl set-ntp true
timedatectl status
```

### Stop everything cleanly

```bash
# Stop all containers (keeps data)
docker compose down

# Stop AND delete all data (fresh start)
docker compose down -v

# Stop AND delete images too (full clean)
docker compose down -v --rmi all
```

---

## 17. Quick Reference — All Ports & URLs

| Service | Local URL | Purpose |
|---|---|---|
| **React Frontend** | http://localhost:4457 | Main web interface |
| **API Gateway** | http://localhost:4456 | All API calls go through here |
| **Connector Service** | http://localhost:4448/docs | Source connections (Swagger UI) |
| **Metadata Service** | http://localhost:4449/docs | Metadata enrichment (Swagger UI) |
| **Classification Service** | http://localhost:4450/docs | PII detection (Swagger UI) |
| **Term Service** | http://localhost:4451/docs | Business glossary (Swagger UI) |
| **Catalog Service** | http://localhost:4452/docs | Main catalog (Swagger UI) |
| **Auth Service** | http://localhost:4453/docs | Login / RBAC (Swagger UI) |
| **Audit Service** | http://localhost:4454/docs | Audit log (Swagger UI) |
| **Lineage Service** | http://localhost:4455/docs | DataHub lineage (Swagger UI) |
| **Prometheus** | http://localhost:4458 | Metrics & alerting |
| **Grafana** | http://localhost:4459 | Dashboards (admin/admin123) |
| **Alertmanager** | http://localhost:4460 | Alert routing |
| **OPA** | http://localhost:4447 | Policy engine |
| **Kafka** | localhost:4445 | Message broker (external) |
| **Redis** | localhost:4446 | Cache |
| **DataHub UI** | http://localhost:9002 | Lineage graph UI |
| **DataHub GMS** | http://localhost:8080 | Lineage REST API |

### Demo Login Credentials

| Role | Email | Password | Can do |
|---|---|---|---|
| **Admin** | admin@datacatalog.io | Admin@SecureP@ss1 | Everything |
| **Data Steward** | steward@datacatalog.io | Steward@SecureP@ss1 | Edit metadata, classify, manage terms |
| **Data Analyst** | analyst@datacatalog.io | Analyst@SecureP@ss1 | Read catalog, view lineage |
| **Viewer** | viewer@datacatalog.io | Viewer@SecureP@ss1 | Read public/internal assets only |

### Swagger API Docs

Every FastAPI service has automatic interactive documentation.
Go to any service URL + `/docs`, for example:
- **http://localhost:4453/docs** — Auth service API explorer
- **http://localhost:4450/docs** — Classification service API explorer

You can test API calls directly from the browser — no code needed.

---

*Generated by Data Catalog Platform v1.0.0*
