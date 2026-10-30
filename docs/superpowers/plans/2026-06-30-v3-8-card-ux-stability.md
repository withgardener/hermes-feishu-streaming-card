# V3.8.0 卡片体验与流式稳定性实现计划

> **给 agentic workers：** 必须使用子技能：推荐 `superpowers:subagent-driven-development`，或使用 `superpowers:executing-plans` 逐任务执行。本计划使用 checkbox（`- [ ]`）跟踪进度。

**目标：** 发布 V3.8.0，让飞书卡片在多 reasoning、多工具、burst 流式输出下仍然完整、清楚、可诊断。

**架构：** 保持现有 sidecar-first 事件协议不变，只在 sidecar 内新增三块聚焦能力：session timeline、卡片渲染预算层、可 drain 的更新调度器。hook payload 形状保持兼容；V3.8.0 只改变事件到达 sidecar 之后的存储、渲染和刷新方式。

**技术栈：** Python 3.9+、aiohttp sidecar、pytest、Feishu Card 2.0 JSON、现有 `CardSession` / `render_card` / `create_app` 流程。

## 全局约束

- V3.8.0 不重写 installer、patcher 或 hook event protocol。
- 现有用户升级到 V3.8.0 不应该需要编辑配置。
- reasoning 展示仍然可配置，不能强制所有用户展示。
- 私有凭据、token、chat ID 不能暴露在卡片、日志、health response 或测试产物里。
- 公开仓库文档不能出现私有 / 内部对比项目的名称或链接。
- V3.8.1 命令能力和 V3.8.2 E2E 后续再做；本计划只实现 V3.8.0。

---

## 文件结构

- 新建 `hermes_feishu_card/card_timeline.py`：为 `CardSession` 提供按时间顺序排列的 reasoning / tool timeline 状态。
- 新建 `hermes_feishu_card/flush.py`：按 message 管理卡片更新调度，支持 coalescing、pending metrics、final drain。
- 修改 `hermes_feishu_card/session.py`：在保留现有字段的同时，把 reasoning / tool / answer 事件喂给 `CardTimeline`。
- 修改 `hermes_feishu_card/render.py`：把主回答和辅助 timeline 分开渲染，在卡片预算内折叠辅助内容，并保持长 markdown 安全。
- 修改 `hermes_feishu_card/metrics.py`：新增 update queue、coalesce、drain、latency 计数器。
- 修改 `hermes_feishu_card/config.py`：增加 V3.8.0 可选卡片默认配置，并使用安全默认值。
- 修改 `hermes_feishu_card/runner.py`：把 V3.8.0 卡片配置传给 `create_app`。
- 修改 `hermes_feishu_card/server.py`：用每个 session 一个 `FlushController` 替代临时的 `UPDATE_TASKS_KEY` / `PENDING_UPDATE_REQUESTS_KEY` 调度逻辑。
- 修改 `tests/unit/test_session.py`：覆盖 timeline 状态和 DeepSeek-style duplicate / replacement reasoning。
- 修改 `tests/unit/test_render.py`：覆盖主回答、timeline panel、折叠和长 markdown 渲染。
- 修改 `tests/unit/test_text.py`：补 inline code 和 list split 的结构安全覆盖。
- 修改 `tests/unit/test_config.py`：覆盖 V3.8.0 默认配置和自定义配置。
- 修改 `tests/integration/test_server.py`：覆盖 burst coalescing、final drain、terminal update failure diagnostics、避免重复 fallback 风险。
- 实现通过后再修改文档：`CHANGELOG.md`、`TODO.md`、`docs/release-notes-v3.8.0.md`。

---

### Task 1：按时间顺序记录卡片 Timeline 状态

**Files:**
- 新建：`hermes_feishu_card/card_timeline.py`
- 修改：`hermes_feishu_card/session.py`
- 测试：`tests/unit/test_session.py`

**Interfaces:**
- 产出：`TimelineEntry`、`CardTimeline`、`CardTimeline.record_reasoning(text: str, replace: bool = False) -> None`、`CardTimeline.record_answer_started() -> None`、`CardTimeline.record_tool(tool_id: str, name: str, status: str, detail: str = "") -> None`、`CardTimeline.snapshot(max_items: int | None = None) -> list[TimelineEntry]`、`CardTimeline.folded_count(max_items: int | None = None) -> int`。
- 消费：`CardSession.apply` 里已有的 `SidecarEvent` 数据。

- [ ] **Step 1：写失败的 timeline 单元测试**

把这些测试追加到 `tests/unit/test_session.py`：

