"use client";

import { useEffect, useState } from "react";
import { BackupItem, DiagnosticsReport, parseBackups } from "../../lib/admin";

export default function AdminPage() {
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsReport | null>(null);
  const [message, setMessage] = useState("Loading deployment status…");
  const [actionStatus, setActionStatus] = useState<string | null>(null);

  const fetchBackupsAndDiagnostics = () => {
    const controller = new AbortController();
    fetch("/api/v1/admin/backups", { signal: controller.signal })
      .then(async (res) => (res.ok ? res.json() : []))
      .then((data: unknown) => setBackups(parseBackups(data)))
      .catch(() => {});

    fetch("/api/v1/admin/diagnostics", { signal: controller.signal })
      .then(async (res) => (res.ok ? res.json() : null))
      .then((data: DiagnosticsReport | null) => {
        setDiagnostics(data);
        setMessage("Deployment Status");
      })
      .catch(() => setMessage("Sign in to view administrative deployment status."));

    return () => controller.abort();
  };

  useEffect(() => {
    return fetchBackupsAndDiagnostics();
  }, []);

  const handleCreateBackup = async () => {
    setActionStatus("Creating backup…");
    try {
      const res = await fetch("/api/v1/admin/backups", { method: "POST" });
      if (res.ok) {
        setActionStatus("Backup created successfully.");
        fetchBackupsAndDiagnostics();
      } else {
        setActionStatus("Failed to create backup.");
      }
    } catch {
      setActionStatus("Error creating backup.");
    }
  };

  const handleRestore = async (backupId: string) => {
    if (!confirm(`Are you sure you want to restore backup ${backupId}?`)) return;
    setActionStatus(`Restoring backup ${backupId}…`);
    try {
      const res = await fetch("/api/v1/admin/backups/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backup_id: backupId }),
      });
      if (res.ok) {
        setActionStatus(`Backup ${backupId} restored successfully.`);
        fetchBackupsAndDiagnostics();
      } else {
        setActionStatus("Failed to restore backup.");
      }
    } catch {
      setActionStatus("Error restoring backup.");
    }
  };

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-slate-600">Administration</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">Deployment & Recovery</h1>
          <p className="mt-2 text-slate-700">{message}</p>
        </div>
        <button
          onClick={handleCreateBackup}
          className="inline-flex items-center justify-center rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white shadow hover:bg-slate-800"
        >
          Create Backup
        </button>
      </div>

      {actionStatus && (
        <div className="mt-4 rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900" role="status">
          {actionStatus}
        </div>
      )}

      {diagnostics && (
        <section className="mt-8 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-950">System Diagnostics</h2>
          <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-md bg-slate-50 p-3">
              <dt className="text-xs font-medium text-slate-500">Environment</dt>
              <dd className="mt-1 text-sm font-semibold text-slate-900">{diagnostics.system_info.environment}</dd>
            </div>
            <div className="rounded-md bg-slate-50 p-3">
              <dt className="text-xs font-medium text-slate-500">Database Integrity</dt>
              <dd className="mt-1 text-sm font-semibold text-slate-900">
                {diagnostics.database_status.integrity_ok ? "OK" : "Error"} (Rev: {diagnostics.database_status.alembic_version || "N/A"})
              </dd>
            </div>
            <div className="rounded-md bg-slate-50 p-3">
              <dt className="text-xs font-medium text-slate-500">SQLCipher Encryption</dt>
              <dd className="mt-1 text-sm font-semibold text-slate-900">
                {diagnostics.system_info.database_encryption_enabled ? "Enabled" : "Disabled"}
              </dd>
            </div>
            <div className="rounded-md bg-slate-50 p-3">
              <dt className="text-xs font-medium text-slate-500">Task Payload Encryption</dt>
              <dd className="mt-1 text-sm font-semibold text-slate-900">
                {diagnostics.system_info.task_payload_encryption_enabled ? "Enabled" : "Disabled"}
              </dd>
            </div>
            <div className="rounded-md bg-slate-50 p-3">
              <dt className="text-xs font-medium text-slate-500">Redaction Verified</dt>
              <dd className="mt-1 text-sm font-semibold text-slate-900">
                {diagnostics.redaction_verified ? "Verified" : "Unverified"}
              </dd>
            </div>
          </dl>
        </section>
      )}

      <section className="mt-8">
        <h2 className="text-xl font-semibold text-slate-950">Database Backups</h2>
        <ul className="mt-4 space-y-4">
          {backups.length === 0 ? (
            <p className="text-sm text-slate-500">No backup bundles available yet.</p>
          ) : (
            backups.map((b) => (
              <li key={b.backup_id} className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between shadow-sm">
                <div>
                  <h3 className="font-semibold text-slate-950">{b.backup_id}</h3>
                  <p className="text-xs text-slate-600">
                    Created: {b.created_at} · Size: {(b.size_bytes / 1024).toFixed(1)} KB · Revision: {b.alembic_version || "N/A"}
                  </p>
                </div>
                <button
                  onClick={() => handleRestore(b.backup_id)}
                  className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50"
                >
                  Restore
                </button>
              </li>
            ))
          )}
        </ul>
      </section>
    </main>
  );
}
