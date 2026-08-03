import { describe, expect, it } from "vitest";
import { parseBackups } from "../../lib/admin";

describe("parseBackups", () => {
  it("parses valid backup metadata objects and rejects invalid items", () => {
    const valid = [
      {
        backup_id: "backup_20260803_120000_12345678",
        archive_path: "/data/backups/backup_1.tar.gz",
        created_at: "2026-08-03T12:00:00Z",
        size_bytes: 4096,
        integrity_status: "ok",
        has_chroma: false,
      },
    ];
    expect(parseBackups(valid)).toHaveLength(1);
    expect(parseBackups([{ invalid: "item" }])).toEqual([]);
    expect(parseBackups(null)).toEqual([]);
  });
});
