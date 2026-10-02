# Cloud-Development

基于 Docker 的隔离开发环境，集成 code-server、开发工具链和可选 AI Agent。工作区及工具配置可以持久化，重建容器即可恢复镜像提供的环境。

## 本项目的缘由

希望快速拉起和重建开发环境，让 Agent 在容器内完成开发任务，并按项目需要选择工具，减少不使用的 SDK、软件和缓存占用。

## 使用自定义镜像

**按需选择组件时，使用 `custom` 应用镜像。AI Agent 默认只安装 Codex，Go 和音视频工具默认保留。**

1. 打开仓库的 **Actions → Build Custom Base Image → Run workflow**。
2. 勾选需要的开发组件和 Agent。
3. `image_tag` 默认保留 `base-custom`；要保存另一套组合，可以填写 `base-custom-go` 等名称。
4. 运行工作流。成功后，在运行摘要中查看镜像标签、digest 和本次安装清单。

工作流会先构建所选基础组件，再基于本次 Base 构建应用层：

```text
Dockerfile.base.custom → :base-custom
          ↓
Dockerfile.custom      → :custom
```

| 组件类别 | 默认配置 |
|---|---|
| 基础环境 | Node.js/npm/pnpm/Yarn、Python/uv、Git、基础编译工具和常用命令始终保留 |
| Web IDE | 应用镜像保留 code-server |
| 开发工具 | 默认勾选 Go（含 gopls、govulncheck）、Rust、Bun、Docker、GitHub CLI |
| 音视频 | 默认勾选 FFmpeg、Hyperframes、whisper.cpp、CPU torch 等，自动补齐浏览器和 Docker 依赖 |
| AI Agent | Codex 默认开启；Claude Code、Codex Security、Antigravity、Serena 默认关闭，均可独立选择 |
| 其他组件 | Java、Android、Flutter、办公、逆向、Windows 打包、CodeGraph、mihomo 等按需勾选 |
| Go 依赖预下载 | `prewarm_go` 默认关闭；它缓存的是原 `new-api` 项目的依赖，新 Go 项目不需要开启 |

组件依赖会自动补齐，例如 Flutter 会安装 Android SDK 和 Java。取消 Serena 时，也会同步移除其自启和对应健康检查。

完整的 24 个开关、依赖关系及本地构建命令见 [自定义镜像使用说明](custom-base/README.md)。

## 镜像变体

| Tag | 用途 | 远程桌面 |
|---|---|---|
| `custom` | 自定义应用镜像，包含所选组件、code-server 和 Agent | 不包含 |
| `base-custom` | 自定义基础层，供应用层继承，不含动态层 Agent 和 code-server | 不包含 |
| `custom-名称` / `base-custom-名称` | 命名的自定义组合，例如 `custom-go` / `base-custom-go` | 不包含 |
| `vYYYY.MM.DD` | 原完整配置的无桌面应用镜像，基于 `:base` | 不包含 |
| `vYYYY.MM.DD-desktop` | 原完整配置的桌面应用镜像，基于 `:desktop` | XFCE4/xrdp，容器端口 3390 |
| `base` / `desktop` | 原发布链的基础层 / 桌面层，供正式应用镜像继承 | 由层级决定 |

CI 将镜像发布到 `ghcr.io/<仓库所有者>/<仓库名>`，名称统一小写。当前仓库的自定义应用镜像为：

```text
ghcr.io/xiaoqiqiya/cloud-development:custom
```

自定义镜像还会生成 `标签-运行ID-重试次数`，用于找回某次成功构建的组合。正式版本使用北京时间日期作为发行号，同一天的重新发布会更新同一个日期标签。

## 部署

仓库提供 [docker-compose.yml](docker-compose.yml)。**当前 Compose 的默认镜像仍指向原仓库和旧桌面版**，切换到本仓库的 custom 镜像时，需要同时修改服务的 `image` 仓库地址和版本配置。

将 `opencode` 服务的 `image` 改为：

```yaml
image: ghcr.io/xiaoqiqiya/cloud-development:${OPENCODE_SERVER_VERSION:-custom}
```

在 `.env` 中配置：

```dotenv
OPENCODE_SERVER_VERSION=custom
CODE_SERVER_PASSWORD=请替换为你的登录密码
ENABLE_DESKTOP=0
```

按 Compose 挂载项准备工作区和配置文件，其中 `app-config/authorized_keys` 应是 SSH 公钥文件。当前 Compose 使用已有的外部网络 `1panel-network`；如果部署环境没有该网络，需要先创建它或调整网络配置。

```shell
docker compose pull opencode
docker compose up -d opencode
```

这里保留已有 Compose 的部署配置；它包含 `privileged: true`。安装 Docker 或 mihomo 只代表镜像中有对应工具，是否启动仍由 `ENABLE_DOCKERD` / `ENABLE_CLASH` 等运行参数控制。

## 开发入口