```python
def test_session_timeline_records_reasoning_tool_answer_order():
    session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")

    assert session.apply(event("thinking.delta", 1, {"text": "先看约束。"}))
    assert session.apply(event("tool.updated", 2, {"tool_id": "read", "name": "read_file", "status": "running", "detail": "README.md"}))
    assert session.apply(event("tool.updated", 3, {"tool_id": "read", "name": "read_file", "status": "completed", "detail": "README.md"}))
    assert session.apply(event("answer.delta", 4, {"text": "最终回答开始"}))

    entries = session.timeline.snapshot()
    assert [(item.kind, item.title, item.status) for item in entries] == [
        ("reasoning", "思考 1", "completed"),
        ("tool", "read_file", "completed"),
    ]
    assert entries[0].content == "先看约束。"
    assert entries[1].detail == "README.md"


def test_session_timeline_appends_reasoning_blocks_without_losing_text():
    session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")

    assert session.apply(event("thinking.delta", 1, {"text": "第一句", "mode": "append_block"}))
    assert session.apply(event("thinking.delta", 2, {"text": "第二句", "mode": "append_block"}))

    entries = session.timeline.snapshot()
    assert len(entries) == 1
    assert entries[0].kind == "reasoning"
    assert entries[0].content == "第一句\n\n第二句"
    assert session.thinking_text == "第一句\n\n第二句"


def test_session_timeline_replace_mode_replaces_open_reasoning_without_duplication():
    session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")

    assert session.apply(event("thinking.delta", 1, {"text": "我先看"}))
    assert session.apply(event("thinking.delta", 2, {"text": "我先看看今天的变更", "mode": "replace"}))

    entries = session.timeline.snapshot()
    assert len(entries) == 1
    assert entries[0].content == "我先看看今天的变更"
    assert session.thinking_text == "我先看看今天的变更"


def test_session_timeline_folded_count_reports_hidden_old_entries():
    session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")
    for index in range(5):
        assert session.apply(event("thinking.delta", index * 2 + 1, {"text": f"思考{index}"}))
        assert session.apply(event("tool.updated", index * 2 + 2, {"tool_id": f"tool-{index}", "name": f"tool_{index}", "status": "completed"}))

    assert session.timeline.folded_count(max_items=3) == 7
    assert [item.title for item in session.timeline.snapshot(max_items=3)] == ["tool_3", "思考 5", "tool_4"]
```

- [ ] **Step 2：运行测试，确认当前失败**

运行：

```bash
python -m pytest tests/unit/test_session.py::test_session_timeline_records_reasoning_tool_answer_order tests/unit/test_session.py::test_session_timeline_appends_reasoning_blocks_without_losing_text tests/unit/test_session.py::test_session_timeline_folded_count_reports_hidden_old_entries -q
```

预期：FAIL，错误包含 `AttributeError: 'CardSession' object has no attribute 'timeline'`。

- [ ] **Step 3：实现 timeline 状态**

新建 `hermes_feishu_card/card_timeline.py`：

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TimelineEntry:
    kind: str
    title: str
    status: str
    content: str = ""
    detail: str = ""
    tool_id: str = ""


class CardTimeline:
    def __init__(self) -> None:
        self._entries: list[TimelineEntry] = []
        self._open_reasoning_index: int | None = None
        self._reasoning_count = 0
        self._tool_entry_by_id: dict[str, int] = {}

    def record_reasoning(self, text: str, replace: bool = False) -> None:
        if not text:
            return
        if replace and self._open_reasoning_index is not None:
            self._entries[self._open_reasoning_index].content = text
            return
        if self._open_reasoning_index is None:
            self._reasoning_count += 1
            self._entries.append(
                TimelineEntry(
                    kind="reasoning",
                    title=f"思考 {self._reasoning_count}",
                    status="running",
                    content=text,
                )
            )
            self._open_reasoning_index = len(self._entries) - 1
            return
        entry = self._entries[self._open_reasoning_index]
        if entry.content and not entry.content.endswith(("\n", "\n\n")) and not text.startswith(("\n", "\n\n")):
            entry.content += text
        else:
            entry.content += text

    def record_answer_started(self) -> None:
        self._finish_open_reasoning()

    def record_tool(self, tool_id: str, name: str, status: str, detail: str = "") -> None:
        if not tool_id:
            return
        self._finish_open_reasoning()
        title = name or tool_id
        normalized_status = status or "running"
        if tool_id in self._tool_entry_by_id:
            entry = self._entries[self._tool_entry_by_id[tool_id]]
            entry.title = title
            entry.status = normalized_status
            entry.detail = detail or entry.detail
            return
        self._entries.append(
            TimelineEntry(
                kind="tool",
                title=title,
                status=normalized_status,
                detail=detail,
                tool_id=tool_id,
            )
        )
        self._tool_entry_by_id[tool_id] = len(self._entries) - 1

    def complete(self) -> None:
        self._finish_open_reasoning()

    def snapshot(self, max_items: int | None = None) -> list[TimelineEntry]:
        if max_items is None or max_items <= 0 or len(self._entries) <= max_items:
            return list(self._entries)
        return list(self._entries[-max_items:])

    def folded_count(self, max_items: int | None = None) -> int:
        if max_items is None or max_items <= 0:
            return 0
        return max(0, len(self._entries) - max_items)

    def _finish_open_reasoning(self) -> None:
        if self._open_reasoning_index is None:
            return
        self._entries[self._open_reasoning_index].status = "completed"
        self._open_reasoning_index = None
```

修改 `hermes_feishu_card/session.py`：

```python
from .card_timeline import CardTimeline
```

给 `CardSession` 增加字段：

```python
    timeline: CardTimeline = field(default_factory=CardTimeline)
