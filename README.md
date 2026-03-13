# Ruto Phone MCP

[English](README.md) | [简体中文](README_zh-CN.md) | [繁體中文](README_zh-TW.md)

Ruto Phone MCP is a phone automation toolkit for Android devices.

It can run on the phone itself, or on any other machine that can reach the phone through `adb`. With a vision-capable model, it can observe screenshots, operate the device, and complete multi-step tasks. It can also expose the same capabilities as an MCP server, so tools such as OpenClaw and PicoClaw can control the phone indirectly.

QQ Group: [Join the group](https://qm.qq.com/cgi-bin/qm/qr?k=cX461O2DhAyGuaaSKdh-9aVPKhW8RpKv&jump_from=webapi&qr=1). You can also share your own app operating manuals and `SKILL.md` instructions there.

Discussions: [GitHub Discussions](https://github.com/iamr0s/ruto-phone-mcp/discussions)

## What It Can Do

- Control an Android device through touch, swipe, back, home, launch-app, and app inspection tools.
- Run an interactive agent from the command line with screenshots and tool callbacks.
- Expose the phone controller and the task-running agent through MCP.
- Load local `SKILL.md` files so the model can follow product-specific operating instructions.

## TODO

- Add a web UI for phone control, task execution, and session inspection.
- Make configuration easier to edit and validate.
- Add built-in skill management for install, update, enable, disable, and uninstall flows.
- Support more notification channels for task progress and completion events.

## Contributing

My time is limited and work is busy, so progress on the project will not always be fast. If you find this project useful, you are welcome to join development, improve documentation, contribute skills, and help make the whole system more complete.

## Deployment Model

You can use this project in either of these setups:

1. Install and run it directly on an Android environment.
2. Install and run it on another device, as long as that device can access the phone through `adb`.

Typical examples:

- Run on a PC and connect to a USB Android phone.
- Run on a server, mini PC, or SBC that can reach the phone through `adb connect`.
- Run locally on Android if the Python environment is available there.

## Installation

1. Download and extract this repository to the phone, or to another device that can access the phone through `adb`.
2. Install Python 3.10+.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Runtime configuration is loaded in this order:

1. `config/...`
2. `config-example/...`

That means you can copy the example files and then edit only what you need.

Available example files:

- `config-example/agent.json`
- `config-example/server.json`
- `config-example/phone.json`

Recommended setup:

```text
config/
  agent.json
  server.json
  phone.json
```

### `agent.json`

Used by the vision agent.

Main fields:

- `base_url`: OpenAI-compatible API base URL.
- `model_id`: Model name.
- `auth.api_key`: API key.
- `extra_body`: Provider-specific request body fields.
- `skills_dir`: Local skills directory.

### `server.json`

Used by the MCP server.

Main fields:

- `host`
- `port`
- `transport`: `stdio`, `sse`, or `streamable-http`
- `mount_path`
- `sse_path`
- `message_path`
- `streamable_http_path`
- `agent_config`: Path to the agent config file

### `phone.json`

Used by the phone controller.

Main fields:

- `adb`: adb executable name or path
- `device_id`: optional adb device id

## Command Line Agent

Run:

```bash
python run_agent_test.py
```

This starts the interactive agent loop. You can enter a task in natural language, and the agent will:

- capture a screenshot
- analyze the current screen with the model
- call one tool at a time
- continue until it calls `finish`

Use this when you want to directly command the phone from a terminal.

## MCP Server

Run:

```bash
python run_server.py
```

Or select a transport explicitly:

```bash
python run_server.py --transport stdio
python run_server.py --transport sse
python run_server.py --transport streamable-http
```

This starts the MCP server and exposes tools such as phone actions and the `task` method.

The `task` method runs the agent to completion and streams intermediate events such as:

- `Assistant: ...`
- `Tool: ...`
- `Tool Result (...): ...`

## Using With OpenClaw / PicoClaw

This project can be used as the phone-control backend for MCP-capable clients such as OpenClaw and PicoClaw.

Recommended transport: `streamable-http`

Example client-side MCP config:

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

Then start the server with:

```bash
python run_server.py --transport streamable-http
```

If your client genuinely supports MCP `sse`, you can also use SSE. Otherwise prefer `streamable-http`.

## SKILLS

The `skills/` directory is for local operating manuals for the model.

A skill is not just a feature description. It should help the model avoid mistakes and complete tasks faster, as if you were explaining how to use a piece of software to someone who has never used it before.

Use skills for things like:

- app-specific navigation rules
- business workflows
- fragile UI procedures
- naming conventions for buttons, tabs, and menus
- what to do when a dialog or special page appears

Skill format:

```text
skills/
  your-skill-name/
    SKILL.md
```

The agent reads skill metadata from `SKILL.md`, and can call `load_skill(name)` when it needs the full instructions.

## Repository Entry Points

- `run_agent_test.py`: start the interactive terminal agent
- `run_server.py`: start the MCP server
- `src/ruto_phone_mcp/phone.py`: phone control implementation
- `src/ruto_phone_mcp/agent.py`: agent loop implementation
- `src/ruto_phone_mcp/server.py`: MCP server implementation

## Donation

If this project helps you, you can support the author here.

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