以下端口和容器名对应仓库提供的 Compose：

| 入口 | 使用方式 |
|---|---|
| code-server | 浏览器访问 `http://127.0.0.1:4097`，密码由 `CODE_SERVER_PASSWORD` 设置，工作区为 `/workspace` |
| SSH | 配置 `app-config/authorized_keys` 后执行 `ssh -p 2223 app@宿主机地址` |
| 容器终端 | `docker exec -it -u app -w /workspace opencode bash` |
| RDP | 仅桌面版可用，Compose 映射到宿主机 `127.0.0.1:3390` |

当前 Compose 的网页端口只绑定宿主机回环地址，远程访问可使用 SSH 转发。
镜像不再安装 OpenCode / OpenChamber，也不再提供 4096 网页入口。Compose 服务名、容器名 `opencode` 和镜像版本变量 `OPENCODE_SERVER_VERSION` 保留用于兼容已有部署。
原有 OpenCode 配置和会话目录不再挂载，但宿主机上的文件不会被删除。已有部署需要拉取新镜像并重建容器，镜像变更才会生效。

## CI/CD 工作流

| 工作流 | 作用 | 触发与发布 |
|---|---|---|
| [Build Custom Base Image](.github/workflows/build-base-custom.yml) | 构建自定义 Base 和 Agent 应用层 | 手动勾选或更新检查调用时发布；相关源码的 push / PR 只做构建验证 |
| [Check Updates](.github/workflows/check-update.yml) | 检查上游组件版本，发现变化再触发构建 | 每天北京时间 08:00、12:00、20:00 **只检查默认 custom 组合**；也支持手动运行 |
| [Build Base Image](.github/workflows/build-base.yml) | 构建原完整基础层 `:base`，成功后触发桌面层 | 手动或对应源码变更触发，已取消每周定时构建；PR 不发布、不级联 |
| [Build Desktop Image](.github/workflows/build-desktop.yml) | 构建原桌面层 `:desktop`，成功后触发原动态层 | 手动、对应源码变更或 Base 成功后触发；PR 不发布、不级联 |
| [Build and Push Docker Image](.github/workflows/docker-build.yml) | 发布原完整配置的无桌面版和桌面版 | 手动、对应源码变更、旧版版本检查或桌面层成功后触发；PR 只验证 |

原发布链仍是 `Base → 桌面层 → 两个应用变体`。无桌面和带桌面两个版本均成功后，才更新正式 GitHub Release 和组件版本锁。**旧版不再由定时任务触发，但手动运行和代码变更触发仍保留。**

修改共用的 `base/**` 或 `agent/**` 时，可能同时触发新旧流程。自定义工作流不经过原发布链，也不覆盖原来的 `base`、`desktop` 或日期发行标签。

## 自定义镜像自动更新

定时更新针对 `base-custom / custom`，流程为：

```text
读取上次成功发布的勾选配置
    ↓
检查 code-server 和已启用的 Agent
    ↓ 有版本变化
构建并发布自定义 Base 和应用镜像
    ↓ 两层均成功
保存勾选配置、精确版本和镜像摘要
```

未勾选的 Agent 不检查、不安装；版本没有变化则跳过构建。发布时传入精确版本，使有更新的安装层重新构建，其他组件继续复用缓存。

需要手动检查时，进入 **Actions → Check Updates → Run workflow**：

| 参数 | 含义 |
|---|---|
| `target=custom` | 默认，只检查自定义镜像 |
| `target=legacy` | 只检查原完整配置镜像 |
| `target=all` | 检查两套流程 |
| `image_tag=base-custom` | 自定义组合的基础标签；其他组合可填写 `base-custom-go` 等，当前定时任务不会自动遍历这些命名组合 |

成功记录存放在独立的预发布记录 `custom-state-<基础标签>` 中，不会成为正式 Latest Release，也不会覆盖原版版本锁。构建失败不会推进记录，后续检查仍会尝试更新。

**首次没有成功记录时使用默认组件配置。** 要让自动更新沿用自己的勾选组合，应先通过 `Build Custom Base Image` 手动成功发布一次。后续自动更新会保留已保存的选择，包括明确取消的组件。

## 文件分工

稳定开发依赖和更新频繁的 Agent 分层构建，便于复用缓存；需要图形桌面时，原发布链额外提供桌面层。

| 文件或目录 | 用途 |
|---|---|
| `Dockerfile.base.custom` / `Dockerfile.custom` | 自定义基础组件 / 可选 Agent 应用层 |
| `custom-base/` | 自定义构建、组件检查、更新记录及详细使用说明 |
| `Dockerfile.base` / `Dockerfile.desktop` / `Dockerfile` | 原完整配置的基础层 / 桌面层 / 动态应用层 |
| `base/` | 共用启动文件、健康检查及基础工具脚本 |
| `desktop/` | 桌面配置、主题资源和桌面启动脚本 |
| `agent/` | Claude Code 补丁及执行器 |
