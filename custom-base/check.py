"""可选 Base 的参数解析、依赖检查和镜像自检；仅用 Python 标准库。"""

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


def defaults():
    text = (ROOT / "Dockerfile.base.custom").read_text(encoding="utf-8")
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
    # 推送/PR 只检查默认组合；手动运行才发布，避免覆盖用户已选的组合。
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"image={image}\ntag={tag}\nbuild_args<<CUSTOM_ARGS\n")
        output.writelines(f"{key}={str(value).lower()}\n" for key, value in selected.items())
        output.write("CUSTOM_ARGS\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(f"目标镜像：`{image}:{tag}`（仅手动运行发布）\n\n")
        summary.write("| 组件参数 | 勾选 | 实际安装（含依赖） |\n|---|---|---|\n")
        for key, value in selected.items():
            summary.write(f"| {key} | {'是' if value else '否'} | {'是' if actual[key] else '否'} |\n")


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
    assert set(baseline) == set(COMMANDS) | {"INSTALL_PYTHON_PACKAGES", "PREWARM_GO"}
    off = dict.fromkeys(baseline, False)
    assert not any(resolve(off).values())
    assert all(resolve(dict.fromkeys(baseline, True)).values())
    assert baseline["INSTALL_MEDIA"]
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
    {"--prepare": prepare, "--image": check_image, "--self-test": self_test}[sys.argv[1]]()
