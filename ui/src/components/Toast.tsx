import { useEffect } from "react";

/** A dismissible, auto-clearing notice for background-action failures — it layers
 *  over the workspace instead of replacing the results view. */
export default function Toast({
  message,
  onClose,
  timeoutMs = 6000,
}: {
  message: string;
  onClose: () => void;
  timeoutMs?: number;
}) {
  useEffect(() => {
    const t = setTimeout(onClose, timeoutMs);
    return () => clearTimeout(t);
  }, [onClose, timeoutMs]);
  return (
    <div className="toast" role="alert">
      <span className="toast-msg">{message}</span>
      <button className="toast-close" aria-label="Dismiss" onClick={onClose}>
        ×
      </button>
    </div>
  );
}
