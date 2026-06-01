# Sample APIs for scanner validation

Two deliberately-contrasting OpenAPI 3.0 specs used to seed Swagger Studio with something for the scanner to find:

| File | Intent | Expected scan result |
|---|---|---|
| [`good-petstore.yaml`](./good-petstore.yaml) | Clean spec — operationIds, tags, summaries, descriptions, examples, contact + license, error responses | `pass` (zero findings) |
| [`bad-petstore.yaml`](./bad-petstore.yaml) | Deliberately sloppy — missing operationId, no tag, no summary, no schema on response, no contact/license | `fail` (several findings, including critical ones) |

The push script `push_samples.sh` uses `swaggerhub-cli` (already installed in the devcontainer) to upload both to the org named in `.env`.

## Prerequisite: an active ruleset in Studio

Without an active standardization ruleset, `/standardization` returns empty regardless of how broken a spec is. The ruleset is now its own sub-project — push it from there:

```bash
# Python publisher
cd ../../swagger-studio-ruleset/python
uv run ruleset-publisher publish

# Or the TypeScript publisher
cd ../../swagger-studio-ruleset/typescript
pnpm dev publish
```

See [`projects/swagger-studio-ruleset/README.md`](../../swagger-studio-ruleset/README.md) for full details on the ruleset structure, modularization, and backend selection.

## Push the sample specs

```bash
cd projects/swagger-studio-scanner
set -a; source .env; set +a
bash samples/push_samples.sh
```

The script:

1. Checks both specs exist
2. For each one, calls `swaggerhub api:create` (creates) or `api:update` (overwrites)
3. Marks them as **unpublished** (sample data shouldn't appear as a published API)
4. Sets visibility to private

After pushing, SwaggerHub takes ~10–30 seconds to evaluate standardization. Then run `uv run scanner scan` from the Python scanner sub-project.

## Clean up

```bash
swaggerhub api:delete "$SWAGGERHUB_ORG/scanner-good-petstore"
swaggerhub api:delete "$SWAGGERHUB_ORG/scanner-bad-petstore"
```
