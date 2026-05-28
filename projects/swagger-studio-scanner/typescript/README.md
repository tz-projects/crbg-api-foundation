# swagger-studio-scanner (TypeScript)

Node 20+ implementation. Managed by `pnpm`. Part of the root `pnpm-workspace.yaml`.

## Layout

```
typescript/
├── package.json
├── tsconfig.json + tsconfig.build.json
├── eslint.config.mjs       # ESLint 9 flat config, strict-type-checked
├── .prettierrc
├── vitest.config.ts
├── src/
│   ├── index.ts            # Public exports
│   ├── cli.ts              # Commander commands (`scanner` bin)
│   ├── config.ts           # Settings (zod-validated)
│   ├── logger.ts           # pino wiring
│   ├── models.ts           # Domain types + zod schemas
│   ├── client.ts           # SwaggerHub HTTP client (native fetch + p-limit)
│   └── probe.ts            # Step-zero capability probe
└── tests/
    └── smoke.test.ts
```

## Common commands

```bash
pnpm install              # (post-create runs this for you)
pnpm dev version          # Confirm CLI is wired
pnpm dev probe            # Capability probe (needs .env one level up)

pnpm test                 # Vitest
pnpm lint                 # ESLint (strict-type-checked + stylistic)
pnpm typecheck            # tsc --noEmit
pnpm format               # Prettier write
pnpm build                # Emit dist/
```

## Conventions

- ESM only (`"type": "module"`), `.js` extensions on relative imports (NodeNext-compatible).
- Strict TS: `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `useUnknownInCatchVariables`.
- ESLint flat config, `strictTypeChecked` + `stylisticTypeChecked` profiles.
- Wire validation via `zod` at I/O boundaries — never trust untyped payloads.
- HTTP via native `fetch`; concurrency via `p-limit`. No axios.
- Logging via `pino`; runtime output never uses `console.log` (CLI version banner uses `process.stdout` deliberately).
