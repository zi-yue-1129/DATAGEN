# 快速入門

本指南幫助您快速配置 DATAGEN 的 Agent 系統。

## 前提條件
- 確保已完成基本安裝 (參閱 [README.md](../../README.md#installation))
- 確保 `.env` 文件已正確配置

---

## 教學 1：配置現有 Agent

現有 9 個 Agent 均支援外部配置。您可以修改它們的行為而無需更改程式碼。

### 步驟 1：修改系統提示詞

編輯 `config/agents/{agent_name}/AGENT.md`：

```markdown
---
name: code-agent
description: Python 專家，負責數據分析代碼的編寫與執行
version: 1.0.0
---

# Code Agent

您是一位專精於數據處理的 Python 程式設計師...

## 自定義指令
[在此添加您的自定義指令]
```

### 步驟 2：修改可用工具

編輯 `config/agents/{agent_name}/config.yaml`：

```yaml
tools:
  - execute_code
  - read_document
  - wikipedia        # 新增研究工具
  - arxiv
```

### 步驟 3：驗證變更

重新啟動系統，Agent 將使用新配置：
```bash
python main.py
```

---

## 教學 2：修改 LLM 模型

編輯 `config/agent_models.yaml` 更改 Agent 使用的模型：

```yaml
agents:
  code_agent:
    provider: anthropic      # openai, google, anthropic, ollama
    model_config:
      model: claude-sonnet-5
```

只有在模型接受 `temperature` 時才加上 `temperature: 0.7`：Gemini 3.x 會忽略它，
Claude Sonnet 5 則會拒絕預設值以外的任何值。

支援的 Provider：
- `openai` - GPT 系列
- `google` - Gemini 系列
- `anthropic` - Claude 系列
- `ollama` - 本地模型

---

## 教學 3：添加全域規則

編輯 `config/agents/_shared/rules.md`，所有 Agent 都會自動遵循：

```markdown
# 全域規則

## 輸出格式
- 所有代碼必須包含 type hints
- 使用 Google Style docstrings

## 安全規範
- 禁止執行刪除文件的操作
- 敏感數據必須脫敏處理
```

---

## 現有 Agent 列表

| Agent | 配置路徑 | 職責 |
|-------|----------|------|
| `hypothesis_agent` | `config/agents/hypothesis_agent/` | 生成研究假設 |
| `process_agent` | `config/agents/process_agent/` | 監督整體流程 |
| `code_agent` | `config/agents/code_agent/` | 編寫分析代碼 |
| `search_agent` | `config/agents/search_agent/` | 文獻與網路搜尋 |
| `visualization_agent` | `config/agents/visualization_agent/` | 數據可視化 |
| `report_agent` | `config/agents/report_agent/` | 撰寫報告 |
| `quality_review_agent` | `config/agents/quality_review_agent/` | 品質審核 |
| `note_agent` | `config/agents/note_agent/` | 記錄研究過程 |
| `refiner_agent` | `config/agents/refiner_agent/` | 優化最終報告 |

---

## 下一步
- [Agent 配置參考](AGENT_CONFIG.md) - 完整的配置選項
- [工具配置](TOOL_CONFIG.md) - 可用工具列表
- [技能配置](SKILL_CONFIG.md) - 創建可重用知識模組
