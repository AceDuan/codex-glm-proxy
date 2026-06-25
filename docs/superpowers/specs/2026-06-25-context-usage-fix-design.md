# Context 使用量修复设计

## 问题

代理将 Anthropic Messages 的 usage 转换为 OpenAI Responses usage 时，只使用
`input_tokens` 和 `output_tokens` 计算输入量与总量，遗漏了：

- `cache_read_input_tokens`
- `cache_creation_input_tokens`

Anthropic 的 `input_tokens` 不包含缓存读取和缓存创建所处理的输入 token。Codex 使用
`response.completed.response.usage.total_tokens` 作为当前上下文占用量，因此缓存命中后，
代理返回的上下文使用量会严重偏低，状态栏可能长期显示 `0%`。

## 修复方案

在响应转换层统一解析 Anthropic usage：

```text
responses_input_tokens =
    input_tokens
    + cache_read_input_tokens
    + cache_creation_input_tokens

responses_cached_tokens = cache_read_input_tokens

responses_total_tokens =
    responses_input_tokens
    + output_tokens
```

OpenAI Responses usage 中：

- `input_tokens` 表示完整输入 token 数，包含缓存读取和缓存创建 token。
- `input_tokens_details.cached_tokens` 只表示缓存命中的 token，即
  `cache_read_input_tokens`。
- `total_tokens` 等于完整输入 token 数加输出 token 数。

## 数据流

`message_start` 和 `message_delta` 中出现的 usage 都通过同一更新逻辑写入转换状态。
字段缺失时保留之前事件中的值，字段显式为 `0` 时允许覆盖之前的值。

最终收到 `message_stop` 时，根据状态中的四类 Anthropic token 构造
`response.completed.response.usage`。

## 兼容性

- 不改变 SSE 事件类型、顺序或其他响应字段。
- 不依赖智谱特有字段；标准 Anthropic usage 仍按同一规则工作。
- 上游不返回缓存字段时，其值按 `0` 处理，结果与当前无缓存场景一致。
- 不估算上游未报告的 token，避免代理生成无法验证的使用量。

## 测试

新增回归测试覆盖：

1. 缓存读取 token 被计入 `input_tokens` 和 `total_tokens`，并映射到
   `cached_tokens`。
2. 缓存创建 token 被计入 `input_tokens` 和 `total_tokens`，但不计入
   `cached_tokens`。
3. usage 字段跨 `message_start` 和 `message_delta` 聚合时，缺失字段不会清空已有值。
4. 现有无缓存文本流和工具调用转换测试保持通过。

## 验收标准

- 使用真实代理请求时，`response.completed.response.usage.total_tokens` 包含缓存 token。
- Codex 的 `context-usage` 能随当前上下文规模变化，不再因缓存命中长期显示 `0%`。
- 全部响应转换测试和服务器集成测试通过。
