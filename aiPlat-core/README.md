# aiPlat-core

AI Platform Core Layer - Agent Framework, Memory Systems, Model Abstractions, and Skills.

## Architecture

This is **Layer 1** in the AI Platform architecture:

```
aiPlat-management  (管理系统 - 横切)
        │aiPlat-app (Layer 3) - Application Layer
        │aiPlat-platform (Layer 2) - Platform Services Layer
        │aiPlat-core (Layer 1) - AI Core Layer ← YOU ARE HERE
        │aiPlat-infra (Layer 0) - Infrastructure Layer
```

## Core Modules

### harness - Agent Framework
Agent lifecycle management, heartbeat monitoring, health scoring, state tracking.

### memory - Memory System
Short-term and long-term memory, conversation history, execution history.

### models - Model Abstractions
Unified interface for LLM providers (OpenAI, Anthropic, local models).

### skills - Skill System
Skill definition, registration, execution, and management.

### tools - Tool System
External tool integration, registration, and execution.

### knowledge - Knowledge Management
Knowledge base construction, document parsing, vector indexing, retrieval.

### services - Core Services
Shared services: prompts, contexts, tracing, caching.

### orchestration - Workflow Engine
Task coordination, workflow definition and execution.

### agents - Agent Implementations
Pre-built agent types: ReAct, Plan-and-Execute, RAG, etc.

## Dependencies

- Depends on: `aiPlat-infra` (Layer 0)
- Used by: `aiPlat-platform` (Layer 2)

## Installation

```bash
pip install -e .
```

## Testing

```bash
pytest core/tests
```