```

更新 `CardSession.apply`：

```python
        if event.event == "thinking.delta":
            mode = str(event.data.get("mode") or "delta").strip().lower()
            raw_text = str(event.data.get("text", ""))
            if mode == "replace":
                normalized = normalize_stream_text(raw_text)
                self.thinking_text = normalized
                self.timeline.record_reasoning(normalized, replace=True)
            elif mode == "append_block":
                text = normalize_stream_text(raw_text).strip()
                if text:
                    if self.thinking_text:
                        self.thinking_text = self.thinking_text.rstrip() + "\n\n" + text
                        self.timeline.record_reasoning("\n\n" + text)
                    else:
                        self.thinking_text = text
                        self.timeline.record_reasoning(text)
            else:
                delta = self.thinking_normalizer.feed(raw_text)
                self.thinking_text += delta
                self.timeline.record_reasoning(delta)
        elif event.event == "answer.delta":
            self.timeline.record_answer_started()
            self.answer_text += self.answer_normalizer.feed(str(event.data.get("text", "")))
```

更新 `tool.updated` 和 terminal 分支：

```python
            self.timeline.record_tool(
                tool_id,
                name if isinstance(name, str) else tool_id,
                status if isinstance(status, str) else "running",
                detail if isinstance(detail, str) else "",
            )
```

```python
        elif event.event == "message.completed":
            self.timeline.complete()
            self.status = "completed"
```

```python
        elif event.event == "message.failed":
            self.timeline.complete()
            self.status = "failed"
```

- [ ] **Step 4：运行聚焦 timeline 测试**

运行：

```bash
python -m pytest tests/unit/test_session.py -q
```

预期：PASS。

- [ ] **Step 5：提交**

```bash
git add hermes_feishu_card/card_timeline.py hermes_feishu_card/session.py tests/unit/test_session.py
git commit -m "feat: track card reasoning timeline"
```

---

### Task 2：渲染主回答和可折叠 Timeline

**Files:**
- 修改：`hermes_feishu_card/render.py`
- 测试：`tests/unit/test_render.py`

**Interfaces:**
- 消费：`CardSession.timeline.snapshot(max_items)` 和 `CardSession.timeline.folded_count(max_items)`。
- 产出：`render_card(..., show_reasoning: bool = True, timeline_expanded: bool = False, max_timeline_items: int = 12, max_reasoning_chars: int = 1200, max_tool_result_chars: int = 600) -> dict[str, Any]`。

- [ ] **Step 1：写失败的 render 测试**

把这些测试追加到 `tests/unit/test_render.py`：

```python
def test_render_answer_stays_primary_and_reasoning_moves_to_timeline():
    from hermes_feishu_card.events import SidecarEvent

    session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")
    session.apply(
        SidecarEvent(
            schema_version="1",
            event="thinking.delta",
            conversation_id="chat-1",
            message_id="msg-1",
            chat_id="oc_abc",
            platform="feishu",
            sequence=1,
            created_at=0.0,
            data={"text": "先分析约束。"},
        )
    )
    session.apply(
        SidecarEvent(
            schema_version="1",
            event="answer.delta",
            conversation_id="chat-1",
            message_id="msg-1",
            chat_id="oc_abc",
            platform="feishu",
            sequence=2,
            created_at=0.0,
            data={"text": "这是主回答。"},
        )
    )

    card = render_card(session)
    main = next(item for item in card["body"]["elements"] if item.get("element_id") == "main_content")
    timeline = next(item for item in card["body"]["elements"] if item.get("element_id") == "auxiliary_timeline")

    assert main["content"] == "这是主回答。"
    assert timeline["tag"] == "collapsible_panel"
    assert timeline["expanded"] is False
    assert "先分析约束。" in str(timeline)


def test_render_timeline_folds_old_entries_before_answer():
    from hermes_feishu_card.events import SidecarEvent

    session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")
    for index in range(8):
        session.apply(
            SidecarEvent(
                schema_version="1",
                event="thinking.delta",
                conversation_id="chat-1",
                message_id="msg-1",
                chat_id="oc_abc",
                platform="feishu",
                sequence=index * 2 + 1,
                created_at=0.0,
                data={"text": f"思考{index}"},
            )
        )
        session.apply(
            SidecarEvent(
                schema_version="1",
                event="tool.updated",
                conversation_id="chat-1",
                message_id="msg-1",
                chat_id="oc_abc",
                platform="feishu",
                sequence=index * 2 + 2,
                created_at=0.0,
                data={"tool_id": f"tool-{index}", "name": f"tool_{index}", "status": "completed"},
            )
        )
    session.answer_text = "最终回答不能被折叠"

    card = render_card(session, max_timeline_items=4)
    content = str(card)

    assert "最终回答不能被折叠" in content
    assert "已折叠 12 条早期思考/工具记录" in content
    assert "tool_7" in content
    assert "tool_0" not in content


def test_render_can_hide_reasoning_timeline_when_configured():
    from hermes_feishu_card.events import SidecarEvent

    session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")
    session.apply(
        SidecarEvent(
            schema_version="1",
            event="thinking.delta",
            conversation_id="chat-1",
            message_id="msg-1",
            chat_id="oc_abc",
            platform="feishu",
            sequence=1,
            created_at=0.0,
            data={"text": "隐藏的思考"},
        )
    )
    session.answer_text = "主回答"

    card = render_card(session, show_reasoning=False)

    content = str(card)
    assert "主回答" in content
    assert "隐藏的思考" not in content
    assert "auxiliary_timeline" not in content
