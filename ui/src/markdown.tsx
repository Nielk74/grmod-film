// A small Markdown renderer for release notes (GitHub release text): headings, paragraphs, nested
// lists, tables, bold, inline code and links. Everything becomes React text, nothing is inserted as
// HTML. Links open in the browser through `onLink`.
import type { ReactNode } from 'react';

type Link = (href: string) => void;

/** Inline: **bold**, `code`, [text](https://...). */
function inline(text: string, onLink: Link, key = ''): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g;
  let last = 0, m: RegExpExecArray | null, n = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const k = `${key}i${n++}`;
    if (m[2] !== undefined) out.push(<b key={k}>{inline(m[2], onLink, k)}</b>);
    else if (m[3] !== undefined) out.push(<code key={k}>{m[3]}</code>);
    else {
      const href = m[5];
      out.push(<a key={k} href={href} onClick={(e) => { e.preventDefault(); onLink(href); }}>{m[4]}</a>);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

interface Item { text: string; children: Item[] }

/** Lines of a list (indent by spaces) into a tree. */
function listTree(lines: string[]): Item[] {
  const root: Item[] = [];
  const stack: { indent: number; items: Item[] }[] = [{ indent: -1, items: root }];
  for (const line of lines) {
    const m = /^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$/.exec(line);
    if (!m) {
      // A continuation of the previous item.
      const top = stack[stack.length - 1].items;
      if (top.length) top[top.length - 1].text += ' ' + line.trim();
      continue;
    }
    const indent = m[1].replace(/\t/g, '  ').length;
    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) stack.pop();
    const parent = stack[stack.length - 1].items;
    const item: Item = { text: m[2], children: [] };
    parent.push(item);
    stack.push({ indent, items: item.children });
  }
  return root;
}

function list(items: Item[], ordered: boolean, onLink: Link, key: string): ReactNode {
  const body = items.map((it, i) => (
    <li key={`${key}-${i}`}>{inline(it.text, onLink, `${key}-${i}`)}{it.children.length > 0 && list(it.children, false, onLink, `${key}-${i}c`)}</li>
  ));
  return ordered ? <ol key={key}>{body}</ol> : <ul key={key}>{body}</ul>;
}

const cells = (line: string): string[] => line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());

/**
 * Render `text`. `skip` leaves out sections whose heading matches (e.g. checksums), and a first
 * level-1 heading is left out when `dropTitle` is set (the dialog shows the version itself).
 */
export function Markdown({ text, onLink, skip, dropTitle = true }: { text: string; onLink: Link; skip?: RegExp; dropTitle?: boolean }) {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const out: ReactNode[] = [];
  let i = 0, k = 0, skipping = false, first = true;
  while (i < lines.length) {
    const line = lines[i];
    const h = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (h) {
      const level = h[1].length;
      i++;
      if (first && level === 1 && dropTitle) { first = false; continue; }
      first = false;
      skipping = !!skip && skip.test(h[2]);
      if (skipping) continue;
      const key = `h${k++}`;
      out.push(level <= 2 ? <h4 key={key}>{inline(h[2], onLink, key)}</h4> : <h5 key={key}>{inline(h[2], onLink, key)}</h5>);
      continue;
    }
    if (skipping || !line.trim() || /^\s*(---+|\*\*\*+)\s*$/.test(line)) { i++; continue; }
    first = false;
    if (/^\s*(?:[-*+]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]/.test(line);
      const block: string[] = [];
      while (i < lines.length && lines[i].trim() && !/^#{1,6}\s/.test(lines[i])) block.push(lines[i++]);
      out.push(list(listTree(block), ordered, onLink, `l${k++}`));
      continue;
    }
    if (line.trim().startsWith('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(cells(lines[i++]));
      const key = `t${k++}`;
      out.push(
        <table key={key}>
          <thead><tr>{head.map((c, j) => <th key={j}>{inline(c, onLink, `${key}h${j}`)}</th>)}</tr></thead>
          <tbody>{rows.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j}>{inline(c, onLink, `${key}r${ri}c${j}`)}</td>)}</tr>)}</tbody>
        </table>,
      );
      continue;
    }
    if (/^\s*>/.test(line)) {
      const block: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) block.push(lines[i++].replace(/^\s*>\s?/, ''));
      const key = `q${k++}`;
      out.push(<blockquote key={key}>{inline(block.join(' '), onLink, key)}</blockquote>);
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^#{1,6}\s/.test(lines[i]) && !/^\s*(?:[-*+]|\d+[.)])\s+/.test(lines[i]) && !lines[i].trim().startsWith('|')) {
      // Images are left out (the dialog has no room for them); their alt text stays.
      para.push(lines[i++].replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1'));
    }
    if (!para.length) { i++; continue; }
    const key = `p${k++}`;
    out.push(<p key={key}>{inline(para.join(' '), onLink, key)}</p>);
  }
  return <div className="md">{out}</div>;
}
