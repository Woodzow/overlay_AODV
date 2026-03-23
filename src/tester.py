"""脚本化测试器。

读取测试脚本后，按行向目标节点下发控制命令，
用于自动化复现实验场景（建邻、收发消息、查看路由等）。
"""

import argparse
import json
import re
import socket
import time
from pathlib import Path


def load_cluster(path: str) -> dict[str, tuple[str, int]]:
    """加载集群节点清单：node_id -> (ip, control_port)。"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = {}
    for node_id, item in raw.get("nodes", {}).items():
        nodes[node_id] = (item["ip"], int(item["control_port"]))
    return nodes


class Tester:
    """脚本化测试器：按脚本向多台设备下发控制命令。"""

    def __init__(self, cluster: dict[str, tuple[str, int]]):
        """初始化测试器 UDP 套接字。"""
        self.cluster = cluster
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.settimeout(5)

    def send_to_node(self, target: str, command: str) -> str:
        """向指定节点发送命令并同步等待响应。"""
        if target not in self.cluster:
            return f"未知节点: {target}"
        ip, port = self.cluster[target]
        self.sock.sendto(command.encode("utf-8"), (ip, port))
        raw, _ = self.sock.recvfrom(16384)
        return raw.decode("utf-8", errors="ignore")

    def process_line(self, line: str) -> None:
        """解析并执行脚本中的单行命令。"""
        # 兼容形如 `1. add_neighbors n2 to n1` 的编号脚本格式。
        clean_line = re.sub(r"^\d+\.\s*", "", line.strip())
        words = clean_line.split()
        if not words:
            return

        op = words[0]

        if op == "sleep" and len(words) == 2:
            time.sleep(float(words[1]))
            return

        if op == "activate_link" and len(words) == 2:
            print(self.send_to_node(words[1], "NODE_ACTIVATE"))
            return

        if op == "deactivate_link" and len(words) == 2:
            print(self.send_to_node(words[1], "NODE_DEACTIVATE"))
            return

        if op in {"add_neighbors", "add_neighbor"} and len(words) == 4 and words[2] == "to":
            neighbor_id = words[1]
            target_id = words[3]
            if neighbor_id not in self.cluster:
                print(f"未知邻居节点: {neighbor_id}")
                return
            neighbor_ip = self.cluster[neighbor_id][0]
            print(self.send_to_node(target_id, f"ADD_NEIGHBOR:{neighbor_id}:{neighbor_ip}"))
            return

        if op == "delete_neighbor" and len(words) == 3:
            neighbor_id = words[1]
            target_id = words[2]
            print(self.send_to_node(target_id, f"DELETE_NEIGHBOR:{neighbor_id}"))
            return

        if op == "send_message" and len(words) >= 5 and words[2] == "to":
            src_addr = words[1]
            dest_addr = words[3]
            if dest_addr in self.cluster:
                dest_addr = self.cluster[dest_addr][0]
            payload_words = words[4:]
            payload = " ".join(payload_words).replace("@", " ")
            print(self.send_to_node(src_addr, f"SEND_MESSAGE:{dest_addr}:{payload}"))
            return

        if op == "show_route" and len(words) == 2:
            print(self.send_to_node(words[1], "SHOW_ROUTE"))
            return
        if op == "show_route_detail" and len(words) == 3:
            print(self.send_to_node(words[1], f"SHOW_ROUTE_DETAIL:{words[2]}"))
            return

        if op == "show_neighbors" and len(words) == 2:
            print(self.send_to_node(words[1], "SHOW_NEIGHBORS"))
            return

        if op == "show_messages" and len(words) == 2:
            print(self.send_to_node(words[1], "SHOW_MESSAGES"))
            return

        if op == "clear_messages" and len(words) == 2:
            print(self.send_to_node(words[1], "CLEAR_MESSAGES"))
            return

        if op == "show_discovery" and len(words) == 2:
            print(self.send_to_node(words[1], "SHOW_DISCOVERY"))
            return

        if op == "show_rrep_ack" and len(words) == 2:
            print(self.send_to_node(words[1], "SHOW_RREP_ACK"))
            return

        if op == "show_local_repair" and len(words) == 2:
            print(self.send_to_node(words[1], "SHOW_LOCAL_REPAIR"))
            return

        if op == "show_pending_data" and len(words) == 2:
            print(self.send_to_node(words[1], "SHOW_PENDING_DATA"))
            return

        if op == "show_precursors" and len(words) == 2:
            print(self.send_to_node(words[1], "SHOW_PRECURSORS"))
            return

        if op == "show_timer" and len(words) == 2:
            print(self.send_to_node(words[1], "SHOW_TIMER"))
            return

        print(f"无法解析脚本行: {line}")

    def run_script(self, script_path: str) -> None:
        """顺序执行脚本文件。"""
        lines = Path(script_path).read_text(encoding="utf-8").splitlines()
        for line in lines:
            text = line.strip()
            if (not text) or text.startswith("#"):
                continue
            self.process_line(text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AODV 覆盖网络脚本测试器")
    parser.add_argument("--cluster", required=True, help="集群配置 JSON 文件")
    parser.add_argument("--script", required=True, help="测试脚本路径")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cluster = load_cluster(args.cluster)
    tester = Tester(cluster)
    tester.run_script(args.script)