```

- [ ] **Step 2：运行测试，确认当前失败**

运行：

```bash
python -m pytest tests/unit/test_render.py::test_render_answer_stays_primary_and_reasoning_moves_to_timeline tests/unit/test_render.py::test_render_timeline_folds_old_entries_before_answer -q
```

预期：FAIL，因为当前还没有渲染 `auxiliary_timeline`，且 `render_card` 还不接受 timeline 选项。

- [ ] **Step 3：实现 timeline 渲染**

修改 `render_card` 签名：

```python
def render_card(
    session: CardSession,
    footer_fields: list[str] | tuple[str, ...] | None = None,
    title: str = DEFAULT_TITLE,
    interaction_mode: str = "callback",
    show_reasoning: bool = True,
    timeline_expanded: bool = False,
    max_timeline_items: int = 12,
    max_reasoning_chars: int = 1200,
    max_tool_result_chars: int = 600,
) -> Dict[str, Any]:
```

替换当前主文本选择逻辑：

```python
    primary_text = normalize_stream_text(session.answer_text)
    if not primary_text:
        primary_text = "正在思考..." if session.status == "thinking" else normalize_stream_text(session.visible_main_text)
    elements = _render_main_content_elements(primary_text)
    if show_reasoning:
        elements.extend(
            _render_timeline_elements(
                session,
                expanded=timeline_expanded,
                max_items=max_timeline_items,
                max_reasoning_chars=max_reasoning_chars,
                max_tool_result_chars=max_tool_result_chars,
            )
        )
```

在 `render.py` 中新增 helper：

```python
def _render_timeline_elements(
    session: CardSession,
    *,
    expanded: bool,
    max_items: int,
    max_reasoning_chars: int,
    max_tool_result_chars: int,
) -> list[Dict[str, Any]]:
    if not getattr(session, "timeline", None):
        return []
    entries = session.timeline.snapshot(max_items=max_items)
    folded = session.timeline.folded_count(max_items=max_items)
    if not entries and not folded:
        return []
    lines: list[str] = []
    if folded:
        lines.append(f"> 已折叠 {folded} 条早期思考/工具记录")
        lines.append("")
    for item in entries:
        if item.kind == "reasoning":
            content = _limit_text(item.content, max_reasoning_chars)
            lines.append(f"**{item.title}** · {item.status}")
            if content:
                lines.append(content)
        elif item.kind == "tool":
            detail = _limit_text(item.detail, max_tool_result_chars)
            lines.append(f"- `{item.title}`: {item.status}")
            if detail:
                lines.append(f"  - {detail}")
        lines.append("")
    panel_content = "\n".join(lines).strip()
    if not panel_content:
        return []
    return [
        {
            "tag": "collapsible_panel",
            "element_id": "auxiliary_timeline",
            "expanded": expanded,
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"思考与工具 · {session.tool_count} 次工具调用",
                },
                "vertical_align": "center",
            },
            "border": {"color": "grey", "corner_radius": "5px"},
            "padding": "8px 8px 8px 8px",
            "elements": [
                {
                    "tag": "markdown",
                    "element_id": "auxiliary_timeline_content",
                    "content": panel_content,
                }
            ],
        }
    ]


def _limit_text(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 18)].rstrip() + "\n> 内容已折叠"
```

- [ ] **Step 4：运行聚焦 render 测试**

运行：

```bash
python -m pytest tests/unit/test_render.py -q
```

预期：PASS。

- [ ] **Step 5：提交**

```bash
git add hermes_feishu_card/render.py tests/unit/test_render.py
git commit -m "feat: render auxiliary card timeline"
```

---

### Task 3：增加可配置的卡片体验默认值

**Files:**
- 修改：`hermes_feishu_card/config.py`
- 修改：`hermes_feishu_card/runner.py`
- 修改：`hermes_feishu_card/server.py`
- 测试：`tests/unit/test_config.py`
- 测试：`tests/integration/test_server.py`

**Interfaces:**
- 在 `card` 下产出配置字段：`flush_interval_ms`、`final_drain_timeout_ms`、`show_reasoning`、`timeline_expanded`、`max_timeline_items`、`max_reasoning_chars`、`max_tool_result_chars`。
- 在 `_render_session_card` 中消费这些字段。

- [ ] **Step 1：写失败的配置测试**

追加到 `tests/unit/test_config.py`：

```python
def test_load_config_defaults_include_v38_card_options(tmp_path):
    config = load_config(tmp_path / "missing.yaml")

    assert config["card"]["flush_interval_ms"] == 200
    assert config["card"]["final_drain_timeout_ms"] == 900
    assert config["card"]["show_reasoning"] is True
    assert config["card"]["timeline_expanded"] is False
    assert config["card"]["max_timeline_items"] == 12
    assert config["card"]["max_reasoning_chars"] == 1200
    assert config["card"]["max_tool_result_chars"] == 600


