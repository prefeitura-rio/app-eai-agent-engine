# EAI Agent Google Engine

A conversational AI agent based on Google Vertex AI, built with LangChain and LangGraph, specialized for municipal public services.

## 🎯 Overview

This project implements an intelligent agent that utilizes:

- **Google Vertex AI** (Gemini 2.5 Flash) as the language model
- **LangChain/LangGraph** for workflow orchestration
- **PostgreSQL** for state persistence
- **OpenTelemetry** for observability
- **MCP (Model Context Protocol)** for external tool integration

## 🏗️ Architecture

### Main Components

```
├── engine/
│   ├── agent.py              # Main agent class
│   └── custom_react_agent.py # Custom ReAct implementation
├── src/
│   ├── config/
│   │   └── env.py            # Environment configuration
│   ├── utils/
│   │   └── infisical.py      # Environment variable utilities
│   ├── deploy.py             # Vertex AI deployment script
│   ├── interactive_test.py   # Interactive test interface
│   ├── prompt.py             # System prompt management
│   └── tools.py              # MCP tools integration
```

### Execution Flow

1. **Initialization**: Agent configures PostgreSQL and OpenTelemetry connections
2. **Processing**: Uses custom ReAct pattern for reasoning and action
3. **Persistence**: Saves conversation state in PostgreSQL for continuity
4. **Observability**: Sends traces to monitoring system

## 🚀 Installation and Configuration

### Prerequisites

- Python 3.13+
- Google Cloud Project with Vertex AI enabled
- PostgreSQL instance

### Configuration with UV

```bash
# Install dependencies
uv sync
```

### Required Environment Variables

Create the file `src/config/.env`

```bash
# Google Cloud
PROJECT_ID=your-project-id
PROJECT_NUMBER=your-project-number
LOCATION=us-central1
GCS_BUCKET=your-bucket

# Vertex AI
REASONING_ENGINE_ID=reasoning-engine-id

# Database
INSTANCE=sql-instance-name
DATABASE=database-name
DATABASE_USER=username
DATABASE_PASSWORD=password

# MCP Server
MPC_SERVER_URL=mcp-server-url
MPC_API_TOKEN=api-token

# EAI Agent API
EAI_AGENT_URL=prompts-api-url
EAI_AGENT_TOKEN=api-token

# OpenTelemetry
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=otlp-endpoint
OTEL_EXPORTER_OTLP_TRACES_HEADERS=otlp-headers

# Gemini API (optional)
GEMINI_API_KEY=your-gemini-key

# Optional Configurations
MCP_EXCLUDED_TOOLS=tool1,tool2
```

## 🔧 Usage

### Authentication

Before deploying, authenticate with Google Cloud:

```bash
# Authenticate with Google Cloud
gcloud auth application-default login
```

### Local Testing

```bash
# Interactive local test
python src/interactive_test.py local

# Test with remote agent (Vertex AI)
python src/interactive_test.py
```

### Deploy to Vertex AI

```bash
# Deploy agent
python src/deploy.py
```

### Checkpoint Table Initialization

```python
from engine.agent import Agent

# Create agent instance
agent = Agent()

# Initialize checkpoint table (only once)
await agent.init_checkpoint_table()
```

## 🛠️ Features

### Agent Class (`engine/agent.py`)

The main class that implements:

- **Multiple Interfaces**: Sync/Async and Streaming/Non-streaming
- **State Persistence**: Using PostgreSQL with LangGraph checkpointer
- **Observability**: Complete OpenTelemetry integration
- **Custom Hooks**: 
  - Automatic timestamp in messages
  - Thread_id injection in user_id parameters
  - Malformed message cleanup

### Custom ReAct Agent (`engine/custom_react_agent.py`)

Customized version of the ReAct pattern that includes:

- **Message Cleanup**: Removes malformed AIMessages
- **Disabled Validation**: For greater flexibility
- **Pre/Post Model Hooks**: For custom processing

### MCP Integration (`src/tools.py`)

External tools system via Model Context Protocol:

- Connection to MCP server via HTTP
- Tool filtering (include/exclude)
- Asynchronous tool loading

### Prompt System (`src/prompt.py`)

Dynamic prompt management:

- Fetch prompts via external API
- Fallback system for local prompts
- Prompt versioning


### Interactive Testing

The `interactive_test.py` file provides:

- Interactive chat interface
- Detailed execution analysis
- Performance metrics
- Support for local and remote agents

### Thread Configuration

```python
config = {
    "configurable": {
        "thread_id": "unique-user-identifier"
    }
}
```
