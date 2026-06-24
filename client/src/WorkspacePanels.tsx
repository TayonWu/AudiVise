import { AgentTrace, TranscriptChunk } from "./api";

function formatTime(value: number) {
  const seconds = Math.floor(value / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

export function TranscriptPanel({
  chunks,
  onSeek,
}: {
  chunks: TranscriptChunk[];
  onSeek: (startMs: number) => void;
}) {
  return (
    <div className="transcript-panel">
      {chunks.map((chunk) => (
        <button key={chunk.chunk_id} onClick={() => onSeek(chunk.start_ms)}>
          <span>{formatTime(chunk.start_ms)}–{formatTime(chunk.end_ms)}</span>
          <p>{chunk.text}</p>
        </button>
      ))}
      {!chunks.length && <p className="empty">解析完成后可按时间查看字幕。</p>}
    </div>
  );
}

export function TracePanel({ trace }: { trace: AgentTrace }) {
  return (
    <aside className="trace-panel" aria-label="Agent Trace">
      <header>
        <div>
          <span>Agent Trace</span>
          <small>{trace.id}</small>
        </div>
        <b>{trace.status}</b>
      </header>
      <dl>
        <div><dt>意图</dt><dd>{trace.intent ?? "UNKNOWN"}</dd></div>
        <div><dt>模型</dt><dd>{trace.model_name ?? "规则路由 / 抽取式回答"}</dd></div>
        <div><dt>总耗时</dt><dd>{trace.latency_ms ?? 0} ms</dd></div>
      </dl>
      <section>
        <h3>节点耗时</h3>
        <div className="trace-timeline">
          {trace.node_timings.map((timing) => (
            <div key={timing.node}>
              <strong>{timing.node}</strong><span>{timing.duration_ms} ms</span>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h3>工具调用</h3>
        {trace.tool_calls.map((call, index) => (
          <article key={`${String(call.name)}-${index}`}>
            <strong>{String(call.name ?? "unknown_tool")}</strong>
            {"duration_ms" in call && <span>{String(call.duration_ms)} ms</span>}
            <pre>{JSON.stringify(call.arguments ?? {}, null, 2)}</pre>
          </article>
        ))}
        {!trace.tool_calls.length && <p className="empty">本次请求未调用工具。</p>}
      </section>
      <section>
        <h3>证据 ID</h3>
        <div className="trace-evidence">
          {trace.evidence_ids.map((id) => <code key={id}>{id}</code>)}
        </div>
      </section>
      {trace.error_type && (
        <p className="trace-error">
          异常：{trace.error_type}{trace.error_message ? ` · ${trace.error_message}` : ""}
        </p>
      )}
    </aside>
  );
}
