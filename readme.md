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
- `tools/mininet_wifi_linear_10hop_route_bench.py`：Mininet-WiFi 线性多跳 AODV 建路时间批量测试
- `tools/mininet_wifi_complex_12sta.py`：Mininet-WiFi 十二节点复杂拓扑一键测试
- `tools/mininet_wifi_complex_12sta_loss_sweep.py`：Mininet-WiFi 十二节点复杂拓扑底层丢包率扫描测试
- `configs/mininet_wifi_linear_10hop/`：Mininet-WiFi 用的 `sta1-sta11` 线性多跳拓扑描述
- `configs/mininet_wifi_complex_12sta/`：Mininet-WiFi 用的 `sta1-sta12` 复杂拓扑配置

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

查看 `sta7` 到 `10.0.0.12` 的详细路由：

```bash
sta7 python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3); s.sendto(b'SHOW_ROUTE_DETAIL:10.0.0.12', ('127.0.0.1', 5100)); print(s.recvfrom(8192)[0].decode())"
```

触发 `sta12 -> 10.0.0.1` 的路由发现：

```bash
sta12 python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3); s.sendto(b'DISCOVER_ROUTE:10.0.0.1', ('127.0.0.1', 5100)); print(s.recvfrom(8192)[0].decode())"
```

## Mininet-WiFi 线性多跳建路时间测试

当前线性多跳建路时间场景：

- 拓扑：`sta1 - sta2 - ... - sta11`
- 节点 IP：`10.0.0.1` 到 `10.0.0.11`
- 默认测量范围：`sta1 -> sta2` 到 `sta1 -> sta9`，即 `1-8` 跳
- 可选最大跳数：当前拓扑最多支持到 `10` 跳
- 测量方式：每一跳测量前会重新启动一轮 AODV 进程，尽量避免路由缓存污染结果

在 Linux 环境中执行默认 `1-8` 跳测试：

```bash
cd /home/woodzow/overlay_AODV
sudo python3 tools/mininet_wifi_linear_10hop_route_bench.py
```

把汇总结果保存到 JSON：

```bash
sudo python3 tools/mininet_wifi_linear_10hop_route_bench.py --output-json logs/mininet_wifi_linear_10hop/results.json
```

如果需要测到 `10` 跳：

```bash
sudo python3 tools/mininet_wifi_linear_10hop_route_bench.py --max-hop 10
```

测量完成后保留拓扑并进入 `mininet-wifi>` CLI：

```bash
sudo python3 tools/mininet_wifi_linear_10hop_route_bench.py --cli
```

说明：

- 脚本会在终端打印每一跳的 `route_setup_sec / hop_count / next_hop_ip / status`
- 如果指定 `--output-json`，结果会写入对应 JSON 文件
- AODV 日志和运行时配置默认保存在 `logs/mininet_wifi_linear_10hop/`

## Mininet-WiFi 十二节点复杂拓扑一键测试

当前复杂拓扑实验场景：

- 拓扑：`sta1-sta12`，邻接关系见 `configs/mininet_wifi_complex_12sta/topology.json`
- 节点 IP：`10.0.0.1` 到 `10.0.0.12`
- AODV：自动启动
- 文件传输：默认把仓库根目录下的 `data.mp4` 从 `sta1` 发到 `sta12`
- 配置目录：`configs/mininet_wifi_complex_12sta/`

在 Linux 环境中执行：

```bash
cd /home/woodzow/overlay_AODV
sudo python3 tools/mininet_wifi_complex_12sta.py
```

跑完后进入 `mininet-wifi>` CLI：

```bash
sudo python3 tools/mininet_wifi_complex_12sta.py --cli
```

给十二个无线接口统一加 `5%` 底层丢包率：

```bash
sudo python3 tools/mininet_wifi_complex_12sta.py --link-loss 5
```

同时保留 CLI：

```bash
sudo python3 tools/mininet_wifi_complex_12sta.py --link-loss 5 --cli
```

指定其他文件：

```bash
sudo python3 tools/mininet_wifi_complex_12sta.py --video-file another.mp4
```

只建网络和启动 AODV，不跑文件传输：

```bash
sudo python3 tools/mininet_wifi_complex_12sta.py --skip-file-transfer --cli
```

说明：

- 该场景的逻辑拓扑由 `sta1.json` 到 `sta12.json` 里的静态 `neighbors` 定义
- Mininet-WiFi 坐标与默认通信范围记录在 `configs/mininet_wifi_complex_12sta/topology.json`
- 现有单元测试命令不需要修改；`tests/test_mininet_wifi_complex_12sta.py` 会被 `unittest discover` 自动发现

## 在 Mininet-WiFi CLI 中手动设置底层丢包率

给 12 个站点统一加 `5%` 底层丢包率：

```bash
for i in $(seq 1 12); do
  sta${i} tc qdisc replace dev sta${i}-wlan0 root netem loss 5%
done
```

查看是否生效：

```bash
for i in $(seq 1 12); do
  sta${i} tc qdisc show dev sta${i}-wlan0
done
```

