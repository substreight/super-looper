"""Secure remote-runner planning for case-study execution.

This module intentionally plans a remote VM run without executing SSH. The first
security boundary is making credential-spillage decisions explicit and
machine-checkable before any untrusted repository setup code runs.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse


class RemoteRunnerError(RuntimeError):
    """Raised when a remote runner plan would be unsafe or malformed."""


_WORKDIR_RE = re.compile(r"^/[A-Za-z0-9._/\-]+$")
_SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9._:\-\[\]]+$")
_DEFAULT_KEY_NAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
_BANNED_WORKDIRS = {"/", "/tmp", "/var/tmp", "/home", "/root"}
_RUNNER_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_SSH_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
_POSIX_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_PUBLIC_KEY_PREFIXES = ("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-")
_SUPPORTED_PROVIDERS = {"digitalocean", "aws", "gcp", "azure", "hetzner", "custom"}


@dataclass(frozen=True)
class RemoteTarget:
    """Normalized SSH target."""

    user: str
    host: str
    port: int = 22

    @property
    def ssh_destination(self) -> str:
        return f"{self.user}@{self.host}"


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slug(text: str) -> str:
    bits = re.findall(r"[a-z0-9]+", (text or "").lower())
    return "-".join(bits[:6]) or "case-study"


def _q(value: str) -> str:
    return shlex.quote(str(value))


def validate_runner_name(name: str) -> str:
    """Validate a reusable runner/profile name."""
    value = (name or "").strip().lower()
    if not _RUNNER_NAME_RE.match(value):
        raise RemoteRunnerError(
            "runner name must start with a letter and contain only lowercase letters, digits, and hyphens"
        )
    return value


def validate_ssh_user(user: str, *, allow_root: bool = False) -> str:
    """Validate a username used in SSH destinations."""
    value = (user or "").strip()
    if not value or not _SSH_USER_RE.match(value):
        raise RemoteRunnerError("remote user contains unsupported characters")
    if value == "root" and not allow_root:
        raise RemoteRunnerError("refusing root remote user; pass allow_root only for disposable VMs")
    return value


def validate_runner_user(user: str) -> str:
    """Validate a Linux account name that bootstrap may create."""
    value = (user or "").strip()
    if value == "root":
        raise RemoteRunnerError("runner_user must be non-root")
    if not value or not _POSIX_USER_RE.match(value):
        raise RemoteRunnerError(
            "runner_user must be a safe Linux account name using lowercase letters, digits, '_' or '-'"
        )
    return value


def parse_remote(remote: str, allow_root: bool = False) -> RemoteTarget:
    """Parse ssh://user@host[:port] or user@host[:port] into a RemoteTarget."""
    text = (remote or "").strip()
    if not text:
        raise RemoteRunnerError("remote target is required")
    if "://" not in text:
        text = "ssh://" + text
    parsed = urlparse(text)
    if parsed.scheme != "ssh":
        raise RemoteRunnerError("remote target must use ssh://")
    if parsed.path not in ("", "/"):
        raise RemoteRunnerError("remote target must not include a path; use --remote-workdir")
    if not parsed.username:
        raise RemoteRunnerError("remote target must include an explicit unprivileged user")
    user = validate_ssh_user(parsed.username, allow_root=allow_root)
    if not parsed.hostname:
        raise RemoteRunnerError("remote target must include a host")
    host = parsed.hostname
    if not _SAFE_HOST_RE.match(host):
        raise RemoteRunnerError("remote host contains unsupported characters")
    return RemoteTarget(user=user, host=host, port=parsed.port or 22)


def validate_remote_workdir(workdir: str) -> str:
    """Validate a remote workdir is a narrow absolute POSIX path."""
    value = (workdir or "").strip().rstrip("/")
    if not value:
        raise RemoteRunnerError("remote workdir is required")
    if not value.startswith("/"):
        raise RemoteRunnerError("remote workdir must be an absolute POSIX path")
    if not _WORKDIR_RE.match(value):
        raise RemoteRunnerError("remote workdir may contain only POSIX path-safe characters")
    if value in _BANNED_WORKDIRS:
        raise RemoteRunnerError("remote workdir is too broad; choose a dedicated subdirectory")
    parts = [part for part in value.split("/") if part]
    if len(parts) < 2:
        raise RemoteRunnerError("remote workdir must be at least two path components deep")
    return value


