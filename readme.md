# AODV 应用层覆盖网络（UDP/5005）

本项目实现多设备节点间运行的 AODV 应用层覆盖网络。AODV 负责邻居维护、路由发现与路由维护；文件传输业务通过独立的 `video_forwarder.py` 数据面脚本逐跳转发。

## 实现范围

- 控制报文：`RREQ / RREP / RERR / RREP-ACK`
- HELLO：采用 RFC 语义，使用 `TTL=1` 的特殊 `RREP`
- 业务报文：`DATA`（工程扩展）
- 数据面文件转发：`src/video_forwarder.py`
- 地址编码：IPv4 4 字节二进制
- Python 版本：3.12+

## 目录

- `src/aodv_protocol.py`：协议核心状态机
- `src/aodv_codec.py`：二进制编解码
- `src/aodv_route_manager.py`：路由表状态与更新策略
- `src/aodv_error_manager.py`：前驱、RERR 去重/限速
- `src/aodv_discovery_manager.py`：RREQ 发现重试
- `src/aodv_local_repair_manager.py`：本地修复状态
- `src/aodv_ack_manager.py`：RREP-ACK 等待状态
- `src/aodv_control.py`：控制命令
- `src/video_forwarder.py`：独立 UDP 文件转发程序
- `tools/mininet_wifi_linear_4sta.py`：Mininet-WiFi 四节点线性拓扑一键测试
- `configs/mininet_wifi/`：Mininet-WiFi 用的 `sta1-sta4` 配置

## 启动单节点

```bash
cd src
python main.py node --config node_config.json
```

## 单元测试

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## 控制命令

支持的控制命令：

- `DISCOVER_ROUTE:<dest>`：只触发路由发现，不发送业务数据
- `SEND_MESSAGE:<dest>:<payload>`：发送一条文本业务消息
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
- `CLEAR_MESSAGES`

## 在 Mininet-WiFi CLI 中查看路由表

`SHOW_ROUTE` 不是 `mininet-wifi>` 自带命令，需要通过节点本地 AODV 控制端口发送。

查看 `sta2` 的完整路由表：

```bash
sta2 python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3); s.sendto(b'SHOW_ROUTE', ('127.0.0.1', 5100)); print(s.recvfrom(8192)[0].decode())"
```

查看 `sta2` 到 `10.0.0.4` 的详细路由：

```bash
sta2 python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3); s.sendto(b'SHOW_ROUTE_DETAIL:10.0.0.4', ('127.0.0.1', 5100)); print(s.recvfrom(8192)[0].decode())"
```

触发 `sta4 -> 10.0.0.1` 的路由发现：

```bash
sta4 python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3); s.sendto(b'DISCOVER_ROUTE:10.0.0.1', ('127.0.0.1', 5100)); print(s.recvfrom(8192)[0].decode())"
```

## Mininet-WiFi 四节点线性拓扑一键测试

当前默认实验场景：

- 拓扑：`sta1 - sta2 - sta3 - sta4`
- 节点 IP：`10.0.0.1` 到 `10.0.0.4`
- AODV：自动启动
- 文件传输：自动把仓库根目录下的 `data.mp4` 从 `sta1` 发到 `sta4`

在 Linux 环境中执行：

```bash
cd /home/admin/overlay_AODV
sudo python3 tools/mininet_wifi_linear_4sta.py
```

跑完后进入 `mininet-wifi>` CLI：

```bash
sudo python3 tools/mininet_wifi_linear_4sta.py --cli
```

给四个无线接口统一加 `5%` 底层丢包率：

```bash
sudo python3 tools/mininet_wifi_linear_4sta.py --link-loss 5
```

同时保留 CLI：

```bash
sudo python3 tools/mininet_wifi_linear_4sta.py --link-loss 5 --cli
```

指定其他文件：

```bash
sudo python3 tools/mininet_wifi_linear_4sta.py --video-file another.mp4
```

只建网络和启动 AODV，不跑文件传输：

```bash
sudo python3 tools/mininet_wifi_linear_4sta.py --skip-file-transfer --cli
```

## 在 Mininet-WiFi CLI 中手动设置底层丢包率

