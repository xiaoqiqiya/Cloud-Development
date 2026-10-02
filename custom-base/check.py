"""可选 Base 的参数解析、依赖检查和镜像自检；仅用 Python 标准库。"""

import configparser
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = {
    "INSTALL_FLUTTER": ("INSTALL_ANDROID",),
    "INSTALL_ANDROID": ("INSTALL_JAVA",),
    "INSTALL_REVERSE": ("INSTALL_JAVA",),
    "INSTALL_MEDIA": ("INSTALL_BROWSER", "INSTALL_DOCKER"),
    "PREWARM_GO": ("INSTALL_GO",),
}
COMMANDS = {
    "INSTALL_GO": ("go", "gopls", "govulncheck"),
    "INSTALL_RUST": ("rustc", "cargo", "rustup"),
    "INSTALL_BUN": ("bun", "bunx"),
    "INSTALL_DOCKER": ("docker", "dockerd"),
    "INSTALL_GH": ("gh",),
    "INSTALL_NODE_TOOLS": ("tsc", "eslint", "prettier", "vitest"),
    "INSTALL_JAVA": ("java", "javac", "gradle"),
    "INSTALL_ANDROID": ("sdkmanager", "adb", "apksigner", "zipalign"),
    "INSTALL_FLUTTER": ("flutter", "dart"),
    "INSTALL_BROWSER": ("google-chrome", "playwright", "scrapling"),
    "INSTALL_OFFICE": ("libreoffice", "pandoc", "inkscape"),
    "INSTALL_REVERSE": ("apktool", "jadx", "d2j-dex2jar", "uber-apk-signer", "r2", "rabin2", "anything-analyzer"),
    "INSTALL_WINDOWS": ("wine", "makensis"),
    "INSTALL_MEDIA": ("ffmpeg", "ffprobe", "hyperframes", "whisper-cli"),
    "INSTALL_CLOUD": ("wrangler", "eas"),
    "INSTALL_CODEGRAPH": ("codegraph",),
    "INSTALL_CLASH": ("mihomo",),
}
AGENT_COMMANDS = {
    "INSTALL_CODEX": ("codex",),
    "INSTALL_CLAUDE_CODE": ("claude",),
    "INSTALL_CODEX_SECURITY": ("codex-security",),
    "INSTALL_ANTIGRAVITY": ("agy",),
    "INSTALL_SERENA": ("serena",),
}


def defaults():
    text = "\n".join((ROOT / name).read_text(encoding="utf-8")
                     for name in ("Dockerfile.base.custom", "Dockerfile.custom"))
    return {key: value == "true" for key, value in re.findall(
        r"^ARG ((?:INSTALL_\w+|PREWARM_GO))=(true|false)$", text, re.M
    )}


def resolve(options):
    result = options.copy()
    while True:
        previous = result.copy()
        for option, required in DEPENDENCIES.items():
            if result[option]:
                result.update({key: True for key in required})
        if previous == result:
            return result


def parse_inputs(raw, baseline):
    unknown = set(raw) - {key.lower() for key in baseline} - {"image_tag"}
    if unknown:
        raise ValueError(f"未知输入: {sorted(unknown)}")
    result = baseline.copy()
    for key in result:
        value = raw.get(key.lower(), result[key])
        if type(value) is not bool:
            raise ValueError(f"{key} 必须为布尔值")
        result[key] = value
    return result


def validate_tag(tag):
    if not isinstance(tag, str) or not re.fullmatch(r"base-custom(?:-[a-z0-9][a-z0-9._-]{0,63})?", tag):
        raise ValueError("镜像标签必须为 base-custom 或 base-custom-小写名称")
    return tag


