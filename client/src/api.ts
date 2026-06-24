export type MediaItem = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  object_key: string;
  sha256: string | null;
  status: "UPLOADED" | "PROCESSING" | "READY" | "FAILED";
  duration_seconds: number | null;
  summary: string | null;
  created_at: string;
};

export type Citation = {
  chunk_id: string;
  start_ms: number;
  end_ms: number;
  text: string;
  score: number;
};

export type ChatResponse = {
  trace_id: string;
  answer: string;
  citations: Citation[];
};

export type AnalysisTask = {
  task_id: string;
  video_id: string;
  status: string;
  progress: number;
  current_stage: string | null;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
};

export type TranscriptChunk = {
  chunk_id: string;
  chunk_index: number;
  start_ms: number;
  end_ms: number;
  text: string;
};

export type AgentTrace = {
  id: string;
  video_id: string;
  question: string;
  status: string;
  intent: string | null;
  model_name: string | null;
  node_timings: { node: string; duration_ms: number }[];
  tool_calls: Record<string, unknown>[];
  evidence_ids: string[];
  answer: string | null;
  error_type: string | null;
  error_message: string | null;
  latency_ms: number | null;
};

type UploadPart = { part_number: number; etag: string };

type UploadSession = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  object_key: string;
  status: "INITIATED" | "COMPLETED" | "ABORTED";
  completed_parts: UploadPart[];
  video_id: string | null;
};

export async function listMedia(): Promise<MediaItem[]> {
  const response = await fetch("/api/videos");
  if (!response.ok) throw new Error("无法加载媒体列表");
  return response.json();
}

function inferContentType(file: File): string {
  if (file.type.startsWith("audio/") || file.type.startsWith("video/")) return file.type;
  const extension = file.name.split(".").pop()?.toLowerCase();
  const known: Record<string, string> = {
    mp3: "audio/mpeg",
    wav: "audio/wav",
    m4a: "audio/mp4",
    aac: "audio/aac",
    flac: "audio/flac",
    ogg: "audio/ogg",
    mp4: "video/mp4",
    mov: "video/quicktime",
    webm: "video/webm",
    mkv: "video/x-matroska",
  };
  const inferred = extension ? known[extension] : undefined;
  if (!inferred) throw new Error("请选择常见格式的音频或视频文件");
  return inferred;
}

