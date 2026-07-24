import { useCallback, useState } from "react";

/**
 * A single draggable dimension (px), persisted to localStorage.
 * `axis`: "x" tracks clientX, "y" tracks clientY. `invert` for panels that grow
 * when the handle moves toward them (e.g. a right-docked panel's left edge).
 */
export function useResize(key: string, initial: number, axis: "x" | "y", invert = false, min = 140) {
  const [size, setSize] = useState<number>(() => {
    const saved = Number(localStorage.getItem(key));
    return saved > 0 ? saved : initial;
  });

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const start = axis === "x" ? e.clientX : e.clientY;
      const startSize = size;
      const move = (ev: MouseEvent) => {
        const cur = axis === "x" ? ev.clientX : ev.clientY;
        const delta = (cur - start) * (invert ? -1 : 1);
        const next = Math.max(min, startSize + delta);
        setSize(next);
        localStorage.setItem(key, String(next));
      };
      const up = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
        document.body.style.userSelect = "";
      };
      document.body.style.userSelect = "none";
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
    },
    [size, axis, key, invert, min],
  );

  return { size, onMouseDown };
}
