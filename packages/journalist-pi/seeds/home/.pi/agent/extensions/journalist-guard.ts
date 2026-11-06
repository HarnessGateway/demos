/**
 * Journalist guard: keep every file the agent writes inside the workspace.
 * The newsroom agent drafts stories and charts under /workspace only; this
 * blocks pi's write/edit tools from touching anything else. Bash-side writes
 * are covered by the standing instructions in AGENTS.md.
 */
export default function (pi: any) {
  const allowedRoot = (process.env.HG_WORKSPACE || process.cwd()).replace(/\/+$/, "") || "/workspace";

  function resolvePath(p: string): string {
    const base = (process.env.HG_WORKSPACE || process.cwd()).replace(/\/+$/, "");
    const abs = p.startsWith("/") ? p : base + "/" + p;
    const parts: string[] = [];
    for (const seg of abs.split("/")) {
      if (seg === "" || seg === ".") continue;
      if (seg === "..") parts.pop();
      else parts.push(seg);
    }
    return "/" + parts.join("/");
  }

  pi.on("tool_call", async (event: any, _ctx: any) => {
    if (event.toolName !== "write" && event.toolName !== "edit") return undefined;

    const raw = event.input && event.input.path;
    if (typeof raw !== "string" || raw.length === 0) return undefined;

    const resolved = resolvePath(raw);
    const ok = resolved === allowedRoot || resolved.startsWith(allowedRoot + "/");
    if (!ok) {
      return {
        block: true,
        reason:
          `Blocked: "${raw}" resolves outside the workspace (${allowedRoot}). ` +
          "Journalist drafts and charts belong under the workspace only.",
      };
    }
    return undefined;
  });
}
