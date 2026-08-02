"use client";

import { useEffect, useState } from "react";

import { Capability, parseCapabilities } from "../../lib/actions";

export default function ActionsPage() {
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [message, setMessage] = useState("Loading server capability status…");

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/v1/actions", { signal: controller.signal })
      .then(async (response) => response.ok ? response.json() : Promise.reject())
      .then((response: unknown) => {
        setCapabilities(parseCapabilities(response));
        setMessage("Server capability status");
      })
      .catch(() => setMessage("Sign in to view current server capability status."));
    return () => controller.abort();
  }, []);

  return (
    <main className="mx-auto min-h-screen max-w-2xl px-6 py-12">
      <p className="text-sm font-medium text-slate-600">Actions</p>
      <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950">Available capabilities</h1>
      <p className="mt-3 text-slate-700">{message}</p>
      <ul className="mt-8 space-y-3" aria-live="polite">
        {capabilities.map((capability) => <li key={capability.name} className="rounded-lg border border-slate-200 p-4"><p className="font-medium">{capability.label}</p><p className="mt-1 text-sm text-slate-600">{capability.summary}</p><p className="mt-2 text-sm font-medium">{capability.state}{capability.read_only ? " · read-only" : ""}</p></li>)}
      </ul>
    </main>
  );
}
