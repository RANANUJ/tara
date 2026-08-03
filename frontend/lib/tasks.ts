export type TaskState =
  | "draft"
  | "pending_confirmation"
  | "active"
  | "paused"
  | "canceled"
  | "completed"
  | "failed"
  | "disabled";

export interface ScheduledTaskSchedule {
  timezone: string;
  run_at: string;
  interval_minutes?: number | null;
  occurrence_limit?: number | null;
}

export interface ScheduledTask {
  id: string;
  title: string;
  kind: string;
  schedule: ScheduledTaskSchedule;
  state: TaskState;
  enabled: boolean;
  capability_id?: string | null;
  target_summary?: string | null;
  risk_level?: string | null;
  confirmation_id?: string | null;
  confirmation_status?: string | null;
  confirmation_expires_at?: string | null;
}

export interface ScheduledTaskRun {
  id: string;
  run_id: string;
  task_id: string;
  scheduled_for: string;
  claimed_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  state: string;
  outcome_code?: string | null;
  error_code?: string | null;
}

export function parseScheduledTasks(value: unknown): ScheduledTask[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is ScheduledTask =>
      typeof item === "object" &&
      item !== null &&
      typeof (item as Record<string, unknown>).id === "string" &&
      typeof (item as Record<string, unknown>).title === "string" &&
      typeof (item as Record<string, unknown>).state === "string",
  );
}

export function parseTaskRuns(value: unknown): ScheduledTaskRun[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is ScheduledTaskRun =>
      typeof item === "object" &&
      item !== null &&
      typeof (item as Record<string, unknown>).id === "string" &&
      typeof (item as Record<string, unknown>).task_id === "string",
  );
}