def test_load_config_accepts_v38_card_options(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "card:\n"
        "  flush_interval_ms: 80\n"
        "  final_drain_timeout_ms: 1500\n"
        "  show_reasoning: false\n"
        "  timeline_expanded: true\n"
        "  max_timeline_items: 6\n"
        "  max_reasoning_chars: 800\n"
        "  max_tool_result_chars: 300\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config["card"]["flush_interval_ms"] == 80
    assert config["card"]["final_drain_timeout_ms"] == 1500
    assert config["card"]["show_reasoning"] is False
    assert config["card"]["timeline_expanded"] is True
    assert config["card"]["max_timeline_items"] == 6
    assert config["card"]["max_reasoning_chars"] == 800
    assert config["card"]["max_tool_result_chars"] == 300
```

- [ ] **Step 2：写失败的渲染透传集成测试**

追加到 `tests/integration/test_server.py`：

```python
async def test_card_config_controls_timeline_rendering():
    feishu_client = FakeFeishuClient()
    app = create_app(
        feishu_client,
        card_config={
            "timeline_expanded": True,
            "show_reasoning": True,
            "max_timeline_items": 1,
            "max_reasoning_chars": 20,
            "max_tool_result_chars": 20,
        },
    )
    server = TestServer(app)
    test_client = TestClient(server)
    await test_client.start_server()
    try:
        await test_client.post("/events", json=event_payload("message.started", 0))
        await test_client.post("/events", json=event_payload("thinking.delta", 1, {"text": "第一段很长很长很长很长很长"}))
        await test_client.post("/events", json=event_payload("tool.updated", 2, {"tool_id": "read", "name": "read_file", "status": "completed", "detail": "工具输出很长很长很长很长"}))
        await wait_for_card_update(feishu_client, "read_file")
    finally:
        await test_client.close()

    card = feishu_client.updated[-1][1]
    timeline = next(item for item in card["body"]["elements"] if item.get("element_id") == "auxiliary_timeline")
    assert timeline["expanded"] is True
    assert "已折叠 1 条早期思考/工具记录" in str(timeline)
    assert "内容已折叠" in str(timeline)
```

- [ ] **Step 3：运行测试，确认当前失败**

运行：

```bash
python -m pytest tests/unit/test_config.py::test_load_config_defaults_include_v38_card_options tests/unit/test_config.py::test_load_config_accepts_v38_card_options tests/integration/test_server.py::test_card_config_controls_timeline_rendering -q
```

预期：FAIL，因为配置字段和渲染透传还不存在。

- [ ] **Step 4：实现配置默认值和渲染透传**

修改 `hermes_feishu_card/config.py` 中的 `DEFAULT_CONFIG["card"]`：

```python
        "flush_interval_ms": 200,
        "final_drain_timeout_ms": 900,
        "show_reasoning": True,
        "timeline_expanded": False,
        "max_timeline_items": 12,
        "max_reasoning_chars": 1200,
        "max_tool_result_chars": 600,
```

修改 `hermes_feishu_card/server.py` 中的 `_render_session_card`：

```python
    return render_card(
        session,
        footer_fields=footer_fields,
        title=title,
        interaction_mode=interaction_mode,
        show_reasoning=bool(card_config.get("show_reasoning", True)),
        timeline_expanded=bool(card_config.get("timeline_expanded", False)),
        max_timeline_items=_safe_positive_int(card_config.get("max_timeline_items"), 12),
        max_reasoning_chars=_safe_positive_int(card_config.get("max_reasoning_chars"), 1200),
        max_tool_result_chars=_safe_positive_int(card_config.get("max_tool_result_chars"), 600),
    )
```

添加到 `server.py`：

```python
def _safe_positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default
```

- [ ] **Step 5：运行聚焦 config / render 测试**

运行：

```bash
python -m pytest tests/unit/test_config.py tests/unit/test_render.py tests/integration/test_server.py::test_card_config_controls_timeline_rendering -q
```

预期：PASS。

- [ ] **Step 6：提交**

```bash
git add hermes_feishu_card/config.py hermes_feishu_card/server.py tests/unit/test_config.py tests/integration/test_server.py
git commit -m "feat: add V3.8 card UX config"
```

---

### Task 4：可 Drain 的 FlushController 和 Metrics

**Files:**
- 新建：`hermes_feishu_card/flush.py`
- 修改：`hermes_feishu_card/metrics.py`
- 修改：`hermes_feishu_card/server.py`
- 测试：`tests/integration/test_server.py`

**Interfaces:**
- 产出：`FlushController.schedule(render_update: Callable[[], Awaitable[bool]], terminal: bool = False) -> asyncio.Task[None]`、`FlushController.drain(timeout_seconds: float) -> bool`、`FlushController.snapshot() -> dict[str, int | float]`。
- 消费：现有 `_update_card_for_app(app, message_id, card, bot_id) -> bool`。

- [ ] **Step 1：写失败的 coalescing 和 final drain 服务端测试**

追加到 `tests/integration/test_server.py`：

```python
async def test_burst_updates_are_coalesced_and_reported_in_health(client, monkeypatch):
    test_client, feishu_client = client
    feishu_client.update_delay = 0.03
    monkeypatch.setattr(sidecar_server, "UPDATE_MIN_INTERVAL_SECONDS", 0)

    await test_client.post("/events", json=event_payload("message.started", 0))
    responses = await asyncio.gather(
        *[
            test_client.post("/events", json=event_payload("answer.delta", index, {"text": f"片段{index}"}))
            for index in range(1, 25)
        ]
    )

    assert all(response.status == 200 for response in responses)
    await wait_for_card_update(feishu_client, "片段24")
    health = await test_client.get("/health")
    body = await health.json()
    assert body["metrics"]["update_coalesced"] > 0
    assert body["metrics"]["update_queue_peak"] >= 1
    assert body["metrics"]["feishu_update_attempts"] < 24


async def test_terminal_event_drains_latest_pending_content_before_final_card(client, monkeypatch):
    test_client, feishu_client = client
    feishu_client.update_delay = 0.04
    monkeypatch.setattr(sidecar_server, "UPDATE_MIN_INTERVAL_SECONDS", 0)

    await test_client.post("/events", json=event_payload("message.started", 0))
    await asyncio.gather(
        *[
            test_client.post("/events", json=event_payload("answer.delta", index, {"text": f"片段{index}"}))
            for index in range(1, 15)
        ]
    )
    completed = await test_client.post(
        "/events",
        json=event_payload("message.completed", 15, {"answer": ""}),
    )

    assert completed.status == 200
    await wait_for_card_update(feishu_client, "片段14")
    health = await test_client.get("/health")
    metrics = (await health.json())["metrics"]
    assert metrics["terminal_drains"] == 1
    assert metrics["terminal_drain_timeouts"] == 0
    assert "片段14" in str(feishu_client.updated[-1][1])
```

- [ ] **Step 2：运行测试，确认当前失败**

运行：

```bash
python -m pytest tests/integration/test_server.py::test_burst_updates_are_coalesced_and_reported_in_health tests/integration/test_server.py::test_terminal_event_drains_latest_pending_content_before_final_card -q
```

预期：FAIL，因为 flush metrics 还不存在，terminal drain 也没有显式实现。

- [ ] **Step 3：扩展 metrics**

修改 `hermes_feishu_card/metrics.py`：

```python
    update_scheduled: int = 0
    update_coalesced: int = 0
    update_queue_peak: int = 0
    terminal_drains: int = 0
    terminal_drain_timeouts: int = 0
    terminal_drain_latency_ms: int = 0
    feishu_update_latency_ms: int = 0
```

- [ ] **Step 4：实现 `FlushController`**

新建 `hermes_feishu_card/flush.py`：

```python
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


class FlushController:
    def __init__(self, *, interval_seconds: float, metrics: Any) -> None:
        self.interval_seconds = max(0.0, interval_seconds)
        self.metrics = metrics
        self._task: asyncio.Task[None] | None = None
        self._pending = False
        self._closed = False
        self._last_flush_at = 0.0

    def schedule(self, render_update: Callable[[], Awaitable[bool]], *, terminal: bool = False) -> asyncio.Task[None]:
        if self._closed and not terminal:
            return self._task or asyncio.create_task(self._noop())
        self.metrics.update_scheduled += 1
        if self._task is not None and not self._task.done():
            self._pending = True
            self.metrics.update_coalesced += 1
            self.metrics.update_queue_peak = max(self.metrics.update_queue_peak, 1)
            return self._task
        self._task = asyncio.create_task(self._run(render_update, terminal=terminal))
        return self._task

    async def drain(self, timeout_seconds: float) -> bool:
        started = time.monotonic()
        self.metrics.terminal_drains += 1
        task = self._task
        if task is None or task.done():
            self.metrics.terminal_drain_latency_ms = int((time.monotonic() - started) * 1000)
            return True
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=max(0.0, timeout_seconds))
        except asyncio.TimeoutError:
            self.metrics.terminal_drain_timeouts += 1
            self.metrics.terminal_drain_latency_ms = int((time.monotonic() - started) * 1000)
            return False
        self.metrics.terminal_drain_latency_ms = int((time.monotonic() - started) * 1000)
        return True

    def close(self) -> None:
        self._closed = True

    async def _run(self, render_update: Callable[[], Awaitable[bool]], *, terminal: bool) -> None:
        while True:
            now = time.monotonic()
            delay = 0.0 if terminal else max(0.0, self.interval_seconds - (now - self._last_flush_at))
            if delay > 0:
                await asyncio.sleep(delay)
            started = time.monotonic()
            await render_update()
            self.metrics.feishu_update_latency_ms = int((time.monotonic() - started) * 1000)
            self._last_flush_at = time.monotonic()
            if terminal or not self._pending:
                return
            self._pending = False

    async def _noop(self) -> None:
        return None
