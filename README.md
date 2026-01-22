# EAI Agent Engine

Vertex AI Agent Engine deployment for Rio de Janeiro municipal services (IplanRio).

## Overview

AI agent using Google Cloud Vertex AI Agent Engine with Gemini 2.5 Flash model. Connects to both MCP (Model Context Protocol) server and Cloud SQL PostgreSQL via Private Service Connect (PSC) interface for secure, private connectivity.

## Architecture

```
Vertex AI Agent Engine (Google-Managed VPC)
    ↓ (PSC Interface)
psc-mcp-subnet (10.1.0.0/28)
    ├─→ MCP Server (ILB: mcp.agent-engine.internal)
    └─→ Cloud SQL Proxy (ILB: postgres.agent-engine.internal:5432)
```

**Components:**
- Vertex AI Agent Engine (Gemini 2.5 Flash)
- MCP Server (private via Internal Load Balancer)
- Cloud SQL Proxy (private via Internal Load Balancer)
- Cloud SQL PostgreSQL (accessed via proxy)
- LangGraph with Cloud SQL checkpointing

## Quick Start

### 1. Prerequisites

Infrastructure (managed in `/infra/superapp`):
- Network Attachment: `agent-engine-mcp-attachment`
- PSC Subnet: `psc-mcp-subnet` (10.1.0.0/28)
- DNS: `mcp.agent-engine.internal` → MCP ILB
- DNS: `postgres.agent-engine.internal` → Cloud SQL Proxy ILB

### 2. Configure Environment

Create `src/config/.env` with required variables:

```bash
# GCP Project
PROJECT_ID="rj-superapp-staging"
PROJECT_NUMBER="989726518247"
LOCATION="us-central1"
GCS_BUCKET="gs://your-staging-bucket"

# Database (Cloud SQL via Proxy ILB)
INSTANCE="postgres"
DATABASE="eai-agent"
DATABASE_USER="eai-agent"
DATABASE_PASSWORD="your-password"

# MCP Server (Private Network via PSC)
MCP_SERVER_URL="http://mcp.agent-engine.internal/mcp"
MCP_API_TOKEN="your-mcp-api-token"

# PSC Network Configuration - REQUIRED for private MCP and Cloud SQL access
NETWORK_ATTACHMENT="projects/rj-superapp-staging/regions/us-central1/networkAttachments/agent-engine-mcp-attachment"

# Agent Gateway
EAI_AGENT_URL="https://your-agent-api.example.com"
EAI_AGENT_TOKEN="your-agent-token"

# Observability
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="https://your-otel-collector.example.com/v1/traces"
OTEL_EXPORTER_OTLP_TRACES_HEADERS="x-api-key=your-api-key"

# Memory Limits
SHORT_MEMORY_TIME_LIMIT="30"
SHORT_MEMORY_TOKEN_LIMIT="50000"
```

### 3. Deploy

```bash
# Install dependencies
pip install -r requirements.txt

# Deploy agent (with PSC if NETWORK_ATTACHMENT is set)
python src/deploy.py
```

The deployment logs will show: `✓ PSC Interface: Enabled`

## Private Service Connect (PSC)

PSC enables private connectivity from Vertex AI Agent Engine to VPC resources:

- MCP server via Internal Load Balancer (`mcp.agent-engine.internal:8000`)
- Cloud SQL Proxy via Internal Load Balancer (`postgres.agent-engine.internal:5432`)
- DNS resolution for `agent-engine.internal` domain

**Network Attachments:**
- Staging: `projects/rj-superapp-staging/regions/us-central1/networkAttachments/agent-engine-mcp-attachment`
- Production: `projects/rj-superapp/regions/us-central1/networkAttachments/agent-engine-mcp-attachment`

## Usage

**Local Testing:**

```bash
python src/interactive_test.py
```

**Production:** Agent is invoked via the EAI Agent Gateway API.

## Troubleshooting

### Check PSC Configuration

```bash
# Verify network attachment
gcloud compute network-attachments describe agent-engine-mcp-attachment \
  --region=us-central1 --project=rj-superapp-staging

# Check agent logs
gcloud logging read "resource.type=aiplatform.googleapis.com/ReasoningEngine" \
  --project=rj-superapp-staging --limit=50
```

### MCP Connection Issues

```bash
# Check firewall rules
gcloud compute firewall-rules list --filter="name~agent-engine" --project=rj-superapp-staging

# Verify MCP service
kubectl get service mcp-ilb -n mcp
```

### Cloud SQL Connection Issues

```bash
# Verify Cloud SQL Proxy ILB
kubectl get service postgres-ilb -n cloudsql-proxy

# Check Cloud SQL Proxy logs
kubectl logs -n cloudsql-proxy deployment/postgres --tail=50
```

## Infrastructure

Managed in `/infra/superapp/modules/`:
- `gcp/network.tf` - PSC subnet and network attachment
- `gcp/firewall.tf` - Firewall rules (ports 80, 443, 5432, 8000, 8080)
- `gcp/dns-records.tf` - Private DNS for `agent-engine.internal`
- `gcp/addresses.tf` - Internal Load Balancer IPs
- `deployments/cloudsql-proxy.tf` - Cloud SQL Proxy with ILB
- `databases/main.tf` - Cloud SQL PostgreSQL (public IP)
