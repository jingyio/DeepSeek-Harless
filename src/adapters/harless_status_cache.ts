/** Coalesce read-only UI status checks. Never use this cache for admission. */
export function createStatusCache<T>(load: (key: string) => Promise<T>, ttlMs = 4000, now = Date.now) {
  const entries = new Map<string, { value?: T; expires: number; pending?: Promise<T> }>();
  return async (key: string): Promise<T> => {
    let entry = entries.get(key);
    if (entry?.pending) return entry.pending;
    if (entry && entry.expires > now()) return entry.value!;
    entry = { expires: 0 };
    entries.set(key, entry);
    const current = entry;
    current.pending = Promise.resolve().then(() => load(key)).then(value => {
      current.value = value;
      current.expires = now() + ttlMs;
      current.pending = undefined;
      return value;
    }, error => {
      entries.delete(key);
      throw error;
    });
    return current.pending;
  };
}