def _expand_identity_file(path: str) -> str:
    value = os.path.abspath(os.path.expanduser(path or ""))
    if not value:
        raise RemoteRunnerError("identity file is required; do not rely on ssh-agent for remote runners")
    return value


def _read_public_key(path: str) -> str:
    value = os.path.abspath(os.path.expanduser(path or ""))
    if not value or not os.path.exists(value):
        raise RemoteRunnerError("runner public key file does not exist")
    with open(value, encoding="utf-8") as f:
        key = f.read().strip()
    if "\n" in key or not key.startswith(_PUBLIC_KEY_PREFIXES):
        raise RemoteRunnerError("runner public key must be a single OpenSSH public key")
    return key


def _identity_warnings(path: str) -> List[str]:
    warnings: List[str] = []
    basename = os.path.basename(path)
    if basename in _DEFAULT_KEY_NAMES:
        warnings.append(
            "identity_file appears to be a default personal SSH key; use a dedicated runner key"
        )
    if not os.path.exists(path):
        warnings.append("identity_file does not exist on this host; plan was generated but cannot run yet")
    return warnings


def _host_warnings(host: str, accept_new_host_key: bool) -> List[str]:
    warnings: List[str] = []
    if host in {"localhost", "127.0.0.1", "::1"}:
        warnings.append("remote host is loopback; this does not isolate from the local machine")
    if accept_new_host_key:
        warnings.append(
            "accept_new_host_key weakens first-connect MITM protection; pin the VM host key when possible"
        )
    return warnings


def _ssh_options(
    identity_file: str,
    known_hosts: Optional[str],
    accept_new_host_key: bool,
) -> List[str]:
    host_key_mode = "accept-new" if accept_new_host_key else "yes"
    opts = [
        "-i",
        identity_file,
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "PubkeyAuthentication=yes",
        "-o",
        f"StrictHostKeyChecking={host_key_mode}",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "ControlMaster=no",
    ]
    if known_hosts:
        opts.extend(["-o", f"UserKnownHostsFile={os.path.abspath(os.path.expanduser(known_hosts))}"])
    return opts


def _shell_command(parts: Iterable[str]) -> str:
    return " ".join(_q(part) for part in parts)


def _ssh_command(target: RemoteTarget, options: List[str], remote_command: str) -> str:
    parts = ["ssh", "-p", str(target.port), *options, target.ssh_destination, remote_command]
    return _shell_command(parts)


def _scp_command(target: RemoteTarget, options: List[str], source: str, destination: str) -> str:
    parts = ["scp", "-P", str(target.port), *options, source, f"{target.ssh_destination}:{destination}"]
    return _shell_command(parts)


def _scp_from_remote_command(target: RemoteTarget, options: List[str], source: str, destination: str) -> str:
    parts = ["scp", "-P", str(target.port), *options, f"{target.ssh_destination}:{source}", destination]
    return _shell_command(parts)


def _artifact_allowlist() -> List[str]:
    return [
        "summary.json",
        "manifest.json",
        "loop.json",
        "repo.json",
        "issue.json",
        "autonomy.json",
        "verifier-results.json",
        "scope-check.json",
        "diff.json",
        "diff.patch",
        "verifier-resolution.json",
        "shadow-verifier.json",
        "shadow.patch",
        "report-maintainer.md",
        "report-pr.md",
        "*.stdout.txt",
        "*.stderr.txt",
        "shadow-proposed/**",
    ]


