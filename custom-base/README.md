# 可勾选组件与 AI Agent 的镜像

`Dockerfile.base.custom` 管理基础组件，`Dockerfile.custom` 管理可选 AI Agent；统一使用 `.github/workflows/build-base-custom.yml`。原 Base、桌面、动态层及其工作流保持独立。

## 在 GitHub Actions 中选择组件

1. 打开仓库 **Actions → Build Custom Base Image → Run workflow**。
2. 保留默认选项，或按需勾选/取消组件。
3. `image_tag` 默认填写 `base-custom`；需要保留多套配置时分别填写 `base-custom-go`、`base-custom-media` 等名称。名称后缀最长 64 个字符，只使用小写字母、数字、点、下划线和连字符，首字符必须是字母或数字。
4. 点击 **Run workflow**。运行摘要会显示勾选项、依赖自动补齐后的安装项、镜像标签和 digest。

一次运行构建两层，应用层直接使用本次选定的 Base，不会引用上次发布的基础镜像：

- `ghcr.io/xiaoqiqiya/cloud-development:base-custom`：基础组件，不含动态层 Agent。
- **`ghcr.io/xiaoqiqiya/cloud-development:custom`**：日常使用的完整应用镜像，包含所选 Agent，默认仅 Codex。

如果输入 `base-custom-go`，对应的应用标签为 `custom-go`。两个镜像均额外发布 `标签-运行ID-重试次数`，便于找回当次组合。

**手动运行或更新检查调用时才推送镜像。** push / PR 使用默认配置做构建检查，避免把已经手动选择的组合覆盖掉。新流程不会派发旧桌面/动态层构建，也不会更新原来的 `base`、`desktop`、正式 release 标签或版本锁。

## 自动检查更新

`Check Updates` 每天北京时间 **08:00、12:00、20:00** 检查默认 `base-custom` / `custom` 组合。旧 `Build Base Image` 已取消每周定时构建；定时检查也不会再触发旧版发布链。旧版的手动构建和代码变更触发仍保留。

更新流程：读取该标签上次成功发布的勾选配置 → 只检查 code-server 和已启用的 Agent → 有版本变化时调用 `Build Custom Base Image`，联动基础层和应用层。未选中的 Agent 不检查、不安装；版本没有变化时跳过构建。

需要手动检查时，进入 **Actions → Check Updates → Run workflow**：

- `target=custom`：默认选项，只更新自定义镜像。
- `target=legacy`：只检查并更新原完整镜像流程。
- `target=all`：两套流程都检查。
- `image_tag`：自定义基础标签，默认 `base-custom`；例如填写 `base-custom-go`，就检查 `base-custom-go` / `custom-go`。其他命名组合目前需要在这里手动指定。

两层镜像均成功发布后，才把勾选配置、精确组件版本和镜像摘要保存到独立的预发布记录 `custom-state-<基础标签>`。这份记录不会成为正式 Latest Release，也不会改写旧版版本锁。失败不会推进记录，下一次检查仍会尝试更新。

**首次没有记录时使用默认配置**，包括 Go、音视频和 Codex；此前发布、但没有记录的组合无法自动还原，请先手动按需要勾选并成功发布一次。后续自动更新会沿用成功保存的配置；排队期间如果有新的手动发布，也会重新读取最新选择。

发布时会把上游解析出的精确版本传入动态层，确保 Agent 更新能使对应安装层的缓存失效，基础组件仍复用缓存。

## 默认组件与依赖

始终保留：Node.js/npm/pnpm/Yarn、Python/uv、Git、基础编译工具、常用命令、中文 locale、app 用户及原容器启动依赖。应用镜像保留 code-server 作为 Web IDE 和容器主服务。

**AI Agent 默认只勾选 Codex**，也可以取消。Claude Code、Codex Security、Antigravity 和 Serena 均默认关闭；Go 和音视频仍按之前的配置默认保留。

