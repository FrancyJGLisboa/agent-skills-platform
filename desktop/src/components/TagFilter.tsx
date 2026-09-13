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
