export interface BackupItem {
  backup_id: string;
  archive_path: string;
  created_at: string;
  size_bytes: number;
  alembic_version?: string | null;
  integrity_status: string;
  has_chroma: boolean;
}

export interface DiagnosticsReport {
  diagnostics_timestamp: string;
  application_name: string;
  application_version: string;
  build_revision?: string | null;
  system_info: {
    python_version: string;
    platform: string;
    environment: string;
    log_level: string;
    host: string;
    port: number;
    database_driver: string;
    database_encryption_enabled: boolean;
    task_payload_encryption_enabled: boolean;
    service_secret_configured: boolean;
  };
  database_status: {
    available: boolean;
    integrity_ok: boolean;
    alembic_version?: string | null;
  };
  scheduler_status: Record<string, unknown>;
  capabilities: Array<Record<string, unknown>>;
  features: Record<string, boolean>;
  redaction_verified: boolean;
}

export function parseBackups(value: unknown): BackupItem[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is BackupItem =>
      typeof item === "object" &&
      item !== null &&
      typeof (item as Record<string, unknown>).backup_id === "string",
  );
}
