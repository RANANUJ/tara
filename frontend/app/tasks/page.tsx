"use client";

import { useEffect, useState } from "react";
import { parseScheduledTasks, parseTaskRuns, ScheduledTask, ScheduledTaskRun } from "../../lib/tasks";

export default function TasksPage() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [message, setMessage] = useState("Loading scheduled tasks…");
  const [selectedTaskRuns, setSelectedTaskRuns] = useState<{ taskId: string; runs: ScheduledTaskRun[] } | null>(null);

  // Form states
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [instruction, setInstruction] = useState("");
  const [capabilityId, setCapabilityId] = useState("filesystem.list");
  const [target, setTarget] = useState(".");
  const [runAt, setRunAt] = useState(() => new Date(Date.now() + 86400000).toISOString().slice(0, 16));
  const [formError, setFormError] = useState<string | null>(null);

  const fetchTasks = () => {
    const controller = new AbortController();
    fetch("/api/v1/tasks", { signal: controller.signal })
      .then(async (res) => (res.ok ? res.json() : Promise.reject()))
      .then((data: unknown) => {
        setTasks(parseScheduledTasks(data));
        setMessage("Scheduled Tasks");
      })
      .catch(() => setMessage("Sign in to view scheduled tasks."));
    return () => controller.abort();
  };

  useEffect(() => {
    return fetchTasks();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    try {
      const res = await fetch("/api/v1/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          instruction,
          capability_id: capabilityId,
          target,
          parameters: {},
          schedule: {
            timezone: "UTC",
            run_at: new Date(runAt).toISOString(),
          },
          idempotency_key: `create-${Date.now()}`,
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData?.error?.message || "Failed to create task");
      }
      setShowCreate(false);
      setTitle("");
      setInstruction("");
      fetchTasks();
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "Error creating task");
    }
  };

  const handleAction = async (taskId: string, action: string, body?: unknown) => {
    try {
      const res = await fetch(`/api/v1/tasks/${taskId}/${action}`, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (res.ok) {
        fetchTasks();
      }
    } catch {
      // Ignored
    }
  };

  const handleDelete = async (taskId: string) => {
    try {
      const res = await fetch(`/api/v1/tasks/${taskId}`, { method: "DELETE" });
      if (res.ok) {
        fetchTasks();
      }
    } catch {
      // Ignored
    }
  };

  const handleViewRuns = async (taskId: string) => {
    try {
      const res = await fetch(`/api/v1/tasks/${taskId}/runs`);
      if (res.ok) {
        const data = await res.json();
        setSelectedTaskRuns({ taskId, runs: parseTaskRuns(data) });
      }
    } catch {
      // Ignored
    }
  };

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-slate-600">Automation</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">Scheduled Tasks</h1>
          <p className="mt-2 text-slate-700">{message}</p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="inline-flex items-center justify-center rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white shadow hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-950"
        >
          {showCreate ? "Cancel" : "New Task"}
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4 sm:p-6">
          <h2 className="text-lg font-semibold text-slate-950">Create Scheduled Task</h2>
          {formError && <p className="mt-2 text-sm text-red-600" role="alert">{formError}</p>}
          <div className="mt-4 space-y-4">
            <div>
              <label htmlFor="title" className="block text-sm font-medium text-slate-700">Title</label>
              <input
                id="title"
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-slate-950 focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor="instruction" className="block text-sm font-medium text-slate-700">Instruction</label>
              <input
                id="instruction"
                type="text"
                required
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-slate-950 focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor="capability" className="block text-sm font-medium text-slate-700">Capability ID</label>
              <input
                id="capability"
                type="text"
                required
                value={capabilityId}
                onChange={(e) => setCapabilityId(e.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-slate-950 focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor="target" className="block text-sm font-medium text-slate-700">Target</label>
              <input
                id="target"
                type="text"
                required
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-slate-950 focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor="runAt" className="block text-sm font-medium text-slate-700">Run At</label>
              <input
                id="runAt"
                type="datetime-local"
                required
                value={runAt}
                onChange={(e) => setRunAt(e.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-slate-950 focus:outline-none"
              />
            </div>
          </div>
          <div className="mt-6 flex justify-end gap-3">
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-800"
            >
              Save Task
            </button>
          </div>
        </form>
      )}

      <ul className="mt-8 space-y-4" aria-live="polite">
        {tasks.map((task) => (
          <li key={task.id} className="rounded-lg border border-slate-200 bg-white p-4 sm:p-5 shadow-sm">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-semibold text-slate-950">{task.title}</h3>
                <p className="mt-1 text-sm text-slate-600">
                  {task.target_summary || "Configured target"} · Schedule: {task.schedule.run_at}
                </p>
              </div>
              <span className={`inline-self-start rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                task.state === "active" ? "bg-emerald-100 text-emerald-800" :
                task.state === "pending_confirmation" ? "bg-amber-100 text-amber-800" :
                task.state === "paused" ? "bg-slate-100 text-slate-800" : "bg-red-100 text-red-800"
              }`}>
                {task.state}
              </span>
            </div>

            {task.state === "pending_confirmation" && (
              <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3">
                <p className="text-sm font-medium text-amber-900">Confirmation required for consequential action.</p>
                <button
                  onClick={() => handleAction(task.id, "approve", { response: "yes" })}
                  className="mt-2 rounded bg-amber-900 px-3 py-1 text-xs font-medium text-white shadow-sm hover:bg-amber-800"
                >
                  Approve Confirmation
                </button>
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-2 pt-2 border-t border-slate-100">
              {task.state === "active" && (
                <button
                  onClick={() => handleAction(task.id, "pause")}
                  className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Pause
                </button>
              )}
              {task.state === "paused" && (
                <button
                  onClick={() => handleAction(task.id, "resume")}
                  className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Resume
                </button>
              )}
              {task.state !== "canceled" && (
                <button
                  onClick={() => handleAction(task.id, "cancel")}
                  className="rounded border border-red-200 bg-white px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                >
                  Cancel
                </button>
              )}
              <button
                onClick={() => handleViewRuns(task.id)}
                className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                Run History
              </button>
              <button
                onClick={() => handleDelete(task.id)}
                className="rounded border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>

      {selectedTaskRuns && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-950">Task Run History</h3>
            <ul className="mt-4 max-h-60 overflow-y-auto divide-y divide-slate-100">
              {selectedTaskRuns.runs.length === 0 ? (
                <p className="text-sm text-slate-500 py-2">No execution runs recorded yet.</p>
              ) : (
                selectedTaskRuns.runs.map((run) => (
                  <li key={run.id} className="py-2 text-sm">
                    <p className="font-medium text-slate-900">State: {run.state} · Outcome: {run.outcome_code || run.error_code || "none"}</p>
                    <p className="text-xs text-slate-500">Claimed: {run.claimed_at}</p>
                  </li>
                ))
              )}
            </ul>
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setSelectedTaskRuns(null)}
                className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-800"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
