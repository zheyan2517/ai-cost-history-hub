# Server packaging status

The current `v0.2.0` release does not publish a server binary, Docker image,
installer, or remote deployment recipe. The supported workflow is the local
desktop viewer and the Python dashboard described in the repository root
[README](../../README.md).

The optional Rust `webui-server` feature remains source code for development
and testing. It is not a released distribution channel. Do not expose local
session data on a network until authentication, deployment artifacts, and
end-to-end release checks are provided.
