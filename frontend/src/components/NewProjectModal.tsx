import React, { useMemo, useState } from "react";
import { api } from "../api";
import type { DomainPack, Project } from "../types";
import { Badge, Button, ErrorNote, Field, Modal, Note, Select } from "./ui";
import { IconPlus, IconX } from "./icons";

const MAX_TOPIC = 300;

/**
 * Project creation is a two-field contract:
 *  - topic  : the short research topic that search engines will see (<300 chars)
 *  - brief  : free-text instructions kept as context for the agents only
 * Splitting them is what stops the old bug where the whole brief was sent to
 * OpenAlex and rejected for being longer than 400 characters.
 */
export function NewProjectModal({
  open,
  onClose,
  onCreated,
  domains,
  defaultDomain,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (p: Project) => void;
  domains: DomainPack[];
  defaultDomain: string;
}) {
  const [name, setName] = useState("");
  const [topic, setTopic] = useState("");
  const [domain, setDomain] = useState(defaultDomain || "auto");
  const [instructions, setInstructions] = useState("");
  const [questions, setQuestions] = useState<string[]>([""]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const topicTooLong = topic.trim().length > MAX_TOPIC;
  const topicTooShort = topic.trim().length > 0 && topic.trim().length < 8;
  const valid = topic.trim().length >= 8 && !topicTooLong && name.trim().length > 0;

  const suggestions = useMemo(
    () => domains.filter((d) => d.key !== "generic").slice(0, 6),
    [domains],
  );

  function reset() {
    setName("");
    setTopic("");
    setDomain(defaultDomain || "auto");
    setInstructions("");
    setQuestions([""]);
    setError(null);
  }

  async function submit() {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createProject({
        name: name.trim(),
        topic: topic.trim(),
        domain,
        research_instructions: instructions.trim(),
        research_questions: questions.map((q) => q.trim()).filter(Boolean),
      });
      reset();
      onCreated(created);
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        if (!busy) onClose();
      }}
      title="New research project"
      description="A short topic for the search engines, and an optional brief that only the agents read."
      width="max-w-2xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={busy} disabled={!valid}>
            Create project
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field
          label="Project name"
          required
          hint="A short label for the sidebar. Used nowhere else."
        >
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Precision agriculture — yield prediction"
            maxLength={120}
            autoFocus
          />
        </Field>

        <Field
          label="Research topic"
          required
          counter={`${topic.length}/${MAX_TOPIC}`}
          hint="Sent to OpenAlex / Crossref / arXiv as the search intent. Keep it short and specific."
          error={
            topicTooLong
              ? "Too long — search APIs reject queries over 400 characters. Move the detail into the brief below."
              : topicTooShort
                ? "Add a little more detail (at least 8 characters)."
                : null
          }
        >
          <textarea
            className="textarea min-h-[64px]"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="AI-driven precision agriculture for crop yield prediction"
            rows={2}
          />
        </Field>

        <Field
          label="Domain"
          hint="Controls metrics, baselines, venue hints and manuscript rules used by the agents."
        >
          <Select value={domain} onChange={(e) => setDomain(e.target.value)}>
            <option value="auto">Auto-detect from the topic</option>
            {domains.map((d) => (
              <option key={d.key} value={d.key}>
                {d.label}
              </option>
            ))}
          </Select>
        </Field>

        <div className="flex flex-wrap gap-1">
          {suggestions.slice(0, 4).map((d) => (
            <button
              key={d.key}
              onClick={() => setDomain(d.key)}
              className={`rounded-full border px-2 py-0.5 text-2xs ${
                domain === d.key
                  ? "border-primary-200 bg-primary-50 text-primary-700"
                  : "border-slate-200 text-ink-500 hover:bg-slate-50"
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>

        <Field
          label="Research instructions (optional)"
          hint="Method constraints, population, scope, exclusions. Stored as agent context — never sent as a search query."
          counter={`${instructions.length} chars`}
        >
          <textarea
            className="textarea min-h-[88px]"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="Focus on smallholder farms in South Asia, 2019 onwards. Prefer studies reporting RMSE / R². Exclude remote-sensing-only papers without a yield model."
            rows={3}
          />
        </Field>

        <div>
          <span className="mb-1 flex items-baseline justify-between">
            <span className="text-[13px] font-medium text-ink-700">Research questions (optional)</span>
            <span className="text-2xs text-ink-400">{questions.filter((q) => q.trim()).length} added</span>
          </span>
          <div className="space-y-1.5">
            {questions.map((q, idx) => (
              <div key={idx} className="flex items-center gap-1.5">
                <input
                  className="input"
                  value={q}
                  placeholder={
                    idx === 0
                      ? "Which sensors and models are used for crop yield prediction?"
                      : "Another question…"
                  }
                  onChange={(e) => {
                    const next = [...questions];
                    next[idx] = e.target.value;
                    setQuestions(next);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      setQuestions([...questions, ""]);
                    }
                  }}
                />
                <button
                  className="btn-ghost btn-sm shrink-0"
                  onClick={() => setQuestions(questions.filter((_, i) => i !== idx) || [""])}
                  disabled={questions.length === 1}
                  title="Remove"
                >
                  <IconX size={14} />
                </button>
              </div>
            ))}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="mt-1.5"
            icon={<IconPlus size={13} />}
            onClick={() => setQuestions([...questions, ""])}
          >
            Add question
          </Button>
        </div>

        <Note>
          Every dispatched query is derived from the <strong>topic</strong> plus keywords from your questions, capped at
          400 characters and de-duplicated. The brief stays local context, and the run records exactly which queries were
          sent — check the run panel after starting.
        </Note>
        {domain === "auto" && (
          <p className="text-2xs text-ink-400">
            Auto-detect inspects keywords in the topic: e.g. <Badge tone="neutral">agriculture</Badge> for
            crop/yield/soil topics, <Badge tone="neutral">cybersecurity</Badge> for blockchain/identity,
            <Badge tone="neutral">energy</Badge> for battery/storage.
          </p>
        )}
        {error && <ErrorNote>{error}</ErrorNote>}
      </div>
    </Modal>
  );
}
