import copy
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from kitchen.sample import seed
from kitchen.planner import forecasts, plan
from kitchen.store import Store


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.config = seed(self.folder)
        self.demand = forecasts(self.folder / "orders.csv", self.config)
        self.store = Store(self.folder)

    def tearDown(self):
        self.tmp.cleanup()

    def event(self, identity, action, sender="owner", thread="shift"):
        return self.store.handle(identity, "room", thread, sender, action, "owner")

    def test_absent_cook_shared_stock_cost_and_forecast(self):
        result = plan(self.config, self.demand)
        self.assertEqual(self.demand["chilli-noodles"]["comparable_days"], 3)
        self.assertEqual(self.demand["chilli-noodles"]["quantity"], 12)
        self.assertFalse(
            next(r for r in result["menu"] if r["dish"] == "chilli-noodles")[
                "available"
            ]
        )
        self.assertEqual(result["stock_reservations"]["rice"], 2160)
        self.assertFalse(any(r["ingredient"] == "rice" for r in result["buying"]))
        self.assertEqual(result["economics"]["trip_cost"], 4000)
        self.assertEqual(result["economics"]["expected_contribution"], 237540)

    def test_unknown_supplier_then_confirmed_order_changes_decision(self):
        c = copy.deepcopy(self.config)
        c["ingredients"]["chilli"]["quotes"]["main"]["available"] = False
        unknown = plan(c, self.demand)
        self.assertTrue(any("confirm chilli" in q for q in unknown["questions"]))
        self.assertFalse(any(r["ingredient"] == "chilli" for r in unknown["buying"]))
        c["ingredients"]["chilli"]["quotes"]["other"]["available"] = True
        known = plan(c, self.demand)
        self.assertFalse(any(r["market"] == "other" for r in known["buying"]))
        c["dishes"]["paneer-bowl"]["confirmed"] = 18
        paid = plan(c, self.demand)
        self.assertTrue(any(r["market"] == "other" for r in paid["buying"]))
        self.assertEqual(paid["confirmed_at_risk"], {})
        c["markets"]["other"]["closes"] = "16:00"
        closed = plan(c, self.demand)
        self.assertEqual(closed["confirmed_at_risk"]["paneer-bowl"], 18)

    def test_idempotent_and_atomic_approval(self):
        proposal = self.event("m1", {"kind": "plan"})
        approval = {"kind": "approve", "proposal_id": proposal["proposal_id"]}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.event("m2", approval), range(2)))
        self.assertEqual(results[0], results[1])
        state = self.store.snapshot()
        self.assertEqual(state["version"], 1)
        self.assertEqual(state["approved"]["buying"], proposal["plan"]["buying"])
        self.assertEqual(
            state["approved"]["stock_reservations"],
            proposal["plan"]["stock_reservations"],
        )

    def test_reject_stale_unauthorized_and_wrong_thread(self):
        proposal = self.event("m1", {"kind": "plan"})
        approval = {"kind": "approve", "proposal_id": proposal["proposal_id"]}
        with self.assertRaisesRegex(ValueError, "owner"):
            self.event("m2", approval, sender="buyer")
        with self.assertRaisesRegex(ValueError, "thread"):
            self.event("m3", approval, thread="another")
        self.event(
            "m4",
            {
                "kind": "update",
                "changes": [
                    {
                        "group": "markets",
                        "name": "other",
                        "field": "closes",
                        "value": "16:00",
                    }
                ],
            },
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            self.event("m5", approval)
        self.assertEqual(self.store.snapshot()["version"], 0)

    def test_bad_update_rolls_back_and_expired_stock_not_reserved(self):
        with self.assertRaises(ValueError):
            self.event(
                "bad",
                {
                    "kind": "update",
                    "changes": [
                        {
                            "group": "ingredients",
                            "name": "rice",
                            "field": "stock",
                            "value": -1,
                        }
                    ],
                },
            )
        self.assertEqual(self.store.snapshot()["revision"], 0)
        c = copy.deepcopy(self.config)
        c["ingredients"]["rice"]["use_by"] = "2026-11-05"
        result = plan(c, self.demand)
        self.assertEqual(result["stock_reservations"].get("rice", 0), 0)
        self.assertEqual(result["expired_stock"]["rice"], 3500)

    def test_closing_conserves_portions_and_is_once(self):
        proposal = self.event("m1", {"kind": "plan"})
        self.event("m2", {"kind": "approve", "proposal_id": proposal["proposal_id"]})
        rows = {
            r["dish"]: {"sold": r["portions"] - 1, "carried": 0, "discarded": 1}
            for r in proposal["plan"]["prep"]
        }
        bad = copy.deepcopy(rows)
        bad["paneer-bowl"]["sold"] += 1
        with self.assertRaisesRegex(ValueError, "equal"):
            self.event("bad", {"kind": "close", "rows": bad})
        result = self.event("m3", {"kind": "close", "rows": rows})
        self.assertEqual(
            result["report"]["recorded_portions"]["paneer-bowl"]["discarded"], 1
        )
        with self.assertRaisesRegex(ValueError, "already closed"):
            self.event("m4", {"kind": "close", "rows": rows})


if __name__ == "__main__":
    unittest.main()
