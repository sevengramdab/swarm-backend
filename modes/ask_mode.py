"""Ask Mode -- Direct Q&A with strict factual grounding.

This module acts like a closed-circuit electrical panel: real-time data is the
only energized path. Training data is locked out at the main breaker.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, AsyncGenerator, Optional, Set, Tuple

from core.model_router import chat_completion, select_model
from integrations.weather import get_current_weather, get_time_at_location

logger = logging.getLogger(__name__)

# ===============================================================================
# CONSTANTS -- Like a title block: every value is dimensioned and locked
# ===============================================================================
_ASK_TEMPERATURE: float = 0.0   # Main breaker locked -- zero creative current
_ASK_TOP_P: float = 0.1          # Narrow pipe -- only the most probable tokens flow
_MAX_TOOL_ITERATIONS: int = 3   # Max relay cycles before we trip the breaker
_MAX_CONTEXT_CHARS: int = 6000  # Circuit ampacity -- max load before we derate
_CHUNK_OVERLAP_CHARS: int = 200  # Like lap joints in welded beams: overlap for strength
_REFUSAL_PHRASE: str = (
    "I do not have sufficient information to answer that question."
)

_SIMPLE_SYSTEM_PROMPT: str = (
    "You are OrbitScribe, a helpful AI assistant with tool access. "
    "Answer the user's questions clearly and concisely. "
    "When you need to use a tool, output ONLY a JSON block inside ```tool ... ``` like:\n"
    '```tool\n{"tool": "web_search", "args": {"query": "search term"}}\n```\n\n'
    "Available tools: web_search, calculate, get_current_weather, get_time_at_location, etsy_profit_calculator, etsy_research, etsy_pricing_optimizer.\n"
    "After a tool result, provide your final answer. Be concise."
)

# ===============================================================================
# TOOL REGISTRY -- Like a BOM (Bill of Materials) for our automation panel
# ===============================================================================
AVAILABLE_TOOLS: Dict[str, Dict[str, Any]] = {
    "get_weather": {
        "description": "Get current weather conditions for a city or location.",
        "parameters": {"location": "string"},
    },
    "get_time": {
        "description": "Get the current local time for a city or location.",
        "parameters": {"location": "string"},
    },
}

# ===============================================================================
# REGEX PATTERNS -- Like AutoCAD layer filters: we only let exact matches through
# ===============================================================================
_WEATHER_PATTERNS: List[re.Pattern] = [
    # "weather in Seattle" or "what's the weather in Seattle"
    re.compile(
        r"weather\s+(?:in|at|for)\s+([A-Za-z][A-Za-z\s,]+?)(?:\?|$|\.|\!|\s+and|\s+with|\s+like|\s+today|\s+right\s+now|\s+now|\s+tomorrow)",
        re.IGNORECASE,
    ),
    re.compile(
        r"what(?:'s|s| is)\s+the\s+weather\s+(?:in|at|for)\s+([A-Za-z][A-Za-z\s,]+?)(?:\?|$|\.|\!|\s+and|\s+with|\s+like|\s+today|\s+right\s+now|\s+now|\s+tomorrow)",
        re.IGNORECASE,
    ),
    re.compile(
        r"how(?:'s|s| is)\s+the\s+weather\s+(?:in|at|for)\s+([A-Za-z][A-Za-z\s,]+?)(?:\?|$|\.|\!|\s+and|\s+with|\s+like|\s+today|\s+right\s+now|\s+now|\s+tomorrow)",
        re.IGNORECASE,
    ),
    # Bare "weather Seattle?" -- like a direct dimension callout without a leader line
    re.compile(r"weather\s+(?!in\s|at\s|for\s)([A-Za-z][A-Za-z\s,]+?)(?:\?|$|\.|\!)", re.IGNORECASE),
]

_TIME_PATTERNS: List[re.Pattern] = [
    re.compile(
        r"time\s+(?:in|at|for)\s+([A-Za-z][A-Za-z\s,]+?)(?:\?|$|\.|\!|\s+and|\s+with|\s+there|\s+right\s+now|\s+now)",
        re.IGNORECASE,
    ),
    re.compile(
        r"what\s+time\s+(?:is\s+it\s+)?(?:in|at|for)\s+([A-Za-z][A-Za-z\s,]+?)(?:\?|$|\.|\!|\s+and|\s+with|\s+there|\s+right\s+now|\s+now)",
        re.IGNORECASE,
    ),
    re.compile(
        r"current\s+time\s+(?:in|at|for)\s+([A-Za-z][A-Za-z\s,]+?)(?:\?|$|\.|\!|\s+and|\s+with|\s+there|\s+right\s+now|\s+now)",
        re.IGNORECASE,
    ),
    re.compile(
        r"what\s+is\s+the\s+time\s+(?:in|at|for)\s+([A-Za-z][A-Za-z\s,]+?)(?:\?|$|\.|\!|\s+and|\s+with|\s+there|\s+right\s+now|\s+now)",
        re.IGNORECASE,
    ),
    re.compile(r"time\s+(?!in\s|at\s|for\s)([A-Za-z][A-Za-z\s,]+?)(?:\?|$|\.|\!)", re.IGNORECASE),
]

# Words that are not city names -- like filtering out grid lines in a viewport selection
_LOCATION_NOISE_WORDS: Set[str] = {
    "right", "now", "today", "tomorrow", "and", "with", "like", "there",
    "the", "time", "weather", "is", "it", "what", "how", "current",
    "in", "at", "for",
}


# -------------------------------------------------------------------------------
# Data Classes -- Like a structured title block: every field has a type and purpose
# -------------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation -- like a wire label: name on one end, args on the other."""
    tool: str
    args: Dict[str, Any]


