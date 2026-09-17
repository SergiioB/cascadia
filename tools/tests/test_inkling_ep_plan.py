"""Storage/replica contracts for the EP deployment planner; no ML dependencies."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("inkling_ep_plan", ROOT / "tools/inkling_ep_plan.py")
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.m = json.loads((ROOT / "crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export/manifest.json").read_text())
        self.workers = [dict(name=f"w{i}", expert_capacity_bytes=100_000,
                             read_us=100, compute_us=10, dispatch_us=20) for i in range(3)]

    def test_exact_bin_sizes_and_partial_copy_lists(self):
        p = planner.make_plan(self.m, self.workers)
        for li, layer in enumerate(p["layers"]):
            for eid, owners in enumerate(layer):
                self.assertEqual(len(owners), 1 if eid < self.m["num_experts"] else 3)
        for wi in range(3):
            files = planner.shard_files(p, wi)
            self.assertEqual(files[0], "manifest.json")
            actual_bytes = sum((ROOT / "crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export" / f).stat().st_size for f in files[1:])
            self.assertEqual(actual_bytes, (len(files) - 1) * p["expert_bytes"])
            self.assertLessEqual(actual_bytes, self.workers[wi]["expert_capacity_bytes"])
        self.assertEqual(p, planner.make_plan(self.m, self.workers))

    def test_heterogeneous_budgets_and_routed_replicas(self):
        self.workers[0]["expert_capacity_bytes"] *= 2
        p = planner.make_plan(self.m, self.workers, routed_replicas=2, shared_replicas=2)
        counts = [len(planner.shard_files(p, wi)) - 1 for wi in range(3)]
        self.assertGreater(counts[0], counts[1])
        self.assertTrue(all(len(set(owners)) == 2 for layer in p["layers"] for owners in layer))

    def test_insufficient_capacity_and_invalid_costs_fail(self):
        for w in self.workers:
            w["expert_capacity_bytes"] = 1
        with self.assertRaisesRegex(ValueError, "insufficient"):
            planner.make_plan(self.m, self.workers)
        bad = copy.deepcopy(self.workers)
        bad[0]["read_us"] = float("nan")
        with self.assertRaises(ValueError):
            planner.make_plan(self.m, bad)
        with self.assertRaises(ValueError):
            planner.make_plan(self.m, self.workers, routed_replicas=4)


if __name__ == "__main__":
    unittest.main()
