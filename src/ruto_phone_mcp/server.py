from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import string
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP

from ruto_phone_mcp.agent import PhoneAgent
from ruto_phone_mcp.config_utils import project_root_from_module, resolve_default_config_file


DEFAULT_CONFIG_ARG = "config"
DEFAULT_CONFIG_FILE = "server.json"
DEFAULT_AGENT_CONFIG_FILE = "agent.json"
LOGGER = logging.getLogger("ruto_phone_mcp")


@dataclass(slots=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    transport: Literal["stdio", "http", "streamable-http"] = "streamable-http"
    mount_path: str = "/"
    streamable_http_path: str = "/mcp"
    log_level: str = "DEBUG"
    debug: bool = True
    agent_config_path: Path = Path(DEFAULT_AGENT_CONFIG_FILE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the ruto-phone MCP server.")
    parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_ARG,
        help="Config file path, or a config directory containing server.json.",
    )
    parser.add_argument(
        "-t",
        "--transport",
        choices=["stdio", "http", "streamable-http"],
        help="Override the configured transport for this run.",
    )
    return parser


def resolve_config_path(config_arg: str) -> Path:
    candidate = Path(config_arg)

    if candidate.exists() and candidate.is_dir():
        return (candidate / DEFAULT_CONFIG_FILE).resolve()

    if candidate.exists():
        return candidate.resolve()

    if candidate.suffix == "" and candidate.name == DEFAULT_CONFIG_ARG:
        return resolve_default_config_file(__file__, DEFAULT_CONFIG_FILE)

    if candidate.suffix == "":
        return (candidate / DEFAULT_CONFIG_FILE).resolve()

    return candidate.resolve()


def setup_logging(log_level: str) -> None:
    level_name = log_level.upper()
    level = getattr(logging, level_name, logging.DEBUG)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def load_config(config_arg: str) -> ServerConfig:
    config_path = resolve_config_path(config_arg)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as fh:
        raw: dict[str, Any] = json.load(fh)

    host = str(raw.get("host", "127.0.0.1"))
    port = int(raw.get("port", 8000))
    transport = str(raw.get("transport", "streamable-http")).strip().lower() or "streamable-http"
    if transport not in {"stdio", "http", "streamable-http"}:
        raise ValueError(f"Unsupported transport: {transport}")

    mount_path = str(raw.get("mount_path", "/"))
    streamable_http_path = str(raw.get("streamable_http_path", "/mcp"))
    log_level = str(raw.get("log_level", "DEBUG")).upper()
    debug = bool(raw.get("debug", True))

    agent_config_value = str(raw.get("agent_config", DEFAULT_AGENT_CONFIG_FILE)).strip() or DEFAULT_AGENT_CONFIG_FILE
    agent_config_path = Path(agent_config_value)
    if agent_config_path.is_absolute():
        agent_config_path = agent_config_path.resolve()
    elif agent_config_path.name == DEFAULT_AGENT_CONFIG_FILE and str(agent_config_path.parent) in {"", "."}:
        agent_config_path = resolve_default_config_file(__file__, DEFAULT_AGENT_CONFIG_FILE)
    else:
        agent_config_path = (config_path.parent / agent_config_path).resolve()

    return ServerConfig(
        host=host,
        port=port,
        transport=transport,
        mount_path=mount_path,
        streamable_http_path=streamable_http_path,
        log_level=log_level,
        debug=debug,
        agent_config_path=agent_config_path,
    )


def format_agent_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("type", "")).strip()
    if event_type == "assistant":
        text = str(event.get("text", "")).strip()
        return f"Assistant: {text}" if text else ""
    if event_type == "tool_call":
        name = str(event.get("name", "")).strip()
        args = event.get("args", {})
        return f"Tool: {name} {args}"
    if event_type == "tool_result":
        name = str(event.get("name", "")).strip()
        result = str(event.get("result", "")).strip()
        return f"Tool Result ({name}): {result}"
    if event_type == "finish":
        text = str(event.get("text", "")).strip()
        return f"Assistant: {text}" if text else ""
    return json.dumps(event, ensure_ascii=False)


def create_server(config: ServerConfig) -> FastMCP:
    mcp = FastMCP(
        name="ruto-phone-mcp",
        host=config.host,
        port=config.port,
        mount_path=config.mount_path,
        streamable_http_path=config.streamable_http_path,
        log_level=config.log_level,
        debug=config.debug,
    )

    @mcp.tool()
    def hello(name: str = "world") -> str:
        """Return a simple greeting."""
        LOGGER.debug("hello tool called with name=%s", name)
        return f"Hello, {name}!"

    @mcp.tool(description="Emit 4 random characters over progress/log events, then return the combined string.")
    async def test(ctx: Context) -> str:
        """Stream 4 random characters through progress/log notifications and return the final text."""
        chars: list[str] = []
        for index in range(4):
            char = random.choice(string.ascii_letters + string.digits)
            chars.append(char)
            await ctx.info(f"random_char[{index + 1}/4]: {char}")
            await ctx.report_progress(index + 1, 4, message=char)
            await asyncio.sleep(3)

        result = "".join(chars)
        await ctx.info(f"random_char_done: {result}")
        return result

    @mcp.tool(description="Run the phone agent until it finishes the requested task. Stream intermediate assistant and tool events over progress/log notifications, then return the final answer.")
    async def task(prompt: str, ctx: Context) -> str:
        """Run the phone agent to completion for a single task request."""
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        finished = asyncio.Event()
        loop = asyncio.get_running_loop()

        def callback(event: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        async def drain_events() -> None:
            step = 0
            while not finished.is_set() or not event_queue.empty():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                step += 1
                message = format_agent_event(event)
                if message:
                    await ctx.info(message)
                await ctx.report_progress(step, None, message=event.get("type"))
                event_queue.task_done()

        drainer = asyncio.create_task(drain_events())
        try:
            agent = PhoneAgent(config.agent_config_path)
            response = await asyncio.to_thread(
                partial(agent.ask, prompt, with_screenshot=True, callback=callback)
            )
        except Exception as exc:
            await ctx.error(f"Agent error: {exc}")
            raise
        finally:
            finished.set()
            await drainer

        output = str(response.get("output", "")).strip() if isinstance(response, dict) else str(response).strip()
        if output:
            await ctx.info(f"Assistant: {output}")
        return output

    return mcp


def main() -> None:
    args = build_parser().parse_args()
    config = load_config(args.config)
    if args.transport:
        config.transport = args.transport
    setup_logging(config.log_level)
    LOGGER.info(
        "starting server host=%s port=%s transport=%s mount_path=%s streamable_http_path=%s agent_config=%s log_level=%s debug=%s",
        config.host,
        config.port,
        config.transport,
        config.mount_path,
        config.streamable_http_path,
        config.agent_config_path,
        config.log_level,
        config.debug,
    )
    server = create_server(config)
    if config.transport == "stdio":
        server.run(transport="stdio")
        return
    server.run(transport=config.transport, mount_path=config.mount_path)


if __name__ == "__main__":
    main()
