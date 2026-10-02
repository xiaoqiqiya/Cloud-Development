# 可勾选组件的 Base 镜像

新增文件 `Dockerfile.base.custom` 和 `.github/workflows/build-base-custom.yml`，原 Base、桌面、动态层及其工作流保持独立。

## 在 GitHub Actions 中选择组件

1. 打开仓库 **Actions → Build Custom Base Image → Run workflow**。
2. 保留默认选项，或按需勾选/取消组件。
3. `image_tag` 默认填写 `base-custom`；需要保留多套配置时分别填写 `base-custom-go`、`base-custom-media` 等名称。名称后缀最长 64 个字符，只使用小写字母、数字、点、下划线和连字符，首字符必须是字母或数字。
4. 点击 **Run workflow**。运行摘要会显示勾选项、依赖自动补齐后的安装项、镜像标签和 digest。

默认发布到 `ghcr.io/xiaoqiqiya/cloud-development:base-custom`。每次还会发布 `base-custom-运行ID-重试次数` 标签，便于找回当次组合。

**只有手动运行才推送镜像。** push / PR 使用默认配置做构建检查，避免把已经手动选择的组合覆盖掉。新流程不会派发旧桌面/动态层构建，也不会更新原来的 `base`、`desktop`、正式 release 标签或版本锁。

## 默认组件与依赖

始终保留：Node.js/npm/pnpm/Yarn、Python/uv、Git、基础编译工具、常用命令、中文 locale、app 用户及原容器启动依赖。

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

自动补齐的依赖：

- 音视频 → 浏览器 + Docker。因此默认镜像实际包含浏览器；想去掉浏览器，需要同时取消音视频和浏览器。
- Flutter → Android SDK → Java / Gradle。
- APK 逆向 → Java / Gradle。
- Go 预下载 → Go。

依赖是否勾选不影响补齐结果。镜像内 `/usr/local/share/base-custom.json` 保存勾选项和实际安装项。

## 本地构建

与现有 Base 一样只提供 `linux/amd64`。参数值使用 `true` / `false`。

```powershell
# 默认组合，包含音视频。
docker build --platform linux/amd64 -f Dockerfile.base.custom -t cloud-base:custom .

# 例：取消音视频和 Rust，增加 Java。
docker build --platform linux/amd64 -f Dockerfile.base.custom -t cloud-base:custom --build-arg INSTALL_MEDIA=false --build-arg INSTALL_RUST=false --build-arg INSTALL_JAVA=true .

# Base 本身没有 Serena、code-server 等动态层服务，检查工具时覆盖入口。
docker run --rm -it --entrypoint /bin/bash cloud-base:custom

# 继续使用现有动态层 Dockerfile，本地生成一份完整应用镜像。
docker build -f Dockerfile --build-arg BASE_IMAGE=cloud-base:custom -t cloud-development:custom .

# 只检查开关、默认值和依赖逻辑，不下载组件。
python custom-base/check.py --self-test
```

浏览器、音视频、文档和逆向的 Python 包按组件分开安装，不调用原来的全量 `base/install-python.sh`。Go 依赖缓存仅在勾选预下载时安装。whisper 的转录模型按需另行下载。

构建末尾会检查已选组件的命令是否存在、未选组件是否被意外带入；音视频额外执行 Hyperframes 依赖检查。安装 Docker / mihomo 只提供工具，运行时仍需按原方式设置 `ENABLE_DOCKERD=1` / `ENABLE_CLASH=1` 和相应容器权限。