@dataclass
class DocumentChunk:
    """A slice of document text -- like a detail view clipped from a master drawing."""
    source: str          # Which document this chunk came from (filename or label)
    text: str            # The actual chunk content
    index: int           # Chunk sequence number
    score: float = 0.0   # Relevance score after ranking


# -------------------------------------------------------------------------------
# System Prompt Builder -- The "Main Breaker" that isolates training data
# -------------------------------------------------------------------------------
def _build_system_prompt(
    realtime_data: str = "",
    workspace_context: str = "",
    document_chunks: List[DocumentChunk] = None,
) -> str:
    """Build a helpful assistant system prompt with optional context."""
    lines: List[str] = [_SIMPLE_SYSTEM_PROMPT]

    if workspace_context:
        lines.extend([
            "",
            "=== WORKSPACE CONTEXT ===",
            workspace_context,
            "=== END WORKSPACE CONTEXT ===",
        ])

    if document_chunks:
        lines.extend([
            "",
            "=== REFERENCE DOCUMENTS ===",
        ])
        for chunk in document_chunks:
            lines.append(f"--- Source: {chunk.source} | Chunk {chunk.index} ---")
            lines.append(chunk.text)
            lines.append("")
        lines.extend([
            "=== END REFERENCE DOCUMENTS ===",
        ])

    if realtime_data:
        lines.extend([
            "",
            "=== REAL-TIME DATA ===",
            realtime_data,
            "=== END REAL-TIME DATA ===",
        ])

    lines.extend([
        "",
        "=== TOOLS ===",
        "If you need current weather or time data, output a tool block like:",
        "```tool",
        '{"tool": "get_weather", "args": {"location": "Seattle"}}',
        "```",
    ])

    return "\n".join(lines)


# -------------------------------------------------------------------------------
# RAG Pipeline -- Like a smart home hub routing only relevant sensor feeds
# -------------------------------------------------------------------------------
def _tokenize(text: str) -> Set[str]:
    """
    Extract lowercase alphabetic tokens from text.

    Like running an AutoCAD filter to select only text entities on a specific layer:
    we ignore dimensions, lines, and hatches (numbers/punctuation) and keep only words.
    """
    return set(re.findall(r"[a-z]{2,}", text.lower()))


def _chunk_document(source: str, text: str, max_chunk_size: int = 2000, overlap: int = _CHUNK_OVERLAP_CHARS) -> List[DocumentChunk]:
    """
    Split a document into overlapping chunks.

    Like cutting a long I-beam into transportable sections, but leaving a lap joint
    at each cut so the welder (the LLM) knows how the pieces connect.
    """
    chunks: List[DocumentChunk] = []
    if not text:
        return chunks

    start = 0
    idx = 0
    while start < len(text):
        end = start + max_chunk_size
        # Try to break at a paragraph or sentence boundary so we don't cut mid-thought
        if end < len(text):
            # Look for the nearest paragraph break before the limit
            para_break = text.rfind("\n\n", start, end)
            if para_break != -1 and para_break > start + 100:
                end = para_break
            else:
                # Fallback to sentence break
                sent_break = max(
                    text.rfind(". ", start, end),
                    text.rfind("? ", start, end),
                    text.rfind("! ", start, end),
                )
                if sent_break != -1 and sent_break > start + 100:
                    end = sent_break + 1
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(DocumentChunk(source=source, text=chunk_text, index=idx))
            idx += 1
        start = end - overlap if end < len(text) else len(text)
    return chunks


