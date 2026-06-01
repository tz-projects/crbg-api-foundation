# swagger-studio-ruleset-publisher (TypeScript)

Node 20+ implementation. Mirrors the Python publisher's surface.

## Layout

```
typescript/
├── package.json
├── tsconfig.json + tsconfig.build.json
├── eslint.config.mjs
├── .prettierrc
├── vitest.config.ts
├── src/
│   ├── index.ts                # Public exports
│   ├── cli.ts                  # Commander commands (`ruleset-publisher` bin)
│   ├── config.ts               # Settings (zod-validated, shared .env)
│   ├── logger.ts               # pino
│   ├── packager.ts             # validate + zip the ruleset dir
│   └── publishers/
│       ├── base.ts             # Publisher interface + types
│       ├── cliPublisher.ts     # Backend: swaggerhub spectral:upload
│       └── restPublisher.ts    # Backend: REST PUT
└── tests/
    └── packager.test.ts
```

## Common commands

```bash
pnpm install

# CLI backend (default)
pnpm dev publish

# REST backend
pnpm dev publish --backend rest

# Point at a different ruleset directory
pnpm dev publish --ruleset /path/to/other/ruleset

# Sanity
pnpm dev version
pnpm test
pnpm lint
pnpm typecheck
```

## Backend selection

`Publisher` interface in `publishers/base.ts` defines a single async surface; the CLI picks `CliPublisher` or `RestPublisher` based on `--backend`. Add a third backend by implementing the interface and registering it in `cli.ts`.

## REST endpoint

Same as the Python publisher: `PUT /standardization/spectral-rulesets/{owner}/{rulesetName}/zip`, `Content-Type: application/zip`, raw zip body. Mirrors swaggerhub-cli's `saveSpectralRuleset`. Verified against a real trial org.
