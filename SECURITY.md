# Security policy

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Report it privately with GitHub's private vulnerability reporting: open the **Security** tab of this
repository and choose **Report a vulnerability**. Include what you found, how to reproduce it, and what you
think the impact is. Do not include real identity documents; use a synthetic image.

You can expect an acknowledgement within a few days. This is a small project run by one maintainer, so
fixes are made as fast as is realistic, and you will be told when one is released.

## Supported versions

Only the latest release receives security fixes. The project is at an early stage (0.x).

## What is in scope

- The HTTP API and its authentication (`X-API-Key`).
- Handling of uploaded images: size limits, decoding, memory use.
- Anything that could make the service store, log or leak uploaded images or the extracted values.
- The Docker image.

## What to keep in mind when deploying

- The service listens on `127.0.0.1` by default. It is meant to be called by your own backend, not directly
  by browsers. Put it behind your own network controls.
- Set `ID_ATLAS_API_KEY` if the service is reachable by anything you do not fully trust.
- Images and extracted values are processed in memory and are not written to disk or logged by the service.
- There is no liveness check, face matching or forgery detection. A result is a hint for a human reviewer,
  not proof that a document is genuine.
