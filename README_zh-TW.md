# Ruto Phone MCP

[English](README.md) | [简体中文](README_zh-CN.md) | [繁體中文](README_zh-TW.md)

Ruto Phone MCP 是一個面向 Android 裝置的手機自動化工具集。

它既可以直接執行在手機上，也可以執行在任何一台能透過 `adb` 存取手機的裝置上。接入視覺模型後，它可以查看截圖、操作手機，並完成多步任務。它也可以透過 MCP 服務暴露這些能力，供 OpenClaw、PicoClaw 等「小龍蝦」間接操控手機。

QQ 群：[點擊加入](https://qm.qq.com/cgi-bin/qm/qr?k=cX461O2DhAyGuaaSKdh-9aVPKhW8RpKv&jump_from=webapi&qr=1)。你也可以在群裡分享你自己的應用說明書與 `SKILL.md` 操作指引。

討論區：[GitHub Discussions](https://github.com/iamr0s/ruto-phone-mcp/discussions)

## 它能做什麼

- 透過點擊、滑動、返回、主畫面、啟動應用、取得目前應用等工具控制 Android 裝置。
- 在命令列中啟動一個帶截圖與工具回呼的視覺 Agent。
- 透過 MCP 暴露手機控制能力與任務執行能力。
- 載入本地 `SKILL.md`，讓模型遵循產品級操作說明書。

## TODO

- 增加用於手機控制、任務執行與會話檢視的 Web 介面。
- 提供更方便的配置方式，以及更清楚的配置檢查。
- 增加內建的 Skill 管理能力，支援安裝、更新、啟用、停用與解除安裝。
- 支援更多形式的通知管道，用於任務進度與完成結果推送。

## 參與開發

我平時工作比較繁忙，這個專案的推進速度未必會一直很快。如果你覺得這個專案有價值，歡迎一起參與開發、完善文件、補充 Skills，讓整個系統逐步變得更完整。

## 部署方式

你可以用以下任一方式部署：

1. 直接安裝並執行於 Android 環境中。
2. 安裝並執行於其他裝置上，只要該裝置能透過 `adb` 存取手機即可。

常見場景：

- 在電腦上執行，透過 USB 連接 Android 手機。
- 在伺服器、迷你主機或單板機上執行，透過 `adb connect` 存取手機。
- 在 Android 本地具備 Python 環境時直接執行。

## 安裝

1. 下載並解壓本專案到手機上，或解壓到另一台可透過 `adb` 存取手機的裝置上。
2. 安裝 Python 3.10+。
3. 安裝依賴：

```bash
pip install -r requirements.txt
```

## 設定

執行時設定會依以下順序查找：

1. `config/...`
2. `config-example/...`

也就是說，你可以先複製示例設定，再按需求修改。

示例設定檔：

- `config-example/agent.json`
- `config-example/server.json`
- `config-example/phone.json`

建議目錄結構：

```text
config/
  agent.json
  server.json
  phone.json
```

### `agent.json`

用於視覺 Agent。

主要欄位：

- `base_url`：OpenAI 相容介面位址
- `model_id`：模型名稱
- `auth.api_key`：API Key
- `extra_body`：服務商特定請求欄位
- `skills_dir`：本地技能目錄

### `server.json`

用於 MCP 服務。

主要欄位：

- `host`
- `port`
- `transport`：`stdio`、`sse` 或 `streamable-http`
- `mount_path`
- `sse_path`
- `message_path`
- `streamable_http_path`
- `agent_config`：Agent 設定檔路徑

### `phone.json`

用於手機控制器。

主要欄位：

- `adb`：adb 執行檔名稱或路徑
- `device_id`：可選的 adb 裝置 ID

## 命令列 Agent

執行：

```bash
python run_agent_test.py
```

這會啟動一個互動式 Agent 迴圈。你可以直接輸入自然語言任務，Agent 會：

- 擷取目前畫面
- 用模型分析目前介面
- 每輪只呼叫一個工具
- 一直執行到呼叫 `finish`

適合你直接在終端機中向手機下命令。

## MCP 服務

執行：

```bash
python run_server.py
```

也可以明確指定傳輸方式：

```bash
python run_server.py --transport stdio
python run_server.py --transport sse
python run_server.py --transport streamable-http
```

服務啟動後會暴露手機控制工具與 `task` 方法。

其中 `task` 會持續執行 Agent 直到任務完成，並串流輸出這些中間事件：

- `Assistant: ...`
- `Tool: ...`
- `Tool Result (...): ...`

## 接入 OpenClaw / PicoClaw

本專案可以作為支援 MCP 的客戶端後端，例如 OpenClaw、PicoClaw 等。

建議使用：`streamable-http`

客戶端 MCP 設定範例：

```json
{
  "servers": {
    "ruto-phone": {
      "enabled": true,
      "type": "streamable-http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

然後用下面的方式啟動服務：

```bash
python run_server.py --transport streamable-http
```

如果你的客戶端真正支援 MCP 的 `sse` 流程，也可以使用 `sse`。否則請優先使用 `streamable-http`。

## SKILLS

`skills/` 目錄用來放模型的本地操作說明書。

Skill 不應只是「功能描述」，而應該像軟體說明書一樣，幫助模型少犯錯、更快完成任務。你可以把它理解成：如果模型從來沒用過某個軟體，這份說明書也能告訴它如何正確操作。

Skill 適合寫這些內容：

- 某個 App 的頁面導航規則
- 某種業務流程的標準步驟
- 容易出錯的 UI 操作順序
- 按鈕、分頁、選單的命名習慣
- 彈窗、特殊頁面出現時的處理方式

格式：

```text
skills/
  your-skill-name/
    SKILL.md
```

Agent 會先讀取 `SKILL.md` 的中繼資料，必要時再呼叫 `load_skill(name)` 讀取完整內容。

## 倉庫入口

- `run_agent_test.py`：啟動互動式終端 Agent
- `run_server.py`：啟動 MCP 服務
- `src/ruto_phone_mcp/phone.py`：手機控制實作
- `src/ruto_phone_mcp/agent.py`：Agent 迴圈實作
- `src/ruto_phone_mcp/server.py`：MCP 服務實作

## 捐贈

如果這個專案對你有幫助，歡迎支持作者。

Donate | 捐赠 | 捐贈
|-|-|-|

# Donate

If you like this app, please consider donating!

如果您喜欢这个应用，请考虑捐赠！

## Alipay

<a href="https://qr.alipay.com/fkx18805bxhq1yohgluna25" target="_blank"><img src="https://github.com/user-attachments/assets/5265755d-4594-44c0-8f83-7fe195b4bde2" width="400"></a>

## WeChat Pay

<img src="https://github.com/user-attachments/assets/d5fa6bab-5953-49ff-a8b6-4d3577a21558" width="400">

## Binance

<a href="https://app.binance.com/qr/dplk26612880de614feeb3132342bd79c9f7" target="_blank"><img src="https://github.com/user-attachments/assets/449f94b0-3680-4a7e-bc04-1060dac569b7" width="400"></a>
