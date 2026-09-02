# Workflows

`verify.yml` is the persistent credential-free local CI gate. It runs on pull
requests targeting `main` and pushes to `main`, using the repository's
documented Python 3.12 and Node 22 toolchains. It installs locked frontend
dependencies and runs `scripts/verify.py`, covering backend/frontend lint,
types, tests, build, formatting, recorded Chromium E2E, and the tracked-file
secret scan.

The workflow intentionally does not configure production credentials, call
hosted deployments, run `scripts/verify_hosted.py`, place paper orders, or
mutate a database. Hosted/deployment checks and credentialed paper-cycle
operations are separate release gates and must be run only in their explicitly
authorized environments.

Generated dependencies and credentials do not belong in this directory.
