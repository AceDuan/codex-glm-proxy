# Context 使用量修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正 Anthropic 缓存 token 到 OpenAI Responses usage 的映射，使 Codex 能正确显示当前上下文使用量。

**Architecture:** 在现有响应转换状态中分别保存普通输入、缓存读取、缓存创建和输出 token。通过一个统一的 usage 更新方法处理 `message_start` 与 `message_delta`，最终按 Responses 语义构造完整输入量、缓存命中量和总量。

**Tech Stack:** Python 3.10+、标准库 `unittest`、Anthropic Messages SSE、OpenAI Responses SSE、`misc-run`。

---

## 文件结构

- 修改 `src/codex_glm_proxy/response_transform.py`：统一聚合 Anthropic usage，并生成符合 Responses 语义的 usage。
- 修改 `tests/test_response_transform.py`：覆盖缓存读取、缓存创建和跨事件字段保留。
- 修改 `tests/test_server.py`：在 HTTP 集成测试中验证最终 Responses usage。

### Task 1: 添加缓存 token 回归测试

**Files:**
- Modify: `tests/test_response_transform.py`

- [ ] **Step 1: 编写缓存读取与缓存创建的失败测试**

在 `ResponseTransformTests` 中新增：

```python
def test_includes_cache_tokens_in_input_and_total_usage(self):
    source = [
        event(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_cache",
                    "model": "glm-5.2",
                    "usage": {
                        "input_tokens": 9,
                        "output_tokens": 0,
                        "cache_read_input_tokens": 100,
                        "cache_creation_input_tokens": 20,
                    },
                },
            },
        ),
        event(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 2},
            },
        ),
        event("message_stop", {"type": "message_stop"}),
    ]

    output = parse_output(transform_anthropic_sse(source))
    completed = output[-1][1]["response"]

    self.assertEqual(
        completed["usage"],
        {
            "input_tokens": 129,
            "input_tokens_details": {"cached_tokens": 100},
            "output_tokens": 2,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 131,
        },
    )
```

- [ ] **Step 2: 运行测试并确认失败原因**

运行：

```bash
misc-run codex-glm-proxy -- \
  env PYTHONPATH=src python -m unittest \
  tests.test_response_transform.ResponseTransformTests.test_includes_cache_tokens_in_input_and_total_usage -v
```

预期：断言失败；实际 `input_tokens` 为 `9`、`total_tokens` 为 `11`，证明缓存 token 未计入。

- [ ] **Step 3: 提交失败测试**

```bash
git add tests/test_response_transform.py
git commit -m "test: 覆盖缓存令牌使用量转换"
```

### Task 2: 统一聚合 Anthropic usage

**Files:**
- Modify: `src/codex_glm_proxy/response_transform.py`
- Test: `tests/test_response_transform.py`

- [ ] **Step 1: 扩展响应状态并增加 usage 更新方法**

在 `_ResponsesState.__init__` 中将缓存状态拆分为：

```python
self.input_tokens = 0
self.output_tokens = 0
self.cache_read_input_tokens = 0
self.cache_creation_input_tokens = 0
```

在 `_ResponsesState` 中增加：

```python
def update_usage(self, usage: JsonObject) -> None:
    if "input_tokens" in usage:
        self.input_tokens = int(usage["input_tokens"] or 0)
    if "output_tokens" in usage:
        self.output_tokens = int(usage["output_tokens"] or 0)
    if "cache_read_input_tokens" in usage:
        self.cache_read_input_tokens = int(
            usage["cache_read_input_tokens"] or 0
        )
    if "cache_creation_input_tokens" in usage:
        self.cache_creation_input_tokens = int(
            usage["cache_creation_input_tokens"] or 0
        )

def final_usage(self) -> JsonObject:
    input_tokens = (
        self.input_tokens
        + self.cache_read_input_tokens
        + self.cache_creation_input_tokens
    )
    return _usage(
        input_tokens,
        self.output_tokens,
        self.cache_read_input_tokens,
    )
```

- [ ] **Step 2: 让所有 usage 事件使用统一更新逻辑**

将 `message_start` 中的直接赋值替换为：

```python
usage = message.get("usage") or {}
state.update_usage(usage)
```

将 `message_delta` 中的直接赋值替换为：

```python
usage = data.get("usage") or {}
state.update_usage(usage)
```

将 `message_stop` 中的 usage 构造替换为：

```python
final_usage = state.final_usage()
```

- [ ] **Step 3: 运行缓存 usage 测试并确认通过**

运行：

```bash
misc-run codex-glm-proxy -- \
  env PYTHONPATH=src python -m unittest \
  tests.test_response_transform.ResponseTransformTests.test_includes_cache_tokens_in_input_and_total_usage -v
```

预期：`PASS`。

- [ ] **Step 4: 运行全部响应转换测试**

运行：

```bash
misc-run codex-glm-proxy -- \
  env PYTHONPATH=src python -m unittest tests.test_response_transform -v
```

