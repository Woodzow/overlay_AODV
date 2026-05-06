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
        table = self.tool_module.format_results_table(self.tool_module.SCREENSHOT_TABLE_RESULTS)

        lines = table.splitlines()
        self.assertEqual(
            [
                "tc_loss%  hop  loss_rate  goodput_mbps",
                "       0    3          0         4.428",
                "       1    3      0.026         4.276",
                "       2    3      0.056         4.042",
                "       3    3      0.077         3.985",
                "       4    3      0.115         3.594",
                "       5    3      0.141         3.436",
            ],
            lines,
        )


if __name__ == "__main__":
    unittest.main()
