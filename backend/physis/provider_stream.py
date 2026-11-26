"""Decode provider events incrementally. Only a complete structured proposal leaves this module."""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

MAX_CONTENT = 16_384
MAX_WIRE = 2 * 1024 * 1024


class ReplayTransport:
    """One-shot, network-free adapter for a previously stored assistant response.

    `content` is already-extracted assistant text. `wire_message` may be a
    normalized assistant message or a complete OpenAI, Anthropic, or Ollama
    response envelope. This adapter never sends an HTTP request and does not
    claim where the stored response originally came from.
    """

    def __init__(self, *, content=None, wire_message=None):
        if (content is None) == (wire_message is None):
            raise ValueError("provide exactly one replay content or wire message")
        if content is not None:
            extracted = content
        else:
            extracted = self._extract_wire_content(wire_message)
        if not isinstance(extracted, str) or not extracted or len(extracted) > MAX_CONTENT:
            raise ValueError("invalid replay content")
        self._content = extracted
        self._consumed = False
        self.origin = "replay"

    @staticmethod
    def _extract_wire_content(wire):
        if not isinstance(wire, dict) or "error" in wire:
            raise ValueError("invalid replay wire message")
        if "choices" in wire:
            choices = wire.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError("invalid replay choices")
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
                raise ValueError("incomplete replay choice")
            message = choice.get("message")
        elif "stop_reason" in wire:
            if wire.get("role") != "assistant" or wire.get("stop_reason") != "end_turn":
                raise ValueError("incomplete replay message")
            blocks = wire.get("content")
            if not isinstance(blocks, list) or len(blocks) != 1 or not isinstance(blocks[0], dict):
                raise ValueError("invalid replay content blocks")
            block = blocks[0]
            if block.get("type") != "text":
                raise ValueError("unexpected replay block")
            return block.get("text")
        elif "message" in wire:
            if wire.get("done") is not True or wire.get("done_reason", "stop") != "stop":
                raise ValueError("incomplete replay message")
            message = wire.get("message")
        else:
            message = wire
        if (not isinstance(message, dict) or message.get("role") != "assistant"
                or message.get("refusal") or message.get("tool_calls") or message.get("function_call")):
            raise ValueError("unexpected replay assistant message")
        return message.get("content")

    @property
    def consumed(self) -> bool:
        return self._consumed

    def take_content(self):
        if self._consumed:
            raise ValueError("replay response already consumed")
        self._consumed = True
        return self._content


_current_replay: ContextVar[ReplayTransport | None] = ContextVar("physis_replay", default=None)


@contextmanager
def replay_context(transport):
    """Scope one explicit replay to a test turn; never changes provider selection."""
    if not isinstance(transport, ReplayTransport):
        raise TypeError("replay_context requires ReplayTransport")
    token = _current_replay.set(transport)
    try:
        yield transport
    finally:
        _current_replay.reset(token)


def current_replay_transport():
    return _current_replay.get()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def parse_json(data):
    return json.loads(data, object_pairs_hook=no_duplicates)


async def bounded_bytes(response, limit=MAX_WIRE):
    size = 0
    async for packet in response.aiter_bytes():
        size += len(packet)
        if size > limit:
            raise ValueError("response too large")
        yield packet


async def read_json(response):
    body = bytearray()
    async for packet in bounded_bytes(response):
        body.extend(packet)
    return parse_json(body)


async def lines(response):
    """Handle UTF-8 characters and lines split across network packets."""
    tail = b""
    async for packet in bounded_bytes(response):
        *complete, tail = (tail + packet).split(b"\n")
        if len(tail) > 65_536:
            raise ValueError("line too long")
        for line in complete:
            if len(line) > 65_536:
                raise ValueError("line too long")
            yield line.rstrip(b"\r").decode("utf-8")
    if tail:
        yield tail.rstrip(b"\r").decode("utf-8")


async def sse(response):
    data = []
    event = None
    async for line in lines(response):
        if not line:
            if data:
                yield event, "\n".join(data)
            data, event = [], None
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
    # SSE dispatch requires a blank line. Dropping a partial terminal event
    # leaves the decoder without its required completion marker.


def usage_from(name, data, record):
    if not isinstance(data, dict):
        return
    fields = {
        "anthropic": ("input_tokens", "output_tokens"),
        "ollama": ("prompt_eval_count", "eval_count"),
    }.get(name, ("prompt_tokens", "completion_tokens"))
    for source, target in zip(fields, ("input_tokens", "output_tokens")):
        value = data.get(source)
        if type(value) is int and 0 <= value <= 2**53 - 1:
            record[target] = value
    if name == "ollama":
        for source, target in (("load_duration", "model_load_ms"),
                               ("eval_duration", "generation_ms")):
            value = data.get(source)
            if type(value) is int and 0 <= value <= 2**63 - 1:
                record[target] = round(value / 1_000_000)