def _rank_chunks(question: str, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
    """
    Score chunks by keyword overlap with the question and sort descending.

    Like a smart thermostat polling every room sensor and only displaying the ones
    that actually changed temperature -- irrelevant sensors are dimmed out.
    """
    q_tokens = _tokenize(question)
    if not q_tokens:
        return chunks

    scored: List[Tuple[float, DocumentChunk]] = []
    for chunk in chunks:
        c_tokens = _tokenize(chunk.text)
        if not c_tokens:
            continue
        # Simple Jaccard-ish overlap score
        intersection = len(q_tokens & c_tokens)
        union = len(q_tokens | c_tokens)
        score = intersection / union if union else 0.0
        # Boost exact phrase matches
        q_lower = question.lower()
        if q_lower in chunk.text.lower():
            score += 0.5
        chunk.score = round(score, 4)
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]


def _select_top_chunks(
    question: str,
    documents: List[str],
    source_names: Optional[List[str]] = None,
    max_chars: int = _MAX_CONTEXT_CHARS,
) -> List[DocumentChunk]:
    """
    Chunk all documents, rank by relevance, and return the best chunks that fit under max_chars.

    Like a Load Center (breaker panel) schedule: you can only fit so many breakers
    before the bus bar is full. We sort by priority (relevance) and fill the panel
    until we hit ampacity.
    """
    all_chunks: List[DocumentChunk] = []
    for i, doc in enumerate(documents):
        name = source_names[i] if source_names and i < len(source_names) else f"Document {i + 1}"
        all_chunks.extend(_chunk_document(name, doc))

    if not all_chunks:
        return []

    ranked = _rank_chunks(question, all_chunks)

    selected: List[DocumentChunk] = []
    used_chars = 0
    for chunk in ranked:
        chunk_len = len(chunk.text)
        if used_chars + chunk_len > max_chars and selected:
            # Ampacity reached -- stop adding breakers
            break
        selected.append(chunk)
        used_chars += chunk_len

    return selected


# -------------------------------------------------------------------------------
# Location Extraction -- Like a smart home sensor filtering out noise
# -------------------------------------------------------------------------------
def _clean_location(raw: str) -> str:
    """
    Strip noise words from a location string.

    Like a proximity sensor in a smart home: it ignores pets walking by
    and only triggers when a real person (city name) enters the zone.
    """
    words = raw.split()
    while words and words[-1].lower().strip(",") in _LOCATION_NOISE_WORDS:
        words.pop()
    while words and words[0].lower().strip(",") in _LOCATION_NOISE_WORDS:
        words.pop(0)
    return " ".join(words)


