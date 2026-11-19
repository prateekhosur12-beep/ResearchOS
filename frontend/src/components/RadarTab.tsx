import React, { useState } from "react";
import { api } from "../api";
import type { TabProps } from "../App";
import type { RadarPayload } from "../types";
import { useAsync } from "../hooks";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorNote, Note, Spinner, StatusPill } from "./ui";
import { IconExternal, IconRadar } from "./icons";

type Kind = "journals" | "funding" | "collaborators";

export function RadarTab({ projectId, refreshKey, goTo }: TabProps) {
  const { data, loading, error, reload } = useAsync(() => api.radar(projectId), [projectId, refreshKey]);
  const [kind, setKind] = useState<Kind>("journals");

  const payload: RadarPayload | null = data && (data.journals || data.funding || data.collaborators) ? data : null;

  if (loading && !data) return <Spinner label="Loading venue and funding scan…" />;
  if (error) return <ErrorNote title="Could not load the radar">{error}</ErrorNote>;

  if (!payload) {
    return (
      <EmptyState
        icon={<IconRadar size={22} />}
        title="No venue or funding scan yet"
        description="The radar stage resolves venues against the Crossref journal registry and reads funder metadata from the papers that were actually retrieved. No impact factors or deadlines are invented."
        action={
          <Button variant="primary" size="sm" onClick={() => goTo("overview")}>
            Run the workflow
          </Button>
        }
      />
    );
  }

  const counts: Record<Kind, number> = {
    journals: payload.journals?.length ?? 0,
    funding: payload.funding?.length ?? 0,
    collaborators: payload.collaborators?.length ?? 0,
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex gap-1 rounded-lg bg-slate-100 p-0.5">
          {(
            [
              ["journals", "Venues"],
              ["funding", "Funding"],
              ["collaborators", "Collaborators"],
            ] as [Kind, string][]
          ).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={`rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors ${
                kind === k ? "bg-white text-ink-900 shadow-card" : "text-ink-500 hover:text-ink-700"
              }`}
            >
              {label} <span className="text-2xs text-ink-400">{counts[k]}</span>
            </button>
          ))}
        </div>
        <Button variant="ghost" size="sm" onClick={reload}>
          Refresh
        </Button>
      </div>

      <Note tone="neutral">{payload.disclaimers?.[kind === "journals" ? "venues" : kind] ?? ""}</Note>

      {kind === "journals" && (
        <Card padded={false}>
          <div className="px-4 pb-2 pt-4">
            <CardHeader
              title="Candidate venues"
              description="Matched against real Crossref journal records; impact factor and acceptance rate are not claimed."
            />
          </div>
          <div className="border-t border-slate-100">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Venue</th>
                  <th className="w-28">Verification</th>
                  <th className="w-40">Publisher</th>
                  <th className="w-28">ISSN</th>
                  <th className="w-20 text-right">In corpus</th>
                  <th className="w-16">Source</th>
                </tr>
              </thead>
              <tbody>
                {payload.journals.map((j) => (
                  <tr key={j.name}>
                    <td>
                      <p className="text-[13px] font-medium text-ink-900">{j.name}</p>
                      {j.venue_in_literature && j.venue_in_literature !== j.name && (
                        <p className="text-2xs text-ink-400">in corpus as “{j.venue_in_literature}”</p>
                      )}
                      {j.note && <p className="text-2xs text-ink-400">{j.note}</p>}
                    </td>
                    <td>
                      <StatusPill status={j.verification === "verified" ? "verified" : j.verification} />
                    </td>
                    <td className="text-[12.5px] text-ink-600">{j.publisher ?? "—"}</td>
                    <td className="font-mono text-2xs text-ink-500">{j.issn ?? "—"}</td>
                    <td className="text-right tabular-nums text-[13px]">{j.papers_in_corpus ?? 0}</td>
                    <td className="text-2xs">
                      {j.source_url ? (
                        <a
                          href={j.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-0.5 text-primary-700 hover:underline"
                        >
                          open <IconExternal size={10} />
                        </a>
                      ) : (
                        <span className="text-ink-300">—</span>
                      )}
                    </td>
                  </tr>
                ))}
                {payload.journals.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-[13px] text-ink-400">
                      No venues were resolved for this corpus.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {kind === "funding" && (
        <div className="grid gap-3 sm:grid-cols-2">
          {payload.funding.map((f) => (
            <Card key={f.name}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="truncate text-[14px] font-semibold text-ink-900">{f.name}</h3>
                  {f.funder && f.funder !== f.name && <p className="text-2xs text-ink-400">{f.funder}</p>}
                </div>
                {(f as any).verification && <Badge tone="ok">{(f as any).verification}</Badge>}
              </div>
              {f.award_ids?.length ? (
                <p className="mt-1.5 flex flex-wrap gap-1">
                  {f.award_ids.slice(0, 4).map((a) => (
                    <Badge key={a} tone="neutral">
                      {a}
                    </Badge>
                  ))}
                </p>
              ) : null}
              {f.papers?.length ? (
                <div className="mt-2">
                  <p className="section-title mb-1">Seen on</p>
                  <ul className="space-y-0.5 text-2xs text-ink-600">
                    {f.papers.slice(0, 3).map((p, i) => (
                      <li key={i} className="truncate" title={p.title}>
                        · {p.title}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </Card>
          ))}
          {payload.funding.length === 0 && (
            <Card className="sm:col-span-2">
              <Note>
                No funder metadata was present on the retrieved records. Nothing was guessed: OpenAlex and Crossref
                simply did not report grants for this corpus.
              </Note>
            </Card>
          )}
        </div>
      )}

      {kind === "collaborators" && (
        <div className="grid gap-3 sm:grid-cols-2">
          {payload.collaborators.map((c) => (
            <Card key={c.name}>
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-[14px] font-semibold text-ink-900">{c.name}</h3>
                <Badge tone="info">{Math.round((c.similarity ?? 0) * 100)}% overlap</Badge>
              </div>
              <p className="mt-0.5 text-2xs text-ink-400">
                {c.papers_in_corpus} paper(s) in this corpus
              </p>
              <p className="mt-1 text-[12.5px] text-ink-600">{c.evidence_note}</p>
              {c.papers?.length ? (
                <ul className="mt-1.5 space-y-0.5 text-2xs text-ink-500">
                  {c.papers.slice(0, 3).map((p, i) => (
                    <li key={i} className="truncate" title={p.title}>
                      · {p.title}
                    </li>
                  ))}
                </ul>
              ) : null}
            </Card>
          ))}
          {payload.collaborators.length === 0 && (
            <Card className="sm:col-span-2">
              <Note>
                No collaborators are suggested because no author appeared on more than one retrieved paper. Similarity is
                computed from the corpus, never from a contact database.
              </Note>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