def create_runner_key(
    *,
    name: str,
    out_dir: str,
    force: bool = False,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a dedicated ed25519 SSH keypair for a runner VM."""
    runner_name = validate_runner_name(name)
    target_dir = os.path.abspath(os.path.expanduser(out_dir or ""))
    if not target_dir:
        raise RemoteRunnerError("out_dir is required")
    os.makedirs(target_dir, exist_ok=True)
    identity_file = os.path.join(target_dir, f"{runner_name}_ed25519")
    public_key_file = identity_file + ".pub"
    if not force and (os.path.exists(identity_file) or os.path.exists(public_key_file)):
        raise RemoteRunnerError("runner key already exists; use --force to replace it")
    key_comment = comment or f"super-looper:{runner_name}"
    command = [
        "ssh-keygen",
        "-t",
        "ed25519",
        "-N",
        "",
        "-C",
        key_comment,
        "-f",
        identity_file,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise RemoteRunnerError(f"failed to run ssh-keygen: {exc}") from exc
    if completed.returncode != 0:
        raise RemoteRunnerError(completed.stderr.strip() or "ssh-keygen failed")
    return {
        "name": runner_name,
        "identity_file": identity_file,
        "public_key_file": public_key_file,
        "public_key": _read_public_key(public_key_file),
        "next_step": (
            "Create a disposable VM, then run runner bootstrap-plan with "
            f"--runner-public-key {public_key_file}"
        ),
    }


def build_runner_profile(
    *,
    name: str,
    remote: str,
    identity_file: str,
    remote_workdir: str = "/tmp/super-looper-runs",
    isolation: str = "container",
    container_engine: str = "podman",
    provider: str = "custom",
    accept_new_host_key: bool = False,
    known_hosts: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a reusable runner profile."""
    runner_name = validate_runner_name(name)
    if provider not in _SUPPORTED_PROVIDERS:
        raise RemoteRunnerError("provider must be one of: " + ", ".join(sorted(_SUPPORTED_PROVIDERS)))
    target = parse_remote(remote)
    workdir = validate_remote_workdir(remote_workdir)
    identity = _expand_identity_file(identity_file)
    if isolation not in {"remote-vm", "container"}:
        raise RemoteRunnerError("isolation must be one of: remote-vm, container")
    if container_engine not in {"podman", "docker"}:
        raise RemoteRunnerError("container_engine must be podman or docker")
    return {
        "schema_version": 1,
        "name": runner_name,
        "provider": provider,
        "remote": f"ssh://{target.ssh_destination}:{target.port}",
        "identity_file": identity,
        "remote_workdir": workdir,
        "isolation": isolation,
        "container_engine": container_engine,
        "accept_new_host_key": bool(accept_new_host_key),
        "known_hosts": os.path.abspath(os.path.expanduser(known_hosts)) if known_hosts else "",
    }


def _package_install_command(container_engine: str) -> str:
    packages = "ca-certificates git python3 python3-venv pipx"
    if container_engine == "podman":
        packages += " podman"
    else:
        packages += " docker.io"
    return (
        "if command -v apt-get >/dev/null 2>&1; then "
        "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y "
        f"{packages}; "
        "elif command -v dnf >/dev/null 2>&1; then "
        f"dnf install -y {packages}; "
        "elif command -v yum >/dev/null 2>&1; then "
        f"yum install -y {packages}; "
        "else echo 'unsupported package manager' >&2; exit 1; fi"
    )


def _provider_guidance(provider: str) -> Dict[str, Any]:
    guidance = {
        "digitalocean": {
            "label": "DigitalOcean Droplet",
            "suggested_vm": {
                "image": "ubuntu-24-04-x64",
                "size": "s-2vcpu-4gb",
                "region": "nyc3",
                "firewall": "allow TCP 22 only from your current IP",
            },
            "automation_note": (
                "Future automation can call doctl or the DigitalOcean API, but this plan "
                "does not read cloud credentials or create a Droplet yet."
            ),
        },
        "aws": {
            "label": "AWS EC2",
            "suggested_vm": {
                "image": "Ubuntu 24.04 LTS AMI",
                "size": "t3.medium or larger",
                "firewall": "allow TCP 22 only from your current IP in the security group",
            },
            "automation_note": "Future automation can use aws ec2 APIs with a short-lived scoped profile.",
        },
        "gcp": {
            "label": "Google Compute Engine",
            "suggested_vm": {
                "image": "Ubuntu 24.04 LTS",
                "size": "e2-standard-2 or larger",
                "firewall": "allow TCP 22 only from your current IP",
            },
            "automation_note": "Future automation can use gcloud with an isolated project and short-lived credentials.",
        },
        "azure": {
            "label": "Azure VM",
            "suggested_vm": {
                "image": "Ubuntu Server 24.04 LTS",
                "size": "Standard_B2s or larger",
                "firewall": "allow TCP 22 only from your current IP in the NSG",
            },
            "automation_note": "Future automation can use az vm with a scoped resource group.",
        },
        "hetzner": {
            "label": "Hetzner Cloud Server",
            "suggested_vm": {
                "image": "ubuntu-24.04",
                "size": "cx22 or larger",
                "firewall": "allow TCP 22 only from your current IP",
            },
            "automation_note": "Future automation can use hcloud with a scoped project token.",
        },
        "custom": {
            "label": "Custom Linux VM",
            "suggested_vm": {
                "image": "Ubuntu 24.04, Debian 12, Fedora, or compatible Linux",
                "size": "2 vCPU / 4 GB RAM minimum for medium repositories",
                "firewall": "allow TCP 22 only from your current IP",
            },
            "automation_note": "Bring any disposable Linux host reachable over SSH.",
        },
    }
    return guidance[provider]


def build_bootstrap_plan(
    *,
    provider: str,
    ip: str,
    admin_identity_file: str,
    runner_public_key_file: str,
    runner_identity_file: str,
    name: str = "sandbox1",
    admin_user: str = "root",
    runner_user: str = "runner",
    remote_workdir: str = "/tmp/super-looper-runs",
    container_engine: str = "podman",
    accept_new_host_key: bool = False,
    known_hosts: Optional[str] = None,
) -> Dict[str, Any]:
    """Build an inspectable plan that hardens a fresh VM into a runner."""
    runner_name = validate_runner_name(name)
    if provider not in _SUPPORTED_PROVIDERS:
        raise RemoteRunnerError("provider must be one of: " + ", ".join(sorted(_SUPPORTED_PROVIDERS)))
    admin_user = validate_ssh_user(admin_user, allow_root=True)
    runner_user = validate_runner_user(runner_user)
    if container_engine not in {"podman", "docker"}:
        raise RemoteRunnerError("container_engine must be podman or docker")

    host = (ip or "").strip()
    if not host or not _SAFE_HOST_RE.match(host):
        raise RemoteRunnerError("ip/host contains unsupported characters")
    workdir = validate_remote_workdir(remote_workdir)
    admin_identity = _expand_identity_file(admin_identity_file)
    runner_identity = _expand_identity_file(runner_identity_file)
    public_key = _read_public_key(runner_public_key_file)
    admin_target = parse_remote(f"ssh://{admin_user}@{host}", allow_root=True)
    runner_remote = f"ssh://{runner_user}@{host}:22"
    admin_options = _ssh_options(admin_identity, known_hosts, accept_new_host_key)
    runner_options = _ssh_options(runner_identity, known_hosts, accept_new_host_key)

    install = _package_install_command(container_engine)
    home_ssh = f"/home/{runner_user}/.ssh"
    authorized_keys = f"{home_ssh}/authorized_keys"
    docker_access = f"usermod -aG docker {_q(runner_user)} || true; " if container_engine == "docker" else ""
    harden = (
        "set -eu; "
        f"{install}; "
        f"id -u {_q(runner_user)} >/dev/null 2>&1 || useradd --create-home --shell /bin/bash {_q(runner_user)}; "
        f"install -d -m 700 -o {_q(runner_user)} -g {_q(runner_user)} {_q(home_ssh)}; "
        f"printf '%s\\n' {_q(public_key)} > {_q(authorized_keys)}; "
        f"chown {_q(runner_user)}:{_q(runner_user)} {_q(authorized_keys)}; "
        f"chmod 600 {_q(authorized_keys)}; "
        f"{docker_access}"
        f"install -d -m 700 -o {_q(runner_user)} -g {_q(runner_user)} {_q(workdir)}"
    )
    doctor = "set -eu; whoami; command -v python3; command -v git; command -v " + _q(container_engine)

    profile = build_runner_profile(
        name=runner_name,
        remote=runner_remote,
        identity_file=runner_identity,
        remote_workdir=workdir,
        isolation="container",
        container_engine=container_engine,
        provider=provider,
        accept_new_host_key=accept_new_host_key,
        known_hosts=known_hosts,
    )

    warnings = []
    warnings.extend(_identity_warnings(admin_identity))
    warnings.extend(_identity_warnings(runner_identity))
    warnings.extend(_host_warnings(host, accept_new_host_key))
    if provider == "digitalocean":
        warnings.append(
            "restrict the Droplet firewall to your current IP and destroy the Droplet after the run"
        )
    elif provider != "custom":
        warnings.append(
            f"restrict the {provider} VM firewall to your current IP and destroy the VM after the run"
        )

    return {
        "schema_version": 1,
        "mode": "remote-bootstrap-plan",
        "provider": provider,
        "remote": {
            "admin": f"ssh://{admin_target.ssh_destination}:{admin_target.port}",
            "runner": profile["remote"],
            "workdir": workdir,
        },
        "security": {
            "purpose": "turn a fresh disposable VM into a non-root Super Looper runner",
            "controls": [
                "bootstrap uses admin SSH only to create an unprivileged runner user",
                "runner receives only a dedicated public key",
                "remote workdir is owned by runner and mode 0700",
                "no host secrets are copied",
                "future case-study runs use the non-root runner profile",
            ],
        },
        "commands": {
            "bootstrap": _ssh_command(admin_target, admin_options, harden),
            "doctor_as_runner": _ssh_command(parse_remote(runner_remote), runner_options, doctor),
        },
        "runner_profile": profile,
        "provider_guidance": _provider_guidance(provider),
        "warnings": warnings,
    }


def build_remote_runner_plan(
    *,
    remote: str,
    identity_file: str,
    case_path: str,
    repo: Optional[str] = None,
    remote_workdir: str = "/tmp/super-looper-runs",
    run_id: Optional[str] = None,
    setup: str = "none",
    isolation: str = "container",
    allow_network_setup: bool = False,
    allow_network_run: bool = False,
    accept_new_host_key: bool = False,
    known_hosts: Optional[str] = None,
    allow_root: bool = False,
    keep_remote_workdir: bool = False,
    container_engine: str = "podman",
) -> Dict[str, Any]:
    """Build a hardened remote-runner plan.

    The returned plan is JSON-serializable and does not include secret material.
    It contains command templates and security assertions that a future executor
    can enforce before using SSH.
    """
    target = parse_remote(remote, allow_root=allow_root)
    workdir = validate_remote_workdir(remote_workdir)
    identity = _expand_identity_file(identity_file)
    if setup not in {"none", "deps"}:
        raise RemoteRunnerError("setup must be one of: none, deps")
    if setup == "deps" and not allow_network_setup:
        raise RemoteRunnerError("setup=deps requires --allow-network-setup")
    if isolation not in {"remote-vm", "container"}:
        raise RemoteRunnerError("isolation must be one of: remote-vm, container")
    if container_engine not in {"podman", "docker"}:
        raise RemoteRunnerError("container_engine must be podman or docker")
    if allow_network_run and setup == "none":
        raise RemoteRunnerError("network during verifier run is disabled unless setup=deps is explicit")

    case_abs = os.path.abspath(case_path)
    run_slug = _slug(run_id or os.path.basename(case_abs))
    remote_run_id = run_id or f"{_utc_run_id()}-{run_slug}"
    remote_run_dir = f"{workdir}/{remote_run_id}"
    options = _ssh_options(identity, known_hosts, accept_new_host_key)

    warnings = []
    warnings.extend(_identity_warnings(identity))
    warnings.extend(_host_warnings(target.host, accept_new_host_key))
    if container_engine == "docker":
        warnings.append("docker may run with a privileged daemon; prefer rootless podman on disposable VMs")

    bootstrap = (
        f"umask 077 && mkdir -p {_q(remote_run_dir)} {_q(remote_run_dir + '/in')} "
        f"{_q(remote_run_dir + '/out')} {_q(remote_run_dir + '/repo')} && "
        f"chmod 700 {_q(remote_run_dir)}"
    )
    doctor = (
        "set -eu; "
        "command -v python3; command -v git; "
        f"command -v {_q(container_engine)} >/dev/null 2>&1 || true; "
        "df -Pk . | tail -1"
    )

    repo_step = "repo must be copied or cloned inside the remote run dir"
    if repo:
        repo_step = f"git clone --depth 1 {_q(repo)} {_q(remote_run_dir + '/repo')}"

    runner_invocation = (
        "env -i HOME=/tmp PATH=/usr/local/bin:/usr/bin:/bin "
        f"super-looper case-study run {_q(remote_run_dir + '/in/case')} "
        f"--repo-path {_q(remote_run_dir + '/repo')} "
        f"--run-id {_q(remote_run_id)} --strict"
    )
    if isolation == "container":
        network = "bridge" if allow_network_run else "none"
        runner_invocation = (
            f"{container_engine} run --rm --network {network} --read-only "
            "--tmpfs /tmp:rw,noexec,nosuid,size=512m "
            "--cap-drop all --security-opt no-new-privileges "
            "--memory 4g --cpus 2 --pids-limit 512 "
            f"-v {_q(remote_run_dir + '/repo')}:/workspace/repo:ro "
            f"-v {_q(remote_run_dir + '/in')}:/workspace/in:ro "
            f"-v {_q(remote_run_dir + '/out')}:/out:rw "
            "super-looper-runner:python "
            "env -i HOME=/tmp PATH=/usr/local/bin:/usr/bin:/bin "
            "super-looper case-study run /workspace/in/case "
            "--repo-path /workspace/repo --run-id remote-run --strict"
        )

    cleanup = f"rm -rf {_q(remote_run_dir)}" if not keep_remote_workdir else "preserve remote workdir"

    return {
        "schema_version": 1,
        "mode": "remote-vm-secure-plan",
        "remote": {
            "url": f"ssh://{target.ssh_destination}:{target.port}",
            "user": target.user,
            "host": target.host,
            "port": target.port,
            "workdir": workdir,
            "run_dir": remote_run_dir,
        },
        "inputs": {
            "case_path": case_abs,
            "repo": repo or "",
            "setup": setup,
            "isolation": isolation,
            "container_engine": container_engine if isolation == "container" else "",
        },
        "security": {
            "credential_spillage_controls": [
                "explicit identity file required; no ssh-agent dependency",
                "ForwardAgent=no",
                "ClearAllForwardings=yes",
                "PasswordAuthentication=no",
                "KbdInteractiveAuthentication=no",
                "StrictHostKeyChecking=yes unless explicitly weakened",
                "no host home, ssh, cloud, kube, browser, or package-cache mounts",
                "remote workdir is unique and mode 0700",
                "verifier phase runs with network disabled by default",
                "only artifact allowlist is copied back",
                "remote workdir is deleted by default",
            ],
            "ssh_options": options,
            "network": {
                "setup": "enabled" if allow_network_setup else "disabled",
                "verifier_run": "enabled" if allow_network_run else "disabled",
            },
            "artifact_allowlist": _artifact_allowlist(),
            "blocked_host_paths": [
                "~/.ssh",
                "~/.aws",
                "~/.azure",
                "~/.config/gcloud",
                "~/.kube",
                "~/.docker",
                "~/.npmrc",
                "~/.pypirc",
                "~/.netrc",
                ".env",
                "browser profiles",
                "package caches",
                "docker socket",
            ],
        },
        "commands": {
            "doctor": _ssh_command(target, options, doctor),
            "bootstrap": _ssh_command(target, options, bootstrap),
            "upload_case_bundle": _scp_command(
                target,
                options,
                "case-bundle.tgz",
                f"{remote_run_dir}/in/case-bundle.tgz",
            ),
            "repo_setup": _ssh_command(target, options, repo_step),
            "run": _ssh_command(target, options, runner_invocation),
            "download_artifacts": _scp_from_remote_command(
                target,
                options,
                f"{remote_run_dir}/out/artifacts.tgz",
                "artifacts.tgz",
            ),
            "cleanup": _ssh_command(target, options, cleanup),
        },
        "warnings": warnings,
    }
