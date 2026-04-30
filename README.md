# EAI Agent Engine

Vertex AI Agent Engine deployment for Rio de Janeiro municipal services (IplanRio).

## Overview

AI agent using Google Cloud Vertex AI Agent Engine with Gemini 2.5 Flash model. Connects to both MCP (Model Context Protocol) server and PostgreSQL database via Private Service Connect (PSC) interface for secure, private connectivity.

## Architecture

```
Vertex AI Agent Engine (Google-Managed VPC)
    ↓ (PSC Interface)
psc-mcp-subnet (10.1.0.0/28)
    ├─→ MCP Server (ILB: mcp.agent-engine.internal)
    └─→ PostgreSQL Database (postgres.agent-engine.internal:5432)
```

**Components:**
- Vertex AI Agent Engine (Gemini 2.5 Flash)
- MCP Server (private via Internal Load Balancer)
- PostgreSQL Database (private via Internal Load Balancer)
- LangGraph with PostgreSQL checkpointing

## Quick Start

### 1. Prerequisites

Infrastructure (managed in `/infra/superapp`):
- Network Attachment: `agent-engine-mcp-attachment`
- PSC Subnet: `psc-mcp-subnet` (10.1.0.0/28)
- DNS: `mcp.agent-engine.internal` → MCP ILB
- DNS: `postgres.agent-engine.internal` → PostgreSQL Database ILB

### 2. Configure Environment

Create `.env` in the root directory with required variables:

```bash
# GCP Project
PROJECT_ID="rj-superapp-staging"
PROJECT_NUMBER="989726518247"
LOCATION="us-central1"
GCS_BUCKET="gs://your-staging-bucket"

# Database (PostgreSQL via Private Network)
DATABASE_HOST="postgres.agent-engine.internal"
DATABASE_PORT="5432"
DATABASE="eai-agent"
DATABASE_USER="eai-agent"
DATABASE_PASSWORD="your-password"

# MCP Server (Private Network via PSC)
MCP_SERVER_URL="http://mcp.agent-engine.internal/mcp"
MCP_API_TOKEN="your-mcp-api-token"

# PSC Network Configuration - REQUIRED for private MCP and database access
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
uv sync

# Deploy agent (with PSC if NETWORK_ATTACHMENT is set)
uv run src/deploy.py
```

The deployment logs will show: `✓ PSC Interface: Enabled`

## Private Service Connect (PSC)

PSC enables private connectivity from Vertex AI Agent Engine to VPC resources:

- MCP server via Internal Load Balancer (`mcp.agent-engine.internal`)
- PostgreSQL Database via Internal Load Balancer (`postgres.agent-engine.internal:5432`)
- DNS resolution for `agent-engine.internal` domain

**Network Attachments:**
- Staging: `projects/rj-superapp-staging/regions/us-central1/networkAttachments/agent-engine-mcp-attachment`
- Production: `projects/rj-superapp/regions/us-central1/networkAttachments/agent-engine-mcp-attachment`

## Usage

### Local Testing

Requires `psql` and `cloud-sql-proxy` installed, plus GCP credentials saved locally:
- Staging: `<STAGING_CREDENTIALS_PATH>`
- Production: `<PRODUCTION_CREDENTIALS_PATH>`

If you don't have these files, ask Bruno.

Also make sure `.env` is set with the correct variables for the target environment.

**Staging — Terminal 1 (connect to DB):**
```bash
export GOOGLE_APPLICATION_CREDENTIALS=<STAGING_CREDENTIALS_PATH>
GOOGLE_APPLICATION_CREDENTIALS=<STAGING_CREDENTIALS_PATH> cloud-sql-proxy "rj-superapp-staging:us-central1:postgres"
```

**Production — Terminal 1 (connect to DB):**
```bash
export GOOGLE_APPLICATION_CREDENTIALS=<PRODUCTION_CREDENTIALS_PATH>
GOOGLE_APPLICATION_CREDENTIALS=<PRODUCTION_CREDENTIALS_PATH> cloud-sql-proxy "rj-superapp:us-central1:postgres"
```

**Terminal 2 (run the test):**
```bash
# Run locally (no Reasoning Engine)
uv run src/interactive_test.py local

# Run with REASONING_ENGINE_ID from .env
uv run src/interactive_test.py
```

### Production

Agent is invoked via the EAI Agent Gateway API.

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

### PostgreSQL Connection Issues

```bash
# Test database connectivity
uv run python -c "
import psycopg
conn = psycopg.connect('postgresql://eai-agent:password@postgres.agent-engine.internal:5432/eai-agent')
print('Database connection successful!')
conn.close()
"

# Check PostgreSQL service
kubectl get service postgres-ilb -n database
```

## Dependencies

Key packages:
- `langgraph==0.6.4` - LangGraph workflow engine
- `langgraph-checkpoint-postgres>=3.0.3` - PostgreSQL checkpointer for state persistence
- `psycopg[binary]>=3.2.0` - PostgreSQL adapter
- `langchain-google-vertexai==2.1.2` - Vertex AI integration
- `google-cloud-aiplatform[agent-engines]>=1.106.0` - Agent Engine deployment

## Infrastructure

Managed in `/infra/superapp/modules/`:
- `gcp/network.tf` - PSC subnet and network attachment
- `gcp/firewall.tf` - Firewall rules (ports 80, 443, 5432, 8000, 8080)
- `gcp/dns-records.tf` - Private DNS for `agent-engine.internal`
- `gcp/addresses.tf` - Internal Load Balancer IPs
- `deployments/postgres.tf` - PostgreSQL deployment with ILB
