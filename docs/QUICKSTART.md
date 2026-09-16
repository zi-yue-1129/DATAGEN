# Quick Start

This guide helps you quickly configure DATAGEN's agent system.

## Prerequisites
- Complete basic installation (see [README.md](../README.md#installation))
- Ensure `.env` file is properly configured

---

## Tutorial 1: Configure an Existing Agent

All 9 existing agents support external configuration. You can modify their behavior without changing code.

### Step 1: Modify System Prompt

Edit `config/agents/{agent_name}/AGENT.md`:

```markdown
---
name: code-agent
description: Python expert for writing and executing data analysis code
version: 1.0.0
---

# Code Agent

You are a Python programmer specializing in data processing...

## Custom Instructions
[Add your custom instructions here]
```

### Step 2: Modify Available Tools

Edit `config/agents/{agent_name}/config.yaml`:

```yaml
tools:
  - execute_code
  - read_document
  - wikipedia        # Add research tools
  - arxiv
```

### Step 3: Verify Changes

Restart the system and the agent will use the new configuration:
```bash
python main.py
```

---

## Tutorial 2: Change LLM Model

Edit `config/agent_models.yaml` to change an agent's model:

```yaml
agents:
  code_agent:
    provider: anthropic      # openai, google, anthropic, ollama, orcarouter
    model_config:
      model: claude-sonnet-5
```

Add `temperature: 0.7` only for models that accept it — Gemini 3.x ignores it, and Claude
Sonnet 5 rejects any value other than its default.

Supported providers:
- `openai` - GPT series
- `google` - Gemini series
- `anthropic` - Claude series
- `ollama` - Local models
- `orcarouter` - OrcaRouter gateway models (OpenAI-compatible)

---

## Tutorial 3: Add Global Rules

Edit `config/agents/_shared/rules.md`. All agents will automatically follow these rules:

```markdown
# Global Rules

## Output Format
- All code must include type hints
- Use Google Style docstrings

## Security Guidelines
- Do not execute file deletion operations
- Sensitive data must be anonymized
```

---

## Available Agents

| Agent | Config Path | Responsibility |
|-------|-------------|----------------|
| `hypothesis_agent` | `config/agents/hypothesis_agent/` | Generate research hypotheses |
| `process_agent` | `config/agents/process_agent/` | Supervise overall workflow |
| `code_agent` | `config/agents/code_agent/` | Write analysis code |
| `search_agent` | `config/agents/search_agent/` | Literature and web search |
| `visualization_agent` | `config/agents/visualization_agent/` | Data visualization |
| `report_agent` | `config/agents/report_agent/` | Write reports |
| `quality_review_agent` | `config/agents/quality_review_agent/` | Quality review |
| `note_agent` | `config/agents/note_agent/` | Record research process |
| `refiner_agent` | `config/agents/refiner_agent/` | Refine final report |

---

## Next Steps
- [Agent Configuration Reference](AGENT_CONFIG.md) - Complete configuration options
- [Tool Configuration](TOOL_CONFIG.md) - Available tools list
- [Skill Configuration](SKILL_CONFIG.md) - Create reusable knowledge modules
