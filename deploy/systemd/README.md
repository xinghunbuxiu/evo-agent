# Installing the privileged sandbox broker

These steps are an operator runbook, not an automated host mutation. Do not
apply them to the GitHub Actions runner account. The broker is the only
application component that receives Docker socket access.

## 1. Dedicated identities

Create a dedicated `evo-broker` service account and a narrowly scoped
`evo-app` group. Add only the Mission application service account to
`evo-app`. Add `evo-broker` to the host's `docker` group only after the
broker code, image and configuration have been reviewed: Docker socket access
is effectively host-administrator privilege. Never add `evo-runner`,
Mission workers, or general-purpose worker accounts to `docker`.

Record the numeric UID of the Mission application account. Put only that UID
in `allowed_uids` in the root-owned broker configuration.

## 2. Install code and dependencies

Install the reviewed repository under `/opt/evo-agent`, create a dedicated
virtual environment at `/opt/evo-agent-broker/venv`, and install both runtime
and broker dependencies:

```sh
python3 -m venv /opt/evo-agent-broker/venv
/opt/evo-agent-broker/venv/bin/pip install -r /opt/evo-agent/requirements.txt
/opt/evo-agent-broker/venv/bin/pip install -r /opt/evo-agent/requirements-broker.txt
```

The broker virtual environment must be writable only by the deployment
administrator. The daemon imports the reviewed source from `/opt/evo-agent/src`.

## 3. Prepare signing key and configuration

Create `/etc/evo-sandbox-broker` with owner `root:evo-broker` and mode
`0750`. Generate a dedicated Ed25519 private key and install it as
`/etc/evo-sandbox-broker/signing-key.pem`, owned by
`evo-broker:evo-broker`, mode `0400`. Do not reuse the workspace-local HMAC
key or expose this private key to the Mission application.

Install `sandbox-broker.config.example.json` as
`/etc/evo-sandbox-broker/config.json`, replace every example value, then set
owner `root:evo-broker` and mode `0640`. Each workspace path must be an
absolute canonical directory, not a symlink. The replay database must be
inside the systemd-managed state directory. The image field must contain the
exact immutable digest produced by the separately reviewed image build.

The broker application receives only the Ed25519 public key, pinned by key ID.
The private key stays readable only by the dedicated broker service account.

## 4. Install systemd units

Copy the two unit files from `deploy/systemd/` into
`/etc/systemd/system/`. Confirm that the host has the expected `docker`
service, `docker` group, `evo-broker` user and `evo-app` group. Then, during
a maintenance window:

```sh
systemctl daemon-reload
systemctl enable --now evo-sandbox-broker.socket
systemctl status evo-sandbox-broker.socket
```

The service is socket-activated. Do not enable the service independently
without the socket unit. Verify that `/run/evo-sandbox-broker/broker.sock`
is a Unix stream socket owned by `evo-broker:evo-app`, mode `0660`, and that
the parent directory is not writable by application users.

## 5. Verify before connecting Mission

Review the service logs, inspect the running process identity and confirm that
only the dedicated broker account has Docker socket access. Confirm the
configured image digest exists locally before the first request. Exercise the
broker with a harmless test workspace and verify the Ed25519 response from the
application side.

Do not connect this broker to production Mission completion or strategy
feedback until the host-level isolation settings, image provenance, socket
permissions, signing-key ownership and actual container behavior have all been
independently checked. A passing fake-client unit test does not prove Docker
daemon behavior or host isolation.
