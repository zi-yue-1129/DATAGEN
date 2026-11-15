# MCP 服務配置指南

本文檔說明如何配置 Model Context Protocol (MCP) 服務。

## 概述

MCP (Model Context Protocol) 是一種標準化協議，允許 Agent 安全地與外部系統交互，例如：
- 檔案系統操作
- GitHub 倉庫存取
- 網頁搜尋
- 資料庫查詢

---

## 前置需求

### 必要依賴

```bash
pip install -r requirements.txt
```

### Node.js

MCP 伺服器通常是 Node.js 套件。確保已安裝 Node.js 18+（建議 Node.js 20+）。

```bash
node --version  # 應為 v18+（建議 v20+）
```

---

## 環境變數

在 `.env` 檔案中配置以下變數：

| 變數 | 必需 | 說明 |
|------|------|------|
| `WORKING_DIRECTORY` | ✅ | 資料目錄，供 filesystem MCP 伺服器使用 |
| `YDC_API_KEY` | ❌ | web-search 的 You.com API 金鑰（選填，不設定也可使用） |
| `GITHUB_TOKEN` | ❌ | github MCP 伺服器的個人存取權杖 |

`.env` 範例：

```sh
# 您的數據存儲路徑（同時供 filesystem MCP 伺服器使用）
WORKING_DIRECTORY = ./data/

# MCP (Model Context Protocol) 設定（可選）
# You.com API 金鑰，供 web-search 使用（選填，預設使用免金鑰的免費方案）
# YDC_API_KEY = your_ydc_api_key_here
# GitHub Token，供 github MCP 伺服器使用
GITHUB_TOKEN = your_github_token_here
```

---

## 全域配置

### 文件位置

MCP 服務在 `config/mcp.yaml` 中集中定義：

```yaml
servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "${WORKING_DIRECTORY}"]
    description: 本地檔案系統存取
    
  web-search:
    command: npx
    args: ["-y", "@youdotcom-oss/mcp"]
    env:
      YDC_PROFILE: free
    description: 網頁搜尋功能（You.com）
    
  github:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_TOKEN}
    description: GitHub 倉庫存取

defaults:
  - filesystem   # 所有 Agent 預設啟用
```

### 配置結構

| 欄位 | 說明 |
|------|------|
| `servers` | 所有可用的 MCP 服務定義 |
| `servers.{name}.command` | 啟動服務的命令 |
| `servers.{name}.args` | 命令參數 |
| `servers.{name}.env` | 環境變數 |
| `servers.{name}.description` | 人類可讀的說明 |
| `defaults` | 所有 Agent 預設啟用的服務 |

---

## Agent 特定配置

### 在 config.yaml 中啟用

除了全域 `defaults`，每個 Agent 可以額外啟用服務：

```yaml
# config/agents/search_agent/config.yaml
mcp_servers:
  - filesystem
  - web-search
```

### 最終效果

Agent 實際啟用的服務 = `defaults` ∪ Agent 特定 `mcp_servers`

---

## 可用工具

### Filesystem 伺服器

`filesystem` MCP 伺服器提供 14 個工具：

| 工具 | 說明 |
|------|------|
| `read_file` | 讀取檔案內容為文字 |
| `read_text_file` | 支援編碼的檔案讀取 |
| `read_media_file` | 讀取圖片/音訊為 base64 |
| `read_multiple_files` | 同時讀取多個檔案 |
| `write_file` | 建立或覆寫檔案 |
| `edit_file` | 對文字檔進行行級編輯 |
| `create_directory` | 建立目錄 |
| `list_directory` | 列出目錄內容 |
| `list_directory_with_sizes` | 列出目錄並顯示檔案大小 |
| `directory_tree` | 遞迴樹狀檢視為 JSON |
| `move_file` | 移動或重新命名檔案 |
| `search_files` | 按模式搜尋檔案 |
| `get_file_info` | 取得檔案元資料 |
| `file_exists` | 檢查檔案是否存在 |

> [!NOTE]
> 檔案系統存取限制在 `${WORKING_DIRECTORY}` 範圍內。

### Web Search 伺服器

使用 You.com MCP 伺服器（`@youdotcom-oss/mcp`）。預設使用免金鑰的免費方案
（`YDC_PROFILE: free`，每天約 100 次搜尋），不需要 API 金鑰。若要使用自己的金鑰，
請從 `config/mcp.yaml` 移除 `YDC_PROFILE`，並在 `.env` 設定 `YDC_API_KEY`。

### GitHub 伺服器

需要 `GITHUB_TOKEN`。提供對倉庫、Issues 和 Pull Requests 的存取。

---

## 程式化使用

```python
import asyncio
from src.core.mcp_manager import get_mcp_manager

async def use_mcp():
    manager = get_mcp_manager()
    
    # 發現伺服器上的工具
    tools = await manager.discover_tools("filesystem")
    
    # 呼叫工具
    result = await manager.call_tool(
        "filesystem",
        "read_file",
        {"path": "data/sample.csv"}
    )
    
    # 清理
    await manager.close_all()

asyncio.run(use_mcp())
```

---

## 安全考量

> [!WARNING]
> MCP 服務具有強大的系統存取能力。請確保：
> - 只啟用必要的服務
> - 妥善保管 API Token
> - 透過 `WORKING_DIRECTORY` 限制檔案系統存取範圍

---

## 相關文檔
- [快速入門](QUICKSTART.md)
- [Agent 配置參考](AGENT_CONFIG.md)
- [工具配置](TOOL_CONFIG.md)
