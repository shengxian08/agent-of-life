# Agent of Life - 前端深度解析

> 原生 JS 单页应用 + SSE 流式 + 打字机效果 + 安全确认弹窗
> 3 文件, 2,502 行 | 零框架依赖 (仅 marked + DOMPurify CDN)

---

## 目录

1. [整体架构](#1-整体架构)
2. [认证管理](#2-认证管理)
3. [聊天核心流程](#3-聊天核心流程)
4. [SSE 流式解析](#4-sse-流式解析)
5. [打字机效果](#5-打字机效果)
6. [Markdown 渲染管线](#6-markdown-渲染管线)
7. [消息操作按钮](#7-消息操作按钮)
8. [安全确认弹窗](#8-安全确认弹窗)
9. [告警轮询系统](#9-告警轮询系统)
10. [图片上传与视觉识别](#10-图片上传与视觉识别)
11. [关键函数索引](#11-关键函数索引)

---

## 1. 整体架构

3 个文件, 零 JS 框架, 纯原生实现:

| 文件 | 行数 | 职责 |
|------|:--:|------|
| index.html | 77 | 页面结构 + 登录弹窗 + 安全确认弹窗 |
| app.js | 1256 | 全部业务逻辑: 认证/聊天/渲染/操作/告警/视觉 |
| style.css | 1169 | 设计系统: 8pt栅格 + WCAG 2.1 + 动画 |

外部依赖 (CDN): marked (Markdown渲染) + DOMPurify (XSS清洗)

---

## 2. 认证管理

### 三种身份模式

| 模式 | 触发条件 | user_id来源 | 数据持久化 |
|------|------|------|------|
| 登录用户 | JWT Token存在 | AUTH_USER.user_id | localStorage + 服务端 |
| 游客 | 无Token | guest_随机8位 (localStorage) | localStorage |
| 兜底 | X-User-ID Header | 任意 | 服务端 |

### 游客ID机制
```javascript
function getGuestId() {
    var id = localStorage.getItem('guest_id');
    if (!id) {
        id = 'guest_' + Math.random().toString(36).slice(2, 10);
        localStorage.setItem('guest_id', id);
    }
    return id;  // 同一浏览器永久不变
}
```

### 登录后行为

saveAuth() 做5件事: localStorage存token+user -> 更新UI显示 -> 关闭弹窗 -> 生成新sessionId(清游客残留) -> 显示欢迎卡片 -> 1.2秒后管家主动打招呼(固定话术, 不调API)

### 验证码

注册时从 GET /api/v1/auth/captcha 获取图形验证码, 点击刷新。提交时 captcha_id + captcha_answer 一并发送。

---

## 3. 聊天核心流程

### sendMessage() 主函数

```
用户回车/点发送
  -> 1. 防重: isStreaming? -> return
  -> 2. 清空输入框, 设置 isStreaming=true
  -> 3. 取消上一个请求 (activeAbort.abort())
  -> 4. 取消打字机 (typewriterCancel())
  -> 5. DOM: 追加用户气泡 + AI气泡(三个跳动点)
  -> 6. fetch POST /api/v1/agent/chat/stream
       body: {session_id, user_id, message, intent, stream:true}
       signal: activeAbort.signal (可取消)
  -> 7. 流式读取 response.body.getReader()
  -> 8. 解析SSE -> 打字机渲染 -> 视频卡片 -> 操作按钮
  -> 9. isStreaming=false, scrollDown()
```

---

## 4. SSE 流式解析

### 流式读取循环

```javascript
var reader = resp.body.getReader();
var decoder = new TextDecoder();
var buffer = '';
while (true) {
    var result = await reader.read();
    if (result.done) break;
    buffer += decoder.decode(result.value, {stream:true});
    // 按换行分割, 处理完整行
    var lines = buffer.split('\n');
    buffer = lines.pop();  // 保留不完整行
    for (var i = 0; i < lines.length; i++) {
        if (!line.startsWith('data: ')) continue;
        var d = JSON.parse(line.slice(6));
        // 处理4种事件类型
    }
}
```

### 4种SSE事件类型

| 事件 | JSON格式 | 前端行为 |
|------|------|------|
| 文本内容 | {content: 文字片段} | 类型机逐字输出 |
| 视频卡片 | {video: HTML字符串} | 暂存_pendingVideoHtml, 最后注入 |
| 安全确认 | {requires_confirmation:true, content:...} | 停止打字机, 显示确认弹窗 |
| 完成标记 | {done:true} | 停止读取, flush打字机 |

### 安全确认在流式中的特殊处理

检测到 requires_confirmation 时: typewriterCancel() -> 标记pending-confirm样式 -> renderMD渲染警告 -> 300ms后弹确认窗 -> return(不继续读流)

---

## 5. 打字机效果

### typewriterStart() 核心机制

```javascript
function typewriterStart(streamEl, onFinish) {
    var buf = '', pos = 0, done = false;

    function tick() {
        if (pos < buf.length) {
            var adv = 2 + Math.floor(Math.random() * 2);  // 每次前进2-3字符
            pos = Math.min(pos + adv, buf.length);
            streamEl.innerHTML = renderMD(buf.slice(0, pos));
            scrollDown();
            if (pos >= buf.length && done) { finishUp(); return; }
        }
        setTimeout(tick, 30);  // 每30ms一帧, ~33fps
    }

    return {
        feed: function(s) { buf += s; },         // SSE收到文本 -> 追加到buf
        flush: function() { done = true; ... },   // 流结束 -> 立即显示全部
        text: function() { return buf; }
    };
}
```

### 设计细节

- 随机步长(2-3字符): 模拟真人打字的不均匀感
- done标志: SSE结束时调用flush(), 如果pos已追上buf则立即finishUp, 否则等tick追上
- finishUp: 先渲染完整文字, 再注入_pendingVideoHtml, 最后调onFinish(添加操作按钮)
- typewriterCancel: 安全确认/错误/新消息时立即停止

---

## 6. Markdown 渲染管线

### renderMD() 5步处理

```
1. 提取视频卡片: <!--VIDEOS-->...<!--/VIDEOS--> -> 分离到 videoHtml 变量
2. 清洗文本: 去掉视频表格 (作者/时长/播放量) + bilibili链接 + ---分隔线
3. Markdown->HTML: marked.parse() (GFM全支持: 表格/任务列表/删除线)
   降级: marked未加载时 -> fallbackRenderMD() 简易regex渲染
4. XSS防护: DOMPurify.sanitize() 白名单标签+属性
5. 组合: 清洗后HTML + videoHtml 拼接返回
```

### fallbackRenderMD() 降级渲染

纯 regex: 代码块pre/code, 行内code, 加粗strong, 链接a, h2/h3标题, 段落p, 换行br。无marked时兜底。

### cleanTextForCopy() 复制清洗

复制时去掉视频HTML块、bilibili链接、video-card HTML片段、多余空行。

---

## 7. 消息操作按钮

每条AI回复底部追加5个按钮:

| 按钮 | 数据属性 | 行为 |
|------|------|------|
| 复制 | data-action=copy | 清洗文本 -> navigator.clipboard.writeText |
| 朗读 | data-action=speak | SpeechSynthesis + 甜美女声(Ting-Ting/Yaoyao) + 1.25音调 |
| 喜欢 | data-action=like | 切换样式 + POST /api/v1/agent/feedback (rating=positive) |
| 不喜欢 | data-action=dislike | 切换样式 + 展开反馈调查面板(选原因+补充文字+提交) |
| 重新生成 | data-action=regenerate | 淡出删除气泡 -> 重新发相同query (仅最新一条有效) |

### 不喜欢反馈调查面板

展开面板: 5个原因标签(内容不准确/不完整/格式混乱/无关内容/其他) + 文字补充 + 提交按钮。提交后POST feedback(含reason+detail)。面板有滑入动画。

### 重新生成按钮的去重

removeAllRegenerateButtons(): 每条新回复渲染前, 移除所有历史消息中的重新生成按钮。只有最新一条可以重新生成。

---

## 8. 安全确认弹窗

### 完整链路

```
SSE收到 {requires_confirmation:true, pending_dangerous_calls:[{tool,args,message}]}
  -> showConfirmationDialog(pendingCalls)
      -> 填入弹窗: 操作名(tool) + 参数(args, 隐藏user_id)
      -> 显示 confirmModal
  -> 用户点[取消]
      -> cancelConfirmation() -> 隐藏弹窗 -> 移除AI确认气泡
  -> 用户点[确认执行]
      -> approveConfirmation()
          -> 构建 confirmed_tools = [{tool:..., args:...}]
          -> 重新 fetch POST /chat/stream (带 confirmed_tools)
          -> 后端 _call_tool 检测到 confirmed_dangerous=True -> 放行执行
```

### 关键设计

- _pendingConfirmation 变量缓存待确认数据, 跨请求传递
- 确认后重新发起完整的 /chat/stream 请求 (不是单独的确认接口)
- 参数中隐藏 user_id (不展示给用户)

---

## 9. 告警轮询系统

### autoRefreshAlerts() 三层机制

```
页面加载时:
  1. 立即触发一次 daily_check (POST /dashboard/run/daily)
  2. 快速轮询 (最多5次x8秒=40秒): 每8秒 GET /dashboard/alerts
     检测到告警就停轮询
  3. 每日8:00自动触发 daily_check (setTimeout计算到明天8点的毫秒数)
     触发后 setInterval 每24小时一次
```

### 告警展示

updateStatusBar(): 从 GET /dashboard/alerts 获取告警列表。过滤已关闭的告警(localStorage记录)。有告警时顶部铃铛显示红色数字徽标。点击铃铛弹出下拉列表。点击告警项 -> 发送对应query -> 标记已关闭 -> localStorage持久化。无告警时显示'暂无待办, 一切正常'(2秒自动消失)。

---

## 10. 图片上传与视觉识别

### handleImageUpload() 流程

```
用户点+按钮选图/拍照
  -> 1. 检查isStreaming (不能同时发) + 文件类型(image/*)
  -> 2. 插入用户图片气泡 (URL.createObjectURL本地预览)
  -> 3. 插入AI气泡(加载中)
  -> 4. FormData上传: POST /api/v1/agent/vision/analyze
       file + prompt(描述图片内容)
  -> 5. 收到vision_description + agent_response -> 打字机渲染
  -> 6. 清理 file input
```

图片放大: showLightbox(url) 创建全屏浮层, 点击关闭。

---

## 11. 关键函数索引

| 函数 | 行号 | 职责 |
|------|:--:|------|
| sendMessage() | 514 | 聊天主入口: 发消息+SSE+渲染 |
| sendDirectQuery() | 438 | 无用户气泡的直接查询(告警/重新生成) |
| typewriterStart() | 617 | 打字机引擎: feed/flush/tick |
| renderMD() | 674 | Markdown渲染: 提取视频+清洗+marked+DOMPurify |
| addActionButtons() | 780 | 追加操作按钮(复制/朗读/赞/踩/重新生成) |
| showConfirmationDialog() | 1110 | 安全确认弹窗 |
| approveConfirmation() | 1153 | 确认后重新发请求(带confirmed_tools) |
| autoRefreshAlerts() | 282 | 告警轮询: 立即触发+快轮询+每日定时 |
| updateStatusBar() | 327 | 更新顶部告警徽标 |
| handleImageUpload() | 1057 | 图片上传+视觉识别 |
| saveAuth() | 30 | 登录/注册成功后: 存token+更新UI+欢迎卡片 |
| scrollDown() | 599 | 滚动节流: requestAnimationFrame 60fps |

### 外部CDN依赖

| 库 | 版本 | 用途 |
|------|------|------|
| marked | jsdelivr CDN | Markdown -> HTML (GFM全支持) |
| DOMPurify | jsdelivr CDN | XSS防护 (白名单标签+属性) |

### CSS设计系统

style.css (1169行): 8pt栅格间距, WCAG 2.1 AA/AAA对比度, 三色低饱和主色调(靛蓝+钢蓝灰+青绿), 6个子Agent品牌色, 微阴影层级, cubic-bezier缓动动画, 响应式布局, 暗色主题变量预留