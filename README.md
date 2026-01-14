# EAI Agent Engine

Vertex AI Agent Engine deployment for Rio de Janeiro municipal services (IplanRio).

## Overview

AI agent using Google Cloud Vertex AI Agent Engine with Gemini 2.5 Flash model. Connects to MCP (Model Context Protocol) server via private VPC networking for extended tool capabilities.

## Architecture

```
VPC: application-network
├── application-subnet (10.0.0.0/16)
│   ├── GKE Cluster (MCP Server)
│   └── Internal Load Balancer
├── psc-mcp-subnet (10.1.0.0/28)
│   └── Agent Engine PSC Interface
└── DNS Zone: mcp.internal.
    └── mcp-server.mcp.internal → ILB IP
```

**Components:**

- Vertex AI Agent Engine (Gemini 2.5 Flash)
- MCP Server (private network access via PSC)
- PostgreSQL (Cloud SQL) for memory
- OpenTelemetry for observability

## Quick Start

### 1. Prerequisites

Infrastructure resources (managed in `/infra/superapp/modules/gcp/psc-mcp.tf`):

- VPC Network: `application-network`
- PSC Subnet: `psc-mcp-subnet` (10.1.0.0/28)
- Network Attachment: `agent-engine-mcp-attachment`
- DNS Zone: `mcp.internal.`
- DNS Record: `mcp-server.mcp.internal`
- Firewall rules and IAM permissions

### 2. Configure Environment

Create `src/config/.env` with required variables:

```bash
# GCP Project
PROJECT_ID="rj-superapp"
PROJECT_NUMBER="123456789"
LOCATION="us-central1"
GCS_BUCKET="gs://your-staging-bucket"

# Database
INSTANCE="your-instance-name"
DATABASE="agent_db"
DATABASE_USER="agent_user"
DATABASE_PASSWORD="your-password"

# MCP Server (Private Network)
MCP_SERVER_URL="http://mcp-server.mcp.internal:8000"
MCP_API_TOKEN="your-mcp-api-token"

# VPC Network - REQUIRED for private MCP access
NETWORK_ATTACHMENT="projects/rj-superapp/regions/us-central1/networkAttachments/agent-engine-mcp-attachment"

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

# Deploy agent
python src/deploy.py
```

## VPC Configuration

The agent uses Private Service Connect (PSC) to access the MCP server. When `NETWORK_ATTACHMENT` is set, the deployment automatically configures:

```python
config = {
    "psc_interface_config": {
        "network_attachment": env.NETWORK_ATTACHMENT,
        "dns_peering_configs": [
            {
                "domain": "mcp.internal.",
                "target_project": env.PROJECT_ID,
                "target_network": "application-network",
            },
        ],
    },
}
```

**What this enables:**

- Private connectivity via PSC network attachment
- DNS resolution for `mcp.internal.` domain (resolves `mcp-server.mcp.internal` to ILB IP)
- Secure communication without public internet exposure

## Usage

**Local Testing:**

```bash
python src/interactive_test.py
```

**Production:** Agent is invoked via the EAI Agent Gateway API.

## Troubleshooting

### Agent Cannot Connect to MCP Server

```bash
# Verify network attachment
gcloud compute network-attachments describe agent-engine-mcp-attachment \
  --region=us-central1 --project=rj-superapp

# Check firewall rules
gcloud compute firewall-rules describe allow-agent-engine-to-mcp \
  --project=rj-superapp

# Test DNS (from within VPC)
nslookup mcp-server.mcp.internal

# Check agent logs
gcloud logging read "resource.type=aiplatform.googleapis.com/Endpoint" \
  --project=rj-superapp --limit=50
```

### Deployment Fails

- Verify all required environment variables are set
- Check GCS bucket permissions
- Enable Vertex AI API: `gcloud services enable aiplatform.googleapis.com`
- Check Vertex AI quotas in GCP Console

## Project Structure

```
.
├── src/
│   ├── config/env.py         # Environment configuration
│   ├── deploy.py             # Agent deployment script
│   ├── prompt.py             # System prompt management
│   ├── tools.py              # MCP tools configuration
│   └── interactive_test.py   # Local testing
├── engine/                   # Custom agent implementation
└── README.md
```

## Infrastructure

Infrastructure managed in `/infra/superapp/`:

- `modules/gcp/psc-mcp.tf` - VPC and PSC configuration
- `modules/deployments/mcp.tf` - MCP server deployment

## Security

- Secrets via Infisical or Google Secret Manager
- MCP server not exposed to public internet
- All agent-to-MCP traffic uses private VPC
- Firewall rules restrict traffic to PSC subnet
- User data encrypted at rest in Cloud SQL

## Support

- Infrastructure: DevOps team
- Agent behavior: AI team
- MCP tools: Backend team
