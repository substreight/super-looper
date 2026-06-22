#!/usr/bin/env python3
"""Tests for secure remote-runner planning."""

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from super_looper.remote_runner import (  # noqa: E402
    RemoteRunnerError,
    build_bootstrap_plan,
    build_remote_runner_plan,
    build_runner_profile,
    create_runner_key,
    parse_remote,
    validate_runner_user,
    validate_remote_workdir,
)
from super_looper.cli import main as cli_main  # noqa: E402


def test_parse_remote_accepts_ssh_url_and_shorthand():
    target = parse_remote("ssh://runner@203.0.113.10:2222")
    assert target.user == "runner"
    assert target.host == "203.0.113.10"
    assert target.port == 2222

    shorthand = parse_remote("runner@example.com")
    assert shorthand.user == "runner"
    assert shorthand.host == "example.com"
    assert shorthand.port == 22


def test_parse_remote_rejects_root_by_default():
    try:
        parse_remote("ssh://root@203.0.113.10")
    except RemoteRunnerError as exc:
        assert "root" in str(exc)
    else:
        raise AssertionError("root remote user should be rejected")


def test_workdir_must_be_dedicated_subdirectory():
    assert validate_remote_workdir("/tmp/super-looper-runs") == "/tmp/super-looper-runs"
    for bad in ("/", "/tmp", "relative/path", "/home"):
        try:
            validate_remote_workdir(bad)
        except RemoteRunnerError:
            pass
        else:
            raise AssertionError(f"unsafe workdir accepted: {bad}")


def test_runner_user_validation_rejects_shell_sensitive_names():
    assert validate_runner_user("runner") == "runner"
    assert validate_runner_user("runner-ci") == "runner-ci"
    for bad in ("root", "Runner", "runner;touch-x", "../runner", ""):
        try:
            validate_runner_user(bad)
        except RemoteRunnerError:
            pass
        else:
            raise AssertionError(f"unsafe runner user accepted: {bad}")


def test_deps_setup_requires_explicit_network_setup():
    with tempfile.TemporaryDirectory() as root:
        key = os.path.join(root, "runner_key")
        open(key, "w", encoding="utf-8").close()
        try:
            build_remote_runner_plan(
                remote="runner@203.0.113.10",
                identity_file=key,
                case_path=root,
                repo="https://github.com/example/repo",
                setup="deps",
            )
        except RemoteRunnerError as exc:
            assert "allow-network-setup" in str(exc)
        else:
            raise AssertionError("setup=deps should require explicit network setup")


def test_plan_disables_common_credential_spillage_paths():
    with tempfile.TemporaryDirectory() as root:
        key = os.path.join(root, "runner_key")
        open(key, "w", encoding="utf-8").close()
        plan = build_remote_runner_plan(
            remote="ssh://runner@203.0.113.10",
            identity_file=key,
            case_path=root,
            repo="https://github.com/example/repo",
            run_id="demo-run",
        )

    opts = " ".join(plan["security"]["ssh_options"])
    assert "ForwardAgent=no" in opts
    assert "ClearAllForwardings=yes" in opts
    assert "PasswordAuthentication=no" in opts
    assert "KbdInteractiveAuthentication=no" in opts
    assert "StrictHostKeyChecking=yes" in opts
    assert plan["security"]["network"]["verifier_run"] == "disabled"
    assert "~/.ssh" in plan["security"]["blocked_host_paths"]
    assert "docker socket" in plan["security"]["blocked_host_paths"]
    assert plan["remote"]["run_dir"].endswith("/demo-run")
    assert "podman run" in plan["commands"]["run"]
    assert "runner@203.0.113.10:/tmp/super-looper-runs/demo-run/out/artifacts.tgz artifacts.tgz" in plan["commands"]["download_artifacts"]


def test_bootstrap_plan_creates_non_root_runner_profile():
    with tempfile.TemporaryDirectory() as root:
        admin_key = os.path.join(root, "admin_key")
        runner_key = os.path.join(root, "runner_key")
        runner_pub = runner_key + ".pub"
        open(admin_key, "w", encoding="utf-8").close()
        open(runner_key, "w", encoding="utf-8").close()
        with open(runner_pub, "w", encoding="utf-8") as f:
            f.write("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICaseStudyKeyForTestsOnly000000000000000000 test\n")

        plan = build_bootstrap_plan(
            provider="digitalocean",
            ip="203.0.113.10",
            admin_identity_file=admin_key,
            runner_public_key_file=runner_pub,
            runner_identity_file=runner_key,
            name="sandbox1",
            accept_new_host_key=True,
        )

    assert plan["provider"] == "digitalocean"
    assert plan["runner_profile"]["remote"] == "ssh://runner@203.0.113.10:22"
    assert plan["runner_profile"]["identity_file"].endswith("runner_key")
    assert plan["provider_guidance"]["label"] == "DigitalOcean Droplet"
    assert "useradd" in plan["commands"]["bootstrap"]
    assert "ForwardAgent=no" in plan["commands"]["bootstrap"]
    assert "su -" not in plan["commands"]["bootstrap"]
    assert plan["commands"]["doctor_as_runner"].startswith("ssh ")


