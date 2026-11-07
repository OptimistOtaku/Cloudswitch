import argparse
import json
from pathlib import Path
from uuid import uuid4
from .sample import seed
from .store import Store
from .presentation import render, export


def main():
    parser = argparse.ArgumentParser(
        description="Kitchen Shift — cloud kitchen operating plans"
    )
    parser.add_argument("--data", type=Path, default=Path("data"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("plan")
    commands.add_parser("switch")
    commands.add_parser("web")
    commands.add_parser("snapshot")
    event = commands.add_parser("event")
    event.add_argument("text")
    event.add_argument("--sender", default="owner")
    event.add_argument("--id", default=None)
    event.add_argument("--thread", default="shift")
    action = commands.add_parser("action")
    action.add_argument(
        "json", help="Deterministic JSON action for reproducible testing"
    )
    action.add_argument("--sender", default="owner")
    args = parser.parse_args()
    if args.command == "init":
        if (args.data / "kitchen.json").exists():
            parser.error("Data already exists. Choose a new --data directory.")
        seed(args.data)
        print("Created clearly labeled synthetic sample orders and kitchen tables.")
        return
    store = Store(args.data)
    if args.command == "snapshot":
        print(json.dumps(store.snapshot(), indent=2))
        return
    if args.command == "switch":
        from .agent import serve_switch

        serve_switch(store)
        return
    if args.command == "web":
        from .web import serve

        serve(store)
        return
    if args.command == "event":
        from .agent import process

        response = process(
            store,
            args.id or str(uuid4()),
            "demo",
            args.thread,
            args.sender,
            args.text,
            "owner",
        )
    else:
        action = {"kind": "plan"} if args.command == "plan" else json.loads(args.json)
        response = store.handle(
            str(uuid4()),
            "demo",
            "shift",
            getattr(args, "sender", "owner"),
            action,
            "owner",
        )
    if response["kind"] in ("proposal", "approved"):
        export(args.data / "artifacts", response)
    print(render(response))


if __name__ == "__main__":
    main()
