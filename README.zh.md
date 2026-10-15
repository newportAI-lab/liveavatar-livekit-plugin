# Facemarket LiveKit 插件

`livekit-plugins-facemarket` 会在 LiveKit 房间中启动 Facemarket 渲染器，并把 LiveKit Agents 的语音事件桥接到其 Data Channel 协议。

## 安装与兼容性

```bash
pip install livekit-plugins-facemarket
```

需要 Python `>=3.10,<3.15`、LiveKit Agents `>=1.6.6,<2` 和 LiveKit API `>=1.1.1,<2`。

## 配置

请只在后端环境中保存密钥：

```bash
export FACEMARKET_API_KEY=...
export FACEMARKET_AVATAR_ID=...
export LIVEKIT_URL=wss://your-livekit.example.com
export LIVEKIT_API_KEY=...
export LIVEKIT_API_SECRET=...
```

可选变量：`FACEMARKET_BASE_URL`（默认 `https://facemarket.ai/vih/dispatcher`）、用于显式重连的 `FACEMARKET_PREVIOUS_SESSION_ID`，以及让作业关闭时保留远端会话的 `FACEMARKET_PRESERVE_SESSION=true`。构造函数参数会覆盖环境变量：`api_key`、`base_url`、`livekit_url`、`livekit_api_key`、`livekit_api_secret`、`sandbox` 和 `renderer_token_ttl`。显式传入空白值无效，并且 `renderer_token_ttl` 必须为正值。沙箱模式会发送 `X-Env-Sandbox: true`。

不要把 API 密钥或渲染器 token 暴露到浏览器代码或 Data Channel 消息中。

## 使用

请参阅 [examples/basic_agent.py](examples/basic_agent.py)。`start()` 在 Facemarket 接受 `/v1/session/start` 后完成；它不会等待渲染器媒体或 `scene.ready`。新会话传入 `session_id=None`。请持久化 `avatar.session_id`；进程重建后的显式重连必须传给一个*新的* `AvatarSession` 实例。

只有要显式结束远端平台会话时才调用 `await avatar.stop()`。房间断开不会结束它。示例通过 `JobContext.add_shutdown_callback` 注册 `avatar.stop`，因此会在作业真正关闭时结束远端会话，而不是在 `AgentSession.start()` 返回后立即停止。要为之后重连保留会话，请设置 `FACEMARKET_PRESERVE_SESSION=true` 以跳过该回调。`async with AvatarSession(...)` 会在退出时调用 `stop()`，终止语义相同。

## 回调与协议

使用 `@avatar.on(name)` 注册以下回调：

- `scene.ready`、`scene.resourceTransition`、`session.state`、`session.closing`、`system.idleTrigger`
- `error`、`custom_event` 和 `protocol_error`

回调会收到 `DataChannelEvent`，其中保留 `event`、`data`、`request_id`、`response_id`、`seq`、`timestamp`、发送者 `participant_identity` 和 `topic`。格式错误的数据包会通过 `protocol_error` 提供 `DataChannelProtocolError`。`AvatarSession` 自动发布可靠的语音、ASR 和响应桥接事件，为每个智能体话语分配稳定的响应 ID，并通过 `await avatar.interrupt(request_id=None)` 发布 `control.interrupt`。HTTP 客户端、token 工厂和生命周期协调均保持在后端边界内。

`scene.ready` 只会作为平台协议事件 `SCENE_READY` 原样转发；它不代表、也不会触发额外的数字人会话就绪状态。

## 检查命令

```bash
python -m pytest -q
python -m ruff check .
python -m black --check livekit tests examples
python -m compileall -q livekit examples
```
