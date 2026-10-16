#!/usr/bin/env python3
"""
Obsidian Vault Agent

Usage:
    python vault_chat.py /path/to/vault
    VAULT_PATH=/path/to/vault python vault_chat.py

Claude uses search_notes and read_note tools to retrieve relevant content
on demand rather than loading the entire vault into context.
"""
import os
import re
import sys
from pathlib import Path

import anthropic

MODEL = "claude-opus-5-5"
MAX_TOKENS = 8192

TOOLS = [
    {
        "name": "search_notes",
        "description": (
            "Search the Obsidian vault for notes whose content or filename matches a query. "
            "Returns matching excerpts and file paths. Use this to find relevant notes before "
            "answering a question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords or phrase to search for (case-insensitive).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of notes to return (default 5, max 20).",
                    "default": 5,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "read_note",
        "description": "Read the full content of a specific note by its relative path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the note within the vault, e.g. 'Projects/ideas.md'.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class VaultIndex:
    def __init__(self, vault_path: str):
        self.root = Path(vault_path)
        if not self.root.is_dir():
            sys.exit(f"Vault path not found or not a directory: {vault_path}")
        self.notes: dict[str, str] = {}  # rel_path -> full content
        self._load()

    def _load(self) -> None:
        for path in sorted(self.root.rglob("*.md")):
            rel = str(path.relative_to(self.root))
            # Skip Obsidian system files
            if any(part.startswith(".") for part in Path(rel).parts):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                continue
            if content:
                self.notes[rel] = content

    def index_summary(self) -> str:
        """One-line summary per note for the system prompt."""
        lines = []
        for path, content in sorted(self.notes.items()):
            first_line = content.split("\n", 1)[0].lstrip("# ").strip()[:120]
            lines.append(f"- {path}: {first_line}" if first_line else f"- {path}")
        return "\n".join(lines)

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        max_results = min(max_results, 20)
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results = []
        for path, content in self.notes.items():
            if pattern.search(path) or pattern.search(content):
                # Return a short excerpt around the first match in content
                match = pattern.search(content)
                if match:
                    start = max(0, match.start() - 150)
                    end = min(len(content), match.end() + 300)
                    excerpt = content[start:end].strip()
                else:
                    excerpt = content[:400].strip()
                results.append({"path": path, "excerpt": excerpt})
                if len(results) >= max_results:
                    break
        return results

    def read(self, path: str) -> str | None:
        # Normalize path separators
        normalized = path.replace("\\", "/")
        return self.notes.get(normalized)


def execute_tool(vault: VaultIndex, tool_name: str, tool_input: dict) -> str:
    if tool_name == "search_notes":
        query = tool_input["query"]
        max_results = tool_input.get("max_results", 5)
        results = vault.search(query, max_results)
        if not results:
            return f"No notes found matching '{query}'."
        parts = []
        for r in results:
            parts.append(f"**{r['path']}**\n{r['excerpt']}")
        return "\n\n---\n\n".join(parts)

    if tool_name == "read_note":
        path = tool_input["path"]
        content = vault.read(path)
        if content is None:
            return f"Note not found: {path}"
        return f"**{path}**\n\n{content}"

    return f"Unknown tool: {tool_name}"


def chat(vault_path: str) -> None:
    print(f"Loading vault: {vault_path}", end=" ", flush=True)
    vault = VaultIndex(vault_path)
    note_count = len(vault.notes)
    print(f"({note_count} notes indexed)")
    print("Type your question, or 'quit' / Ctrl-C to exit.\n")

    client = anthropic.Anthropic()
    system = [
        {
            "type": "text",
            "text": (
                "You are a helpful assistant with access to the user's Obsidian vault. "
                "Use the search_notes tool to find relevant notes, and read_note to read "
                "a full note when needed. Always ground your answers in the actual notes. "
                "Cite note paths naturally when relevant "
                "(e.g., 'According to Projects/ideas.md...'). "
                "If the vault doesn't contain relevant information, say so honestly.\n\n"
                "=== VAULT INDEX ===\n\n"
            ),
        },
        {
            "type": "text",
            "text": vault.index_summary(),
            "cache_control": {"type": "ephemeral"},
        },
    ]
    history: list[dict] = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break

        history.append({"role": "user", "content": user_input})

        # Agentic loop: keep going until Claude stops calling tools
        while True:
            print("Claude: ", end="", flush=True)
            response_text = ""

            with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=TOOLS,
                messages=history,
                thinking={"type": "adaptive"},
            ) as stream:
                for event in stream:
                    if hasattr(event, "type") and event.type == "content_block_delta":
                        delta = event.delta
                        if hasattr(delta, "text"):
                            print(delta.text, end="", flush=True)
                            response_text += delta.text

            response = stream.get_final_message()

            # Preserve the full content list (includes thinking + tool_use blocks)
            history.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                print("\n")
                break

            # Execute tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"\n[calling {block.name}({block.input})]", flush=True)
                    result = execute_tool(vault, block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            history.append({"role": "user", "content": tool_results})


def main() -> None:
    vault_path = None
    if len(sys.argv) > 1:
        vault_path = sys.argv[1]
    else:
        vault_path = os.environ.get("VAULT_PATH")

    if not vault_path:
        sys.exit(
            "Usage: python vault_chat.py /path/to/vault\n"
            "       or set VAULT_PATH environment variable"
        )

    chat(vault_path)


if __name__ == "__main__":
    main()