删除丢包设置：

```bash
for i in $(seq 1 12); do
  sta${i} tc qdisc del dev sta${i}-wlan0 root
done
```

## 十二节点复杂拓扑性能测试

复杂拓扑性能测试沿用现有 `src/overlay_bench.py` 与 `src/resource_bench.py`，但现在不需要手动在 `sta2-sta12` 逐个启动 `overlay_bench.py daemon` 了。
`tools/mininet_wifi_complex_12sta.py --bench ...` 会自动完成以下步骤：

- 建立 12 节点复杂拓扑并启动全部 AODV 进程
- 等待邻居稳定
- 在 `latency / throughput` 模式下自动拉起中继与目标节点的 bench daemon
- 在源节点执行一次 benchmark 并打印结果
- 默认测试结束后自动清理；如果附加 `--cli`，则保留拓扑进入 `mininet-wifi>`

### 1. 一键测首次建路时间

```bash
cd /home/woodzow/overlay_AODV
sudo python3 tools/mininet_wifi_complex_12sta.py --bench route
```

如需保留拓扑进入 CLI：

```bash
sudo python3 tools/mininet_wifi_complex_12sta.py --bench route --cli
```

关键结果字段：

- `route_setup_sec`：首次建立有效路由所需时间
- `next_hop_ip`：下一跳
- `hop_count`：跳数

### 2. 一键测端到端时延、丢包率、PDR

```bash
cd /home/woodzow/overlay_AODV
sudo python3 tools/mininet_wifi_complex_12sta.py --bench latency
```

默认等价于：`20` 个探测包、`64` 字节载荷、`100ms` 间隔。若需调整：

```bash
sudo python3 tools/mininet_wifi_complex_12sta.py --bench latency --bench-count 50 --bench-payload-size 128 --bench-interval-ms 50
```

关键结果字段：

- `route_setup_sec`
- `rtt_min_ms / rtt_avg_ms / rtt_p95_ms / rtt_max_ms`
- `one_way_estimated_ms`
- `pdr`
- `loss_rate`
- `lost`

### 3. 一键测吞吐量、丢包率、PDR

```bash
cd /home/woodzow/overlay_AODV
sudo python3 tools/mininet_wifi_complex_12sta.py --bench throughput
```

默认等价于：`1000` 个数据包、`1000` 字节载荷、`0ms` 间隔。若需调整：

```bash
sudo python3 tools/mininet_wifi_complex_12sta.py --bench throughput --bench-count 2000 --bench-payload-size 1200 --bench-interval-ms 1
```

关键结果字段：

- `route_setup_sec`
- `offered_load_mbps`
- `goodput_mbps`
- `pdr`
- `loss_rate`
- `sent_packets / received_packets / lost_packets`
- `duplicate_packets`

### 4. 指定源和目的节点

默认测试源和目的节点取自拓扑中的 `sta1 -> sta12`。如果需要改成其他节点：

```bash
sudo python3 tools/mininet_wifi_complex_12sta.py --bench latency --bench-source sta3 --bench-dest sta11
```

### 5. 查看 benchmark 日志

自动拉起的 bench daemon 日志会写到：

```bash
/home/woodzow/overlay_AODV/logs/mininet_wifi/sta2-bench.log
/home/woodzow/overlay_AODV/logs/mininet_wifi/sta7-bench.log
/home/woodzow/overlay_AODV/logs/mininet_wifi/sta12-bench.log
```

### 6. 测 CPU 与内存占用

查看源节点 `sta1` 当前 overlay 相关进程的 CPU 和内存占用：

```bash
sta1 bash -lc "cd /home/woodzow/overlay_AODV/src && PYTHONPATH=. python3 resource_bench.py"
```

查看核心中继节点 `sta7`：

```bash
sta7 bash -lc "cd /home/woodzow/overlay_AODV/src && PYTHONPATH=. python3 resource_bench.py"
```

查看目的节点 `sta12`：

```bash
sta12 bash -lc "cd /home/woodzow/overlay_AODV/src && PYTHONPATH=. python3 resource_bench.py"
```

只看 AODV 进程：

```bash
sta7 bash -lc "cd /home/woodzow/overlay_AODV/src && PYTHONPATH=. python3 resource_bench.py --role aodv"
```

输出 JSON：

```bash
sta7 bash -lc "cd /home/woodzow/overlay_AODV/src && PYTHONPATH=. python3 resource_bench.py --json"
```

连续采样 10 次，每 1 秒一组：

```bash
sta7 bash -lc "cd /home/woodzow/overlay_AODV/src && PYTHONPATH=. python3 resource_bench.py --watch-sec 1 --samples 10"
```

关键字段说明：

- `cpu_percent`：进程 CPU 占用百分比
- `mem_percent`：进程内存占用百分比
- `rss_kb`：当前常驻内存
- `vmhwm_kb`：历史峰值常驻内存
- `vsz_kb`：虚拟内存大小

说明：

