"""本地交互命令行。

该线程只负责人与节点交互，不参与 AODV 协议本身：
- 从终端读取命令
- 转换为控制面协议命令
- 通过 UDP 发送到节点控制端口
"""

import socket
import threading


class Listener(threading.Thread):
    """本地命令行控制线程，通过控制端口向协议线程发送命令。"""

    def __init__(self, control_ip: str, control_port: int):
        """创建本地 UDP 客户端套接字。"""
        super().__init__(daemon=True)
        self.control_ip = control_ip
        self.control_port = control_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))

    def _send_command(self, command: str) -> str:
        """向控制端口发送命令并等待返回结果。"""
        self.sock.sendto(command.encode("utf-8"), (self.control_ip, self.control_port))
        raw, _ = self.sock.recvfrom(16384)
        return raw.decode("utf-8", errors="ignore")

    def _print_help(self) -> None:
        """打印命令帮助。"""
        print("可用命令:")
        print("  help")
        print("  activate_link")
        print("  deactivate_link")
        print("  add_neighbor <邻居ID> <邻居IP>")
        print("  delete_neighbor <邻居ID>")
        print("  send_message <目标节点ID> <消息内容>")
        print("  show_route")
        print("  show_neighbors")
        print("  show_messages")
        print("  clear_messages")
        print("  quit")

    def run(self) -> None:
        """交互循环：解析用户输入并映射到控制命令。"""
        self._print_help()
        while True:
            try:
                command_line = input("AODV> ").strip()
            except EOFError:
                return

            if not command_line:
                continue

            if command_line == "help":
                self._print_help()
                continue

            if command_line == "quit":
                return

            parts = command_line.split()
            op = parts[0]

            try:
                if op == "activate_link":
                    result = self._send_command("NODE_ACTIVATE")
                elif op == "deactivate_link":
                    result = self._send_command("NODE_DEACTIVATE")
                elif op == "add_neighbor" and len(parts) == 3:
                    result = self._send_command(f"ADD_NEIGHBOR:{parts[1]}:{parts[2]}")
                elif op == "delete_neighbor" and len(parts) == 2:
                    result = self._send_command(f"DELETE_NEIGHBOR:{parts[1]}")
                elif op == "send_message" and len(parts) >= 3:
                    dest_addr = parts[1]
                    payload = " ".join(parts[2:])
                    result = self._send_command(f"SEND_MESSAGE:{dest_addr}:{payload}")
                elif op == "show_route":
                    result = self._send_command("SHOW_ROUTE")
                elif op == "show_neighbors":
                    result = self._send_command("SHOW_NEIGHBORS")
                elif op == "show_messages":
                    result = self._send_command("SHOW_MESSAGES")
                elif op == "clear_messages":
                    result = self._send_command("CLEAR_MESSAGES")
                else:
                    result = "命令格式错误，请输入 help 查看帮助"
            except Exception as exc:
                result = f"命令执行失败: {exc}"

            print(result)
