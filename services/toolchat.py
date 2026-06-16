import enum
import collections.abc
from typing import Callable, Literal, Self
from dataclasses import dataclass

import ollama

from .ollama_adapter import ollama_client

@dataclass
class ChatToolParameter:
    type: str
    description: str
    required: bool = True

    def ollama_toolparam(self) -> ollama.Tool.Function.Parameters.Property:
        return ollama.Tool.Function.Parameters.Property(type=self.type, description=self.description)

@dataclass
class ChatTool:
    description: str
    parameters: dict[str, ChatToolParameter]
    impl: Callable[[collections.abc.Mapping[str, object]], object]

    def ollama_tool(self, name: str) -> ollama.Tool:
        rq = [k for k, v in self.parameters.items() if v.required]
        props = {k: v.ollama_toolparam() for k, v in self.parameters.items()}
        params = ollama.Tool.Function.Parameters(type="object", required=rq, properties=props, **{"$defs": None})
        return ollama.Tool(type="function", function=ollama.Tool.Function(name=name, description=self.description, parameters=params))

class ChatMessageSource(enum.Enum):
    USER = 0
    ASSISTANT = 1

    def ollama_role(self) -> str:
        return {self.USER: "user", self.ASSISTANT: "assistant"}[self]

    @classmethod
    def from_ollama_role(cls, role: str) -> ChatMessageSource:
        return {"user": cls.USER, "assistant": cls.ASSISTANT}[role]

@dataclass
class ChatMessage:
    source: ChatMessageSource
    content: str

    def ollama_message(self) -> ollama.Message:
        return ollama.Message(role=self.source.ollama_role(), content=self.content)

    @classmethod
    def from_ollama_message(cls, msg: ollama.Message) -> Self:
        if msg.content is None:
            raise ValueError("msg.content must not be none")
        return cls(ChatMessageSource.from_ollama_role(msg.role), msg.content)

async def chat_including_tools(client: ollama.AsyncClient, model: str, messages: collections.abc.Sequence[ChatMessage], tools: collections.abc.Mapping[str, ChatTool]) -> collections.abc.AsyncIterator[str]:
    real_tools = [tool.ollama_tool(name) for name, tool in tools.items()]
    real_messages = [x.ollama_message() for x in messages]
    new_messages: list[ollama.Message] = []
    while True:
        response = await client.chat(model, messages=[*real_messages, *new_messages], tools=real_tools, stream=True)
        tool_calls: list[ollama.Message.ToolCall] = []
        async for fragment in response:
            if fragment.message.content:
                yield fragment.message.content

            if fragment.message.tool_calls:
                tool_calls.extend(fragment.message.tool_calls)

        if not tool_calls:
            break

        new_messages.append(ollama.Message(role="assistant", tool_calls=tool_calls))
        for tool_call in tool_calls:
            try:
                tool = tools[tool_call.function.name]
            except KeyError:
                new_messages.append(ollama.Message(role="tool", tool_name=tool_call.function.name, content=f"NameError: Name {tool_call.function.name} is not defined"))
                continue
            try:
                res = str(tool.impl(tool_call.function.arguments))
            except Exception as e:
                res = f"{type(e).__qualname__}: {e}"
            new_messages.append(ollama.Message(role="tool", tool_name=tool_call.function.name, content=res))

type ResponseFragment = tuple[Literal[True], str]
type Script = tuple[Literal[False], str]

async def script_chat(model: str, log: list[ChatMessage], stream: bool = False) -> collections.abc.AsyncGenerator[ResponseFragment | Script, str | None]:
    client = ollama_client()
    
    real_tools = [
        ollama.Tool(type="function", function=ollama.Tool.Function(
            name="run_python_script",
            description="Runs a script in the context of the currently edited UI.",
            parameters=ollama.Tool.Function.Parameters(type="object", **{"$defs": None},
                required=["script"],
                properties={
                    "script": ollama.Tool.Function.Parameters.Property(type="string", description="The Python script to run.")
                }
            )
        ))
    ]
    real_messages = [x.ollama_message() for x in log]
    new_messages: list[ollama.Message] = []
    content = ""
    while True:
        response = await client.chat(model, messages=[*real_messages, *new_messages], tools=real_tools, stream=True)
        tool_calls: list[ollama.Message.ToolCall] = []
        async for fragment in response:
            if fragment.message.content:
                if stream:
                    yield (True, fragment.message.content)
                content += fragment.message.content

            if fragment.message.thinking:
                print(fragment.message.thinking, end="", flush=True)

            if fragment.message.tool_calls:
                tool_calls.extend(fragment.message.tool_calls)

        if not tool_calls:
            break

        new_messages.append(ollama.Message(role="assistant", tool_calls=tool_calls))
        for tool_call in tool_calls:
            result = (yield (False, tool_call.function.arguments["script"]))
            if result is None:
                text = f"RuntimeError: Could not run script: The user has aborted the operation."
            elif len(result) > 1024:
                text = f"RuntimeError: Your script generated overlong output: {len(result)}B. Please ask me again, assistant, but limiting your script's output length."
            elif result.strip():
                text = result
            else:
                text = f"runner.py:1:1: UserWarning: your script successfully finished, but generated no stdout / stderr; did you forget to print()? Analyze the exit condition of your script to figure out if this is correct!"
            new_messages.append(ollama.Message(role="tool", tool_name=tool_call.function.name, content=text))

    if not stream:
        yield (True, content)

async def main():
    def get_temperature(args: collections.abc.Mapping[str, object]) -> object:
        if not isinstance(city_name := args.get("city"), str):
            raise TypeError(f"city must be 'str', got {type(city_name).__qualname__!r}")
        return "22C"

    tools = {
        "get_temperature": ChatTool("Gets the temperature of a city.", {"city": ChatToolParameter("string", "The city to check.")}, get_temperature)
    }

    client = ollama.AsyncClient("localhost:12588")

    messages: list[ChatMessage] = []
    while True:
        messages.append(ChatMessage(ChatMessageSource.USER, input("ask the ai some shit: ")))
        msg = ""
        async for fragment in chat_including_tools(client, "qwen3", messages, tools):
            msg += fragment
            print(fragment, end="", flush=True)
        if not msg.endswith("\n"):
            print()
        messages.append(ChatMessage(ChatMessageSource.ASSISTANT, msg.strip()))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
