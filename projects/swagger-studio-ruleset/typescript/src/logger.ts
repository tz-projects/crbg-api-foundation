/**
 * Pino-based logger. Pretty on TTY, JSON elsewhere.
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