```

- [ ] **Step 5：在 `server.py` 中接入 controller**

新增：

```python
from .flush import FlushController
FLUSH_CONTROLLERS_KEY = web.AppKey("flush_controllers", dict)
```

在 `create_app` 中初始化：

```python
    app[FLUSH_CONTROLLERS_KEY] = {}
```

把 `_apply_event_locked` 里的更新调度替换成这个结构：

```python
        controller = _flush_controller_for_session(request.app, session_key)
        bot_id = message_bot_ids.get(_session_key(event))

        async def _render_and_update() -> bool:
            latest_session = sessions.get(session_key)
            if latest_session is None:
                return False
            latest_card = _render_session_card(request, latest_session)
            return await _update_card_for_app(request.app, feishu_message_id, latest_card, bot_id)

        if is_terminal:
            await controller.drain(_final_drain_timeout_seconds(request.app, session_key))
            current_task = controller.schedule(_render_and_update, terminal=True)
            controller.close()
        else:
            current_task = controller.schedule(_render_and_update, terminal=False)
        update_tasks[session_key] = current_task
        post_lock_task = current_task
```

新增 helper：

```python
def _flush_controller_for_session(app: web.Application, session_key: str) -> FlushController:
    controllers: dict[str, FlushController] = app[FLUSH_CONTROLLERS_KEY]
    controller = controllers.get(session_key)
    if controller is not None:
        return controller
    card_config = app[SESSION_CARD_CONFIGS_KEY].get(session_key, app[BASE_CARD_CONFIG_KEY])
    interval_ms = _safe_positive_int(card_config.get("flush_interval_ms"), 200)
    controller = FlushController(
        interval_seconds=interval_ms / 1000.0,
        metrics=app[METRICS_KEY],
    )
    controllers[session_key] = controller
    return controller


