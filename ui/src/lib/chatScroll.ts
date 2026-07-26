/** Whether the chat log is scrolled near enough to the bottom that new content
 *  should keep it pinned there. Scrolled-up readers are left where they are. */
export function shouldAutoScroll(
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
  threshold = 80,
): boolean {
  return scrollHeight - (scrollTop + clientHeight) <= threshold;
}