def test_bootstrap_plan_supports_provider_presets_without_cloud_credentials():
    with tempfile.TemporaryDirectory() as root:
        admin_key = os.path.join(root, "admin_key")
        runner_key = os.path.join(root, "runner_key")
        runner_pub = runner_key + ".pub"
        open(admin_key, "w", encoding="utf-8").close()
        open(runner_key, "w", encoding="utf-8").close()
        with open(runner_pub, "w", encoding="utf-8") as f:
            f.write("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICaseStudyKeyForTestsOnly000000000000000000 test\n")

        plan = build_bootstrap_plan(
            provider="aws",
            ip="203.0.113.11",
            admin_identity_file=admin_key,
            runner_public_key_file=runner_pub,
            runner_identity_file=runner_key,
            name="aws-sandbox",
            admin_user="ubuntu",
        )

    assert plan["provider_guidance"]["label"] == "AWS EC2"
    assert "aws ec2 APIs" in plan["provider_guidance"]["automation_note"]
    assert plan["remote"]["admin"] == "ssh://ubuntu@203.0.113.11:22"


def test_cli_runner_plan_can_use_profile_defaults():
    with tempfile.TemporaryDirectory() as root:
        key = os.path.join(root, "runner_key")
        profile_path = os.path.join(root, "profile.json")
        plan_path = os.path.join(root, "plan.json")
        open(key, "w", encoding="utf-8").close()
        profile = build_runner_profile(
            name="sandbox1",
            remote="ssh://runner@203.0.113.10:2222",
            identity_file=key,
            remote_workdir="/tmp/super-looper-runs",
            provider="custom",
            accept_new_host_key=True,
        )
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f)

        rc = cli_main(
            [
                "runner",
                "plan",
                "--profile",
                profile_path,
                "--case",
                root,
                "--repo",
                "https://github.com/example/repo",
                "--out",
                plan_path,
            ]
        )
        assert rc == 0
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)

    assert plan["remote"]["port"] == 2222
    assert plan["remote"]["user"] == "runner"
    assert plan["security"]["ssh_options"][-1] == "StrictHostKeyChecking=accept-new" or "StrictHostKeyChecking=accept-new" in plan["security"]["ssh_options"]


def test_create_runner_key_writes_dedicated_keypair_when_ssh_keygen_exists():
    if shutil.which("ssh-keygen") is None:
        print("SKIP test_create_runner_key_writes_dedicated_keypair_when_ssh_keygen_exists")
        return
    with tempfile.TemporaryDirectory() as root:
        result = create_runner_key(name="sandbox1", out_dir=root)
        assert os.path.exists(result["identity_file"])
        assert os.path.exists(result["public_key_file"])
        assert result["public_key"].startswith("ssh-ed25519 ")


def test_plan_does_not_assert_unenforced_controls():
    # #12 / #13: the plan must not CLAIM controls it doesn't enforce. In remote-vm mode
    # super-looper enforces no sandbox and no artifact filter -- it must say so.
    with tempfile.TemporaryDirectory() as root:
        key = os.path.join(root, "runner_key")
        open(key, "w", encoding="utf-8").close()
        plan = build_remote_runner_plan(
            remote="ssh://runner@203.0.113.10",
            identity_file=key,
            case_path=root,
            isolation="remote-vm",
            run_id="demo-run",
        )
    sec = plan["security"]
    blob = " ".join(sec.get("credential_spillage_controls", [])).lower()
    assert "network disabled" not in blob, sec
    assert "only artifact allowlist is copied back" not in blob, sec
    assert sec["isolation_enforced"] is False, sec
    assert sec["network"]["enforced"] is False, sec
    advisory = " ".join(sec.get("not_enforced_here", [])).lower()
    assert "not enforced" in advisory and "infrastructure" in advisory, sec
    assert "advisory" in advisory, sec


def test_container_mode_marks_isolation_enforced():
    with tempfile.TemporaryDirectory() as root:
        key = os.path.join(root, "runner_key")
        open(key, "w", encoding="utf-8").close()
        plan = build_remote_runner_plan(
            remote="ssh://runner@203.0.113.10",
            identity_file=key,
            case_path=root,
            isolation="container",
            run_id="demo-run",
        )
    sec = plan["security"]
    assert sec["isolation_enforced"] is True, sec
    assert sec["network"]["enforced"] is True, sec   # --network none unless allow_network_run


def _run_all():
    fns = sorted((n, fn) for n, fn in globals().items() if n.startswith("test_") and callable(fn))
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