def prepare():
    raw = json.loads(os.environ.get("INPUTS_JSON", "{}")) or {}
    selected = parse_inputs(raw, defaults())
    actual = resolve(selected)
    tag = validate_tag(raw.get("image_tag", "base-custom"))
    image = "ghcr.io/" + os.environ["GITHUB_REPOSITORY"].lower()
    app_tag = tag.removeprefix("base-")
    config = bake_config(selected, image, tag, os.environ["GITHUB_RUN_ID"],
                         os.environ["GITHUB_RUN_ATTEMPT"],
                         os.environ["GITHUB_EVENT_NAME"] == "workflow_dispatch")
    bake_file = Path(os.environ["RUNNER_TEMP"]) / "custom-bake.json"
    bake_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    # 推送/PR 只检查默认组合；手动运行才发布，避免覆盖用户已选的组合。
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"image={image}\ntag={tag}\napp_tag={app_tag}\nbake_file={bake_file}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(f"基础镜像：`{image}:{tag}`；含 Agent 的应用镜像：`{image}:{app_tag}`（仅手动运行发布）\n\n")
        summary.write("| 组件参数 | 勾选 | 实际安装（含依赖） |\n|---|---|---|\n")
        for key, value in selected.items():
            summary.write(f"| {key} | {'是' if value else '否'} | {'是' if actual[key] else '否'} |\n")


def bake_config(selected, image, tag, run_id, attempt, publish):
    targets = {}
    for name, dockerfile, image_tag in (("base", "Dockerfile.base.custom", tag),
                                       ("custom", "Dockerfile.custom", tag.removeprefix("base-"))):
        target = {
            "context": ".", "dockerfile": dockerfile, "platforms": ["linux/amd64"],
            "tags": [f"{image}:{image_tag}", f"{image}:{image_tag}-{run_id}-{attempt}"],
            "args": {key: str(value).lower() for key, value in selected.items()
                     if (key in AGENT_COMMANDS) == (name == "custom")},
            "cache-from": [f"type=registry,ref={image}:buildcache-{image_tag}"],
        }
        if publish:
            target["cache-to"] = [f"type=registry,ref={image}:buildcache-{image_tag},mode=min"]
        if name == "custom":
            target["contexts"] = {"custom-base": "target:base"}
            target["args"]["BASE_IMAGE"] = "custom-base"
        targets[name] = target
    return {"group": {"default": {"targets": ["base", "custom"]}}, "target": targets}


def service_config(text, serena):
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(text)
    if not serena:
        config.remove_section("program:serena")
    output = io.StringIO()
    config.write(output, space_around_delimiters=False)
    return output.getvalue()


def check_agents():
    selected = {}
    for key, commands in AGENT_COMMANDS.items():
        value = os.environ[key]
        if value not in ("true", "false"):
            raise ValueError(f"{key} 必须为 true 或 false")
        selected[key] = value == "true"
        for command in commands:
            assert bool(shutil.which(command)) == selected[key], f"Agent 开关与命令不一致: {key} / {command}"
            if selected[key]:
                subprocess.run([command, "--help"], check=True, stdout=subprocess.DEVNULL)
    assert shutil.which("code-server"), "缺少 code-server"
    config = Path("/etc/supervisor/supervisord.conf")
    config.write_text(service_config(config.read_text(), selected["INSTALL_SERENA"]))
    metadata = Path("/usr/local/share/base-custom.json")
    content = json.loads(metadata.read_text())
    content["selected"].update(selected)
    content["installed"].update(selected)
    metadata.write_text(json.dumps(content, indent=2) + "\n")
    print("Agent 组件及启动配置自检通过")