- `latency` 当前测的是 RTT，并给出 `RTT/2` 的单向估计值；严格单向时延需要时钟同步
- `route_setup_sec` 只有在目标路由尚未建立时才代表真正的“首次收敛时间”
- 如果需要在 benchmark 后继续排查路径变化，可附加 `--cli` 并结合 `SHOW_ROUTE`、`SHOW_ROUTE_DETAIL:10.0.0.12` 与 AODV 日志一起分析

## 十二节点复杂拓扑底层丢包率扫描测试

该场景用于批量测试底层 `tc netem loss=1%..10%` 时，`sta1 -> sta12` 的 overlay 丢包率和吞吐量变化。脚本会在每个丢包档位：

- 先清理旧的 `qdisc`
- 给全部 `staX-wlan0` 接口施加统一底层丢包率
- 重新启动 AODV 和 `overlay_bench.py daemon`
- 运行 `sta1 -> sta12` 的 throughput 测试
- 输出并保存 `loss_rate / pdr / goodput_mbps / offered_load_mbps / route_setup_sec / hop_count`

默认执行 `1%-10%` 丢包率扫描：

```bash
cd /home/woodzow/overlay_AODV
sudo python3 tools/mininet_wifi_complex_12sta_loss_sweep.py
```

把汇总结果写入指定 JSON：

```bash
sudo python3 tools/mininet_wifi_complex_12sta_loss_sweep.py --output-json logs/mininet_wifi_complex_12sta_loss_sweep/results.json
```

调整 throughput 测试参数：

```bash
sudo python3 tools/mininet_wifi_complex_12sta_loss_sweep.py --count 2000 --payload-size 1200 --interval-ms 1
```

按步长扫描，例如只测 `2% 4% 6% 8% 10%`：

```bash
sudo python3 tools/mininet_wifi_complex_12sta_loss_sweep.py --min-loss 2 --max-loss 10 --loss-step 2
```

扫描完成后保留拓扑并进入 `mininet-wifi>` CLI：

```bash
sudo python3 tools/mininet_wifi_complex_12sta_loss_sweep.py --cli
```

结果位置：

- 汇总结果默认保存到 `logs/mininet_wifi_complex_12sta_loss_sweep/results.json`
- 每个丢包档位会额外保存到 `logs/mininet_wifi_complex_12sta_loss_sweep/loss_XX/result.json`
- 每个档位对应的 AODV 日志和 bench daemon 日志也会保存在对应的 `loss_XX/` 目录下

## Overlay CPU 与内存占用测试

资源占用统计脚本：`src/resource_bench.py`

在 `mininet-wifi>` 中查看当前节点全部 overlay 相关进程的 CPU 和内存占用：

```bash
sta1 bash -lc "cd /home/woodzow/overlay_AODV/src && PYTHONPATH=. python3 resource_bench.py"
```

只看 AODV 进程：

```bash
sta1 bash -lc "cd /home/woodzow/overlay_AODV/src && PYTHONPATH=. python3 resource_bench.py --role aodv"
```

输出 JSON：

```bash
sta1 bash -lc "cd /home/woodzow/overlay_AODV/src && PYTHONPATH=. python3 resource_bench.py --json"
```

连续采样 10 次，每 1 秒一组：

```bash
sta1 bash -lc "cd /home/woodzow/overlay_AODV/src && PYTHONPATH=. python3 resource_bench.py --watch-sec 1 --samples 10"
```

关键字段说明：

- `cpu_percent`：进程 CPU 占用百分比
- `mem_percent`：进程内存占用百分比
- `rss_kb`：当前常驻内存
- `vmhwm_kb`：历史峰值常驻内存
- `vsz_kb`：虚拟内存大小

## 常用日志位置

AODV 日志：

```bash
/home/woodzow/overlay_AODV/logs/mininet_wifi/sta1-aodv.out
/home/woodzow/overlay_AODV/logs/mininet_wifi/sta12-aodv.out
```

`video_forwarder` 日志：

```bash
/home/woodzow/overlay_AODV/logs/mininet_wifi/sta1-video_forwarder.log
/home/woodzow/overlay_AODV/logs/mininet_wifi/sta12-video_forwarder.log
```

接收文件目录：

```bash
/home/woodzow/overlay_AODV/logs/received_videos
```

查看日志示例：

```bash
cat /home/woodzow/overlay_AODV/logs/mininet_wifi/sta12-aodv.out
cat /home/woodzow/overlay_AODV/logs/mininet_wifi/sta1-video_forwarder.log
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

- Mininet-WiFi 线性多跳基线配置：`configs/mininet_wifi_linear_10hop/base_config.json`
- Mininet-WiFi 线性多跳拓扑描述：`configs/mininet_wifi_linear_10hop/topology.json`
- Mininet-WiFi 十二节点复杂拓扑配置：`configs/mininet_wifi_complex_12sta/sta1.json` 到 `configs/mininet_wifi_complex_12sta/sta12.json`
- 拓扑描述与坐标：`configs/mininet_wifi_complex_12sta/topology.json`


