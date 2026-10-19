#!/usr/bin/env python3
"""Minimal terminal chat with the Apertus models over the OpenAI-compatible API.

Standalone: only the Python standard library, nothing from the project.

    python3 tools/apertus_chat.py                     # asks for the key if APERTUS_API_KEY is not set
    APERTUS_API_KEY=... python3 tools/apertus_chat.py --model apertus-v1-5-8b

Commands in the chat:
    /models          list available models        /model <name>   switch model
    /system <text>   set a system prompt          /temp <0..2>    set temperature
    /reset           forget the conversation      /quit           exit
"""
import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = "https://gateway.keera.ch/api/v1"


def request(url: str, key: str, payload: dict | None = None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=600)


def list_models(base: str, key: str) -> list[str]:
    with request(base + "/models", key) as r:
        return sorted(m["id"] for m in json.load(r).get("data", []))


def chat(base: str, key: str, model: str, messages: list[dict], temperature: float) -> str:
    """Stream the answer to the terminal and return it."""
    payload = {"model": model, "messages": messages, "temperature": temperature, "stream": True}
    t0, first, parts = time.time(), None, []
    with request(base + "/chat/completions", key, payload) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            delta = json.loads(data)["choices"][0].get("delta", {})
            text = delta.get("content") or ""
            if text:
                first = first or time.time()
                parts.append(text)
                print(text, end="", flush=True)
    answer = "".join(parts)
    took = time.time() - t0
    wait = (first - t0) if first else took
    print(f"\n\033[2m[{model} · erste Antwort nach {wait:.1f}s · total {took:.1f}s · ~{len(answer.split())} Wörter]\033[0m")
    return answer


def main():
    ap = argparse.ArgumentParser(description="Apertus test chat")
    ap.add_argument("--url", default=os.environ.get("APERTUS_BASE_URL", DEFAULT_URL))
    ap.add_argument("--model", default="apertus-v1-5-70b")
    ap.add_argument("--temp", type=float, default=0.7)
    args = ap.parse_args()

    key = os.environ.get("APERTUS_API_KEY") or getpass.getpass("API key (hidden): ").strip()
    base, model, temp = args.url.rstrip("/"), args.model, args.temp
    system, history = "", []
    print(f"Chat mit {model} über {base}. /models, /model <name>, /system <text>, /temp <x>, /reset, /quit\n")

    while True:
        try:
            user = input("\033[1mDu:\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        cmd, _, arg = user.partition(" ")
        if cmd == "/quit":
            break
        if cmd == "/reset":
            history = []
            print("(Verlauf gelöscht)")
            continue
        if cmd == "/system":
            system, history = arg, []
            print(f"(Systemprompt gesetzt, Verlauf gelöscht: {system!r})")
            continue
        if cmd == "/temp":
            temp = float(arg)
            print(f"(Temperatur {temp})")
            continue
        if cmd == "/model":
            model = arg.strip() or model
            print(f"(Modell {model})")
            continue
        if cmd == "/models":
            try:
                print("\n".join("  " + m for m in list_models(base, key)))
            except urllib.error.URLError as e:
                print(f"(Fehler: {e})")
            continue

        history.append({"role": "user", "content": user})
        messages = ([{"role": "system", "content": system}] if system else []) + history
        print(f"\033[1m{model}:\033[0m ", end="", flush=True)
        try:
            history.append({"role": "assistant", "content": chat(base, key, model, messages, temp)})
        except urllib.error.HTTPError as e:
            history.pop()
            print(f"\n(HTTP {e.code}: {e.read().decode(errors='replace')[:300]})")
        except (urllib.error.URLError, TimeoutError) as e:
            history.pop()
            print(f"\n(Verbindungsfehler: {e})")


if __name__ == "__main__":
    sys.exit(main())
