import { CheckIcon, CloseIcon } from "./Icons";

export interface Toast {
  id: number;
  text: string;
  kind: "success" | "error";
}

export function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <span className="toast-icon">
            {t.kind === "success" ? (
              <CheckIcon width={11} height={11} strokeWidth={3} />
            ) : (
              <CloseIcon width={11} height={11} strokeWidth={3} />
            )}
          </span>
          {t.text}
        </div>
      ))}
    </div>
  );
}