export async function uploadMedia(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<MediaItem> {
  const contentType = inferContentType(file);
  const resumeKey = `audivise-upload:${file.name}:${file.size}:${file.lastModified}`;
  let upload: UploadSession | undefined;
  const savedUploadId = localStorage.getItem(resumeKey);
  if (savedUploadId) {
    const resumed = await fetch(`/api/uploads/${savedUploadId}`);
    if (resumed.ok) {
      upload = await resumed.json();
      if (upload?.status === "COMPLETED" && upload.video_id) {
        localStorage.removeItem(resumeKey);
        return findMedia(upload.video_id);
      }
    } else {
      localStorage.removeItem(resumeKey);
    }
  }

  if (!upload) {
    const created = await fetch("/api/uploads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: file.name,
        content_type: contentType,
        size_bytes: file.size,
      }),
    });
    if (!created.ok) throw new Error("无法创建上传会话");
    const createdUpload = await created.json();
    localStorage.setItem(resumeKey, createdUpload.id);
    const session = await fetch(`/api/uploads/${createdUpload.id}`);
    if (!session.ok) throw new Error("无法读取上传会话");
    upload = await session.json();
  }
  if (!upload) throw new Error("上传会话初始化失败");

  const chunkSize = 8 * 1024 * 1024;
  const confirmed = new Map(upload.completed_parts.map((part) => [part.part_number, part.etag]));
  const totalParts = Math.ceil(file.size / chunkSize);
  onProgress?.(Math.round((confirmed.size / totalParts) * 100));

  for (let offset = 0, partNumber = 1; offset < file.size; offset += chunkSize, partNumber++) {
    if (confirmed.has(partNumber)) continue;
    const partResponse = await fetch(`/api/uploads/${upload.id}/parts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ part_number: partNumber }),
    });
    if (!partResponse.ok) throw new Error(`无法创建第 ${partNumber} 个分片`);
    const { url } = await partResponse.json();
    if (!url.startsWith("memory://")) {
      const uploaded = await fetch(url, {
        method: "PUT",
        body: file.slice(offset, Math.min(offset + chunkSize, file.size)),
      });
      if (!uploaded.ok) throw new Error(`第 ${partNumber} 个分片上传失败`);
      const etag = uploaded.headers.get("etag")?.replaceAll('"', "");
      if (!etag) throw new Error(`第 ${partNumber} 个分片缺少 ETag`);
      confirmed.set(partNumber, etag);
    } else {
      confirmed.set(partNumber, `memory-${partNumber}`);
    }
    const recorded = await fetch(`/api/uploads/${upload.id}/parts/${partNumber}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ etag: confirmed.get(partNumber) }),
    });
    if (!recorded.ok) throw new Error(`第 ${partNumber} 个分片状态保存失败`);
    onProgress?.(Math.round((confirmed.size / totalParts) * 100));
  }

  const parts = [...confirmed.entries()]
    .map(([part_number, etag]) => ({ part_number, etag }))
    .sort((left, right) => left.part_number - right.part_number);
  const completed = await fetch(`/api/uploads/${upload.id}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parts }),
  });
  if (!completed.ok) throw new Error("无法完成上传");
  const result = await completed.json();
  localStorage.removeItem(resumeKey);
  onProgress?.(100);
  return findMedia(result.video_id);
}

async function findMedia(mediaId: string): Promise<MediaItem> {
  const media = (await listMedia()).find((item) => item.id === mediaId);
  if (!media) throw new Error("上传后未找到媒体文件");
  return media;
}

export async function startAnalysis(mediaId: string): Promise<AnalysisTask> {
  const response = await fetch(`/api/videos/${mediaId}/analysis`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  if (!response.ok) throw new Error("无法创建解析任务");
  return response.json();
}

export async function getTask(taskId: string): Promise<AnalysisTask> {
  const response = await fetch(`/api/tasks/${taskId}`);
  if (!response.ok) throw new Error("无法查询任务状态");
  return response.json();
}

export async function getPlaybackUrl(mediaId: string): Promise<string> {
  const response = await fetch(`/api/videos/${mediaId}/playback`);
  if (!response.ok) throw new Error("无法获取播放地址");
  return (await response.json()).url;
}

export async function getTranscript(mediaId: string): Promise<TranscriptChunk[]> {
  const response = await fetch(`/api/videos/${mediaId}/transcript`);
  if (!response.ok) throw new Error("无法加载字幕");
  return response.json();
}

export async function getTrace(traceId: string): Promise<AgentTrace> {
  const response = await fetch(`/api/traces/${traceId}`);
  if (!response.ok) throw new Error("无法加载 Agent Trace");
  return response.json();
}

type StreamHandlers = {
  onStatus?: (payload: Record<string, unknown>) => void;
  onTool?: (payload: Record<string, unknown>) => void;
  onEvidence?: (citation: Citation) => void;
  onToken?: (text: string) => void;
  onFinal?: (payload: { trace_id: string; answer: string; citations: string[] }) => void;
};

export async function streamMediaQuestion(
  mediaId: string,
  question: string,
  handlers: StreamHandlers,
): Promise<void> {
  const response = await fetch(`/api/videos/${mediaId}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!response.ok || !response.body) throw new Error("无法建立 Agent 流");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      let event = "message";
      let data = "";
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "status") handlers.onStatus?.(payload);
      if (event === "tool") handlers.onTool?.(payload);
      if (event === "evidence") handlers.onEvidence?.(payload);
      if (event === "token") handlers.onToken?.(payload.text);
      if (event === "final") handlers.onFinal?.(payload);
      if (event === "error") throw new Error(payload.message ?? "Agent 执行失败");
    }
    if (done) break;
  }
}
