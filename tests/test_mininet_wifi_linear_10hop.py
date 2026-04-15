import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_FILE = REPO_ROOT / "configs" / "mininet_wifi_linear_10hop" / "topology.json"


class Linear10HopTopologyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.topology = json.loads(TOPOLOGY_FILE.read_text(encoding="utf-8"))
        cls.station_items = cls.topology["stations"]
        cls.station_map = {item["name"]: item for item in cls.station_items}

    def test_station_inventory_is_complete(self) -> None:
        self.assertEqual(11, len(self.station_items))
        self.assertEqual({f"sta{i}" for i in range(1, 12)}, set(self.station_map))

    def test_station_coordinates_form_a_line(self) -> None:
        self.assertEqual({50}, {item["y"] for item in self.station_items})
        self.assertEqual(
            [20 + 40 * index for index in range(11)],
            [item["x"] for item in self.station_items],
        )

    def test_route_source_exists(self) -> None:
        self.assertEqual("sta1", self.topology["route_source"])
        self.assertIn(self.topology["route_source"], self.station_map)

    def test_edges_form_a_linear_chain(self) -> None:
        for index in range(1, 12):
            name = f"sta{index}"
            expected_neighbors = []
            if index > 1:
                expected_neighbors.append(f"sta{index - 1}")
            if index < 11:
                expected_neighbors.append(f"sta{index + 1}")
            self.assertEqual(expected_neighbors, self.topology["edges"][name])

    def test_edges_are_symmetric(self) -> None:
        for node_name, neighbors in self.topology["edges"].items():
            self.assertIn(node_name, self.station_map)
            for neighbor_name in neighbors:
                self.assertIn(neighbor_name, self.station_map)
                self.assertIn(node_name, self.topology["edges"][neighbor_name])


if __name__ == "__main__":
    unittest.main()
