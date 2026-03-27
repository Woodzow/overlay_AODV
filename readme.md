# AODV 应用层覆盖网络（UDP/5005）

本项目实现多设备节点间运行的 AODV 应用层覆盖网络，数据面统一使用 UDP `5005` 端口。

## 实现范围

- 控制报文：`RREQ / RREP / RERR / RREP-ACK`
- HELLO：采用 RFC 语义，使用 `TTL=1` 的特殊 `RREP`
- 业务报文：`DATA`（工程扩展）
- 地址编码：IPv4 4 字节二进制
- Python 版本：3.12+

## RFC 3561 实现对照

- Section 5.1 `RREQ`：已实现（含扩环 TTL 与重试）
- Section 5.2 `RREP`：已实现（含 A 位）
- Section 5.3 `RERR`：已实现（按前驱定向、聚合、限速）
- Section 5.4 `RREP-ACK`：已实现（ACK 等待与超时）
- HELLO（Section 6.9 语义）：已实现（`RREP ttl=1`）
- Local Repair（Section 6.11 思路）：部分实现（修复发起、超时回退 RERR）

说明：项目为教学/实验型实现，不是 RFC 全量实现。

## 目录

- `src/aodv_protocol.py`：协议核心状态机
- `src/aodv_codec.py`：二进制编解码
- `src/aodv_route_manager.py`：路由表状态与更新策略
- `src/aodv_error_manager.py`：前驱、RERR 去重/限速
- `src/aodv_discovery_manager.py`：RREQ 发现重试
- `src/aodv_local_repair_manager.py`：本地修复状态
- `src/aodv_ack_manager.py`：RREP-ACK 等待状态
- `src/aodv_control.py`：控制命令

## 启动

```bash
cd src
python main.py node --config node_config.json
```

无交互模式：

```bash
python main.py node --config node_config.json --no-cli
```

脚本测试：

```bash
cd src
python main.py tester --cluster cluster_config.json --script aodv_script
```

## 单元测试

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## 控制命令

- `SHOW_ROUTE`
- `SHOW_ROUTE_DETAIL:<dest>`
- `SHOW_NEIGHBORS`
- `SHOW_MESSAGES`
- `SHOW_DISCOVERY`
- `SHOW_RREP_ACK`
- `SHOW_LOCAL_REPAIR`
- `SHOW_PENDING_DATA`
- `SHOW_PRECURSORS`
- `SHOW_TIMER`

## 关键参数与推荐值

- `hello_interval_sec`: 10
- `hello_timeout_sec`: 30
- `rreq_ttl_start`: 2
- `rreq_ttl_increment`: 2
- `rreq_ttl_threshold`: 7
- `rreq_retries`: 3
- `local_repair_wait_sec`: 5
- `rrep_ack_timeout_sec`: 2
- `rerr_rate_limit_sec`: 1
- `rerr_max_dest_per_msg`: 16
- `tx_jitter_max_ms`: 30
- `pending_queue_limit_per_dest`: 32
- `pending_total_limit`: 256

## 示例配置

- 节点配置：`Src/node_config.example.json`
- 集群配置：`Src/cluster_config.example.json`
