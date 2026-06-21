# Remote Runners

Use a remote runner when a case study needs dependency installs, untrusted build
steps, browsers, native tooling, or larger test suites that should not touch the
user's main machine.

## Security Model

Treat the VM as disposable and untrusted after the run. Super Looper's secure
remote-runner plan is designed to prevent credential spillage from the host to
the VM and from setup code into verifier artifacts.

Defaults:

- require an explicit SSH identity file
- disable SSH agent forwarding
- disable password and keyboard-interactive auth
- require strict host-key checking unless explicitly weakened
- refuse root SSH by default
- use a dedicated remote workdir with mode `0700`
- do not mount host home directories, SSH config, cloud credentials, package
  caches, browser profiles, or the Docker socket
- keep verifier network access disabled by default
- copy back only allowlisted report artifacts
- delete the remote workdir by default

Dependency installation is a separate setup phase. `setup=deps` requires an
explicit network setup flag. The verifier run remains offline unless the user
also explicitly allows network during the run.

## Provider-Neutral Shape

The durable abstraction is not "DigitalOcean runner" or "AWS runner"; it is an
ephemeral Linux host reachable over SSH with a dedicated, non-root runner
identity. Provider-specific code should only create or describe that host.
Everything after that should consume a runner profile:

- `remote`: `ssh://runner@host:port`
- `identity_file`: dedicated runner private key
- `remote_workdir`: dedicated mode-0700 parent directory
- `isolation`: `container` or `remote-vm`
- `container_engine`: `podman` by default, `docker` only when accepted
- `known_hosts` / `accept_new_host_key`: explicit host-key policy

`digitalocean` is the friendly first preset because Droplets are simple and
cheap for disposable scans. The same CLI accepts `aws`, `gcp`, `azure`,
`hetzner`, and `custom` presets so future automation can create equivalent
profiles without changing the case-study runner.

## CLI Flow

Create a dedicated local keypair for the disposable runner:

```bash
super-looper runner keygen \
  --name headroom-sandbox \
  --out-dir .super-looper/runners
```

Create a disposable VM in the provider UI or CLI. For DigitalOcean, use a fresh
Ubuntu 24.04 Droplet, allow SSH only from your current IP, and destroy the
Droplet after the run.

Generate an inspectable bootstrap plan:

```bash
super-looper runner bootstrap-plan \
  --provider digitalocean \
  --ip 203.0.113.10 \
  --admin-identity-file ~/.ssh/do_bootstrap_key \
  --runner-public-key .super-looper/runners/headroom-sandbox_ed25519.pub \
  --runner-identity-file .super-looper/runners/headroom-sandbox_ed25519 \
  --profile-out .super-looper/runners/headroom-sandbox.profile.json \
  --out bootstrap-plan.json
```

Review `bootstrap-plan.json`. Its `commands.bootstrap` command uses the admin
key only to install packages, create a non-root runner user, install the runner
public key, and create the private workdir. Its `commands.doctor_as_runner`
checks that the non-root runner can reach Python, Git, and the selected
container engine.

Run those commands only after review. Future automation may execute them, but
the safe default is still plan-first and inspectable.

Use the saved profile for case-study execution planning:

```bash
super-looper runner plan \
  --profile .super-looper/runners/headroom-sandbox.profile.json \
  --case case-studies/headroom-ast-compression \
  --repo https://github.com/chopratejas/headroom \
  --setup deps \
  --allow-network-setup \
  --isolation container \
  --out remote-plan.json
```

The plan is JSON. It contains the normalized target, SSH hardening options,
network policy, artifact allowlist, blocked host paths, and command templates.
It intentionally does not execute SSH yet.

## Automation Ladder

Keep these stages separate:

1. **Profile-only**: user brings any SSH VM; Super Looper writes the runner
   plan. This is implemented.
2. **Bootstrap helper**: Super Looper generates keypairs, bootstrap commands,
   and reusable runner profiles. This is implemented as plan-only CLI.
3. **Provider provisioner**: Super Looper calls `doctl`, `aws`, `gcloud`,
   `az`, `hcloud`, or provider APIs to create and destroy disposable VMs. This
   should use short-lived, provider-scoped credentials and never read broad host
   credential stores implicitly.
4. **Hosted service**: Super Looper owns disposable runners and exposes reports
   as a product. This can reduce user friction, but it changes the trust model:
   the service must isolate tenants, retain minimal artifacts, redact secrets,
   and make repository access explicit.

## Review Rules

Before running a plan:

1. Use a dedicated SSH key for the runner VM, not a personal default key.
2. Pin the VM host key in `known_hosts`; avoid `--accept-new-host-key` except
   for throwaway first-contact experiments.
3. Use an unprivileged remote user. Root requires an explicit override and
   should be limited to disposable VMs.
4. Keep private repo credentials on the disposable VM if needed; do not copy
   host secrets into the run bundle.
5. Prefer rootless Podman over Docker. If Docker is used, treat the VM as more
   privileged and disposable.
6. Preserve the remote workdir only for debugging. The normal path deletes it.
