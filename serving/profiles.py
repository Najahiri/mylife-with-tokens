"""Render HF hosting options and inspect quota. Never provisions resources."""

import argparse
from collections import defaultdict
from copy import deepcopy
import dataclasses
import json
from pathlib import Path

import yaml

DIRECTORY = Path(__file__).with_name("profiles")
NAMES = ("finetuned-8b", "stock-8b", "stock-70b")


def load_profile(name):
    if name not in NAMES:
        raise ValueError(f"Unknown profile: {name}")
    common = yaml.safe_load((DIRECTORY / "common.yaml").read_text())
    option = yaml.safe_load((DIRECTORY / f"{name}.yaml").read_text())
    return {**common, **option}


def endpoint_specs(profile):
    decision, generation = (
        deepcopy(profile["decision"]),
        deepcopy(profile["generation"]),
    )
    if profile["layout"] == "shared_backbone":
        return [
            {
                **decision,
                "name": "apertus-shared-8b",
                "dockerfile": generation["dockerfile"],
                "env": {**decision["env"], **generation["env"]},
                "secrets": generation["secrets"],
            }
        ]
    if profile["layout"] == "external_generation":
        return [{**decision, "name": "apertus-decision-8b"}]
    return [
        {**decision, "name": "apertus-decision-8b"},
        {**generation, "name": f"apertus-chat-{profile['name']}"},
    ]


def render(
    profile,
    chat_url=None,
    decision_url="${DECISION_ENDPOINT_URL}",
):
    model = profile["generation"]["model"]
    chat_url = (
        chat_url
        or profile["generation"].get("base_url")
        or "${GENERATION_ENDPOINT_URL}"
    )
    chat_url = chat_url.rstrip("/")
    chat_base_url = chat_url if chat_url.endswith("/v1") else chat_url + "/v1"
    if profile["layout"] == "shared_backbone":
        decision_url = chat_url
    return {
        "profile": profile["name"],
        "namespace": profile["namespace"],
        "vendor": profile["vendor"],
        "region": profile["region"],
        "container_port": 8000,
        "health_route": "/health",
        "container_images_published": False,
        "endpoints": endpoint_specs(profile),
        "external_services": [profile["generation"]]
        if profile["layout"] == "external_generation"
        else [],
        "cost_scope": "HF endpoints only; external Keera usage is not included",
        "scaling": {
            key: profile[key]
            for key in ("min_replica", "max_replica", "scale_to_zero_timeout")
        },
        "backend_environment": {
            "APERTUS_BASE_URL": chat_base_url,
            "APERTUS_API_KEY": "${KEERA_API_KEY}"
            if profile["layout"] == "external_generation"
            else "${CHAT_API_KEY}",
            "APERTUS_CHAT_MODEL": model,
            **{
                f"APERTUS_MODEL_{role}": model for role in ("AGENT", "QUERIES", "BRIEF")
            },
            "APERTUS_DECISION_URL": decision_url.rstrip("/") + "/decide",
            "APERTUS_DECISION_API_KEY": "${DECISION_API_KEY}",
            "APERTUS_DECISION_MODEL": profile["decision"]["model"],
        },
        "application_config": profile["application_config"],
        "notes": profile["notes"],
        "estimated_usd_per_active_hour": round(
            sum(e["estimated_usd_per_active_hour"] for e in endpoint_specs(profile)), 2
        ),
        "billing_balance_known": False,
        "gpu_fit_verified": False,
    }


def check_quota(profile, hardware):
    lookup = {h.id: h for h in hardware}
    requested = defaultdict(int)
    available = {}
    errors, hourly = [], 0.0
    for endpoint in endpoint_specs(profile):
        entry = lookup.get(endpoint["hardware"])
        if entry is None:
            errors.append(f"Hardware not returned: {endpoint['hardware']}")
            continue
        group = (entry.vendor, entry.region, entry.instance_type)
        requested[group] += entry.num_accelerators * profile["max_replica"]
        available[group] = entry.max_accelerators - entry.used_accelerators
        hourly += entry.price_per_hour
        if entry.status not in ("available", "low_availability"):
            errors.append(f"{entry.id}: {entry.status}")
    for group, count in requested.items():
        if count > available[group]:
            errors.append(
                f"{'/'.join(group)} needs {count} GPUs; {available[group]} quota remaining"
            )
    return {
        "quota_ok": not errors,
        "issues": errors,
        "usd_per_active_hour": round(hourly, 2) if not errors else None,
        "billing_ready": "unknown",
        "gpu_fit_verified": False,
    }


