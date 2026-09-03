# Manticora

![Python](https://img.shields.io/badge/python-3.13%2B-blue?logo=python&logoColor=white)
![Build](https://img.shields.io/github/actions/workflow/status/wlix13/Manticora/ci-tests.yaml?label=build&logo=github)
![Lint](https://img.shields.io/github/actions/workflow/status/wlix13/Manticora/ci-code-quality.yaml?label=lint&logo=github)
![Release](https://img.shields.io/github/v/release/wlix13/Manticora?logo=github)
![License](https://img.shields.io/badge/license-MIT-green)
![uv](https://img.shields.io/badge/package%20manager-uv-blueviolet?logo=astral)
![Ruff](https://img.shields.io/badge/linter-ruff-orange?logo=ruff)

GitOps DNS manager: a CLI on top of [octodns](https://github.com/octodns/octodns) for zone repositories (`config.yaml` plus `zones/*.yaml`) deployed to Cloudflare.
It validates, plans and deploys from CI, and edits records in zone files in place so nobody has to hand-edit YAML.

## Install

```bash
uv tool install "git+https://github.com/wlix13/Manticora.git@v1.0.0"
```

## Usage

Run inside a zone repository (the directory holding `config.yaml`, or any directory below it).

```bash
manticora validate                                   # config and every zone through octodns
manticora plan --base-ref main                       # changes for zones touched since a git ref
manticora plan -z example.com. --format discord      # explicit zones, Discord-ready diff block
manticora deploy --dry-run                           # plan, no apply
manticora deploy --force                             # apply without the confirmation prompt

manticora records add www.example.com A 1.2.3.4 --ttl 300 --proxied
manticora records add example.com MX "10 mx.example.com."
manticora records remove www.example.com A           # one type, or every record of the name without it
```

`validate`, `plan` and `deploy` need `CLOUDFLARE_API_TOKEN` in the environment.
The `records` commands only touch zone files and need no token.
`-q` is quiet mode (octodns warnings off), `-v` enables debug logging.

## Development

```bash
uv sync --all-groups
uv run poe check   # format, lint, types, import contracts, dependency hygiene
uv run poe tests
```

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for the commit and pull request conventions.

## License

[MIT](LICENSE)
