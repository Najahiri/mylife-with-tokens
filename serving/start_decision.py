"""Preview a decision-only HF deployment; --deploy explicitly starts paid hosting."""

import argparse
import os
import shlex
import shutil
import subprocess

from serving.profiles import load_profile


def build_command(image, *, name="apertus-decision-8b", namespace=None):
    profile = load_profile("stock-8b")
    decision = profile["decision"]
    # The stock preset deploys only the decision model; generation stays on Keera.
    command = [
        "hf",
        "endpoints",
        "deploy",
        name,
        "--namespace",
        namespace or profile["namespace"],
        "--repo",
        decision["model"],
        "--revision",
        decision["revision"],
        "--framework",
        "custom",
        "--engine",
        "custom",
        "--task",
        "custom",
        "--custom-image",
        image,
        "--vendor",
        profile["vendor"],
        "--region",
        profile["region"],
        "--accelerator",
        "gpu",
        "--instance-type",
        "nvidia-l4",
        "--instance-size",
        "x1",
        "--port",
        "8000",
        "--health-route",
        "/health",
        # Gateway is publicly reachable; /decide itself requires DECISION_API_KEY.
        "--type",
        "public",
        "--min-replica",
        str(profile["min_replica"]),
        "--max-replica",
        str(profile["max_replica"]),
        "--scale-to-zero-timeout",
        str(profile["scale_to_zero_timeout"]),
    ]
    for key, value in decision["env"].items():
        command.extend(["--env", f"{key}={value}"])
    for secret in decision["secrets"]:
        command.extend(["--secrets", secret])
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", required=True, help="Published linux/amd64 decision container image"
    )
    parser.add_argument("--name", default="apertus-decision-8b")
    parser.add_argument("--namespace", default=None)
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Create the paid L4 endpoint; otherwise preview only",
    )
    args = parser.parse_args()
    command = build_command(args.image, name=args.name, namespace=args.namespace)
    print(shlex.join(command), flush=True)
    if not args.deploy:
        print(
            "Preview only: no resources created. Add --deploy to start paid HF hosting."
        )
        return
    if not shutil.which("hf"):
        parser.error("Install the HF CLI and run hf auth login first")
    environment = dict(os.environ)
    if not environment.get("HF_TOKEN"):
        from huggingface_hub import get_token

        environment["HF_TOKEN"] = get_token() or ""
    for key in ("HF_TOKEN", "DECISION_API_KEY"):
        if not environment.get(key):
            parser.error(
                f"Set {key} before deployment (do not pass its value on the command line)"
            )
    subprocess.run(command, env=environment, check=True)
    print(
        f"Inspect startup with: hf endpoints describe {shlex.quote(args.name)} --namespace {shlex.quote(args.namespace or 'HX-Tfd')}"
    )


if __name__ == "__main__":
    main()