def inspect_hf(namespace):
    from huggingface_hub import HfApi, get_hf_file_metadata, hf_hub_url

    api = HfApi()
    account = api.whoami()
    hardware = api.list_inference_endpoints_hardware(namespace=namespace)
    report = {
        "account": account["name"],
        "is_pro": account.get("isPro"),
        "namespace": namespace,
        "credit_balance_usd": None,
        "billing_ready": "unknown",
        "billing_note": "The SDK exposes hardware quota, not the remaining compute-credit balance.",
        "endpoints": [
            {"name": e.name, "status": str(e.status)}
            for e in api.list_inference_endpoints(namespace=namespace)
        ],
        "hardware": [
            dataclasses.asdict(h)
            for h in hardware
            if h.vendor == "aws"
            and h.region == "us-east-1"
            and h.id
            in {
                e["hardware"]
                for name in NAMES
                for e in endpoint_specs(load_profile(name))
            }
        ],
    }
    common = load_profile("finetuned-8b")
    checks = [
        (
            common["decision"]["model"],
            common["decision"]["revision"],
            "adapter_config.json",
        ),
        (
            "swiss-ai/Apertus-v1.5-8B-base",
            common["decision"]["base_revision"],
            "config.json",
        ),
        (
            common["generation"]["env"]["CHAT_TEMPLATE_MODEL"],
            common["generation"]["env"]["CHAT_TEMPLATE_REVISION"],
            "chat_template.jinja",
        ),
    ]
    report["model_access"] = []
    for repo, revision, filename in checks:
        entry = {"repo": repo, "revision": revision, "file": filename}
        try:
            get_hf_file_metadata(
                hf_hub_url(repo, filename, revision=revision), token=api.token
            )
            entry["readable"] = True
        except Exception as error:
            entry.update(
                readable=False,
                http_status=getattr(
                    getattr(error, "response", None), "status_code", None
                ),
                error=type(error).__name__,
            )
        report["model_access"].append(entry)
    try:
        quota = api.get_zero_gpu_quota()
        report["zero_gpu"] = dataclasses.asdict(quota)
    except Exception as error:
        response = getattr(error, "response", None)
        report["zero_gpu"] = {
            "readable": False,
            "http_status": getattr(response, "status_code", None),
            "note": "Reading this quota requires billing-read permission.",
        }
    return report, hardware


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=(*NAMES, "all"))
    parser.add_argument(
        "--check-hf",
        action="store_true",
        help="Read account and endpoint GPU quota; never deploy",
    )
    parser.add_argument("--namespace", default=None)
    parser.add_argument(
        "--chat-url",
        default=None,
        help="Override the generation API URL; stock presets default to Keera",
    )
    parser.add_argument("--decision-url", default="${DECISION_ENDPOINT_URL}")
    parser.add_argument(
        "--credit-budget",
        type=float,
        help="Optional known USD budget; not fetched or changed on HF",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.credit_budget is not None and args.credit_budget < 0:
        parser.error("--credit-budget must be non-negative")
    profiles = [
        load_profile(name)
        for name in (NAMES if args.profile == "all" else [args.profile])
    ]
    namespace = args.namespace or profiles[0]["namespace"]
    report, hardware = inspect_hf(namespace) if args.check_hf else (None, None)
    plans = []
    for profile in profiles:
        profile["namespace"] = namespace
        plan = render(profile, args.chat_url, args.decision_url)
        if hardware is not None:
            plan["live_check"] = check_quota(profile, hardware)
            required = {
                profile["decision"]["model"],
                "swiss-ai/Apertus-v1.5-8B-base",
            }
            if profile["layout"] == "shared_backbone":
                required.add(profile["generation"]["env"]["CHAT_TEMPLATE_MODEL"])
            access = [
                entry for entry in report["model_access"] if entry["repo"] in required
            ]
            plan["live_check"]["model_access_ok"] = all(
                entry["readable"] for entry in access
            )
            plan["live_check"]["blocked_model_files"] = [
                entry for entry in access if not entry["readable"]
            ]
        if args.credit_budget is not None:
            price = (
                plan.get("live_check", {}).get("usd_per_active_hour")
                or plan["estimated_usd_per_active_hour"]
            )
            plan["user_supplied_budget_usd"] = args.credit_budget
            plan["approximate_active_hours"] = round(args.credit_budget / price, 2)
        plans.append(plan)
    output = (
        json.dumps({"account_check": report, "plans": plans}, indent=2, default=str)
        + "\n"
    )
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