def _extract_locations(text: str, patterns: List[re.Pattern]) -> List[str]:
    """
    Extract location names from text using regex patterns.

    Like running a selection filter across multiple AutoCAD layers:
    each pattern is a different layer, and we collect every valid entity.
    """
    locations: List[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            candidate = match.group(1).strip(" ,")
            cleaned = _clean_location(candidate)
            if cleaned and len(cleaned) > 1:
                locations.append(cleaned)
    return locations


# -------------------------------------------------------------------------------
# Real-Time Data Fetcher -- The only "energized" circuit in the panel
# -------------------------------------------------------------------------------
async def _fetch_realtime_data(question: str) -> str:
    """
    Proactively fetch weather and time data based on question intent.

    Like a home automation hub polling every sensor BEFORE the user opens
    the dashboard: the data is already fresh and waiting on the screen.
    """
    results: List[str] = []
    lower_q = question.lower()

    # -- Detect weather intent and pull live sensor readings --
    weather_locations = _extract_locations(question, _WEATHER_PATTERNS)
    seen_weather: Set[str] = set()

    for location in weather_locations:
        loc_key = location.lower()
        if loc_key in seen_weather:
            continue
        seen_weather.add(loc_key)
        try:
            weather = await get_current_weather(location)
            results.append(weather)
        except Exception as e:
            logger.warning(f"Weather fetch failed for '{location}': {e}")
            results.append(f"Could not fetch weather for {location}.")

    # -- Detect time intent and pull live clock readings --
    time_locations = _extract_locations(question, _TIME_PATTERNS)
    seen_time: Set[str] = set()

    for location in time_locations:
        loc_key = location.lower()
        if loc_key in seen_time:
            continue
        seen_time.add(loc_key)
        try:
            time_info = await get_time_at_location(location)
            results.append(time_info)
        except Exception as e:
            logger.warning(f"Time fetch failed for '{location}': {e}")
            results.append(f"Could not fetch time for {location}.")

    # -- Fallback: if user asks about BOTH weather and time but only names --
    #    the city once ("weather in Seattle and the time?"), clone the location.
    #    Like a 3-way switch controlling both a ceiling fan and its light
    #    from a single wall plate.
    has_weather_keyword = "weather" in lower_q
    has_time_keyword = "time" in lower_q or "clock" in lower_q

    if has_weather_keyword and has_time_keyword:
        if weather_locations and not time_locations:
            for location in weather_locations:
                loc_key = location.lower()
                if loc_key in seen_time:
                    continue
                seen_time.add(loc_key)
                try:
                    time_info = await get_time_at_location(location)
                    results.append(time_info)
                except Exception as e:
                    logger.warning(f"Fallback time fetch failed for '{location}': {e}")
                    results.append(f"Could not fetch time for {location}.")
        elif time_locations and not weather_locations:
            for location in time_locations:
                loc_key = location.lower()
                if loc_key in seen_weather:
                    continue
                seen_weather.add(loc_key)
                try:
                    weather = await get_current_weather(location)
                    results.append(weather)
                except Exception as e:
                    logger.warning(f"Fallback weather fetch failed for '{location}': {e}")
                    results.append(f"Could not fetch weather for {location}.")

    return "\n".join(results) if results else ""


# -------------------------------------------------------------------------------
# Tool Call Parser -- Like reading wire labels in a junction box
# -------------------------------------------------------------------------------
def _parse_tool_calls(text: str) -> List[ToolCall]:
    """
    Extract tool calls from assistant response text.

    Like opening a junction box and reading the wire labels:
    each ```tool block is a label telling us which circuit to energize.
    """
    calls: List[ToolCall] = []
    if "```tool" not in text:
        return calls

    parts = text.split("```tool")
    for part in parts[1:]:
        code = part.split("```")[0].strip()
        if not code:
            continue
        try:
            data = json.loads(code)
            tool_name = data.get("tool", "")
            args = data.get("args", {})
            if tool_name and isinstance(args, dict):
                calls.append(ToolCall(tool=tool_name, args=args))
        except json.JSONDecodeError:
            # Corrupted wire label -- ignore it and move to the next one
            logger.debug(f"Ignoring malformed tool call block: {code[:80]!r}")
            continue

    return calls


# -------------------------------------------------------------------------------
# Tool Executor -- Like a relay closing a circuit based on a control signal
# -------------------------------------------------------------------------------
async def _execute_tool(call: ToolCall) -> str:
    """
    Execute a single tool call and return the result as a string.

    Like a smart relay: it receives a control signal (tool name + args),
    closes the appropriate circuit, and returns the voltage reading.
    """
    tool_name = call.tool
    args = call.args

    if tool_name == "get_weather":
        location = str(args.get("location", "")).strip()
        if not location:
            return "Error: location required for get_weather"
        try:
            return await get_current_weather(location)
        except Exception as e:
            logger.error(f"Tool execution error (get_weather): {e}")
            return f"Error fetching weather for {location}: {e}"

    elif tool_name == "get_time":
        location = str(args.get("location", "")).strip()
        if not location:
            return "Error: location required for get_time"
        try:
            return await get_time_at_location(location)
        except Exception as e:
            logger.error(f"Tool execution error (get_time): {e}")
            return f"Error fetching time for {location}: {e}"

    else:
        return f"Error: unknown tool '{tool_name}'"


# -------------------------------------------------------------------------------
# MAIN ENTRY POINT -- The master control panel for Ask Mode
# -------------------------------------------------------------------------------
async def ask(
    question: str,
    history: List[Dict[str, str]] | None = None,
    workspace_context: str = "",
    documents: List[str] | None = None,
    document_names: List[str] | None = None,
    stream: bool = True,
    temperature: float | None = None,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Answer a direct question with strict factual grounding.

    Architecture analogy:
    - The user's question is a load requesting power.
    - _fetch_realtime_data() is the solar inverter: it generates live DC
      (real-time weather/time) BEFORE the inverter stage.
    - _select_top_chunks() is the smart breaker panel: it only routes the
      circuits (document chunks) that are relevant to the load.
    - _build_system_prompt() is the main breaker lockout: it isolates the load
      from the grid (training data) and routes only the authorized feeds.
    - chat_completion() is the inverter: converts the isolated DC into AC
      (natural language) with temperature=0.0 (pure sine wave, no noise).
    - The final stream is the energized circuit feeding the load.

    Parameters are LOCKED for deterministic output:
        temperature = 0.0  (no creative noise)
        top_p       = 0.1  (narrow token sampling)
    """
    # -- Step 0: Reject any attempt to override the breaker setpoints --
    #    Like a tamper-proof thermostat: the user can turn the dial, but
    #    the limit switch snaps back to the safety setpoint.
    if temperature is not None and temperature != _ASK_TEMPERATURE:
        logger.warning(
            f"Ask Mode received temperature={temperature}; overriding to {_ASK_TEMPERATURE} "
            "to prevent hallucination current."
        )
    locked_temperature = _ASK_TEMPERATURE
    locked_top_p = _ASK_TOP_P

    # -- Step 1: Poll every real-time sensor before the LLM even wakes up --
    #    Like a Building Management System (BMS) checking all HVAC sensors
    #    before displaying the dashboard -- the data is already fresh.
    realtime_data = ""
    try:
        realtime_data = await _fetch_realtime_data(question)
    except Exception as e:
        logger.error(f"Real-time data fetch crashed: {e}")
        realtime_data = ""

    # -- Step 2: Route only relevant document circuits to the panel --
    #    Like a smart load center that only energizes the breakers the
    #    appliance actually needs; everything else stays off.
    doc_chunks: List[DocumentChunk] = []
    try:
        if documents:
            doc_chunks = _select_top_chunks(
                question=question,
                documents=documents,
                source_names=document_names,
                max_chars=_MAX_CONTEXT_CHARS,
            )
    except Exception as e:
        logger.error(f"Document chunking/ranking crashed: {e}")
        doc_chunks = []

    # -- Step 3: Build the MAIN BREAKER system prompt --
    #    This is the lockout/tagout step: training data is physically isolated.
    system_content = _build_system_prompt(
        realtime_data=realtime_data,
        workspace_context=workspace_context,
        document_chunks=doc_chunks,
    )

    # -- Step 4: Assemble the message stack like a layered PCB --
    #    Order matters: system prompt at the bottom, user question at the top.
    #    Real-time data and document chunks were injected at the END of the
    #    system prompt so they sit closest to the user message -- highest
    #    attention priority, like a via placed directly under a component pad.
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_content},
    ]

    if history:
        # Sanitize history so we don't accidentally leak training data through it
        messages.extend(history)

    messages.append({"role": "user", "content": question})

    # -- Step 5: Tool-use loop with breaker trip protection --
    #    Like a motor starter with overload relays: we allow a few retries,
    #    but if the current spikes too many times we trip and return raw text.
    for iteration in range(_MAX_TOOL_ITERATIONS):
        full_response = ""
        try:
            # Use stream=True for true streaming -- like a live wire, not a battery
            async for chunk in chat_completion(
                messages,
                model=model,
                stream=True,
                temperature=locked_temperature,
                top_p=locked_top_p,
            ):
                full_response += chunk
                if stream:
                    yield chunk
        except Exception as e:
            logger.error(f"LLM call failed on iteration {iteration}: {e}")
            error_msg = f"[Ask Mode Error] LLM communication failure: {e}"
            if not stream:
                yield error_msg
            return

        # -- Parse any emergency tool calls from the response --
        tool_calls = _parse_tool_calls(full_response)

        if not tool_calls:
            # No more tools needed -- the circuit is stable.
            if not stream:
                yield full_response
            return

        # -- Tool calls detected: execute them and feed results back into the loop --
        #    Like a closed-loop control system: the sensor reading (tool result)
        #    is fed back into the controller (LLM) for the next iteration.
        messages.append({"role": "assistant", "content": full_response})

        for tc in tool_calls:
            try:
                result = await _execute_tool(tc)
            except Exception as e:
                logger.error(f"Tool execution crashed for {tc.tool}: {e}")
                result = f"Error: tool {tc.tool} crashed -- {e}"
            messages.append({"role": "user", "content": f"Tool result ({tc.tool}): {result}"})

    # -- Step 6: Breaker trip -- max iterations exceeded --
    #    Like an overload relay that finally trips after too many inrush events.
    logger.warning("Ask Mode hit max tool iterations -- returning final fallback.")
    final_fallback = ""
    try:
        async for chunk in chat_completion(
            messages,
            model=model,
            stream=True,
            temperature=locked_temperature,
            top_p=locked_top_p,
        ):
            final_fallback += chunk
            if stream:
                yield chunk
    except Exception as e:
        logger.error(f"Final fallback LLM call failed: {e}")
        final_fallback = "[Ask Mode Error] Unable to generate a response after multiple attempts."

    if not stream:
        yield final_fallback
