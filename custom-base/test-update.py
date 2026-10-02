"""离线验证版本筛选、成功记录和自动更新的配置保留。"""

import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check
import update

inputs = update.normalize_inputs({})
all_inputs = update.normalize_inputs({key.lower(): True for key in check.defaults()})
payloads = {url: ({"info": {"version": "1.2.3"}} if field == "info.version" else {field: "1.2.3"})
            for _, url, field in update.SOURCES.values()}
requested = []


def fetch(url):
    requested.append(url)
    return payloads[url]


versions = update.latest_versions(inputs, fetch)
assert set(versions) == {"CODE_SERVER_VERSION", "CODEX_VERSION"}
assert len(requested) == 2  # 不请求未勾选 Agent 的上游。
assert len(update.latest_versions(all_inputs, fetch)) == 6
assert set(update.latest_versions({**inputs, "install_codex": False}, fetch)) == {"CODE_SERVER_VERSION"}
for bad in ({}, {**versions, "CLAUDE_CODE_VERSION": "1.2.3"}, {**versions, "CODEX_VERSION": "latest"},
            {**versions, "CODEX_VERSION": "1.0\nINJECT=true"}):
    try:
        update.validate_versions(inputs, bad)
    except ValueError:
        pass
    else:
        raise AssertionError("接受了无效版本锁")

state = {"schema": 1, "inputs": inputs, "versions": versions, "source_sha": "example"}
metadata = {target: {"containerimage.digest": "sha256:" + "a" * 64} for target in ("base", "custom")}
assert len(update.published_state(state, metadata)["digests"]) == 2
for bad in ({}, {"base": metadata["base"]}, {**metadata, "custom": {"containerimage.digest": ""}}):
    try:
        update.published_state(state, bad)
    except (KeyError, ValueError):
        pass
    else:
        raise AssertionError("未成功生成两个镜像也允许记录版本")

with tempfile.TemporaryDirectory(prefix="custom-update-test-") as folder:
    env = {"GH_TOKEN": "unused-test-token", "GITHUB_REPOSITORY": "example/dev",
           "RUNNER_TEMP": folder, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
           "GITHUB_SHA": "example", "GITHUB_EVENT_NAME": "schedule", "CUSTOM_IMAGE_TAG": "base-custom",
           "GITHUB_OUTPUT": str(Path(folder) / "output"), "GITHUB_STEP_SUMMARY": str(Path(folder) / "summary")}
    with patch.dict(os.environ, env):
        for previous, expected in ((None, True), (state, False),
                                   ({**state, "versions": {**versions, "CODEX_VERSION": "1.2.2"}}, True)):
            Path(env["GITHUB_OUTPUT"]).write_text("")
            with patch.object(update, "load_state", return_value=previous), patch.object(update, "latest_versions", return_value=versions):
                update.check_updates()
            output = Path(env["GITHUB_OUTPUT"]).read_text()
            assert f"changed={str(expected).lower()}" in output
            assert '"install_claude_code": false' in output

        # 检查排队后执行时，会重新读取最新成功选择，避免覆盖用户中途的手动配置。
        current_inputs = {**inputs, "install_codex": False, "install_serena": True}
        current_versions = {"CODE_SERVER_VERSION": "1.2.3", "SERENA_VERSION": "1.2.3"}
        os.environ["REUSABLE_INPUTS_JSON"] = json.dumps(inputs)
        os.environ["VERSIONS_JSON"] = json.dumps(versions)
        with patch.object(update, "load_state", return_value={**state, "inputs": current_inputs}), \
                patch.object(update, "latest_versions", return_value=current_versions) as latest:
            update.prepare()
            latest.assert_called_once_with(current_inputs)
        bake = json.loads((Path(folder) / "custom-bake.json").read_text())
        args = bake["target"]["custom"]["args"]
        assert args["INSTALL_CODEX"] == "false" and args["INSTALL_SERENA"] == "true"
        assert args["SERENA_VERSION"] == "1.2.3" and "CODEX_VERSION" not in args
        assert "publish=true" in Path(env["GITHUB_OUTPUT"]).read_text()

        (Path(folder) / "custom-metadata.json").write_text(json.dumps(metadata))
        with patch.object(update, "request_json", side_effect=[None, {"id": 1}]) as api:
            update.record()
        payload = api.call_args.args[2]
        assert payload["prerelease"] and payload["make_latest"] == "false"
        saved = json.loads(payload["body"])
        assert saved["inputs"] == current_inputs and saved["versions"] == current_versions

        # PR 只验证构建，不解析线上版本，不发布。
        os.environ["GITHUB_EVENT_NAME"] = "pull_request"
        os.environ["REUSABLE_INPUTS_JSON"] = ""
        os.environ["INPUTS_JSON"] = "{}"
        Path(env["GITHUB_OUTPUT"]).write_text("")
        with patch.object(update, "latest_versions", side_effect=AssertionError("PR 不应查询上游")):
            update.prepare()
        assert "publish=false" in Path(env["GITHUB_OUTPUT"]).read_text()

print("Custom update: selected versions, unchanged skip, publish gate, saved choices and PR checks passed")