def _final_drain_timeout_seconds(app: web.Application, session_key: str) -> float:
    card_config = app[SESSION_CARD_CONFIGS_KEY].get(session_key, app[BASE_CARD_CONFIG_KEY])
    timeout_ms = _safe_positive_int(card_config.get("final_drain_timeout_ms"), 900)
    return timeout_ms / 1000.0
```

`UPDATE_MIN_INTERVAL_SECONDS` 只在旧测试迁移期间保留；本任务末尾需要删除不再使用的旧调度分支。

- [ ] **Step 6：运行聚焦 server 测试**

运行：

```bash
python -m pytest tests/integration/test_server.py::test_burst_updates_are_coalesced_and_reported_in_health tests/integration/test_server.py::test_terminal_event_drains_latest_pending_content_before_final_card tests/integration/test_server.py::test_terminal_event_ack_does_not_wait_for_slow_card_patch tests/integration/test_server.py::test_terminal_update_failure_still_accepts_event_to_prevent_native_fallback -q
```

预期：PASS。如果 `test_terminal_event_ack_does_not_wait_for_slow_card_patch` 与 bounded final drain 冲突，把断言改成：没有 pending update 时，响应时间低于配置的 `final_drain_timeout_ms`，并低于旧的慢 Feishu patch 时长。

- [ ] **Step 7：提交**

```bash
git add hermes_feishu_card/flush.py hermes_feishu_card/metrics.py hermes_feishu_card/server.py tests/integration/test_server.py
git commit -m "feat: coalesce and drain card updates"
```

---

### Task 5：Markdown 边界和卡片预算回归

**Files:**
- 修改：`hermes_feishu_card/text.py`
- 修改：`hermes_feishu_card/render.py`
- 测试：`tests/unit/test_text.py`
- 测试：`tests/unit/test_render.py`

**Interfaces:**
- 消费：现有 `split_markdown_blocks(text: str, max_block_size: int) -> list[str]`。
- 产出：对 list item 和 inline code span 更稳的分块保证。

- [ ] **Step 1：写失败的 markdown 边界测试**

追加到 `tests/unit/test_text.py`：

```python
def test_split_markdown_blocks_prefers_list_item_boundaries():
    text = "\n".join(f"- item {index} {'甲' * 40}" for index in range(80))

    chunks = split_markdown_blocks(text, 900)

    assert len(chunks) > 1
    assert all(len(chunk) <= 900 for chunk in chunks)
    assert all(not chunk.startswith("甲") for chunk in chunks[1:])
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_split_markdown_blocks_avoids_inline_code_split_when_possible():
    text = "前言\n\n" + " ".join(f"`code_{index}`" for index in range(300))

    chunks = split_markdown_blocks(text, 900)

    assert len(chunks) > 1
    assert all(len(chunk) <= 900 for chunk in chunks)
    for chunk in chunks:
        assert chunk.count("`") % 2 == 0
```

- [ ] **Step 2：运行测试，确认当前行为**

运行：

```bash
python -m pytest tests/unit/test_text.py::test_split_markdown_blocks_prefers_list_item_boundaries tests/unit/test_text.py::test_split_markdown_blocks_avoids_inline_code_split_when_possible -q
```

预期：如果 plain splitting 仍然会在不安全位置切断 list 或 inline-code，至少有一个测试失败。

- [ ] **Step 3：改进 plain block 分块**

修改 `hermes_feishu_card/text.py` 中的 `_split_plain_block`，按以下优先级选择切分点：

```python
def _split_plain_block(block: str, max_block_size: int) -> list[str]:
    chunks: list[str] = []
    remaining = block
    while len(remaining) > max_block_size:
        split_at = _safe_plain_split_index(remaining, max_block_size)
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if remaining:
        chunks.append(remaining)
    return chunks


def _safe_plain_split_index(text: str, max_block_size: int) -> int:
    window = text[: max_block_size + 1]
    candidates = [
        window.rfind("\n- "),
        window.rfind("\n* "),
        window.rfind("\n1. "),
        window.rfind("\n"),
        window.rfind(" "),
    ]
    split_at = max(candidates)
    if split_at <= 0:
        return max_block_size
    if window[:split_at].count("`") % 2 != 0:
        before_code = window.rfind("`", 0, split_at)
        if before_code > 0:
            return before_code
    return split_at