def check_image():
    selected = {}
    for key in (*COMMANDS, "INSTALL_PYTHON_PACKAGES", "PREWARM_GO"):
        value = os.environ[key]
        if value not in ("true", "false"):
            raise ValueError(f"{key} 必须为 true 或 false")
        selected[key] = value == "true"
    actual = resolve(selected)
    for command in ("node", "npm", "pnpm", "python3", "uv", "git", "gcc", "supervisord", "tini"):
        assert shutil.which(command), f"缺少基础命令: {command}"
    for option, commands in COMMANDS.items():
        for command in commands:
            assert bool(shutil.which(command)) == actual[option], f"组件开关与命令不一致: {option} / {command}"
    if actual["INSTALL_PYTHON_PACKAGES"]:
        import fastapi  # noqa: F401
        import openai  # noqa: F401
        import sqlalchemy  # noqa: F401
    if actual["INSTALL_WINDOWS"]:
        assert Path("/opt/electron-cache/win32-x64/electron.exe").is_file()
    if actual["PREWARM_GO"]:
        assert any(Path("/home/app/go/pkg/mod/cache/download").rglob("*.mod"))
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
    Path("/usr/local/share/base-custom.json").write_text(
        json.dumps({"selected": selected, "installed": actual}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("可选 Base 镜像组件自检通过")


def self_test():
    baseline = defaults()
    assert set(baseline) == set(COMMANDS) | set(AGENT_COMMANDS) | {"INSTALL_PYTHON_PACKAGES", "PREWARM_GO"}
    off = dict.fromkeys(baseline, False)
    assert not any(resolve(off).values())
    assert all(resolve(dict.fromkeys(baseline, True)).values())
    assert baseline["INSTALL_MEDIA"]
    assert {key for key in AGENT_COMMANDS if baseline[key]} == {"INSTALL_CODEX"}
    for selected in (baseline, off, dict.fromkeys(baseline, True)):
        for publish in (False, True):
            config = bake_config(selected, "ghcr.io/example/dev", "base-custom-demo", "123", "1", publish)
            base, app = config["target"]["base"], config["target"]["custom"]
            assert set(base["args"]) == set(baseline) - set(AGENT_COMMANDS)
            assert set(app["args"]) == set(AGENT_COMMANDS) | {"BASE_IMAGE"}
            assert app["contexts"] == {"custom-base": "target:base"}
            assert app["tags"] == ["ghcr.io/example/dev:custom-demo", "ghcr.io/example/dev:custom-demo-123-1"]
            for key, value in selected.items():
                target = app if key in AGENT_COMMANDS else base
                assert target["args"][key] == str(value).lower()
            assert ("cache-to" in app) == publish
    original = (ROOT / "base/supervisord.conf").read_text(encoding="utf-8")
    for serena in (False, True):
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(service_config(original, serena))
        assert config.has_section("program:serena") == serena
        assert config["program:code-server"]["autostart"] == "true"
        assert config["program:dockerd"]["autostart"] == "false"
    # 明确取消 true 默认值时必须保留 false，不能用 a || default 回退。
    assert parse_inputs({key.lower(): False for key in baseline}, baseline) == off
    for key in baseline:
        result = resolve({**off, key: True})
        assert result[key]
        for option, dependencies in DEPENDENCIES.items():
            if result[option]:
                assert all(result[dependency] for dependency in dependencies)
    assert resolve({**off, "INSTALL_FLUTTER": True})["INSTALL_JAVA"]
    for bad in ("false", 0, None):
        try:
            parse_inputs({"install_go": bad}, baseline)
        except ValueError:
            pass
        else:
            raise AssertionError(f"接受了无效布尔值: {bad!r}")
    for tag in ("base", "desktop", "v2026.10.01", "base-custom/a", "base-custom\nx"):
        try:
            validate_tag(tag)
        except ValueError:
            pass
        else:
            raise AssertionError(f"接受了不安全的标签: {tag}")
    assert validate_tag("base-custom-team1") == "base-custom-team1"
    workflow = (ROOT / ".github/workflows/build-base-custom.yml").read_text(encoding="utf-8")
    inputs = dict(re.findall(r"^      ((?:install_\w+|prewarm_go)):\n        description: [^\n]+\n        type: boolean\n        default: (true|false)$", workflow, re.M))
    assert {key.upper(): value == "true" for key, value in inputs.items()} == baseline, "CI 与 Dockerfile 的开关/默认值不同步"
    assert len(inputs) + 1 <= 25
    print(f"通过：{len(baseline)} 个开关、默认值、取消勾选、依赖补齐、标签隔离")


if __name__ == "__main__":
    {"--prepare": prepare, "--image": check_image, "--agents": check_agents, "--self-test": self_test}[sys.argv[1]]()
