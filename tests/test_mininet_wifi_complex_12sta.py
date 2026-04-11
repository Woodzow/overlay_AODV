import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_FILE = REPO_ROOT / 'configs' / 'mininet_wifi_complex_12sta' / 'topology.json'
CONFIG_DIR = REPO_ROOT / 'configs' / 'mininet_wifi_complex_12sta'


class Complex12StaTopologyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.topology = json.loads(TOPOLOGY_FILE.read_text(encoding='utf-8'))
        cls.station_items = cls.topology['stations']
        cls.station_map = {item['name']: item for item in cls.station_items}

    def test_station_inventory_is_complete(self) -> None:
        self.assertEqual(12, len(self.station_items))
        self.assertEqual(
            {f'sta{i}' for i in range(1, 13)},
            set(self.station_map),
        )

    def test_station_coordinates_are_unique(self) -> None:
        coords = {(item['x'], item['y']) for item in self.station_items}
        self.assertEqual(len(self.station_items), len(coords))

    def test_video_source_and_dest_exist(self) -> None:
        self.assertIn(self.topology['video_source'], self.station_map)
        self.assertIn(self.topology['video_dest'], self.station_map)
        self.assertEqual(
            self.topology['video_dest_ip'],
            self.station_map[self.topology['video_dest']]['ip'].split('/', 1)[0],
        )

    def test_topology_edges_are_symmetric(self) -> None:
        for node_name, neighbors in self.topology['edges'].items():
            self.assertIn(node_name, self.station_map)
            self.assertEqual(sorted(neighbors), sorted(set(neighbors)))
            for neighbor_name in neighbors:
                self.assertIn(neighbor_name, self.station_map)
                self.assertIn(node_name, self.topology['edges'][neighbor_name])

    def test_config_neighbors_match_topology(self) -> None:
        for node_name, station in self.station_map.items():
            config_path = CONFIG_DIR / f'{node_name}.json'
            self.assertTrue(config_path.exists(), msg=f'missing config: {config_path}')
            config = json.loads(config_path.read_text(encoding='utf-8-sig'))
            self.assertEqual(node_name, config['node_id'])
            self.assertEqual(station['ip'].split('/', 1)[0], config['node_ip'])
            expected_neighbors = {
                (neighbor_name, self.station_map[neighbor_name]['ip'].split('/', 1)[0])
                for neighbor_name in self.topology['edges'][node_name]
            }
            actual_neighbors = {
                (item['node_id'], item['ip'])
                for item in config['neighbors']
            }
            self.assertEqual(expected_neighbors, actual_neighbors)


if __name__ == '__main__':
    unittest.main()
