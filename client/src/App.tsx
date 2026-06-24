import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  AgentTrace,
  AnalysisTask,
  ChatResponse,
  Citation,
  getPlaybackUrl,
  getTask,
  getTrace,
  getTranscript,
  listMedia,
  MediaItem,
  startAnalysis,
  streamMediaQuestion,
  TranscriptChunk,
  uploadMedia,
} from "./api";
import { TracePanel, TranscriptPanel } from "./WorkspacePanels";

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.ceil(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(value: number) {
  const seconds = Math.floor(value / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function isAudio(media?: MediaItem) {
  return media?.content_type.startsWith("audio/") ?? false;
}

export default function App() {
  const [media, setMedia] = useState<MediaItem[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<ChatResponse>();
  const [task, setTask] = useState<AnalysisTask>();
  const [playbackUrl, setPlaybackUrl] = useState("");
  const [transcript, setTranscript] = useState<TranscriptChunk[]>([]);
  const [trace, setTrace] = useState<AgentTrace>();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("系统就绪");
  const mediaRef = useRef<HTMLMediaElement | null>(null);
  const selected = useMemo(
    () => media.find((item) => item.id === selectedId) ?? media[0],
    [media, selectedId],
  );

  useEffect(() => {
    void listMedia()
      .then((items) => {
        setMedia(items);
        setSelectedId(items[0]?.id);
      })
      .catch(() => setNotice("后端尚未启动"));
  }, []);

  useEffect(() => {
    if (!selected) {
      setPlaybackUrl("");
      setTranscript([]);
      return;
    }
    void getPlaybackUrl(selected.id)
      .then((url) => setPlaybackUrl(url.startsWith("memory://") ? "" : url))
      .catch(() => setPlaybackUrl(""));
    void getTranscript(selected.id).then(setTranscript).catch(() => setTranscript([]));
    setTrace(undefined);
  }, [selected]);

  async function handleUpload(file?: File) {
    if (!file) return;
    setBusy(true);
    setNotice("正在创建上传任务…");
    try {
      const item = await uploadMedia(file, (percent) => {
        setNotice(`正在上传音视频分片… ${percent}%`);
      });
      setMedia((current) => [item, ...current.filter((entry) => entry.id !== item.id)]);
      setSelectedId(item.id);
      setNotice("上传完成，可以开始解析");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAnalysis() {
    if (!selected) return;
    setBusy(true);
    setNotice("正在创建语音内容解析任务…");
    try {
      let current = await startAnalysis(selected.id);
      setTask(current);
      while (!["SUCCEEDED", "FAILED", "CANCELLED"].includes(current.status)) {
        await new Promise((resolve) => setTimeout(resolve, 1200));
        current = await getTask(current.task_id);
        setTask(current);
        setNotice(`解析阶段：${current.current_stage ?? current.status} · ${current.progress}%`);
      }
      setNotice(current.status === "SUCCEEDED" ? "音视频解析完成" : "音视频解析失败");
      setMedia(await listMedia());
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "解析任务失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAsk(event: FormEvent) {
    event.preventDefault();
    if (!selected || !question.trim()) return;
    setBusy(true);
    setNotice("Agent 正在检索字幕证据…");
    try {
      const citations: Citation[] = [];
      let answer = "";
      let traceId = "";
      setChat({ answer: "", citations: [], trace_id: "" });
      await streamMediaQuestion(selected.id, question.trim(), {
        onStatus: () => setNotice("Agent 正在分析问题并选择工具…"),
        onTool: (tool) => setNotice(`正在调用工具：${String(tool.name)}`),
        onEvidence: (citation) => {
          citations.push(citation);
          setChat((current) => ({
            answer: current?.answer ?? "",
            citations: [...citations],
            trace_id: current?.trace_id ?? "",
          }));
        },
        onToken: (text) => {
          answer += text;
          setChat((current) => ({
            answer,
            citations: current?.citations ?? [],
            trace_id: current?.trace_id ?? "",
          }));
        },
        onFinal: (result) => {
          traceId = result.trace_id;
          answer = result.answer;
        },
      });
      setChat({ answer, citations, trace_id: traceId });
      setQuestion("");
      setNotice("回答已生成并完成引用校验");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "问答失败");
    } finally {
      setBusy(false);
    }
  }

  function seekToMs(startMs: number) {
    if (!mediaRef.current) return;
    mediaRef.current.currentTime = startMs / 1000;
    void mediaRef.current.play();
  }

  async function showTrace() {
    if (!chat?.trace_id) return;
    try {
      setTrace(await getTrace(chat.trace_id));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Trace 加载失败");
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">AV</span>
          <span className="brand-copy">
            <strong>AudiVise</strong>
            <small>音视频语音内容理解平台</small>
          </span>
        </div>
        <div className="status">
          <span className={busy ? "pulse busy" : "pulse"} />
          {notice}
        </div>
      </header>

      <section className="hero">
        <p className="eyebrow">TRACEABLE SPEECH INTELLIGENCE</p>
        <h1>让每段声音<br />都成为可追问的证据</h1>
        <p className="hero-copy">
          上传录音、播客或视频，异步生成时间戳字幕、内容摘要与可追溯的 Agent 回答。
        </p>
        <label className="upload">
          <input
            aria-label="上传音频或视频"
            type="file"
            accept="audio/*,video/*"
            disabled={busy}
            onChange={(event) => void handleUpload(event.target.files?.[0])}
          />
          <span>选择音频或视频</span>
          <small>已有文件 · 无需麦克风录音</small>
        </label>
      </section>

      <section className="workspace">
        <aside className="library panel">
          <div className="section-title"><span>媒体库</span><b>{media.length}</b></div>
          <div className="video-list">
            {media.map((item) => (
              <button
                className={item.id === selected?.id ? "video-item active" : "video-item"}
                key={item.id}
                onClick={() => {
                  setSelectedId(item.id);
                  setChat(undefined);
                }}
              >
                <span className="video-icon">{isAudio(item) ? "♫" : "▶"}</span>
                <span>
                  <strong>{item.filename}</strong>
                  <small>{isAudio(item) ? "音频" : "视频"} · {formatBytes(item.size_bytes)} · {item.status}</small>
                </span>
              </button>
            ))}
            {!media.length && <p className="empty">上传一个音频或视频开始体验。</p>}
          </div>
        </aside>

        <section className="stage panel">
          <div className="section-title">
            <span>{selected?.filename ?? "音视频工作台"}</span>
            <b>{selected?.status ?? "EMPTY"}</b>
          </div>
          <div className={isAudio(selected) ? "player audio-player" : "player"}>
            {selected && isAudio(selected) && (
              <div className="audio-stage">
                <span className="audio-disc">♫</span>
                <strong>{selected.filename}</strong>
                <audio
                  ref={(node) => { mediaRef.current = node; }}
                  controls
                  src={playbackUrl || undefined}
                />
              </div>
            )}
            {selected && !isAudio(selected) && (
              <video
                ref={(node) => { mediaRef.current = node; }}
                controls
                src={playbackUrl || undefined}
              />
            )}
            {!selected && <div className="player-empty">AUDIO / VIDEO EVIDENCE PLAYER</div>}
          </div>
          {selected && (
            <div className="task-actions">
              <button disabled={busy} onClick={() => void handleAnalysis()}>
                {task && !["SUCCEEDED", "FAILED", "CANCELLED"].includes(task.status)
                  ? `解析中 ${task.progress}%`
                  : "开始智能解析"}
              </button>
              <span>{task?.current_stage ?? selected.status}</span>
            </div>
          )}
          <div className="summary">
            <span>AI 摘要</span>
            <p>{selected?.summary ?? "解析完成后，这里将展示基于语音字幕生成的结构化摘要。"}</p>
          </div>
          <div className="transcript">
            <span>时间轴字幕</span>
            <TranscriptPanel chunks={transcript} onSeek={seekToMs} />
          </div>
        </section>

        <section className="agent panel">
          <div className="section-title"><span>Agent 问答</span><b>LANGGRAPH</b></div>
          <div className="answer">
            {chat ? (
              <>
                <p>{chat.answer}</p>
                <div className="evidence-list">
                  {chat.citations.map((citation) => (
                    <button key={citation.chunk_id} onClick={() => seekToMs(citation.start_ms)}>
                      <span>{formatTime(citation.start_ms)}–{formatTime(citation.end_ms)}</span>
                      <p>{citation.text}</p>
                    </button>
                  ))}
                </div>
                <button className="trace-link" onClick={() => void showTrace()}>
                  查看 Trace · {chat.trace_id}
                </button>
              </>
            ) : (
              <div className="empty">选择音频或视频后，向 Agent 询问其中的语音内容。</div>
            )}
          </div>
          <form className="ask" onSubmit={(event) => void handleAsk(event)}>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="例如：这段内容的核心观点是什么？"
              disabled={!selected || busy}
            />
            <button disabled={!selected || busy || !question.trim()}>发送问题 ↗</button>
          </form>
        </section>
      </section>

      {trace && (
        <div className="trace-drawer">
          <button
            className="trace-backdrop"
            aria-label="关闭 Trace"
            onClick={() => setTrace(undefined)}
          />
          <TracePanel trace={trace} />
        </div>
      )}
    </main>
  );
}
