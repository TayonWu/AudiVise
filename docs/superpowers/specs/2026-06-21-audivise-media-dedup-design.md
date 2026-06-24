# AudiVise 音视频与内容级去重设计

## 目标

将项目统一命名为“AudiVise音视频语音内容理解平台”，支持上传已有音频和视频文件，通过同一条 ASR、字幕、摘要和问答流水线处理语音内容；同时通过 PostgreSQL 与 Redis 的双层并发控制，确保相同内容不会重复消耗 FFmpeg、ASR、向量化和 LLM 算力。

## 产品边界

- 支持浏览器上传已有的 `audio/*` 与 `video/*` 文件。
- 不提供浏览器麦克风录音。
- 视频使用视频播放器，音频使用音频播放器。
- 音频和视频共享上传、任务、字幕、摘要、问答及 Trace 能力。
- 为保持 API 和数据库兼容，内部继续使用 `Video` 模型与 `/api/videos` 路径；用户界面和文档统一使用“媒体”或“音视频”。

## 品牌与文档

- 根 README、前端 README、HTML metadata、前端标题、FastAPI metadata 和包描述统一为 AudiVise。
- 根 README 重新以 UTF-8 中文编写，说明音视频语音理解边界、ASR 配置、分布式去重与容错机制。

## 双层并发控制

### PostgreSQL 活动任务唯一索引

在 PostgreSQL 上建立 `analysis_tasks(video_id)` 的部分唯一索引，仅覆盖 `PENDING`、`PROBING`、`EXTRACTING`、`TRANSCRIBING`、`INDEXING`、`SUMMARIZING` 状态。同一媒体记录被并发提交时，API 捕获唯一约束冲突并返回现有活动任务，而不是创建重复任务。

SQLite 测试环境使用应用层查询作为兼容路径；PostgreSQL 部分唯一索引是生产环境最终并发裁决者。

### Redis 内容执行租约

Worker 在 PROBING 阶段下载文件并计算 SHA-256。若没有已完成的同内容媒体，则以 `audivise:media:execution:{sha256}` 申请 Redis 租约：

- `SET key token NX PX ttl` 原子申请。
- 后台续租线程每 `ttl / 3` 通过 Lua 脚本执行 compare-token-and-pexpire。
- 释放时通过 Lua 脚本执行 compare-token-and-delete。
- 未取得租约的任务抛出可重试的 `ContentExecutionBusy`，由 Celery 指数退避重新投递，不进入高成本阶段。
- 获得租约后再次查询 READY canonical，关闭“查询后、加锁前”的竞态窗口。

租约覆盖 EXTRACTING 至 SUMMARIZING。PROBING 的下载和哈希可能重复，但不会重复执行转码、ASR、向量写入和摘要生成。

## 幂等、崩溃恢复与清理

- EXTRACTING：本地音频存在或 MinIO 正式音频产物已存在时不重复生成；否则重新生成。
- TRANSCRIBING：数据库已有字幕分片时跳过。
- INDEXING：Qdrant 使用稳定 chunk ID upsert。
- SUMMARIZING：数据库已有摘要时跳过。
- Celery 开启 late ack、worker lost reject 和 prefetch 1；Worker 崩溃后消息重新投递。
- 崩溃后 Redis 租约自然过期，新 Worker 获取租约并根据持久化阶段继续。
- Worker 每次执行结束都在 `finally` 中清理本地媒体工作目录；重试时从 MinIO 重新下载必要文件。

## 音频处理

FFmpeg 对音频和视频统一执行标准化：忽略视频轨，将语音转换为 16 kHz 单声道 MP3。这样录音、播客和视频可以复用同一 ASR 接口。

## 验证

- 上传 schema 接受 audio/video，拒绝其他 MIME。
- 前端文件选择器接受 audio/video，并根据 content type 渲染正确播放器。
- 同一媒体并发提交只返回一个活动任务。
- 相同字节的不同媒体记录并发执行时，只有一个进入昂贵阶段。
- 租约超过初始 TTL 后持续续租，第二个执行者仍无法获得锁。
- 旧 token 无法续租或释放新 token 的锁。
- Worker 异常和正常完成后临时目录均被删除。
- 全量后端测试、前端测试与构建通过。
