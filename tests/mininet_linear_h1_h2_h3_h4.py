#!/usr/bin/env python3
"""Mininet linear topology test: h1 - h2 - h3 - h4.

Usage:
  sudo python3 tests/mininet_linear_h1_h2_h3_h4.py
  sudo python3 tests/mininet_linear_h1_h2_h3_h4.py --cli
"""

from __future__ import annotations

import argparse
import sys

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Controller
from mininet.topo import Topo


class LinearHostTopo(Topo):
    """Host-only linear chain: h1-h2-h3-h4."""

    def build(self) -> None:  # type: ignore[override]
        h1 = self.addHost("h1")
        h2 = self.addHost("h2")
        h3 = self.addHost("h3")
        h4 = self.addHost("h4")

        self.addLink(h1, h2)
        self.addLink(h2, h3)
        self.addLink(h3, h4)


def _flush_v4(host, ifname: str) -> None:
    host.cmd("ip -4 addr flush dev %s" % ifname)


def _configure_host_routes(net: Mininet) -> None:
    """Assign point-to-point IPs and routes for 4-host chain."""
    h1, h2, h3, h4 = net.get("h1", "h2", "h3", "h4")

    _flush_v4(h1, "h1-eth0")
    _flush_v4(h2, "h2-eth0")
    _flush_v4(h2, "h2-eth1")
    _flush_v4(h3, "h3-eth0")
    _flush_v4(h3, "h3-eth1")
    _flush_v4(h4, "h4-eth0")

    h1.cmd("ip addr add 10.0.12.1/24 dev h1-eth0")

    h2.cmd("ip addr add 10.0.12.2/24 dev h2-eth0")
    h2.cmd("ip addr add 10.0.23.2/24 dev h2-eth1")

    h3.cmd("ip addr add 10.0.23.3/24 dev h3-eth0")
    h3.cmd("ip addr add 10.0.34.3/24 dev h3-eth1")

    h4.cmd("ip addr add 10.0.34.4/24 dev h4-eth0")

    # h2/h3 act as forwarding nodes.
    h2.cmd("sysctl -w net.ipv4.ip_forward=1 >/dev/null")
    h3.cmd("sysctl -w net.ipv4.ip_forward=1 >/dev/null")

    # Static routes.
    h1.cmd("ip route replace default via 10.0.12.2 dev h1-eth0")
    h4.cmd("ip route replace default via 10.0.34.3 dev h4-eth0")

    h2.cmd("ip route replace 10.0.34.0/24 via 10.0.23.3 dev h2-eth1")
    h3.cmd("ip route replace 10.0.12.0/24 via 10.0.23.2 dev h3-eth0")


def run_test(enter_cli: bool) -> int:
    topo = LinearHostTopo()
    net = Mininet(topo=topo, controller=Controller, autoSetMacs=True)
    net.start()

    try:
        _configure_host_routes(net)

        h1, h4 = net.get("h1", "h4")
        info("\n*** Ping test: h1 -> h4 (10.0.34.4)\n")
        rc = h1.cmd("ping -c 3 -W 1 10.0.34.4; echo $?").strip().splitlines()[-1]
        success = rc == "0"
        info("*** Result: %s\n" % ("PASS" if success else "FAIL"))

        info("*** Ping test: h4 -> h1 (10.0.12.1)\n")
        rc2 = h4.cmd("ping -c 3 -W 1 10.0.12.1; echo $?").strip().splitlines()[-1]
        success = success and (rc2 == "0")
        info("*** Result: %s\n" % ("PASS" if rc2 == "0" else "FAIL"))

        if enter_cli:
            info("\n*** Entering Mininet CLI. Type 'exit' to quit.\n")
            CLI(net)

        return 0 if success else 1
    finally:
        net.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mininet linear h1-h2-h3-h4 topology test")
    parser.add_argument("--cli", action="store_true", help="enter Mininet CLI after automated ping checks")
    return parser.parse_args()


if __name__ == "__main__":
    setLogLevel("info")
    args = parse_args()
    sys.exit(run_test(args.cli))