class Accumulator:
    def __init__(self, callback, operation, record=None, started=None):
        self.parts = []
        self.size = 0
        self.last_update = 0.0
        self.callback = callback
        self.operation = operation
        self.record = record
        self.started = started

    def add(self, text):
        if not isinstance(text, str):
            raise ValueError("invalid text")
        if not text:
            return
        if self.record is not None and self.started is not None and self.record.get("ttft_ms") is None:
            self.record["ttft_ms"] = round((monotonic() - self.started) * 1000)
        self.size += len(text)
        if self.size > MAX_CONTENT:
            raise ValueError("content too large")
        self.parts.append(text)
        now = monotonic()
        if self.callback and (len(self.parts) == 1 or now - self.last_update >= 0.2):
            self.callback({"operation": self.operation, "received_chunks": len(self.parts)})
            self.last_update = now


def assistant_fields(obj):
    if (obj.get("role", "assistant") != "assistant" or obj.get("refusal")
            or obj.get("tool_calls") or obj.get("function_call")):
        raise ValueError("unexpected message")


async def openai_stream(response, collector, record):
    stopped = False
    async for event, data in sse(response):
        if event not in (None, "message"):
            raise ValueError("unexpected SSE event")
        if data == "[DONE]":
            if stopped:
                return
            raise ValueError("missing stop reason")
        body = parse_json(data)
        if "error" in body:
            raise ValueError("stream error")
        usage_from("openai", body.get("usage"), record)
        if body["choices"] == [] and stopped and isinstance(body.get("usage"), dict):
            continue
        choice, = body["choices"]
        if stopped or choice.get("index", 0) != 0:
            raise ValueError("unexpected choice")
        delta = choice["delta"]
        assistant_fields(delta)
        if delta.get("content") is not None:
            collector.add(delta["content"])
        reason = choice.get("finish_reason")
        if reason is not None:
            if reason != "stop":
                raise ValueError("incomplete choice")
            stopped = True
    raise ValueError("missing stream terminator")


async def anthropic_stream(response, collector, record):
    state = "start"
    async for event, data in sse(response):
        body = parse_json(data)
        kind = body["type"]
        if event is not None and event != kind:
            raise ValueError("event type mismatch")
        if kind == "ping":
            continue
        if kind == "message_start" and state == "start":
            msg = body["message"]
            if msg["role"] != "assistant" or msg["content"] != [] or msg.get("stop_reason") is not None:
                raise ValueError("unexpected message")
            usage_from("anthropic", msg.get("usage"), record)
            state = "message"
        elif kind == "content_block_start" and state == "message" and body["index"] == 0:
            block = body["content_block"]
            if block["type"] != "text":
                raise ValueError("unexpected block")
            collector.add(block["text"])
            state = "text"
        elif kind == "content_block_delta" and state == "text" and body["index"] == 0:
            delta = body["delta"]
            if delta["type"] != "text_delta":
                raise ValueError("unexpected delta")
            collector.add(delta["text"])
        elif kind == "content_block_stop" and state == "text" and body["index"] == 0:
            state = "closed"
        elif kind == "message_delta" and state in {"closed", "stopped"}:
            reason = body["delta"].get("stop_reason")
            if reason not in {None, "end_turn"}:
                raise ValueError("incomplete message")
            if reason == "end_turn":
                state = "stopped"
            usage_from("anthropic", body.get("usage"), record)
        elif kind == "message_stop" and state == "stopped":
            return
        else:
            raise ValueError("unexpected event")
    raise ValueError("missing stream terminator")


async def ollama_stream(response, collector, record):
    async for line in lines(response):
        if not line.strip():
            continue
        body = parse_json(line)
        if "error" in body or type(body["done"]) is not bool:
            raise ValueError("invalid event")
        msg = body["message"]
        if msg["role"] != "assistant":
            raise ValueError("unexpected role")
        assistant_fields(msg)
        collector.add(msg["content"])
        if body["done"]:
            if body.get("done_reason", "stop") != "stop":
                raise ValueError("incomplete message")
            usage_from("ollama", body, record)
            return
    raise ValueError("missing stream terminator")


async def read_stream(name, response, context, record, started=None):
    collector = Accumulator(getattr(context, "on_progress", None), record["operation"], record, started)
    decoder = {"anthropic": anthropic_stream, "ollama": ollama_stream}.get(name, openai_stream)
    await decoder(response, collector, record)
    return "".join(collector.parts)
