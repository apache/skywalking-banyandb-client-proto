# BanyanDB Client Proto Definitions

<img src="http://skywalking.apache.org/assets/logo.svg" alt="Sky Walking logo" height="90px" align="right" />

This repo contains the **BanyanDB public client Protocol Buffer / gRPC definitions**, plus a small toolchain to:

- **Sync** protos from the upstream BanyanDB repo (`apache/skywalking-banyandb`)
- **Normalize and merge** upstream protos into a stable client-facing layout under `proto/banyandb/v1/`
- **Generate + compile Java** from the synced protos to verify the sync is valid (also enforced in CI)

## Upstream source of truth

Protos are synced from the Apache SkyWalking BanyanDB repository:

- **Repo**: `apache/skywalking-banyandb`
- **Path**: `api/proto/banyandb/<module>/v1/*.proto`

Locally, this repo maintains a consolidated, client-friendly layout:

- `proto/banyandb/v1/banyandb-common.proto`
- `proto/banyandb/v1/banyandb-database.proto`
- `proto/banyandb/v1/banyandb-measure.proto`
- `proto/banyandb/v1/banyandb-model.proto`
- `proto/banyandb/v1/banyandb-property.proto`
- `proto/banyandb/v1/banyandb-stream.proto`
- `proto/banyandb/v1/banyandb-trace.proto`

These files are produced by `scripts/sync_proto.py`, which also rewrites imports to match the merged layout.

## Prerequisites

- **Python**: 3.x (for `scripts/sync_proto.py`)
- **Java**: JDK 17 (for compilation verification)
- **Maven**: use `./mvnw` (recommended) or a system `mvn`

If you use `./mvnw` and hit a permission error, run:

```bash
chmod +x mvnw
```

## Sync protos

### Preview changes (dry-run)

```bash
make sync-proto-dry-run
```

Or directly (with extra options):

```bash
python3 scripts/sync_proto.py --branch main --dry-run
```

### Apply changes

Interactive (asks for confirmation):

```bash
make sync-proto
```

Non-interactive (useful in automation):

```bash
python3 scripts/sync_proto.py --branch main --force
```

### Sync only specific module(s)

```bash
python3 scripts/sync_proto.py --branch main --module common --module measure --force
```

Valid modules are: `common`, `database`, `measure`, `model`, `property`, `stream`, `trace`.

### Sync via GitHub Actions (opens a PR)

Run the workflow “Sync Proto Files” (`.github/workflows/sync-proto.yml`) with an optional `branch` input (defaults to `main`).

## Verify the sync (generate + compile)

The fastest correctness check after syncing is to **generate Java from the protos and compile**:

```bash
make compile
```

This runs `mvn clean compile` (preferring `./mvnw` if present), which:

- Generates Java sources from `proto/**/*.proto` into `target/generated-sources/`
- Compiles them into `target/classes/`

This is also what CI runs in “Verify Proto Files” (`.github/workflows/verify-proto.yml`).

## Clean

```bash
make clean
```

## Project structure

```
.
├── proto/
│   └── banyandb/
│       └── v1/                 # Consolidated (synced) proto files
├── scripts/
│   └── sync_proto.py           # Sync + merge tool (pulls from upstream GitHub)
├── pom.xml                     # Java compile verification (protoc + javac via Maven)
├── mvnw                        # Maven wrapper (preferred)
├── Makefile                    # Convenience targets
└── README.md
```

## Code of conduct
This project adheres to the Contributor Covenant [code of conduct](https://www.apache.org/foundation/policies/conduct). By participating, you are expected to uphold this code.
Please follow the [REPORTING GUIDELINES](https://www.apache.org/foundation/policies/conduct#reporting-guidelines) to report unacceptable behavior.

## Contact Us
* Mail list: **dev@skywalking.apache.org**. Mail to `dev-subscribe@skywalking.apache.org`, follow the reply to subscribe the mail list.
* Send `Request to join SkyWalking slack` mail to the mail list(`dev@skywalking.apache.org`), we will invite you in.
* Twitter, [ASFSkyWalking](https://twitter.com/ASFSkyWalking)
* QQ Group: 901167865(Recommended), 392443393
* [bilibili B站 视频](https://space.bilibili.com/390683219)

## License
[Apache 2.0 License.](LICENSE)
