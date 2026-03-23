"""兼容层模块。

历史代码通过 `from aodv import aodv` 引用协议线程类。
本文件保留该导入路径，避免上层脚本改动过大。
"""

from aodv_protocol import AodvProtocol


class aodv(AodvProtocol):
    """兼容旧类名，实际行为由 `AodvProtocol` 提供。"""

    pass
