from __future__ import annotations

from pathlib import Path
from typing import Any

from ruto_phone_mcp.agent import PhoneAgent
from ruto_phone_mcp.config_utils import resolve_default_config_file


CONFIG_PATH = resolve_default_config_file(__file__, "agent.json")
EXIT_COMMANDS = {"exit", "quit", "q", ":q", "退出"}


def handle_agent_event(event: dict[str, Any]) -> None:
    event_type = str(event.get("type", "")).strip()
    if event_type == "assistant":
        text = str(event.get("text", "")).strip()
        if text:
            print(f"Assistant: {text}")
    elif event_type == "tool_call":
        name = str(event.get("name", "")).strip()
        args = event.get("args", {})
        print(f"Tool: {name} {args}")
    elif event_type == "tool_result":
        name = str(event.get("name", "")).strip()
        result = str(event.get("result", "")).strip()
        print(f"Tool Result ({name}): {result}")


def build_agent() -> PhoneAgent:
    return PhoneAgent(
        CONFIG_PATH,
        system_prompt="你是一个智能助手",
    )


def extract_text(response: Any) -> str:
    if isinstance(response, str):
        return response

    if isinstance(response, dict):
        if isinstance(response.get("output"), str):
            return response["output"]

        messages = response.get("messages")
        if isinstance(messages, list) and messages:
            last_message = messages[-1]
            content = getattr(last_message, "content", last_message)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(str(item.get("text", "")))
                    else:
                        text_parts.append(str(item))
                return "\n".join(part for part in text_parts if part)
            return str(content)

    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content

    return str(response)


def main() -> None:
    agent = build_agent()
    print(f"Loaded agent config from: {CONFIG_PATH}")
    print("Terminal chat is ready. Type 'exit' to quit.")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue

        if user_input.lower() in EXIT_COMMANDS:
            print("Bye.")
            break

        try:
            response = agent.ask(user_input, with_screenshot=True, callback=handle_agent_event)
        except Exception as exc:
            print(f"Agent error: {exc}")
            continue

        final_text = extract_text(response)
        if final_text:
            print(f"Assistant: {final_text}")


if __name__ == "__main__":
    main()
