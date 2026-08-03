import { describe, expect, it } from "vitest";
import { parseScheduledTasks, parseTaskRuns } from "../../lib/tasks";

describe("parseScheduledTasks", () => {
  it("parses valid scheduled task objects and filters invalid ones", () => {
    const valid = [
      {
        id: "task-1",
        title: "Reminder",
        kind: "reminder",
        schedule: { timezone: "UTC", run_at: "2027-01-01T00:00:00Z" },
        state: "active",
        enabled: true,
      },
    ];
    expect(parseScheduledTasks(valid)).toHaveLength(1);
    expect(parseScheduledTasks([{ title: "Missing ID" }])).toEqual([]);
    expect(parseScheduledTasks(null)).toEqual([]);
  });
});

describe("parseTaskRuns", () => {
  it("parses valid task run objects", () => {
    const validRuns = [
      {
        id: "run-1",
        run_id: "run-uuid",
        task_id: "task-1",
        scheduled_for: "2027-01-01T00:00:00Z",
        claimed_at: "2027-01-01T00:00:00Z",
        state: "completed",
      },
    ];
    expect(parseTaskRuns(validRuns)).toHaveLength(1);
    expect(parseTaskRuns([{ invalid: true }])).toEqual([]);
  });
});