给四个站点统一加 `5%` 底层丢包率：

```bash
sta1 tc qdisc replace dev sta1-wlan0 root netem loss 5%
sta2 tc qdisc replace dev sta2-wlan0 root netem loss 5%
sta3 tc qdisc replace dev sta3-wlan0 root netem loss 5%
sta4 tc qdisc replace dev sta4-wlan0 root netem loss 5%
```

查看是否生效：

```bash
sta1 tc qdisc show dev sta1-wlan0
sta2 tc qdisc show dev sta2-wlan0
sta3 tc qdisc show dev sta3-wlan0
sta4 tc qdisc show dev sta4-wlan0
```

删除丢包设置：

```bash
sta1 tc qdisc del dev sta1-wlan0 root
sta2 tc qdisc del dev sta2-wlan0 root
sta3 tc qdisc del dev sta3-wlan0 root
sta4 tc qdisc del dev sta4-wlan0 root
```
## Mininet-WiFi 中手动启动文件转发

如果当前环境不能使用 `xterm`，直接在 `mininet-wifi>` 中用后台命令即可。

启动 `sta2` 转发器：

```bash
sta2 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 video_forwarder.py --node-ip 10.0.0.2 --log-file /home/admin/overlay_AODV/logs/video_forwarder_sta2.log > /dev/null 2>&1 &"
```

启动 `sta3` 转发器：

```bash
sta3 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 video_forwarder.py --node-ip 10.0.0.3 --log-file /home/admin/overlay_AODV/logs/video_forwarder_sta3.log > /dev/null 2>&1 &"
```

启动 `sta4` 接收端：

```bash
sta4 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 video_forwarder.py --node-ip 10.0.0.4 --output-dir /home/admin/overlay_AODV/logs/received_videos --log-file /home/admin/overlay_AODV/logs/video_forwarder_sta4.log > /dev/null 2>&1 &"
```

从 `sta1` 发送 `/home/admin/overlay_AODV/data.mp4` 到 `sta4`：

```bash
sta1 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 video_forwarder.py --node-ip 10.0.0.1 --send-file /home/admin/overlay_AODV/data.mp4 --dest-ip 10.0.0.4 --log-file /home/admin/overlay_AODV/logs/video_forwarder_sta1.log --exit-after-send"
```

## 手动校验文件传输

查看接收文件：

```bash
sta4 ls -l /home/admin/overlay_AODV/logs/received_videos
```

校验源文件和目的文件哈希：

```bash
sta1 sha256sum /home/admin/overlay_AODV/data.mp4
sta4 sha256sum /home/admin/overlay_AODV/logs/received_videos/data.mp4
```

两边 `sha256sum` 一致即表示传输成功。


## Overlay 性能测试

性能测试脚本：`src/overlay_bench.py`

支持的测试模式：

- `daemon`：在中间节点和目的节点启动测试守护进程
- `route`：测第一次路由建立时间
- `latency`：测 RTT、估计单向时延、丢包率、PDR
- `throughput`：测吞吐量、PDR、丢包率

### 1. 在 Mininet-WiFi CLI 中启动性能测试守护进程

先在 `sta2`、`sta3`、`sta4` 启动守护进程：

```bash
sta2 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 overlay_bench.py daemon --node-ip 10.0.0.2 --log-file /home/admin/overlay_AODV/logs/bench_sta2.log > /dev/null 2>&1 &"
sta3 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 overlay_bench.py daemon --node-ip 10.0.0.3 --log-file /home/admin/overlay_AODV/logs/bench_sta3.log > /dev/null 2>&1 &"
sta4 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 overlay_bench.py daemon --node-ip 10.0.0.4 --log-file /home/admin/overlay_AODV/logs/bench_sta4.log > /dev/null 2>&1 &"
```

说明：

- `sta1` 不需要先启动 `daemon`
- `sta1` 在执行 `route / latency / throughput` 命令时会临时启动自己的发送端逻辑

### 2. 测路由收敛时间

测 `sta1 -> sta4` 的第一次建路时间：

```bash
sta1 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 overlay_bench.py route --node-ip 10.0.0.1 --dest-ip 10.0.0.4"
```

