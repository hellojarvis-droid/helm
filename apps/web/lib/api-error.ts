/**
 * ApiError — the single error type thrown by apps/web/lib/api.ts on a
 * non-2xx response. Callers read `userMessage` for a human-safe string,
 * `code` to branch on specific conditions, and `traceId` to echo into a
 * support email.
 *
 * The server envelope is the one set up by helm.errors on the API side:
 *   { detail: { error: <code>, message: <user-facing>, trace_id: <id> } }
 *
 * We degrade gracefully: if the server returned a plain string detail
 * (legacy routes) or a non-JSON body (proxy 502 etc.), we fall back to a
 * status-based default message so the user still sees a sentence.
 */

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly traceId: string;
  readonly userMessage: string;

  constructor(init: {
    code: string;
    status: number;
    traceId?: string;
    userMessage: string;
    cause?: unknown;
  }) {
    super(init.userMessage);
    this.name = "ApiError";
    this.code = init.code;
    this.status = init.status;
    this.traceId = init.traceId ?? "";
    this.userMessage = init.userMessage;
    if (init.cause !== undefined) {
      (this as { cause?: unknown }).cause = init.cause;
    }
  }

  /** 5xx, plus 408/429 — the shapes where "retry" is a reasonable CTA. */
  get retryable(): boolean {
    return this.status >= 500 || this.status === 408 || this.status === 429;
  }

  /** True when the right action is "sign in again", not "retry". */
  get authRequired(): boolean {
    return this.status === 401 || this.status === 403;
  }
}

export async function apiErrorFromResponse(
  res: Response,
  operationName: string,
): Promise<ApiError> {
  const traceId = res.headers.get("x-trace-id") ?? "";
  let code = "unknown_error";
  let userMessage = defaultMessage(res.status, operationName);

  try {
    // clone() keeps the original response body readable for any optional
    // diagnostics the caller wants to run after this helper returns.
    const body = (await res.clone().json()) as {
      detail?: unknown;
    };
    const detail = body.detail;
    if (detail && typeof detail === "object") {
      const detailBody = detail as { error?: unknown; message?: unknown };
      if (typeof detailBody.error === "string" && detailBody.error) code = detailBody.error;
      if (typeof detailBody.message === "string" && detailBody.message) {
        userMessage = detailBody.message;
      }
    } else if (typeof detail === "string" && detail) {
      userMessage = detail;
    }
  } catch {
    // Non-JSON body (HTML 502, empty response, etc.) — keep the default.
  }

  return new ApiError({ code, status: res.status, traceId, userMessage });
}

function defaultMessage(status: number, operation: string): string {
  if (status === 401 || status === 403) {
    return "Your session expired. Sign in again.";
  }
  if (status === 404) {
    return "We couldn't find what you're looking for.";
  }
  if (status === 408 || status === 429) {
    return "Going faster than we can keep up — try again in a moment.";
  }
  if (status >= 500) {
    return "Something's off on our side. Try again in a moment.";
  }
  return `That didn't work (${operation}). Check your input and try again.`;
}
