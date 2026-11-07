"""Reproduce the buyer → revised plan → approval drill without model spending."""

import json
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kitchen.sample import seed
from kitchen.store import Store
from kitchen.presentation import export


def main():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        seed(folder)
        store = Store(folder)

        def send(identity, action):
            return store.handle(identity, "demo", "shift", "owner", action, "owner")

        initial = send("initial", {"kind": "plan"})
        shortage = send(
            "shortage",
            {
                "kind": "update",
                "changes": [
                    {
                        "group": "quotes",
                        "name": "chilli/main",
                        "field": "available",
                        "value": False,
                    },
                    {
                        "group": "markets",
                        "name": "other",
                        "field": "arrival",
                        "value": "16:30",
                    },
                ],
            },
        )
        catering = send(
            "catering",
            {
                "kind": "update",
                "changes": [
                    {
                        "group": "quotes",
                        "name": "chilli/other",
                        "field": "available",
                        "value": True,
                    },
                    {
                        "group": "dishes",
                        "name": "paneer-bowl",
                        "field": "confirmed",
                        "value": 18,
                    },
                ],
            },
        )
        approved = send(
            "approval", {"kind": "approve", "proposal_id": catering["proposal_id"]}
        )
        contributions = [
            r["plan"]["economics"]["expected_contribution"]
            for r in (initial, shortage, catering)
        ]
        assert contributions == [237540, 39500, 51560], contributions
        export(Path(__file__).parent / "artifacts", approved)
        print(
            json.dumps(
                {
                    "contribution_paise": contributions,
                    "approved_version": store.snapshot()["version"],
                    "note": "Deterministic replay. verified-run.json records the separate real model / Switch drill.",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
