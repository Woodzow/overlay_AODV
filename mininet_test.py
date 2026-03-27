from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.topo import Topo

import time


class LinearTopo(Topo):
    def build(self):
        h1 = self.addHost("h1", ip="10.0.0.1/24")
        h2 = self.addHost("h2", ip="10.0.0.2/24")
        h3 = self.addHost("h3", ip="10.0.0.3/24")
        h4 = self.addHost("h4", ip="10.0.0.4/24")

        self.addLink(h1, h2, bw=10, delay="5ms", loss=0)
        self.addLink(h2, h3, bw=10, delay="5ms", loss=0)
        self.addLink(h3, h4, bw=10, delay="5ms", loss=0)


def run():
    topo = LinearTopo()
    net = Mininet(topo=topo, link=TCLink, controller=None, autoSetMacs=True)
    net.start()

    # Keep L2/L3 baseline behavior simple. Do not flush routes here.
    for h in net.hosts:
        h.cmd("sysctl -w net.ipv4.ip_forward=1 >/dev/null")

    project_path = "/home/admin/overlay_AODV/src"
    entry = "main.py"

    info("*** Starting AODV node process on all hosts...\n")
    for h in net.hosts:
        host_ip = h.IP()
        cmd = (
            f"cd {project_path} && "
            f"python3 {entry} node --ip {host_ip} --no-cli "
            f"> logs/{h.name}.log 2>&1 &"
        )
        info(f"*** {h.name} executing: {cmd}\n")
        h.cmd(cmd)

    info("*** Waiting 10 seconds for protocol warmup...\n")
    time.sleep(10)

    info("*** Checking routes on h1 and h4...\n")
    print(net["h1"].cmd("ip route"))
    print(net["h4"].cmd("ip route"))

    info("*** Running CLI for manual testing...\n")
    CLI(net)

    info("*** Stopping network...\n")
    for h in net.hosts:
        h.cmd("pkill -f 'python3 src/main.py node' || true")
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()
