# Ruto Phone MCP

[English](README.md) | [简体中文](README_zh-CN.md) | [繁體中文](README_zh-TW.md)

Ruto Phone MCP 是一个面向 Android 设备的手机自动化工具集。

它既可以直接运行在手机上，也可以运行在任何一台能够通过 `adb` 访问手机的设备上。接入视觉模型后，它可以查看截图、操作手机，并完成多步任务。它也可以以 MCP 服务的形式暴露这些能力，供 OpenClaw、PicoClaw 等“小龙虾”间接操控手机。

## 它能做什么

- 通过点击、滑动、返回、主页、启动应用、获取当前应用等工具控制 Android 设备。
- 在命令行中启动一个带截图和工具回调的视觉 Agent。
- 通过 MCP 暴露手机控制能力和任务执行能力。
- 加载本地 `SKILL.md`，让模型遵循产品级操作说明书。

## 部署方式

你可以用以下任一方式部署：

1. 直接安装并运行在 Android 环境中。
2. 安装并运行在其它设备上，只要该设备能通过 `adb` 访问手机即可。

常见场景：

- 在电脑上运行，通过 USB 连接 Android 手机。
- 在服务器、迷你主机或单板机上运行，通过 `adb connect` 访问手机。
- 在 Android 本地具备 Python 环境时直接运行。

## 安装

1. 下载并解压本项目到手机上，或者解压到另一台可以通过 `adb` 访问手机的设备上。
2. 安装 Python 3.10+。
3. 安装依赖：

```bash
pip install -r requirements.txt
```

## 配置

运行时配置按以下顺序查找：

1. `config/...`
2. `config-example/...`

也就是说，你可以先复制示例配置，再按需修改。

示例配置文件：

- `config-example/agent.json`
- `config-example/server.json`
- `config-example/phone.json`

推荐目录结构：

```text
config/
  agent.json
  server.json
  phone.json
```

### `agent.json`

用于视觉 Agent。

主要字段：

- `base_url`：OpenAI 兼容接口地址
- `model_id`：模型名
- `auth.api_key`：API Key
- `extra_body`：服务商特定请求字段
- `skills_dir`：本地技能目录

### `server.json`

用于 MCP 服务。

主要字段：

- `host`
- `port`
- `transport`：`stdio`、`sse` 或 `streamable-http`
- `mount_path`
- `sse_path`
- `message_path`
- `streamable_http_path`
- `agent_config`：Agent 配置文件路径

### `phone.json`

用于手机控制器。

主要字段：

- `adb`：adb 可执行文件名或路径
- `device_id`：可选的 adb 设备 ID

## 命令行 Agent

运行：

```bash
python run_agent_test.py
```

这会启动一个交互式 Agent 循环。你可以直接输入自然语言任务，Agent 会：

- 截取当前屏幕
- 用模型分析当前界面
- 每轮只调用一个工具
- 一直执行到调用 `finish`

适合你直接在终端里向手机下命令。

## MCP 服务

运行：

```bash
python run_server.py
```

也可以显式指定传输方式：

```bash
python run_server.py --transport stdio
python run_server.py --transport sse
python run_server.py --transport streamable-http
```

服务启动后会暴露手机控制工具和 `task` 方法。

其中 `task` 会持续运行 Agent 直到任务完成，并流式输出这些中间事件：

- `Assistant: ...`
- `Tool: ...`
- `Tool Result (...): ...`

## 接入 OpenClaw / PicoClaw

本项目可以作为支持 MCP 的客户端后端，例如 OpenClaw、PicoClaw 等。

推荐使用：`streamable-http`

客户端 MCP 配置示例：

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

然后用下面的方式启动服务：

```bash
python run_server.py --transport streamable-http
```

如果你的客户端真正支持 MCP 的 `sse` 流程，也可以使用 `sse`。否则优先使用 `streamable-http`。

## SKILLS

`skills/` 目录用于放模型的本地操作说明书。

Skill 不应只是“功能描述”，而应该像软件说明书一样，帮助模型少犯错、更快完成任务。你可以把它理解成：如果模型从来没用过某个软件，这份说明书也能告诉它如何正确操作。

Skill 适合写这些内容：

- 某个 App 的页面导航规则
- 某种业务流程的标准步骤
- 容易出错的 UI 操作顺序
- 按钮、标签页、菜单的命名习惯
- 弹窗、特殊页面出现时的处理方式

格式：

```text
skills/
  your-skill-name/
    SKILL.md
```

Agent 会先读取 `SKILL.md` 的元数据，必要时再调用 `load_skill(name)` 读取完整内容。

## 仓库入口

- `run_agent_test.py`：启动交互式终端 Agent
- `run_server.py`：启动 MCP 服务
- `src/ruto_phone_mcp/phone.py`：手机控制实现
- `src/ruto_phone_mcp/agent.py`：Agent 循环实现
- `src/ruto_phone_mcp/server.py`：MCP 服务实现

## 捐赠

如果这个项目对你有帮助，欢迎支持作者。

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