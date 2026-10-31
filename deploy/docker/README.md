# Python sandbox image

This image is built separately from the broker service and is referenced by
the broker only through an immutable image digest.

## Build requirements

1. Choose a supported Python base image and supply its full
   `repository:tag@sha256:<64-hex>` reference as `PYTHON_BASE_IMAGE`.
2. Build from the repository root so `requirements.txt` is available.
3. Push the resulting image to a registry accessible to the host administrator.
4. Resolve the pushed image's manifest digest and place the exact
   `repository@sha256:<64-hex>` reference in the root-owned broker config.
5. Pull that digest on the broker host before enabling the service. The
   executor never performs an image pull; if the exact digest is absent,
   container creation fails closed.

Example build shape (replace the base image reference with a verified digest):

```sh
docker build \
  --build-arg PYTHON_BASE_IMAGE='python:3.12-slim@sha256:<verified-base-digest>' \
  -f deploy/docker/python-runner.Dockerfile \
  -t registry.example/evo/python-runner:build .
```

Do not place a mutable tag in the broker config. The image is intended to
contain the dependencies required by this repository's regression tests;
it does not install project dependencies or download packages at execution
time. Rebuild and review the image whenever trusted dependency inputs change.

The image's package requirements are currently version-ranged in the main
requirements file, not fully hash-locked. For production, generate and review
a complete platform-specific lock with hashes, then build from that lock
before publishing the image digest. This Dockerfile is a reproducible build
entry point, not yet a supply-chain attestation.
