import React from 'react';

// A deliberately small Markdown subset for model answers: headings, lists,
// paragraphs, **bold**, *italic* and `code`. It builds React elements only, so
// model output can never inject HTML.
function inline(text: string, key: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0, match: RegExpExecArray | null, i = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const token = match[0];
    const k = `${key}-${i++}`;
    if (token.startsWith('**')) parts.push(<strong key={k}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith('`')) parts.push(<code key={k}>{token.slice(1, -1)}</code>);
    else parts.push(<em key={k}>{token.slice(1, -1)}</em>);
    last = match.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function Markdown({text, className}: {text: string; className?: string}) {
  const blocks: React.ReactNode[] = [];
  // The assertion keeps TypeScript from narrowing to null; the flush helpers reassign it.
  let list = null as {ordered: boolean; items: string[]} | null;
  let paragraph: string[] = [];
  const flushParagraph = () => {
    if (paragraph.length) blocks.push(<p key={blocks.length}>{paragraph.flatMap((line, i) => i ? [<br key={`b${i}`}/>, ...inline(line, `p${blocks.length}-${i}`)] : inline(line, `p${blocks.length}-${i}`))}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (!list) return;
    const items = list.items.map((item, i) => <li key={i}>{inline(item, `l${blocks.length}-${i}`)}</li>);
    blocks.push(list.ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>);
    list = null;
  };
  for (const raw of text.replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trimEnd();
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)、]\s+(.*)$/.exec(line);
    if (!line.trim()) { flushParagraph(); flushList(); continue; }
    if (heading) { flushParagraph(); flushList(); blocks.push(<h4 key={blocks.length}>{inline(heading[2], `h${blocks.length}`)}</h4>); continue; }
    if (bullet || numbered) {
      flushParagraph();
      const ordered = !!numbered;
      if (list && list.ordered !== ordered) flushList();
      list = list || {ordered, items: []};
      list.items.push((bullet || numbered)![1]);
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushParagraph(); flushList();
  return <div className={'markdown ' + (className || '')}>{blocks}</div>;
}
