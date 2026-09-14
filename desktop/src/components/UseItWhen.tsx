// "Use it when…" — what discovery.json says about when a skill fires, plus the
// verification evidence VERIFICATION.md recorded. Both files are optional; the
// block renders only what exists.
import { useEffect, useState } from "react";
import { CheckCircle2, CircleHelp, ShieldAlert, Sparkles, XCircle } from "lucide-react";
import { skillFile } from "../lib/cli";
import { Pill } from "./ui";

interface Discovery {
  question?: string;
  trigger?: string[];
  decision?: string[];
  success_measure?: string;
  routing_tests?: { should_trigger?: string[]; should_not_trigger?: string[] };
  risk?: { tier?: string; mutation_boundary?: string };
}

interface Verification {
  clean: boolean;
  version?: string;
  generated?: string;
  evals?: string;
}

const STATE_RE = /<!--\s*agent-skill-verification:\s*(\{[\s\S]*?\})\s*-->/;

function parseVerification(md: string): Verification | null {
  const m = md.match(STATE_RE);
  if (!m) return null;
  try {
    const state = JSON.parse(m[1]) as { clean?: boolean; version?: string };
    return {
      clean: !!state.clean,
      version: state.version,
      generated: md.match(/^Generated:\s*(.+)$/m)?.[1]?.slice(0, 10),
      evals: md.match(/Eval rollout:\s*(.+)$/m)?.[1],
    };
  } catch {
    return null;
  }
}

export function UseItWhen({ dir }: { dir: string }) {
  const [discovery, setDiscovery] = useState<Discovery | null>(null);
  const [verification, setVerification] = useState<Verification | null>(null);

  useEffect(() => {
    setDiscovery(null);
    setVerification(null);
    skillFile(dir, "discovery.json").then((t) => setDiscovery(JSON.parse(t) as Discovery)).catch(() => setDiscovery(null));
    skillFile(dir, "VERIFICATION.md").then((t) => setVerification(parseVerification(t))).catch(() => setVerification(null));
  }, [dir]);

  if (!discovery && !verification) return null;
  const yes = discovery?.routing_tests?.should_trigger ?? [];
  const no = discovery?.routing_tests?.should_not_trigger ?? [];

  return (
    <section className="mb-5 rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-[13px] font-semibold"><Sparkles size={14} className="text-accent" /> Use it when…</h3>
        <span className="ml-auto flex flex-wrap items-center gap-1.5">
          {verification && (
            <Pill tone={verification.clean ? "ok" : "err"} title={verification.evals ? `Evals: ${verification.evals}` : undefined}>
              {verification.clean ? <CheckCircle2 size={11} className="mr-1 inline" /> : <XCircle size={11} className="mr-1 inline" />}
              {verification.clean ? "verified" : "verification failed"}{verification.generated ? ` · ${verification.generated}` : ""}
            </Pill>
          )}
          {discovery?.risk?.tier && <Pill tone={discovery.risk.tier === "low" ? "neutral" : "warn"} title={discovery.risk.mutation_boundary ? `Mutation boundary: ${discovery.risk.mutation_boundary}` : undefined}><ShieldAlert size={11} className="mr-1 inline" />{discovery.risk.tier} risk{discovery.risk.mutation_boundary === "read-only" ? " · read-only" : ""}</Pill>}
        </span>
      </div>

      {discovery?.question && (
        <p className="mt-2 flex gap-2 text-ink"><CircleHelp size={14} className="mt-0.5 shrink-0 text-ink-3" /><span>It answers: <strong>{discovery.question}</strong></span></p>
      )}

      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        {yes.length > 0 && (
          <div>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-ok">Ask things like</p>
            <ul className="space-y-1">
              {yes.map((t) => <li key={t} className="rounded-md bg-ok-bg/50 px-2 py-1 text-[12px] text-ink">“{t}”</li>)}
            </ul>
          </div>
        )}
        {no.length > 0 && (
          <div>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-ink-3">Not for</p>
            <ul className="space-y-1">
              {no.map((t) => <li key={t} className="rounded-md bg-surface-2 px-2 py-1 text-[12px] text-ink-2">“{t}”</li>)}
            </ul>
          </div>
        )}
      </div>

      {(discovery?.trigger?.length || discovery?.decision?.length || discovery?.success_measure) && (
        <dl className="mt-3 grid gap-x-4 gap-y-1 text-[12px] sm:grid-cols-[auto_1fr]">
          {discovery?.trigger?.length ? <><dt className="text-ink-3">Starts when</dt><dd className="text-ink-2">{discovery.trigger.join("; ")}</dd></> : null}
          {discovery?.decision?.length ? <><dt className="text-ink-3">Helps you decide</dt><dd className="text-ink-2">{discovery.decision.join(" · ")}</dd></> : null}
          {discovery?.success_measure ? <><dt className="text-ink-3">Done when</dt><dd className="text-ink-2">{discovery.success_measure}</dd></> : null}
        </dl>
      )}
    </section>
  );
}
