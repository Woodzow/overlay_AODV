import importlib.util
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_FILE = REPO_ROOT / "tools" / "mininet_wifi_complex_12sta_loss_sweep.py"


def load_sweep_module():
    mininet_module = types.ModuleType("mininet")
    mininet_log_module = types.ModuleType("mininet.log")
    mininet_log_module.info = lambda *args, **kwargs: None
    mininet_log_module.setLogLevel = lambda *args, **kwargs: None
    mininet_module.log = mininet_log_module

    mn_wifi_module = types.ModuleType("mn_wifi")
    mn_wifi_link_module = types.ModuleType("mn_wifi.link")
    mn_wifi_link_module.adhoc = object()
    mn_wifi_link_module.wmediumd = object()
    mn_wifi_net_module = types.ModuleType("mn_wifi.net")
    mn_wifi_net_module.Mininet_wifi = object
    mn_wifi_wmediumd_module = types.ModuleType("mn_wifi.wmediumdConnector")
    mn_wifi_wmediumd_module.interference = object()
    mn_wifi_cli_module = types.ModuleType("mn_wifi.cli")
    mn_wifi_cli_module.CLI = object
    mn_wifi_cli_module.CLI_wifi = object

    stubbed_modules = {
        "mininet": mininet_module,
        "mininet.log": mininet_log_module,
        "mn_wifi": mn_wifi_module,
        "mn_wifi.link": mn_wifi_link_module,
        "mn_wifi.net": mn_wifi_net_module,
        "mn_wifi.wmediumdConnector": mn_wifi_wmediumd_module,
        "mn_wifi.cli": mn_wifi_cli_module,
    }
    previous_modules = {name: sys.modules.get(name) for name in stubbed_modules}
    sys.modules.update(stubbed_modules)
    spec = importlib.util.spec_from_file_location("complex_12sta_loss_sweep_tool", SCRIPT_FILE)
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


class Complex12StaLossSweepTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool_module = load_sweep_module()

    def test_results_table_outputs_compact_loss_and_goodput_columns(self) -> None:
        table = self.tool_module.format_results_table(
            [
                {
                    "tc_loss_percent": 0,
                    "hop_count": 3,
                    "loss_rate": 0,
                    "goodput_mbps": 4.428,
                },
                {
                    "tc_loss_percent": 5,
                    "hop_count": 3,
                    "loss_rate": 0.141,
                    "goodput_mbps": 3.436,
                    "offered_load_mbps": 4.0,
                },
            ]
        )

        lines = table.splitlines()
        self.assertEqual("tc_loss%  hop  loss_rate  goodput_mbps", lines[0])
        self.assertEqual("       0    3          0         4.428", lines[1])
        self.assertEqual("       5    3      0.141         3.436", lines[2])


if __name__ == "__main__":
    unittest.main()
