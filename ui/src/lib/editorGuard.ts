/** Whether clicking a table/column may replace the editor without asking:
 *  only when it's empty or still holds the last value we loaded into it. A
 *  dirtied editor (in-progress SQL) is preserved — the caller confirms first. */
export function shouldReplaceEditor(current: string, lastLoaded: string): boolean {
  return current.trim() === "" || current === lastLoaded;
}
