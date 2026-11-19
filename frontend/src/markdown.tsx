import React from "react";

/** Minimal, dependency-free Markdown renderer for generated drafts and reports. */

function inline(text: string, key: string): React.ReactNode {
  const nodes: React.ReactNode[] = [];
  let rest = text;
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[P\d+\])/;
  let i = 0;
  while (rest.length) {
    const m = rest.match(pattern);
    if (!m || m.index === undefined) {
      nodes.push(rest);
      break;
    }
    if (m.index > 0) nodes.push(rest.slice(0, m.index));
    const token = m[0];
    const k = `${key}-${i++}`;
    if (token.startsWith("**")) {
      nodes.push(<strong key={k}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code key={k}>{token.slice(1, -1)}</code>);
    } else if (/^\[P\d+\]$/.test(token)) {
      nodes.push(
        <sup key={k} className="mx-0.5 rounded bg-blue-50 px-1 text-[10px] font-semibold text-blue-700">
          {token.slice(1, -1)}
        </sup>,
      );
    } else {
      nodes.push(<em key={k}>{token.slice(1, -1)}</em>);
    }
    rest = rest.slice(m.index + token.length);
  }
  return nodes;
}

export function Markdown({ text, className = "" }: { text: string; className?: string }) {
  const lines = (text || "").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (line.startsWith("```")) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i++;
      blocks.push(
        <pre key={key++} className="my-3 overflow-x-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
          {code.join("\n")}
        </pre>,
      );
      continue;
    }
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i].split("|").slice(1, -1).map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i++;
      }
      blocks.push(
        <table key={key++}>
          <thead>
            <tr>
              {rows[0]?.map((c, ci) => (
                <th key={ci}>{inline(c, `h${ci}`)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(1).map((r, ri) => (
              <tr key={ri}>
                {r.map((c, ci) => (
                  <td key={ci}>{inline(c, `c${ri}${ci}`)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>,
      );
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      const content = inline(heading[2], `h${key}`);
      const Tag = (level === 1 ? "h1" : level === 2 ? "h2" : level === 3 ? "h3" : "h4") as any;
      blocks.push(<Tag key={key++}>{content}</Tag>);
      i++;
      continue;
    }
    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(<blockquote key={key++}>{inline(quote.join(" "), `q${key}`)}</blockquote>);
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      blocks.push(
        <ul key={key++}>
          {items.map((it, ii) => (
            <li key={ii}>{inline(it, `li${ii}`)}</li>
          ))}
        </ul>,
      );
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+\.\s+/, ""));
      blocks.push(
        <ol key={key++} className="list-decimal">
          {items.map((it, ii) => (
            <li key={ii} className="ml-5 my-1">
              {inline(it, `oli${ii}`)}
            </li>
          ))}
        </ol>,
      );
      continue;
    }
    if (/^---+$/.test(line.trim())) {
      blocks.push(<hr key={key++} className="my-4 border-slate-200" />);
      i++;
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,4}\s|\||>|\s*[-*]\s|\s*\d+\.\s|```|---+$)/.test(lines[i])
    ) {
      para.push(lines[i++]);
    }
    blocks.push(<p key={key++}>{inline(para.join(" "), `p${key}`)}</p>);
  }

  return <div className={`prose-draft ${className}`}>{blocks}</div>;
}
