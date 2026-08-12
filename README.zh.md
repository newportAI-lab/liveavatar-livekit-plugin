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
export LIVEKIT_API_KEY=...
export LIVEKIT_API_SECRET=...
```

可选变量：`FACEMARKET_BASE_URL`（默认 `https://facemarket.ai/vih/dispatcher`）以及用于显式重连的 `FACEMARKET_PREVIOUS_SESSION_ID`。构造函数参数会覆盖环境变量：`api_key`、`base_url`、`livekit_api_key`、`livekit_api_secret`、`sandbox` 和 `renderer_token_ttl`。沙箱模式会发送 `X-Env-Sandbox: true`。

不要把 API 密钥或渲染器 token 暴露到浏览器代码或 Data Channel 消息中。

## 使用

请参阅 [examples/basic_agent.py](examples/basic_agent.py)。`start()` 在 Facemarket 接受 `/v1/session/start` 后完成；它不会等待渲染器媒体或 `scene.ready`。新会话传入 `session_id=None`。请持久化 `avatar.session_id`；进程重建后的显式重连必须传给一个*新的* `AvatarSession` 实例。

只有要显式结束远端平台会话时才调用 `await avatar.stop()`。房间断开不会结束它。`async with AvatarSession(...)` 会在退出时调用 `stop()`；如果希望为之后重连保留会话，请不要使用上下文管理器。

## 回调与协议

使用 `@avatar.on(name)` 注册以下回调：

- `session_ready`（一次性的 `scene.ready`）
- `scene.resourceTransition`、`session.state`、`session.closing`、`system.idleTrigger`
- `error`、`custom_event` 和 `protocol_error`

回调会收到 `DataChannelEvent`，其中保留 `event`、`data`、`request_id`、`response_id`、`seq`、`timestamp`、发送者 `participant_identity` 和 `topic`。格式错误的数据包会通过 `protocol_error` 提供 `DataChannelProtocolError`。`AvatarSession` 自动发布可靠的语音、ASR 和响应桥接事件；HTTP 客户端、token 工厂和生命周期协调均保持在后端边界内。

## 检查命令

```bash
python -m pytest -q
python -m ruff check livekit tests
python -m black --check livekit tests
python -m compileall -q livekit examples
```