关键结果字段：

- `route_setup_sec`：第一次建立有效路由所需时间
- `next_hop_ip`：下一跳
- `hop_count`：跳数

### 3. 测端到端时延、丢包率、PDR

发送 20 个探测包：

```bash
sta1 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 overlay_bench.py latency --node-ip 10.0.0.1 --dest-ip 10.0.0.4 --count 20 --payload-size 64 --interval-ms 100"
```

关键结果字段：

- `route_setup_sec`：路由建立时间
- `rtt_min_ms`
- `rtt_avg_ms`
- `rtt_p95_ms`
- `rtt_max_ms`
- `one_way_estimated_ms`：按 `RTT/2` 估算的单向时延
- `pdr`：包投递率
- `loss_rate`：丢包率

如果需要机器可读输出：

```bash
sta1 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 overlay_bench.py latency --node-ip 10.0.0.1 --dest-ip 10.0.0.4 --count 20 --payload-size 64 --interval-ms 100 --json"
```

### 4. 测吞吐量、PDR、丢包率

发送 1000 个 1000 字节数据包：

```bash
sta1 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 overlay_bench.py throughput --node-ip 10.0.0.1 --dest-ip 10.0.0.4 --count 1000 --payload-size 1000 --interval-ms 0"
```

关键结果字段：

- `route_setup_sec`：路由建立时间
- `offered_load_mbps`：发送端注入速率
- `goodput_mbps`：接收端有效吞吐量
- `pdr`：包投递率
- `loss_rate`：丢包率
- `sent_packets / received_packets / lost_packets`
- `duplicate_packets`

如果需要机器可读输出：

```bash
sta1 bash -lc "cd /home/admin/overlay_AODV/src && PYTHONPATH=. python3 overlay_bench.py throughput --node-ip 10.0.0.1 --dest-ip 10.0.0.4 --count 1000 --payload-size 1000 --interval-ms 0 --json"
```

### 5. 查看性能测试日志

```bash
cat /home/admin/overlay_AODV/logs/bench_sta2.log
cat /home/admin/overlay_AODV/logs/bench_sta3.log
cat /home/admin/overlay_AODV/logs/bench_sta4.log
```

### 6. 停止性能测试守护进程

```bash
sta2 pkill -f "overlay_bench.py daemon"
sta3 pkill -f "overlay_bench.py daemon"
sta4 pkill -f "overlay_bench.py daemon"
```

说明：

- `latency` 当前测的是 RTT，并给出 `RTT/2` 的单向估计值；严格单向时延需要时钟同步
- `route_setup_sec` 只有在目标路由尚未建立时才代表真正的“首次收敛时间”
- 吞吐量结果更接近 overlay 业务层有效吞吐，不是底层 802.11 原始物理速率
## 常用日志位置

AODV 日志：

```bash
/home/admin/overlay_AODV/logs/mininet_wifi/sta1-aodv.out
/home/admin/overlay_AODV/logs/mininet_wifi/sta2-aodv.out
/home/admin/overlay_AODV/logs/mininet_wifi/sta3-aodv.out
/home/admin/overlay_AODV/logs/mininet_wifi/sta4-aodv.out
```

`video_forwarder` 日志：

```bash
/home/admin/overlay_AODV/logs/video_forwarder_sta1.log
/home/admin/overlay_AODV/logs/video_forwarder_sta2.log
/home/admin/overlay_AODV/logs/video_forwarder_sta3.log
/home/admin/overlay_AODV/logs/video_forwarder_sta4.log
```

接收文件目录：

```bash
/home/admin/overlay_AODV/logs/received_videos
```

查看日志示例：

```bash
cat /home/admin/overlay_AODV/logs/mininet_wifi/sta2-aodv.out
cat /home/admin/overlay_AODV/logs/video_forwarder_sta3.log
```

## 关键参数与推荐值

- `hello_interval_sec`: 10
- `hello_timeout_sec`: 30
- `bootstrap_peers`: []
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

- Mininet-WiFi 节点配置：`configs/mininet_wifi/sta1.json` 到 `configs/mininet_wifi/sta4.json`


