/**
 * Structured logging via pino.
 *
 * Pretty output on TTY, JSON on non-TTY (CI / file capture).
 * One place to configure it; the rest of the code just imports `createLogger`.
 */

import pino, { type Logger } from "pino";

export function createLogger(level: pino.Level = "info"): Logger {
  const isTty = process.stderr.isTTY;
  return pino({
    level,
    ...(isTty
      ? {
          transport: {
            target: "pino-pretty",
            options: { colorize: true, translateTime: "SYS:HH:MM:ss.l" },
          },
        }
      : {}),
  });
}
