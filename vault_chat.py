#!/usr/bin/env python3
"""
Obsidian Vault Chatbot

Usage:
    python vault_chat.py /path/to/vault
    VAULT_PATH=/path/to/vault python vault_chat.py

Reads all .md files from your Obsidian vault and lets you query them
via a streaming CLI chat. Uses prompt caching to reduce repeated costs.
"""
import os
import sys
from pathlib import Path

import anthropic

MODEL = "claude-opus-4-8"
MAX_TOKENS = 4096


def load_vault(vault_path: str) -> str:
    root = Path(vault_path)
    if not root.is_dir():
        sys.exit(f"Vault path not found or not a directory: {vault_path}")

    notes = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        try:
            content = path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            continue
        if content:
            notes.append(f"## {rel}\n\n{content}")

    if not notes:
        sys.exit(f"No .md files found in vault: {vault_path}")

    return "\n\n---\n\n".join(notes)


def build_system_blocks(vault_content: str) -> list:
    return [
        {
            "type": "text",
            "text": (
                "You are a helpful assistant with access to the user's Obsidian notes below. "
                "Answer questions based on the notes. When your answer is clearly grounded in "
                "specific notes, cite the filename(s) naturally (e.g., 'According to ProjectX/ideas.md...'). "
                "If the notes don't contain relevant information, say so honestly."
                "\n\n"
                "=== OBSIDIAN VAULT ===\n\n"
            ),
        },
        {
            "type": "text",
            "text": vault_content,
            "cache_control": {"type": "ephemeral"},
        },
    ]


def chat(vault_path: str) -> None:
    print(f"Loading vault: {vault_path}", end=" ", flush=True)
    vault_content = load_vault(vault_path)
    note_count = vault_content.count("\n## ")  + 1
    print(f"({note_count} notes loaded)")
    print("Type your question, or 'quit' / Ctrl-C to exit.\n")

    client = anthropic.Anthropic()
    system = build_system_blocks(vault_content)
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

        print("Claude: ", end="", flush=True)
        response_text = ""

        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=history,
            thinking={"type": "adaptive"},
            betas=["prompt-caching-2024-07-31"],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                response_text += text

        print("\n")
        history.append({"role": "assistant", "content": response_text})


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
