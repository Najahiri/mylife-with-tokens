"""Set the Apertus API access from the terminal (the UI will offer the same later).

    python -m rag_model.settings          # asks for URL, key (hidden) and model names, then tests the connection
    python -m rag_model.settings --show   # shows the settings without the key
"""
import argparse
import getpass
import time

from haystack.dataclasses import ChatMessage

from rag_model.llm import ROLES, generator, load_settings, public_settings, save_settings
from rag_model import config


def list_models() -> list[str]:
    import httpx
    s = load_settings()
    r = httpx.get(s["base_url"].rstrip("/") + "/models", headers={"Authorization": f"Bearer {s['api_key']}"},
                  timeout=30)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json().get("data", []))


def test_connection(verbose: bool = True) -> list[dict]:
    results = []
    for role in ROLES:
        t0 = time.time()
        try:
            reply = generator(role, config.load()["llm"]).run(messages=[ChatMessage.from_user("Reply with: ok")])
            results.append({"role": role, "ok": True, "seconds": round(time.time() - t0, 1),
                            "message": (reply["replies"][0].text or "")[:80]})
        except Exception as e:  # show the provider's message as is
            results.append({"role": role, "ok": False, "seconds": round(time.time() - t0, 1), "message": str(e)[:300]})
    if verbose:
        for r in results:
            print(f"  {r['role']}: {'ok' if r['ok'] else 'FAILED'} · {r['seconds']} s · {r['message']!r}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if not args.show:
        current = load_settings()
        ask = lambda label, key: input(f"{label} [{current.get(key, '')}]: ").strip() or current.get(key, "")
        update = {"base_url": ask("API base URL (OpenAI-compatible, usually ends with /v1)", "base_url"),
                  "model_queries": ask("Model for search terms (B2)", "model_queries"),
                  "model_brief": ask("Model for the pitch information (B4)", "model_brief")}
        key = getpass.getpass("API key (hidden, Enter keeps the current one): ").strip()
        if key:
            update["api_key"] = key
        save_settings(update)
        print("saved to data/settings.json")
        try:
            print("models offered by the API:\n  " + "\n  ".join(list_models()))
        except Exception as e:
            print(f"could not list models: {e}")
        if update["model_queries"] and update["model_brief"]:
            print("testing connection …")
            test_connection()
        else:
            print("enter the model names by running this command again")
    print(public_settings())


if __name__ == "__main__":
    main()
