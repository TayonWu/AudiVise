import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { TracePanel, TranscriptPanel } from "./WorkspacePanels";

test("transcript panel renders timestamps and seeks to a selected chunk", () => {
  const onSeek = vi.fn();

  render(
    <TranscriptPanel
      chunks={[
        {
          chunk_id: "chunk-1",
          chunk_index: 0,
          start_ms: 65_000,
          end_ms: 71_000,
          text: "Celery 用于解耦长耗时任务。",
        },
      ]}
      onSeek={onSeek}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: /01:05/ }));

  expect(screen.getByText("Celery 用于解耦长耗时任务。")).toBeInTheDocument();
  expect(onSeek).toHaveBeenCalledWith(65_000);
});

test("trace panel exposes tool calls, evidence and timing", () => {
  render(
    <TracePanel
      trace={{
        id: "trace-1",
        video_id: "video-1",
        question: "Celery 有什么作用？",
        status: "SUCCEEDED",
        intent: "TRANSCRIPT",
        model_name: "demo-model",
        node_timings: [{ node: "search_evidence", duration_ms: 18 }],
        tool_calls: [{ name: "search_transcript", arguments: { query: "Celery" } }],
        evidence_ids: ["chunk-1"],
        answer: "用于异步任务解耦。",
        error_type: null,
        error_message: null,
        latency_ms: 42,
      }}
    />,
  );

  expect(screen.getByText("search_transcript")).toBeInTheDocument();
  expect(screen.getByText("TRANSCRIPT")).toBeInTheDocument();
  expect(screen.getByText("search_evidence")).toBeInTheDocument();
  expect(screen.getByText("chunk-1")).toBeInTheDocument();
  expect(screen.getByText(/42 ms/)).toBeInTheDocument();
});