```

- [ ] **Step 4：增加卡片预算渲染回归测试**

追加到 `tests/unit/test_render.py`：

```python
def test_render_timeline_limits_reasoning_without_truncating_answer():
    from hermes_feishu_card.events import SidecarEvent

    session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")
    session.apply(
        SidecarEvent(
            schema_version="1",
            event="thinking.delta",
            conversation_id="chat-1",
            message_id="msg-1",
            chat_id="oc_abc",
            platform="feishu",
            sequence=1,
            created_at=0.0,
            data={"text": "思考" * 1000},
        )
    )
    session.answer_text = "最终回答完整保留"

    card = render_card(session, max_reasoning_chars=80)

    content = str(card)
    assert "最终回答完整保留" in content
    assert "内容已折叠" in content
    assert len(next(item for item in card["body"]["elements"] if item.get("element_id") == "auxiliary_timeline")["elements"][0]["content"]) < 300
```

- [ ] **Step 5：运行聚焦 markdown / render 测试**

运行：

```bash
python -m pytest tests/unit/test_text.py tests/unit/test_render.py -q
```

预期：PASS。

- [ ] **Step 6：提交**

```bash
git add hermes_feishu_card/text.py hermes_feishu_card/render.py tests/unit/test_text.py tests/unit/test_render.py
git commit -m "fix: preserve markdown structure in card chunks"
```

---

### Task 6：最终 V3.8.0 回归、文档和版本准备

**Files:**
- 修改：`pyproject.toml`
- 修改：`hermes_feishu_card/__init__.py`
- 修改：`CHANGELOG.md`
- 修改：`TODO.md`
- 新建：`docs/release-notes-v3.8.0.md`
- 测试：`tests/unit/test_package_metadata.py`
- 测试：`tests/unit/test_docs.py`

**Interfaces:**
- 消费：前面所有 V3.8.0 改动。
- 产出：V3.8.0 package metadata 和 release docs。

- [ ] **Step 1：写 metadata / docs 测试**

把 `tests/unit/test_package_metadata.py` 的预期版本更新为 `3.8.0`。

追加到 `tests/unit/test_docs.py`：

```python
def test_v38_release_notes_are_linked():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = Path("docs/release-notes-v3.8.0.md")

    assert release_notes.exists()
    assert "V3.8.0" in changelog
    assert "docs/release-notes-v3.8.0.md" in changelog
```

- [ ] **Step 2：运行测试，确认当前失败**

运行：

```bash
python -m pytest tests/unit/test_package_metadata.py tests/unit/test_docs.py::test_v38_release_notes_are_linked -q
```

预期：FAIL，因为版本和 release notes 还没更新。

- [ ] **Step 3：更新版本元数据**

把两个文件都设为 `3.8.0`：

```toml
version = "3.8.0"
```

```python
__version__ = "3.8.0"
```

- [ ] **Step 4：写 release notes**

新建 `docs/release-notes-v3.8.0.md`：

```markdown
# V3.8.0 版本说明

V3.8.0 聚焦飞书卡片可读性和流式稳定性。

## 核心改动

- 将主回答与 reasoning / tool timeline 分离展示。
- 合并 burst 场景下的卡片更新，并在 terminal card 渲染前 drain pending updates。
- 长 markdown 表格和 fenced code block 跨卡片分块时保持结构。
- 新增卡片更新 metrics，覆盖 queue、coalescing、drain、Feishu update latency。

## 升级说明

现有用户不需要修改配置。新增卡片选项都是可选项，并使用安全默认值。

## 验证命令

- `python -m pytest tests/unit/test_session.py tests/unit/test_render.py tests/unit/test_text.py tests/unit/test_config.py -q`
- `python -m pytest tests/integration/test_server.py -q`
```

更新 `CHANGELOG.md`，加入 V3.8.0 条目并链接 `docs/release-notes-v3.8.0.md`。

更新 `TODO.md`，把 V3.8.0 卡片体验 / flush 稳定性标记为已完成，保留 V3.8.1 / V3.8.2 待办。

- [ ] **Step 5：运行聚焦测试和全量测试**

运行：

```bash
python -m pytest tests/unit/test_session.py tests/unit/test_render.py tests/unit/test_text.py tests/unit/test_config.py tests/integration/test_server.py -q
python -m pytest -q
```

预期：PASS。

- [ ] **Step 6：提交**

```bash
git add pyproject.toml hermes_feishu_card/__init__.py CHANGELOG.md TODO.md docs/release-notes-v3.8.0.md tests/unit/test_package_metadata.py tests/unit/test_docs.py
git commit -m "docs: prepare V3.8.0 release notes"
```

---

## Plan 自查

- [x] V3.8.0 范围限定在卡片体验、流式稳定性、markdown 安全和 metrics。
- [x] V3.8.1 命令能力已明确后置。
- [x] V3.8.2 E2E / Agent guide 已明确后置。
- [x] 没有出现私有 / 内部对比项目名称或链接。
- [x] 每个任务都先写聚焦失败测试，再实现。
- [x] 每个任务都有明确 pytest 命令和提交步骤。
