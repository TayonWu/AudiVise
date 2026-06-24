import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubMediaList(contentType?: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/videos") {
        return {
          ok: true,
          json: async () =>
            contentType
              ? [
                  {
                    id: "media-1",
                    filename: contentType.startsWith("audio/") ? "访谈.mp3" : "演示.mp4",
                    content_type: contentType,
                    size_bytes: 2048,
                    object_key: "media/demo",
                    sha256: null,
                    status: "UPLOADED",
                    duration_seconds: null,
                    summary: null,
                    created_at: "2026-06-21T00:00:00Z",
                  },
                ]
              : [],
        };
      }
      if (url.endsWith("/playback")) {
        return { ok: true, json: async () => ({ url: "https://example.test/media" }) };
      }
      if (url.endsWith("/transcript")) {
        return { ok: true, json: async () => [] };
      }
      throw new Error(`unexpected request: ${url}`);
    }),
  );
}

test("renders AudiVise and accepts existing audio or video files", async () => {
  stubMediaList();

  render(<App />);

  expect(screen.getByText("AudiVise")).toBeInTheDocument();
  expect(screen.getByText("音视频语音内容理解平台")).toBeInTheDocument();
  expect(screen.getByLabelText("上传音频或视频")).toHaveAttribute(
    "accept",
    "audio/*,video/*",
  );
  expect(await screen.findByText("上传一个音频或视频开始体验。")).toBeInTheDocument();
});

test("renders an audio player for audio media", async () => {
  stubMediaList("audio/mpeg");

  const { container } = render(<App />);

  expect((await screen.findAllByText("访谈.mp3")).length).toBeGreaterThan(0);
  expect(container.querySelector("audio")).toBeInTheDocument();
  expect(container.querySelector("video")).not.toBeInTheDocument();
});

test("renders a video player for video media", async () => {
  stubMediaList("video/mp4");

  const { container } = render(<App />);

  expect((await screen.findAllByText("演示.mp4")).length).toBeGreaterThan(0);
  expect(container.querySelector("video")).toBeInTheDocument();
});
