# Installing the privileged sandbox broker

These steps are an operator runbook, not an automated host mutation. Do not
apply them to the GitHub Actions runner account. The broker is the only
application component that receives Docker socket access.

## 1. Dedicated identities

Create a dedicated `evo-broker` service account, a narrowly scoped `evo-app`
group, and a separate `evo-validator-client` group. Add only the Mission
application service account as a supplementary member of `evo-app` and
`evo-validator-client`. The Validator service uses `evo-validator-client` as
its primary group so its socket is reachable by Admin without granting the
Validator access to the Broker socket. Add `evo-broker` to the host's `docker`
group only after the broker code, image and configuration have been reviewed:
Docker socket access is effectively host-administrator privilege. Never add
`evo-runner`, Mission workers, or general-purpose worker accounts to `docker`.

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
service, `docker` group, `evo-broker` user, `evo-app` group and
`evo-validator-client` group. Then, during
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

## 5. Connect the independent Validator and Admin runtime

The Validator must run as a separate service identity with its own Ed25519
private key. Install `deploy/evo-skill-validator.service.example` as
`/etc/systemd/system/evo-skill-validator.service`; it must run as
`evo-validator:evo-validator-client` with `RuntimeDirectoryMode=0750`. The
runtime directory and socket therefore have group `evo-validator-client`,
mode `0750` and `0660` respectively. The systemd unit also provisions a
private `/var/lib/evo-skill-validator` state directory (mode `0700`) for the
durable request ledger; set `replay_store_path` in the Validator config to
`/var/lib/evo-skill-validator/requests.sqlite3`. Do not place this database
under the ephemeral `/run` directory. Add the Mission Admin account to
`evo-validator-client`; do not add it to `evo-broker` merely to reach the
Validator socket. The Validator config and policy must be root-controlled,
and its private signing key must be readable only by `evo-validator` (mode
`0600` or stricter). Its policy file must bind the exact tenant, Skill ID,
version and source SHA-256; a generic policy is not accepted.

Install the Validator public key on the Mission application host as a raw
32-byte Ed25519 key, readable by the Admin service but not writable by it.
Configure the Admin service with all three optional variables:

- `EVO_SKILL_REPLAY_VALIDATOR_SOCKET`: absolute Validator Unix socket path
- `EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY`: absolute path to the pinned public key
- `EVO_SKILL_REPLAY_VALIDATOR_KEY_ID`: the configured Validator key ID

The existing Broker variables remain required to enable Replay. Validator
configuration is optional as a group: without it, Mission can record a signed
Broker Replay but will keep the Skill in Draft and will not publish an Artifact.
A partial Validator configuration prevents Replay runtime startup. When fully
configured, Admin verifies the Validator signature and exact artifact identity,
then submits that attestation to the Broker. The Broker independently verifies
the Validator signature before create-once publication to its Artifact Store.

The Validator configuration's `allowed_uids` must include only the Mission
Admin service UID that is authorized to request validation. This peer-UID check
is still required even though the socket group grants filesystem access. The
Broker configuration's `allowed_uids` must likewise include the Admin service
UID. Do not authorize worker, runner or general-purpose user accounts on either
socket. Keep `evo-validator-client` separate from `evo-app`: the Validator
should not be able to open the Broker socket.

The Admin process never receives the Validator private key or Broker private
key. The Broker process receives only the Validator public key; the Validator
receives only the Broker public key.

## 6. Verify before connecting production Mission



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
