import base64
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Optional

from langchain.messages import HumanMessage, SystemMessage, ToolMessage
from langchain.tools import tool
from langchain_openai import ChatOpenAI

from ruto_phone_mcp.config_utils import resolve_default_config_file
from ruto_phone_mcp.phone import RutoPhone


DEFAULT_SYSTEM_PROMPT = """
You are an Android phone automation agent.

You receive the user's instruction and a screenshot of the phone screen.

Use available tools to interact with the phone.

Rules:
- Always analyze the screenshot first.
- Perform one action per step.
- You must call at most one tool in each assistant turn.
- After each tool execution, a new screenshot will be provided to you.
- When the task is complete or you want to stop, call finish with the final answer.
- Do not output a normal final answer directly; use finish instead.
- Do not guess invisible UI elements.
- Scroll when content is not visible.
"""


class PhoneAgent:
    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        system_prompt: Optional[str] = None,
        temperature: Optional[int] = None,
    ):
        self.config_path = Path(config_path).resolve() if config_path is not None else resolve_default_config_file(__file__, "agent.json")
        self.project_root = self.config_path.parent.parent
        self.config = self._load_json_file(self.config_path)

        base_url = self._resolve_base_url(self.config)
        model_id = self._resolve_model_id(self.config)
        api_key = self._resolve_api_key(self.config)
        self.base_system_prompt = str(system_prompt if system_prompt is not None else self.config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT).strip()
        self.skill_registry = self._discover_skills()
        resolved_temperature = int(temperature if temperature is not None else self.config.get("temperature", 0))

        self.model = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model_id,
            temperature=resolved_temperature,
            extra_body=self._resolve_extra_body(self.config),
            model_kwargs=self._resolve_model_kwargs(self.config),
        )
        self.phone = RutoPhone()
        self.load_skill_tool = tool(
            "load_skill",
            description=(
                "Load the full body of a local skill by exact skill name. "
                "Use this when the skill metadata suggests a relevant workflow and you need the detailed instructions. "
                "The input name must exactly match one of the available skill names listed in the system prompt."
            ),
        )(self.load_skill)
        self.finish_tool = tool(
            "finish",
            description=(
                "Stop the tool loop and return the final answer to the user. "
                "Call this only when the task is complete or when you intentionally want to stop. "
                "Provide a concise final answer in the answer field."
            ),
        )(self.finish)
        self.tools = [self.load_skill_tool, *self.phone.tools, self.finish_tool]
        self.tools_by_name = {tool_item.name: tool_item for tool_item in self.tools}
        self.bound_model = self.model.bind_tools(self.tools)
        self.messages: list[Any] = []
        self.max_steps = int(self.config.get("max_steps", 20))

    @staticmethod
    def _load_json_file(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Missing JSON file: {path}")
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"JSON file must contain a JSON object: {path}")
        return data

    @staticmethod
    def _resolve_base_url(config: dict[str, Any]) -> str:
        base_url = str(config.get("base_url") or config.get("api_base") or "").strip()
        if not base_url:
            raise ValueError("base_url or api_base must not be empty.")
        return base_url

    @staticmethod
    def _resolve_model_id(config: dict[str, Any]) -> str:
        model_id = str(config.get("model_id") or config.get("model_name") or "").strip()
        if model_id:
            return model_id

        model = str(config.get("model") or "").strip()
        if not model:
            raise ValueError("model_id, model_name, or model must not be empty.")
        if "/" in model:
            _, _, model_id = model.partition("/")
            if model_id:
                return model_id
        return model

    @staticmethod
    def _resolve_api_key(config: dict[str, Any]) -> str:
        auth = config.get("auth")
        if isinstance(auth, dict):
            auth_type = str(auth.get("type", "")).strip().lower()
            if auth_type and auth_type != "api_key":
                raise ValueError(f"Unsupported auth.type: {auth.get('type')}. Only api_key is supported.")
            api_key = str(auth.get("api_key", "")).strip()
            if api_key:
                return api_key

        api_key = str(config.get("api_key") or "").strip()
        if api_key:
            return api_key

        raise ValueError("api_key is required. Use auth.type=api_key or top-level api_key.")

    @staticmethod
    def _resolve_model_kwargs(config: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(config.get("model_kwargs", {})) if isinstance(config.get("model_kwargs"), dict) else {}

    @staticmethod
    def _resolve_extra_body(config: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(config.get("extra_body", {})) if isinstance(config.get("extra_body"), dict) else {}

    def _resolve_skills_dir(self) -> Path:
        configured = str(self.config.get("skills_dir", "")).strip()
        if configured:
            path = Path(configured)
            if not path.is_absolute():
                path = (self.project_root / path).resolve()
            return path
        return (self.project_root / "skills").resolve()

    @staticmethod
    def _parse_skill_frontmatter(text: str) -> tuple[dict[str, str], str]:
        if not text.startswith("---\n"):
            return {}, text.strip()
        end = text.find("\n---\n", 4)
        if end == -1:
            return {}, text.strip()
        frontmatter_text = text[4:end].strip()
        body = text[end + 5:].strip()
        metadata: dict[str, str] = {}
        for raw_line in frontmatter_text.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in {"name", "description"}:
                metadata[key] = value
        return metadata, body

    def _discover_skills(self) -> dict[str, dict[str, Any]]:
        skills_dir = self._resolve_skills_dir()
        if not skills_dir.exists() or not skills_dir.is_dir():
            return {}

        enabled = self.config.get("enabled_skills")
        enabled_set = {str(item).strip() for item in enabled if str(item).strip()} if isinstance(enabled, list) else None
        entries: dict[str, dict[str, Any]] = {}
        for child in sorted(skills_dir.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.exists():
                continue
            raw_text = skill_file.read_text(encoding="utf-8")
            metadata, body = self._parse_skill_frontmatter(raw_text)
            skill_name = metadata.get("name", "").strip() or child.name.strip()
            description = metadata.get("description", "").strip()
            if enabled_set is not None and skill_name not in enabled_set and child.name not in enabled_set:
                continue
            if not description:
                continue
            entries[skill_name] = {
                "name": skill_name,
                "description": description,
                "body": body,
                "path": skill_file,
            }
        return entries

    def _build_system_message(self) -> SystemMessage:
        sections = [self.base_system_prompt]
        if self.skill_registry:
            sections.extend([
                "",
                "Available local skills metadata:",
            ])
            for skill_name in sorted(self.skill_registry):
                description = self.skill_registry[skill_name]["description"]
                sections.append(f"- {skill_name}: {description}")
            sections.extend([
                "",
                "Use load_skill(name) if one of these skills is relevant and you need its full instructions.",
                "The name must exactly match one of the skill names listed above.",
            ])
        return SystemMessage(content="\n".join(sections).strip())

    @staticmethod
    def _remove_image_blocks(content: Any) -> Any:
        if not isinstance(content, list):
            return content

        filtered_content = [
            item for item in content
            if not (isinstance(item, dict) and item.get("type") in {"image_url", "image", "input_image"})
        ]
        if filtered_content:
            return filtered_content
        return ""

    def _prune_image_history(self, messages: list[Any]) -> list[Any]:
        image_message_indexes: list[int] = []
        for index, message in enumerate(messages):
            content = getattr(message, "content", None)
            if isinstance(content, list) and any(
                isinstance(item, dict) and item.get("type") in {"image_url", "image", "input_image"}
                for item in content
            ):
                image_message_indexes.append(index)

        for index in image_message_indexes[:-1]:
            messages[index].content = self._remove_image_blocks(messages[index].content)

        return messages

    def _build_human_message(
        self,
        chat: str | dict | list,
        image: bytes | None = None,
        image_mime_type: str = "image/webp",
    ) -> HumanMessage:
        if image is None:
            return HumanMessage(chat)

        image_base64 = base64.b64encode(image).decode("ascii")
        image_block = {
            "type": "image_url",
            "image_url": {
                "url": f"data:{image_mime_type};base64,{image_base64}"
            },
        }

        if isinstance(chat, str):
            content: list[Any] = [
                {"type": "text", "text": chat},
                image_block,
            ]
        elif isinstance(chat, list):
            content = list(chat)
            content.append(image_block)
        else:
            content = [chat, image_block]

        return HumanMessage(content=content)

    def _build_followup_screenshot_message(self) -> HumanMessage:
        screenshot = self.phone.screenshot_webp()
        return self._build_human_message(
            "This is the latest screenshot after the previous tool execution. Continue with exactly one next tool call, or call finish if the task is complete.",
            image=screenshot,
            image_mime_type="image/webp",
        )

    @staticmethod
    def _extract_tool_args(tool_call: dict[str, Any]) -> dict[str, Any]:
        args = tool_call.get("args", {})
        if isinstance(args, dict):
            return args
        if isinstance(args, str):
            parsed = json.loads(args) if args.strip() else {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _extract_finish_answer(args: dict[str, Any]) -> str:
        for key in ("answer", "message", "final_answer", "response"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _invoke_tool(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        tool_item = self.tools_by_name.get(tool_name)
        if tool_item is None:
            return f"ERROR: Unknown tool: {tool_name}."
        return str(tool_item.invoke(tool_args))

    def load_skill(self, name: str) -> str:
        skill_name = str(name).strip()
        skill = self.skill_registry.get(skill_name)
        if skill is None:
            available = ", ".join(sorted(self.skill_registry)) or "<none>"
            return f"ERROR: Unknown skill '{skill_name}'. Available skills: {available}."
        return f"OK: Loaded skill {skill_name}.\n\n{skill['body']}"

    def finish(self, answer: str) -> str:
        return answer.strip()

    @staticmethod
    def _emit(callback: Optional[Callable[[dict[str, Any]], None]], event: dict[str, Any]) -> None:
        if callback is not None:
            callback(event)

    @staticmethod
    def _message_text(message: Any) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text", "")).strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts).strip()
        return str(content).strip()

    def ask(
        self,
        chat: str | dict | list,
        image: bytes | None = None,
        image_mime_type: str = "image/webp",
        with_screenshot: bool = False,
        callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        if image is None and with_screenshot:
            image = self.phone.screenshot_webp()
            image_mime_type = "image/webp"

        self.messages.append(self._build_human_message(chat, image=image, image_mime_type=image_mime_type))
        self.messages = self._prune_image_history(self.messages)

        steps = 0
        while steps < self.max_steps:
            llm_messages = [self._build_system_message(), *self.messages]
            ai_message = self.bound_model.invoke(llm_messages)
            self.messages.append(ai_message)

            assistant_text = self._message_text(ai_message)
            if assistant_text:
                self._emit(callback, {"type": "assistant", "text": assistant_text, "message": ai_message})

            tool_calls = getattr(ai_message, "tool_calls", None) or []
            if not tool_calls:
                return {"output": str(getattr(ai_message, "content", "")), "messages": self.messages}

            tool_call = tool_calls[0]
            tool_name = str(tool_call.get("name", "")).strip()
            tool_args = self._extract_tool_args(tool_call)

            if tool_name == "finish":
                final_answer = self._extract_finish_answer(tool_args) or str(getattr(ai_message, "content", "")).strip() or "Done."
                self._emit(callback, {"type": "finish", "text": final_answer, "args": tool_args})
                return {"output": final_answer, "messages": self.messages}

            self._emit(callback, {"type": "tool_call", "name": tool_name, "args": tool_args, "tool_call": tool_call})
            tool_result = self._invoke_tool(tool_name, tool_args)
            self._emit(callback, {"type": "tool_result", "name": tool_name, "result": tool_result})
            self.messages.append(ToolMessage(content=tool_result, tool_call_id=tool_call.get("id", tool_name), name=tool_name))
            self.messages.append(self._build_followup_screenshot_message())
            self.messages = self._prune_image_history(self.messages)
            steps += 1

        final_text = f"Stopped after reaching the maximum tool steps ({self.max_steps})."
        self._emit(callback, {"type": "finish", "text": final_text, "reason": "max_steps"})
        return {
            "output": final_text,
            "messages": self.messages,
        }

    def reset(self) -> None:
        self.messages = []
