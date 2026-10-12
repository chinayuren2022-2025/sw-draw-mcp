# FastGPT（v4.12.0）接入 SolidWorks 插件说明

## 1. 关键约束

SolidWorks 2018 只能运行在 Windows 上，本插件依赖 SolidWorks COM，因此：

- **不能在纯 Ubuntu 服务器上直接运行本插件。**
- 如果“只使用这台 Ubuntu 服务器、不使用其他电脑或云”，唯一可行方案是：
  - 在这台 Ubuntu 服务器上用 KVM/QEMU 创建一台本地 Windows 虚拟机
  - 在 Windows 虚拟机中安装 SolidWorks 2018 和本插件
  - FastGPT（Ubuntu 宿主机）通过网络调用 Windows 虚拟机里的 MCP server

如果无法接受本地 Windows 虚拟机，则无法实现真实 SolidWorks 建模。

## 2. 推荐架构

```text
Ubuntu 服务器
├─ FastGPT（v4.12.0）            ← Agent / 工作流
│    │
│    │  SSE / HTTP
│    ▼
└─ KVM/QEMU Windows 虚拟机
     ├─ SolidWorks 2018
     ├─ sw-draw-skill
     └─ mcp_server.py --transport sse --host 0.0.0.0 --port 8711
```

## 3. 在 Ubuntu 上创建 Windows 虚拟机

1. 安装 KVM/QEMU（或 Proxmox VE，如果服务器已用）。
2. 创建 Windows 10/11 虚拟机。
3. 安装 SolidWorks 2018 SP5。
4. 网络建议使用 **桥接模式**，让 Windows VM 直接获得局域网 IP；
   如果必须 NAT，则配置端口转发：宿主机 `127.0.0.1:8711` → Windows VM `8711`。

## 4. 在 Windows 虚拟机中部署插件

1. 解压对应客户端包到 `D:\sw-draw-skill`
2. 运行：
   ```bat
   D:\sw-draw-skill\setup.bat
   ```
3. 自检：
   ```bat
   python D:\sw-draw-skill\verify_env.py
   ```
4. 启动 MCP SSE 服务（供 FastGPT 调用）：
   ```bat
   python D:\sw-draw-skill\scripts\mcp_server.py --transport sse --host 0.0.0.0 --port 8711
   ```

> 注意：这里必须用 `0.0.0.0`，不能只绑 `127.0.0.1`，因为 FastGPT 在宿主机上，不是 Windows VM 本机。

## 5. FastGPT 接入

### 5.1 如果 v4.12 支持“MCP 工具集”

在 FastGPT 中创建“MCP 工具集”，填入 Windows VM 的 SSE 地址：

```text
http://<Windows虚拟机IP>:8711/sse
```

如果使用 NAT + 端口转发，可填：

```text
http://127.0.0.1:8711/sse
```

创建后，FastGPT Agent 即可调用 `sw_status`、`part_build`、`drawing_build` 等 19 个工具。

### 5.2 如果 v4.12 不支持“MCP 工具集”

老版本 FastGPT 可能只支持 HTTP 插件/工具调用。此时需要再加一个轻量 HTTP 适配层：

- 在 Ubuntu 宿主机运行一个 HTTP 服务，把 FastGPT 的 HTTP 请求转发到 Windows VM 的 MCP SSE 服务。
- 或者把本插件的 19 个工具直接封装成 FastGPT HTTP 工具（每个工具一个 HTTP endpoint）。
- 这个适配层可以后续开发，核心插件不需要改。

## 6. 验证步骤

1. 在 Windows VM 中确认 MCP SSE 已监听：
   ```bat
   netstat -ano | findstr 8711
   ```
2. 在 Ubuntu 宿主机测试连通性：
   ```bash
   curl -N http://<Windows虚拟机IP>:8711/sse
   ```
3. 在 FastGPT 中创建一个测试 Agent，调用 `sw_status`，应返回：
   ```json
   {"running": true, "revision": "26.5.0"}
   ```
4. 再测试 `lens_dry_run` / `part_build`。

## 7. 注意事项

- FastGPT v4.12.0 是否原生支持“MCP 工具集”需要在该版本界面确认；FastGPT 官方 MCP 功能要求私有化部署版本至少为 v4.9.6，但“消费外部 MCP 工具”的能力可能在更晚版本才稳定。
- 如果 v4.12 确实不支持外部 MCP，需要走 HTTP 插件适配层，或升级 FastGPT。
- Windows VM 的防火墙需要放行 8711 端口。
- 如果使用 NAT，宿主机端口转发也要配置。
