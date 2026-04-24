export type FragmentType = "fact" | "preference" | "decision" | "event" | "project";
export type Scope = "global" | "app";

export interface Fragment {
  id: string;
  content: string;
  type: FragmentType;
  importance: number;
  score: number;
  source_client: string | null;
  created_at: string;
}

export interface MemoryResponse {
  user_id: string;
  fragments: Fragment[];
  prompt_block: string;
  meta: {
    total_fragments: number;
    query_ms: number;
  };
}

export interface SessionResponse {
  session_id: string;
  user_id: string;
  status: string;
  message: string;
}

export interface WriteOptions {
  source_client?: string;
  metadata?: Record<string, unknown>;
}

export interface QueryOptions {
  top_k?: number;
  scope?: Scope;
  type?: FragmentType;
}

export class ContextOSError extends Error {
  constructor(
    public readonly status_code: number,
    public readonly detail: string
  ) {
    super(`ContextOS API error ${status_code}: ${detail}`);
    this.name = "ContextOSError";
  }
}

export class ContextOS {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;

  /**
   * ContextOS client.
   *
   * @example
   * const client = new ContextOS({ apiKey: "sk-...", baseUrl: "https://your-app.fly.dev" });
   *
   * // After a conversation
   * await client.write("alice", "User: I prefer async Python\nAssistant: Got it.");
   *
   * // Before an LLM call
   * const memory = await client.query("alice", userMessage);
   * const system = `You are a helpful assistant.\n\n${memory.prompt_block}`;
   */
  constructor({
    apiKey,
    baseUrl = "http://localhost:8000",
  }: {
    apiKey: string;
    baseUrl?: string;
  }) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.headers = {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    };
  }

  /**
   * Ingest a conversation. Extraction runs in the background on the server.
   * Returns the session_id.
   */
  async write(
    userId: string,
    conversation: string,
    options: WriteOptions = {}
  ): Promise<string> {
    const body: Record<string, unknown> = { user_id: userId, conversation };
    if (options.source_client) body.source_client = options.source_client;
    if (options.metadata) body.metadata = options.metadata;

    const resp = await fetch(`${this.baseUrl}/sessions`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(body),
    });

    await raiseForStatus(resp);
    const data = (await resp.json()) as SessionResponse;
    return data.session_id;
  }

  /**
   * Retrieve relevant memory fragments for a user.
   * Returns a MemoryResponse with fragments and a ready-to-inject prompt_block.
   */
  async query(
    userId: string,
    q: string,
    options: QueryOptions = {}
  ): Promise<MemoryResponse> {
    const params = new URLSearchParams({ user_id: userId, q });
    if (options.top_k !== undefined) params.set("top_k", String(options.top_k));
    if (options.scope) params.set("scope", options.scope);
    if (options.type) params.set("type", options.type);

    const resp = await fetch(`${this.baseUrl}/memory?${params}`, {
      headers: this.headers,
    });

    await raiseForStatus(resp);
    return resp.json() as Promise<MemoryResponse>;
  }

  /**
   * Delete a fragment by ID. Only fragments created by this app can be deleted.
   */
  async delete(fragmentId: string): Promise<void> {
    const resp = await fetch(`${this.baseUrl}/memory/${fragmentId}`, {
      method: "DELETE",
      headers: this.headers,
    });
    await raiseForStatus(resp);
  }
}

async function raiseForStatus(resp: Response): Promise<void> {
  if (!resp.ok) {
    let detail: string;
    try {
      const body = (await resp.json()) as { detail?: string };
      detail = body.detail ?? resp.statusText;
    } catch {
      detail = resp.statusText;
    }
    throw new ContextOSError(resp.status, detail);
  }
}
