import React, { useMemo, useState } from "react";
import { api } from "../api";
import type { TabProps } from "../App";
import type { Paper } from "../types";
import { useAsync } from "../hooks";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Dot,
  EmptyState,
  ErrorNote,
  Select,
  Spinner,
  fmtTime,
} from "./ui";
import { IconChevronDown, IconChevronRight, IconDoc, IconExternal, IconSearch } from "./icons";

const SOURCES = ["openalex", "crossref", "arxiv"];

export function LiteratureTab({ projectId, detail, refreshKey, goTo }: TabProps) {
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [sort, setSort] = useState("rank");
  const [yearFrom, setYearFrom] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const params = useMemo(() => {
    const p: Record<string, string> = { sort };
    if (q.trim()) p.q = q.trim();
    if (source) p.source = source;
    if (yearFrom) p.year_from = yearFrom;
    return p;
  }, [q, source, sort, yearFrom]);

  const { data, loading, error, reload, setData } = useAsync(
    () => api.papers(projectId, params),
    [projectId, JSON.stringify(params), refreshKey],
  );

  const papers: Paper[] = data?.papers ?? [];
  const years = papers.map((p) => p.year).filter((y): y is number => !!y);
  const sourceCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of papers) for (const s of p.sources ?? []) counts[s] = (counts[s] ?? 0) + 1;
    return counts;
  }, [papers]);

  async function toggleSelected(p: Paper) {
    const next = !p.is_selected;
    setData((prev: any) => ({
      ...prev,
      papers: prev.papers.map((x: Paper) => (x.id === p.id ? { ...x, is_selected: next } : x)),
    }));
    try {
      await api.patchPaper(projectId, p.id, { is_selected: next });
    } catch {
      reload();
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Literature corpus"
          description={
            <>
              {data?.count ?? 0} papers retrieved by the discovery swarm
              {years.length > 0 && ` · ${Math.min(...years)}–${Math.max(...years)}`}
              {detail?.paper_count ? ` · ${detail.paper_count} stored in project` : ""}
            </>
          }
          actions={
            <>
              {SOURCES.map((s) => (
                <Badge key={s} tone={sourceCounts[s] ? "ok" : "muted"} title={`${sourceCounts[s] ?? 0} records`}>
                  {s} {sourceCounts[s] ?? 0}
                </Badge>
              ))}
            </>
          }
        />

        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <IconSearch size={14} className="absolute left-2.5 top-2.5 text-ink-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter by title, abstract or DOI"
              className="input pl-8"
            />
          </div>
          <div className="w-[150px]">
            <Select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">All sources</option>
              {SOURCES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-[140px]">
            <Select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="rank">Sort: relevance</option>
              <option value="year">Sort: newest</option>
              <option value="citations">Sort: cited</option>
            </Select>
          </div>
          <div className="w-[110px]">
            <Select value={yearFrom} onChange={(e) => setYearFrom(e.target.value)}>
              <option value="">Any year</option>
              {[2026, 2025, 2024, 2023, 2022, 2021, 2020].map((y) => (
                <option key={y} value={y}>
                  {y}+
                </option>
              ))}
            </Select>
          </div>
          <Button variant="ghost" size="sm" onClick={reload}>
            Refresh
          </Button>
        </div>

        {error && <ErrorNote>{error}</ErrorNote>}
        {loading && !data && <Spinner label="Loading papers…" />}

        {!loading && papers.length === 0 && (
          <EmptyState
            icon={<IconDoc size={22} />}
            title="No papers stored yet"
            description="Run the workflow to let the discovery agent query OpenAlex, Crossref and arXiv. Papers are stored only after a real API response."
            action={
              <Button variant="primary" size="sm" onClick={() => goTo("overview")}>
                Go to run panel
              </Button>
            }
          />
        )}

        {papers.length > 0 && (
          <div className="-mx-4 border-t border-slate-100">
            <table className="table-base">
              <thead>
                <tr>
                  <th className="w-8"></th>
                  <th>Paper</th>
                  <th className="w-20">Year</th>
                  <th className="w-24">Cited</th>
                  <th className="w-32">Sources</th>
                  <th className="w-16 text-right">Rank</th>
                </tr>
              </thead>
              <tbody>
                {papers.map((p) => {
                  const isOpen = open === p.id;
                  return (
                    <React.Fragment key={p.id}>
                      <tr className={p.is_selected ? "bg-primary-50/40" : ""}>
                        <td>
                          <button
                            onClick={() => setOpen(isOpen ? null : p.id)}
                            className="rounded p-0.5 text-ink-400 hover:bg-slate-100"
                            title="Show abstract"
                          >
                            {isOpen ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
                          </button>
                        </td>
                        <td>
                          <div className="flex items-start gap-2">
                            <input
                              type="checkbox"
                              checked={p.is_selected}
                              onChange={() => toggleSelected(p)}
                              className="mt-1 h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-200"
                              title="Mark as core reference"
                            />
                            <div className="min-w-0">
                              <p className="text-[13.5px] font-medium leading-snug text-ink-900">
                                {p.url ? (
                                  <a href={p.url} target="_blank" rel="noreferrer" className="hover:text-primary-700">
                                    {p.title}
                                  </a>
                                ) : (
                                  p.title
                                )}
                              </p>
                              <p className="mt-0.5 truncate text-2xs text-ink-400">
                                {(p.authors ?? [])
                                  .slice(0, 4)
                                  .map((a: any) => a.display_name ?? a.name ?? "")
                                  .filter(Boolean)
                                  .join(", ")}
                                {(p.authors?.length ?? 0) > 4 ? " et al." : ""}
                                {p.venue ? ` · ${p.venue}` : ""}
                              </p>
                              <div className="mt-1 flex flex-wrap items-center gap-1">
                                {p.doi && (
                                  <a
                                    href={p.doi.startsWith("http") ? p.doi : `https://doi.org/${p.doi}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex items-center gap-0.5 text-2xs text-primary-700 hover:underline"
                                  >
                                    DOI <IconExternal size={10} />
                                  </a>
                                )}
                                {p.arxiv_id && <Badge tone="neutral">arXiv:{p.arxiv_id}</Badge>}
                                {p.type && <Badge tone="muted">{p.type}</Badge>}
                                {p.pdf_url && (
                                  <a
                                    href={p.pdf_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-2xs text-primary-700 hover:underline"
                                  >
                                    PDF
                                  </a>
                                )}
                                {!p.abstract && (
                                  <Badge tone="warn" title="Abstract missing in the source record">
                                    no abstract
                                  </Badge>
                                )}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="tabular-nums text-[13px]">{p.year ?? "—"}</td>
                        <td className="tabular-nums text-[13px]">{p.cited_by ?? "—"}</td>
                        <td>
                          <div className="flex flex-wrap gap-1">
                            {(p.sources ?? []).map((s) => (
                              <Badge key={s} tone="info">
                                {s}
                              </Badge>
                            ))}
                          </div>
                        </td>
                        <td
                          className="text-right tabular-nums text-[13px] text-ink-600"
                          title={Object.entries(p.rank_explain ?? {})
                            .map(([k, v]) => `${k}: ${typeof v === "number" ? v.toFixed(3) : v}`)
                            .join("\n")}
                        >
                          {Number(p.rank_score ?? 0).toFixed(2)}
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="bg-slate-50/60">
                          <td></td>
                          <td colSpan={5} className="py-3">
                            <div className="space-y-2">
                              <p className="text-[13px] leading-6 text-ink-600">
                                {p.abstract ?? (
                                  <span className="text-warn-700">
                                    The source record for this paper carries no abstract; nothing was invented to fill
                                    the gap.
                                  </span>
                                )}
                              </p>
                              <div className="flex flex-wrap items-center gap-3 text-2xs text-ink-400">
                                <span>retrieved {fmtTime(p.retrieved_at)}</span>
                                <span className="font-mono">id {p.id.slice(0, 8)}</span>
                                {p.authors?.length > 0 && (
                                  <span className="truncate">
                                    {(p.authors as any[]).map((a) => a.display_name ?? a.name).join("; ")}
                                  </span>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="How ranking works" description="Transparent scoring, computed locally from record metadata." />
        <div className="grid gap-2 text-[12.5px] text-ink-600 sm:grid-cols-2 lg:grid-cols-4">
          {[
["Relevance", "Keyword overlap between the title/abstract and the topic."],
            ["Recency", "Linear decay over publication year, no invented dates."],
            ["Citations", "Log-scaled citation count where the source provides it."],
            ["Source agreement", "Bonus when more than one API returned the same DOI."],
          ].map(([label, text]) => (
            <div key={label} className="rounded-md border border-slate-200 bg-slate-50/60 p-2.5">
              <p className="flex items-center gap-1.5 text-[12.5px] font-medium text-ink-800">
                <Dot tone="primary" /> {label}
              </p>
              <p className="mt-0.5 text-2xs text-ink-500">{text}</p>
            </div>
          ))}
        </div>
        <p className="mt-2 text-2xs text-ink-400">
          Hover a rank value to see its individual components. No score is ever derived from a paper that was not
          actually retrieved.
        </p>
      </Card>
    </div>
  );
}
