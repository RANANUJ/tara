export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-6 py-12">
      <p className="text-sm font-medium text-slate-600">Development bootstrap</p>
      <h1 className="text-4xl font-semibold tracking-tight text-slate-950">Tara</h1>
      <p className="max-w-prose text-base leading-7 text-slate-700">
        The frontend shell is ready. Product screens and assistant functionality begin in later
        milestones.
      </p>
      <section aria-label="Service status" className="rounded-lg border border-slate-200 p-4">
        <h2 className="font-medium text-slate-950">Status placeholder</h2>
        <p className="mt-1 text-sm text-slate-600">
          Backend health endpoints are available at <code>/api/v1/health/live</code> and{" "}
          <code>/api/v1/health/ready</code>.
        </p>
      </section>
    </main>
  );
}
