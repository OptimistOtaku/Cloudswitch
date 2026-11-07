import tempfile
import unittest
from pathlib import Path
from kitchen.sample import seed
from kitchen.store import Store


class AlternativeTests(unittest.TestCase):
    def test_owner_choice_rebuilds_all_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed(Path(tmp))
            store = Store(tmp)
            proposal = store.handle(
                "p", "room", "thread", "owner", {"kind": "plan"}, "owner"
            )
            chosen = proposal["plan"]["alternatives"][0]
            approved = store.handle(
                "a",
                "room",
                "thread",
                "owner",
                {
                    "kind": "approve",
                    "proposal_id": proposal["proposal_id"],
                    "alternative": 1,
                },
                "owner",
            )
            self.assertEqual(approved["plan"]["economics"], chosen["economics"])
            self.assertEqual(
                {r["dish"]: r["portions"] for r in approved["plan"]["menu"]},
                chosen["portions"],
            )
            self.assertEqual(
                store.snapshot()["approved"]["prep"], approved["plan"]["prep"]
            )
