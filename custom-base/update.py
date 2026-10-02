"""只更新选中的动态组件；成功发布后保存独立的 custom 配置和版本锁。"""

import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check

SOURCES = {
    "CODE_SERVER_VERSION": (None, "https://api.github.com/repos/coder/code-server/releases/latest", "tag_name"),
    "CODEX_VERSION": ("INSTALL_CODEX", "https://registry.npmjs.org/@openai/codex/latest", "version"),
    "CLAUDE_CODE_VERSION": ("INSTALL_CLAUDE_CODE", "https://registry.npmjs.org/@anthropic-ai/claude-code/latest", "version"),
    "CODEX_SECURITY_VERSION": ("INSTALL_CODEX_SECURITY", "https://registry.npmjs.org/@openai/codex-security/latest", "version"),
    "SERENA_VERSION": ("INSTALL_SERENA", "https://pypi.org/pypi/serena-agent/json", "info.version"),
    "ANTIGRAVITY_VERSION": ("INSTALL_ANTIGRAVITY", "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/linux_amd64.json", "version"),
}


def request_json(url, method="GET", payload=None, missing_ok=False):
    headers = {"User-Agent": "Cloud-Development-custom-update"}
    if url.startswith("https://api.github.com/"):
        headers.update({"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"})
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    for attempt in range(3):
        try:
            with urlopen(Request(url, data=data, headers=headers, method=method), timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            if method != "GET" or error.code < 500 or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if method != "GET" or attempt == 2:
                raise
        time.sleep(attempt + 1)


def normalize_inputs(raw):
    selected = check.parse_inputs(raw, check.defaults())
    return {"image_tag": check.validate_tag(raw.get("image_tag", "base-custom")),
            **{key.lower(): value for key, value in selected.items()}}


def needed_versions(inputs):
    selected = check.parse_inputs(inputs, check.defaults())
    return {key: source for key, source in SOURCES.items() if source[0] is None or selected[source[0]]}


def validate_versions(inputs, versions):
    if not isinstance(versions, dict) or set(versions) != set(needed_versions(inputs)):
        raise ValueError("版本锁必须恰好包含 code-server 和已选 Agent")
    for key, value in versions.items():
        if not isinstance(value, str) or not re.fullmatch(r"[0-9][0-9A-Za-z.+_-]*", value):
            raise ValueError(f"{key} 版本无效: {value!r}")
    return versions


def latest_versions(inputs, fetch=request_json):
    versions = {}
    for key, (_, url, field) in needed_versions(inputs).items():
        value = fetch(url)
        for part in field.split("."):
            value = value[part]
        versions[key] = value.removeprefix("v") if isinstance(value, str) else value
    return validate_versions(inputs, versions)


def release_url(tag):
    return f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/releases/tags/custom-state-{check.validate_tag(tag)}"


def load_state(tag, fetch=request_json):
    release = fetch(release_url(tag), missing_ok=True)
    if release is None:
        return None
    state = json.loads(release["body"])
    if state.get("schema") != 1 or state["inputs"]["image_tag"] != tag:
        raise ValueError("自定义镜像版本记录格式或标签不匹配")
    state["inputs"] = normalize_inputs(state["inputs"])
    return state


def check_updates():
    tag = check.validate_tag(os.environ.get("CUSTOM_IMAGE_TAG") or "base-custom")
    state = load_state(tag)
    inputs = state["inputs"] if state else normalize_inputs({"image_tag": tag})
    versions = latest_versions(inputs)
    changed = state is None or state["versions"] != versions
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"changed={str(changed).lower()}\nimage_tag={tag}\n")
        output.write(f"config_json={json.dumps(inputs)}\nversions_json={json.dumps(versions)}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(f"自定义镜像 `{tag}`：{'需要构建' if changed else '版本未变化，跳过构建'}。\n\n")
        if state is None:
            summary.write("尚无成功版本记录，本次使用默认组件配置。\n\n")
        summary.write("| 已启用组件 | 上次成功版本 | 上游版本 |\n|---|---|---|\n")
        for key, version in versions.items():
            previous = state["versions"].get(key, "未记录") if state else "未记录"
            summary.write(f"| {key} | {previous} | {version} |\n")
    print(f"{tag}: {'更新所选组件' if changed else '没有更新'}")


def prepare():
    raw = json.loads(os.environ.get("REUSABLE_INPUTS_JSON") or os.environ.get("INPUTS_JSON", "{}")) or {}
    inputs = normalize_inputs(raw)
    publish = os.environ["GITHUB_EVENT_NAME"] == "workflow_dispatch" or bool(os.environ.get("REUSABLE_INPUTS_JSON"))
    versions = {}
    if publish:
        supplied = os.environ.get("VERSIONS_JSON")
        if os.environ.get("REUSABLE_INPUTS_JSON"):
            # 等待同标签构建期间，用户可能已经手动发布了新选择。
            current = load_state(inputs["image_tag"])
            if current and current["inputs"] != inputs:
                inputs = current["inputs"]
                os.environ["REUSABLE_INPUTS_JSON"] = json.dumps(inputs)
                supplied = None
        versions = validate_versions(inputs, json.loads(supplied)) if supplied else latest_versions(inputs)
    os.environ["RESOLVED_VERSIONS_JSON"] = json.dumps(versions)
    check.prepare()
    state = {"schema": 1, "inputs": inputs, "versions": versions, "source_sha": os.environ["GITHUB_SHA"]}
    (Path(os.environ["RUNNER_TEMP"]) / "custom-state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def published_state(state, metadata):
    validate_versions(state["inputs"], state["versions"])
    digests = {target: metadata[target]["containerimage.digest"] for target in ("base", "custom")}
    if any(not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value) for value in digests.values()):
        raise ValueError("基础层和应用层必须都成功产出镜像摘要，才能写入版本记录")
    return {**state, "digests": digests}


def record():
    folder = Path(os.environ["RUNNER_TEMP"])
    state = published_state(json.loads((folder / "custom-state.json").read_text()),
                            json.loads((folder / "custom-metadata.json").read_text()))
    tag = state["inputs"]["image_tag"]
    current = request_json(release_url(tag), missing_ok=True)
    payload = {"name": f"Custom build state: {tag}", "body": json.dumps(state, indent=2),
               "prerelease": True, "make_latest": "false"}
    api = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/releases"
    if current:
        request_json(f"{api}/{current['id']}", "PATCH", payload)
    else:
        # 状态标签使用默认分支；实际构建 SHA 单独保存在 body。
        request_json(api, "POST", {**payload, "tag_name": f"custom-state-{tag}"})
    print(f"已保存 {tag} 的成功版本与勾选配置")


if __name__ == "__main__":
    {"--check": check_updates, "--prepare": prepare, "--record": record}[sys.argv[1]]()