预期：全部 `PASS`。

- [ ] **Step 5: 提交生产代码**

```bash
git add src/codex_glm_proxy/response_transform.py
git commit -m "fix: 修正缓存令牌使用量映射"
```

### Task 3: 验证跨事件显式零值覆盖

**Files:**
- Modify: `tests/test_response_transform.py`
- Modify: `src/codex_glm_proxy/response_transform.py` only if the test exposes a defect

- [ ] **Step 1: 编写字段保留和零值覆盖测试**

在 `ResponseTransformTests` 中新增：

```python
def test_usage_updates_preserve_missing_fields_and_accept_zero(self):
    source = [
        event(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_updates",
                    "model": "glm-5.2",
                    "usage": {
                        "input_tokens": 10,
                        "cache_read_input_tokens": 5,
                        "cache_creation_input_tokens": 7,
                    },
                },
            },
        ),
        event(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {
                    "output_tokens": 3,
                    "cache_creation_input_tokens": 0,
                },
            },
        ),
        event("message_stop", {"type": "message_stop"}),
    ]

    output = parse_output(transform_anthropic_sse(source))
    completed = output[-1][1]["response"]

    self.assertEqual(completed["usage"]["input_tokens"], 15)
    self.assertEqual(
        completed["usage"]["input_tokens_details"]["cached_tokens"],
        5,
    )
    self.assertEqual(completed["usage"]["output_tokens"], 3)
    self.assertEqual(completed["usage"]["total_tokens"], 18)
```

- [ ] **Step 2: 运行测试**

运行：

```bash
misc-run codex-glm-proxy -- \
  env PYTHONPATH=src python -m unittest \
  tests.test_response_transform.ResponseTransformTests.test_usage_updates_preserve_missing_fields_and_accept_zero -v
```

预期：`PASS`。若失败，只修改 `update_usage` 的字段存在性判断，不改变其他转换逻辑。

- [ ] **Step 3: 提交测试**

```bash
git add tests/test_response_transform.py src/codex_glm_proxy/response_transform.py
git commit -m "test: 验证使用量跨事件聚合"
```

### Task 4: 增加服务器集成断言

**Files:**
- Modify: `tests/test_server.py`

- [ ] **Step 1: 扩展模拟上游缓存 usage**

将 `ANTHROPIC_STREAM` 的 `message_start` usage 改为：

```python
'"usage":{"input_tokens":4,"output_tokens":0,'
'"cache_read_input_tokens":6,"cache_creation_input_tokens":3}}}\n\n'
```

- [ ] **Step 2: 在 HTTP 测试中解析完成事件**

在 `test_forwards_request_and_streams_responses_events` 中增加：

```python
completed_line = next(
    line
    for line in result.splitlines()
    if line.startswith("data: ")
    and '"type":"response.completed"' in line
)
completed = json.loads(completed_line.removeprefix("data: "))
self.assertEqual(
    completed["response"]["usage"],
    {
        "input_tokens": 13,
        "input_tokens_details": {"cached_tokens": 6},
        "output_tokens": 2,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 15,
    },
)
```

- [ ] **Step 3: 运行服务器集成测试**

运行：

```bash
misc-run codex-glm-proxy -- \
  env PYTHONPATH=src python -m unittest tests.test_server -v
```

预期：全部 `PASS`。该命令需要允许绑定本地回环 socket。

- [ ] **Step 4: 提交集成测试**

```bash
git add tests/test_server.py
git commit -m "test: 验证代理返回完整上下文用量"
```

### Task 5: 完整验证

**Files:**
- Verify: `src/codex_glm_proxy/response_transform.py`
- Verify: `tests/test_response_transform.py`
- Verify: `tests/test_server.py`

- [ ] **Step 1: 运行完整测试套件**

运行：

```bash
misc-run codex-glm-proxy -- \
  env PYTHONPATH=src python -m unittest discover -s tests -v
```

预期：全部测试 `PASS`，无 traceback 或 warning。

- [ ] **Step 2: 检查补丁质量**

运行：

```bash
git diff --check
git status --short
```

预期：`git diff --check` 无输出；状态只包含本计划产生的预期改动。

- [ ] **Step 3: 使用真实代理请求验证**

启动代理后发送一个会产生缓存 token 的请求，检查最终事件：

```text
response.completed.response.usage.input_tokens
response.completed.response.usage.input_tokens_details.cached_tokens
response.completed.response.usage.total_tokens
```

预期：

```text
input_tokens = 普通输入 + 缓存读取 + 缓存创建
cached_tokens = 缓存读取
total_tokens = input_tokens + output_tokens
```

- [ ] **Step 4: 提交最终验证调整**

仅在验证过程中产生必要调整时执行：

```bash
git add src/codex_glm_proxy/response_transform.py tests/test_response_transform.py tests/test_server.py
git commit -m "fix: 完成上下文使用量修复"
```
