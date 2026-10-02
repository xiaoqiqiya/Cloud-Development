# Cloud-Development

基于Docker环境构建的一个隔离开发虚拟环境

## 本项目的缘由

我需要一个可以快速拉起、撤销环境修改的容器，且具备隔离的Agent开发，以便我可以直接开完全访问模式

## 镜像变体

| Tag | 说明 |
|---|---|
| `vxxxxxxxx`（无后缀） | slim 版（NoDesktop-Base）：不含远程桌面，体积更小，`FROM :base` |
| `vxxxxxxxx-desktop` | 完整版（Desktop-Base，默认）：XFCE4/xrdp 远程桌面（端口 3390），`FROM :desktop` |

## 开发入口

镜像不再安装 OpenCode / OpenChamber，也不再提供 4096 网页入口。

- code-server：浏览器访问 `http://127.0.0.1:4097`，密码通过 `CODE_SERVER_PASSWORD` 设置，项目目录为 `/workspace`。
- SSH：配置 `app-config/authorized_keys` 后，通过 `ssh -p 2223 app@宿主机地址` 登录。
- 宿主机终端：`docker exec -it -u app -w /workspace opencode bash`。
- 桌面版仍可通过 RDP 使用 XFCE4；Codex、Claude Code、Antigravity 和 Serena MCP 继续保留。

当前 Compose 的网页端口只绑定宿主机回环地址，远程访问可使用 SSH 转发。
Compose 服务名、容器名 `opencode` 和镜像版本变量 `OPENCODE_SERVER_VERSION` 保留用于兼容已有部署，不代表仍安装 OpenCode。
原有 OpenCode 配置和会话目录不再挂载，但宿主机上的文件不会被删除。已有部署需切换到本次改动构建的新镜像并重建容器后生效。

> 关于开发思路：
> 
> 由于Agent是更新比较频繁的，但是开发依赖却是更新频率较低的。
> 
> 所以本项目拆分成三层 Docker 镜像：Base 存放稳定开发依赖，桌面层提供可选图形桌面，动态层安装更新较频繁的 Agent 等工具。
> 
> 如果你需要定制一个适用你的，可以直接从base入手，将开发依赖进行适配即可，动态层已经覆盖安装了主流的开发Agent（例如CC、Codex、Antigravity）
