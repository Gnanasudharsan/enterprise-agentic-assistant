import type { Components } from "react-markdown";

/**
 * Model output and document text are untrusted: an injected passage can ask the model to
 * emit an image whose URL carries data out, and browsers fetch images without a click.
 * Images are never rendered (only their alt text); the backend also strips them, and the
 * page's CSP blocks remote images as a third layer.
 */
export const untrustedComponents: Components = {
  img: ({ alt }) => (alt ? <span className="img-removed">{alt}</span> : null),
};
