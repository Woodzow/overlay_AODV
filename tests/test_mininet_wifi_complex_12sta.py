import json
import unittest
from pathlib import Path
import importlib.util
import sys
import types


REPO_ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_FILE = REPO_ROOT / 'configs' / 'mininet_wifi_complex_12sta' / 'topology.json'
CONFIG_DIR = REPO_ROOT / 'configs' / 'mininet_wifi_complex_12sta'
SCRIPT_FILE = REPO_ROOT / 'tools' / 'mininet_wifi_complex_12sta.py'


def load_tool_module():
    mininet_module = types.ModuleType('mininet')
    mininet_log_module = types.ModuleType('mininet.log')
    mininet_log_module.info = lambda *args, **kwargs: None
    mininet_log_module.setLogLevel = lambda *args, **kwargs: None
    mininet_module.log = mininet_log_module

    mn_wifi_module = types.ModuleType('mn_wifi')
    mn_wifi_link_module = types.ModuleType('mn_wifi.link')
    mn_wifi_link_module.adhoc = object()
    mn_wifi_link_module.wmediumd = object()
    mn_wifi_net_module = types.ModuleType('mn_wifi.net')
    mn_wifi_net_module.Mininet_wifi = object
    mn_wifi_wmediumd_module = types.ModuleType('mn_wifi.wmediumdConnector')
    mn_wifi_wmediumd_module.interference = object()
    mn_wifi_cli_module = types.ModuleType('mn_wifi.cli')

    class DummyCli:
        def __init__(self, *args, **kwargs):
            pass

    mn_wifi_cli_module.CLI = DummyCli
    mn_wifi_cli_module.CLI_wifi = DummyCli
    mn_wifi_module.link = mn_wifi_link_module
    mn_wifi_module.net = mn_wifi_net_module
    mn_wifi_module.wmediumdConnector = mn_wifi_wmediumd_module
    mn_wifi_module.cli = mn_wifi_cli_module

    stubbed_modules = {
        'mininet': mininet_module,
        'mininet.log': mininet_log_module,
        'mn_wifi': mn_wifi_module,
        'mn_wifi.link': mn_wifi_link_module,
        'mn_wifi.net': mn_wifi_net_module,
        'mn_wifi.wmediumdConnector': mn_wifi_wmediumd_module,
        'mn_wifi.cli': mn_wifi_cli_module,
    }
    previous_modules = {name: sys.modules.get(name) for name in stubbed_modules}
    sys.modules.update(stubbed_modules)
    spec = importlib.util.spec_from_file_location('mininet_wifi_complex_12sta_tool', SCRIPT_FILE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


class Complex12StaTopologyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.topology = json.loads(TOPOLOGY_FILE.read_text(encoding='utf-8'))
        cls.station_items = cls.topology['stations']
        cls.station_map = {item['name']: item for item in cls.station_items}
        cls.tool_module = load_tool_module()

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

    def test_bench_daemon_target_names_skip_default_source(self) -> None:
        source_name, targets = self.tool_module.bench_daemon_target_names(self.topology)
        self.assertEqual('sta1', source_name)
        self.assertEqual({f'sta{i}' for i in range(2, 13)}, set(targets))

    def test_bench_daemon_target_names_support_custom_source(self) -> None:
        source_name, targets = self.tool_module.bench_daemon_target_names(self.topology, 'sta3')
        self.assertEqual('sta3', source_name)
        self.assertEqual({f'sta{i}' for i in range(1, 13)} - {'sta3'}, set(targets))

    def test_bench_daemon_target_names_reject_unknown_source(self) -> None:
        with self.assertRaises(ValueError):
            self.tool_module.bench_daemon_target_names(self.topology, 'sta99')


if __name__ == '__main__':
    unittest.main()
