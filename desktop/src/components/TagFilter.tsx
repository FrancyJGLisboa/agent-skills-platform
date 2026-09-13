import { useMemo, useState } from "react";

interface Tagged {
  tags: string[];
}

export function useTagFilter<T extends Tagged>(items: T[]) {
  const [tag, setTag] = useState<string | null>(null);
  const filtered = useMemo(() => (tag ? items.filter((i) => i.tags.includes(tag)) : items), [items, tag]);
  return { tag, setTag, filtered };
}

interface Props<T extends Tagged> {
  items: T[];
  tag: string | null;
  setTag: (tag: string | null) => void;
}

export function TagFilter<T extends Tagged>({ items, tag, setTag }: Props<T>) {
  const tags = useMemo(() => Array.from(new Set(items.flatMap((i) => i.tags))).sort(), [items]);
  if (tags.length === 0) return null;
  return (
    <label className="filter">
      Tag
      <select value={tag ?? ""} onChange={(e) => setTag(e.target.value || null)}>
        <option value="">all</option>
        {tags.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>
    </label>
  );
}

const MAX_CHIPS = 5;

/** Up to five tag chips; the rest collapse into a "+N" chip that expands on click. */
export function TagChips({ tags, onPick }: { tags: string[]; onPick: (tag: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? tags : tags.slice(0, MAX_CHIPS);
  const hidden = tags.length - shown.length;
  return (
    <>
      {shown.map((t) => (
        <button key={t} className="tag" onClick={() => onPick(t)}>{t}</button>
      ))}
      {hidden > 0 && (
        <button className="tag more" onClick={() => setExpanded(true)} title={tags.slice(MAX_CHIPS).join(", ")}>
          +{hidden}
        </button>
      )}
    </>
  );
}