| CI 输入 / Docker build 参数 | 默认勾选 | 安装内容 |
|---|---|---|
| `install_go` / `INSTALL_GO` | 是 | Go、gopls、govulncheck |
| `install_rust` / `INSTALL_RUST` | 是 | Rust、Clippy、rustfmt、rust-src |
| `install_bun` / `INSTALL_BUN` | 是 | Bun、bunx |
| `install_docker` / `INSTALL_DOCKER` | 是 | Docker CE、Buildx、Compose |
| `install_gh` / `INSTALL_GH` | 是 | GitHub CLI |
| `install_media` / `INSTALL_MEDIA` | **是** | FFmpeg、Hyperframes、whisper.cpp、CPU torch、Kokoro、Transformers |
| `install_node_tools` / `INSTALL_NODE_TOOLS` | 否 | TypeScript、ESLint、Prettier、esbuild、tsx、Turbo、Oxlint、Vitest、vsce |
| `install_java` / `INSTALL_JAVA` | 否 | Temurin JDK 21、Gradle |
| `install_android` / `INSTALL_ANDROID` | 否 | Android SDK |
| `install_flutter` / `INSTALL_FLUTTER` | 否 | Flutter / Dart |
| `install_browser` / `INSTALL_BROWSER` | 否 | Chrome、Playwright MCP、Python Playwright、Scrapling / Camoufox |
| `install_office` / `INSTALL_OFFICE` | 否 | LibreOffice、Pandoc、Inkscape、图像/文档处理工具和对应 Node/Python 包 |
| `install_reverse` / `INSTALL_REVERSE` | 否 | APK 工具链、radare2、Anything Analyzer、Python 逆向工具 |
| `install_windows` / `INSTALL_WINDOWS` | 否 | Wine、NSIS、Windows Electron 缓存 |
| `install_python_packages` / `INSTALL_PYTHON_PACKAGES` | 否 | Python Web、数据库、AI SDK 常用包 |
| `install_cloud` / `INSTALL_CLOUD` | 否 | Wrangler、EAS、飞书 CLI / MCP |
| `install_codegraph` / `INSTALL_CODEGRAPH` | 否 | CodeGraph |
| `install_clash` / `INSTALL_CLASH` | 否 | mihomo / Clash TUN |
| `prewarm_go` / `PREWARM_GO` | 否 | 原项目的 Go 模块缓存预下载 |
| `install_codex` / `INSTALL_CODEX` | **是** | Codex CLI |
| `install_claude_code` / `INSTALL_CLAUDE_CODE` | 否 | Claude Code、ccline、原 Claude 补丁 |
| `install_codex_security` / `INSTALL_CODEX_SECURITY` | 否 | Codex Security CLI |
| `install_antigravity` / `INSTALL_ANTIGRAVITY` | 否 | Antigravity CLI（agy） |
| `install_serena` / `INSTALL_SERENA` | 否 | Serena MCP 常驻服务 |

自动补齐的依赖：

- 音视频 → 浏览器 + Docker。因此默认镜像实际包含浏览器；想去掉浏览器，需要同时取消音视频和浏览器。
- Flutter → Android SDK → Java / Gradle。
- APK 逆向 → Java / Gradle。
- Go 预下载 → Go。

依赖是否勾选不影响补齐结果。镜像内 `/usr/local/share/base-custom.json` 保存勾选项和实际安装项。

Agent 开关彼此独立。取消 Serena 时会移除其 Supervisor 服务，健康检查只要求 code-server 和实际启用的服务正常运行；不会因为没安装 Serena 而不停重启或误报不健康。选择 Claude Code 时才执行其补丁。

## 本地构建

与现有 Base 一样只提供 `linux/amd64`。参数值使用 `true` / `false`。

```powershell
# 默认组合，包含音视频。
docker build --platform linux/amd64 -f Dockerfile.base.custom -t cloud-base:custom .

# 例：取消音视频和 Rust，增加 Java。
docker build --platform linux/amd64 -f Dockerfile.base.custom -t cloud-base:custom --build-arg INSTALL_MEDIA=false --build-arg INSTALL_RUST=false --build-arg INSTALL_JAVA=true .

# Base 本身没有 Serena、code-server 等动态层服务，检查工具时覆盖入口。
docker run --rm -it --entrypoint /bin/bash cloud-base:custom

# 构建可选动态层，AI Agent 默认仅安装 Codex。
docker build -f Dockerfile.custom --build-arg BASE_IMAGE=cloud-base:custom -t cloud-development:custom .

# 例：保留默认 Codex，另外加上 Claude Code。
docker build -f Dockerfile.custom --build-arg BASE_IMAGE=cloud-base:custom --build-arg INSTALL_CLAUDE_CODE=true -t cloud-development:custom .

# 启动 Web IDE，之后在终端里运行 codex。
docker run -d --name cloud-custom -p 8080:8080 -e CODE_SERVER_PASSWORD=请替换为你的密码 cloud-development:custom

# 只检查开关、默认值和依赖逻辑，不下载组件。
python custom-base/check.py --self-test
python custom-base/test-update.py
```

浏览器、音视频、文档和逆向的 Python 包按组件分开安装，不调用原来的全量 `base/install-python.sh`。Go 依赖缓存仅在勾选预下载时安装。whisper 的转录模型按需另行下载。

构建末尾会检查已选组件和 Agent 的命令是否存在、未选项是否被意外带入；音视频额外执行 Hyperframes 依赖检查。安装 Docker / mihomo 只提供工具，运行时仍需按原方式设置 `ENABLE_DOCKERD=1` / `ENABLE_CLASH=1` 和相应容器权限。

请使用 `Dockerfile.custom` 构建应用层；旧 `Dockerfile` 仍然安装原来的全套 Agent，不读取新版开关。CI 使用 Buildx Bake 联动两层，分别缓存基础组件和 Agent，不经过旧发布流程。
