# 工作流程

从新闻抓取到公众号发布的完整流水线。

---

## 整体流程

```
 ① 每日自动爬取  ②  AI 写稿  ③  生成封面  ④  半自动发布  ⑤  自动回复
 (本机计划任务)     (DeepSeek)   (Pillow/生图API) (粘贴进后台)  (后台配置)
       │                 │              │                │               │
 data/finance_*.json   article.md   cover.jpg      mp.weixin.qq.com   后台自动回复
                       cover.jpg                       草稿箱 → 发布     rules.json
```

---

## 第一步：每日自动爬取（已就绪，本地运行）

> **2026-11 起改为本机运行**：GitHub 账户因账单问题被锁、Actions 全停，流水线已迁到本机
> Windows 计划任务，产出完全相同。GitHub Actions 定时器已注释停用（见文末「切换回 GitHub Actions」）。

每天 **09:15**（北京时间）本机自动执行 `run_daily.ps1`，依次完成 ①→③ 全部步骤：

1. `finance_crawler.py` — 多源抓取昨日新闻 → `data/finance_YYYY-MM-DD.json`（约 1000+ 条）+ `daily/YYYY-MM-DD.md`
2. `write_article.py` — DeepSeek 生成观点点评文章（LLM 调用失败自动重试 3 次）
3. `search_images.py` + `md_to_mphtml.py` — 配图下载 + 公众号 HTML
4. 自动 `git add data daily` + commit + push 到 GitHub 做备份（推送失败自动重试 3 次）

**数据字段：** `title` / `url` / `publish_time` / `category` / `source_site` / `intro`（摘要）/ `content`（正文）

### 计划任务（任务计划程序里可查）

| 任务名 | 时间 | 作用 |
|--------|------|------|
| `FinanceNewsBot-Daily` | 每天 09:15 | 主运行 |
| `FinanceNewsBot-CatchUp-13` | 每天 13:00 | 补跑窗口① |
| `FinanceNewsBot-CatchUp-20` | 每天 20:00 | 补跑窗口② |

**可靠性机制：**
- **完成守卫**：当天已成功跑过就跳过（13:00 / 20:00 只补跑失败的，不重复消耗写稿 API）
- **发布守卫**：数据没成功推上 GitHub 就不标记完成，补跑窗口会自动重推
- **防重机制**：若 GitHub Actions 恢复运行（远端出现 bot 提交），本地自动让位跳过；设 `FORCE_LOCAL_RUN=1` 可强制本地跑
- **日志**：`logs/daily_YYYY-MM-DD.log`（中文正常，可直接看每一步成败）

### 手动操作

```powershell
# 立即手动跑一次（和定时任务完全等价；当天已完成则自动跳过）
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\project\finance-news-bot\run_daily.ps1"

# 只重跑某一天的写稿（爬取数据已在 data/ 下）
C:\Tools\Python\python.exe write_article.py --date 2026-11-08
```

---

## 第二步：AI 写稿（观点点评型）

**脚本：** `write_article.py`

**原理：** 从当天 JSON 中筛选候选新闻（AI/科技/财经/美股优先），发给 DeepSeek 让它生成一篇**观点点评文章**（1800-3000 字）。

**文章结构（已在提示词中固化）：**
- 开头一段直接亮出核心观点
- **只挑 2-3 个与标题主旨相关的小节**，宁可少而深，不要多而杂
- 每节约 500-900 字：事件背景用 1-3 句**自然融入正文**（不用"事件背景："标签），主体是看法/影响分析/预测（对哪些公司利空利好、对币圈/黄金/大盘传导、对格局的预测、给投资者的建议）
- 结尾总结 + 引导点赞在看关注
- 文末免责：*以上仅为个人观点分析，不构成投资建议。*

### 运行

```bash
# 先设置 API Key（默认读 .env 或环境变量 DEEPSEEK_API_KEY）
export DEEPSEEK_API_KEY="sk-xxxxx"

# 生成指定日期的稿件（默认当天）
python write_article.py --date 2026-09-11
```

**输出：** `drafts/2026-09-11/`
```
├── article.md      # 观点点评文章 Markdown
├── meta.json       # 结构化元数据（标题 / 摘要 / 各节搜索关键词）
├── raw_llm.txt     # LLM 原始输出（解析失败时排查用）
├── cover.jpg       # 封面（search_images.py 自动下载）
├── imgN.jpg        # 各节配图（search_images.py 自动下载）
└── mp_body.html    # 公众号 HTML（md_to_mphtml.py 生成）
```

### 可用模型配置

脚本兼容任意 OpenAI 格式端点，通过 `.env` 配置：

```
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.xxx.com/v1
DEEPSEEK_MODEL=your-model
```

### 参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `--date` | 日期 YYYY-MM-DD | 今天 |
| `--api-key` | DeepSeek API Key | 环境变量 `DEEPSEEK_API_KEY` |
| `--model` | 模型名 | `deepseek-chat` |
| `--candidates` | 候选新闻数上限 | 40 |
| `--dry-run` | 只打印候选，不调 LLM | — |

---

## 第三步：搜索配图

**脚本：** `search_images.py`

用 **Pixabay 免费 API** 根据文章关键词搜索图片并下载（商用无需署名，版权合规）。先注册获取 Key：<https://pixabay.com/api/docs/>

```bash
# .env 配置
PIXABAY_API_KEY=xxxxx

# 搜索并下载封面 + 各节配图（读取 meta.json 里的英文搜索关键词）
python search_images.py --date 2026-09-11
```

**输出：** `drafts/2026-09-11/cover.jpg` + `img1.jpg`、`img2.jpg`…

- 封面自动搜横图（≥900px 宽）
- 每个小节的 `search_keywords`（写稿时 AI 自动生成）作为搜索词
- 找不到图的节，HTML 会自动留占位框，可手动补

> 若本机访问 Pixabay 需要代理，在 `.env` 配置 `HTTP_PROXY=your-proxy`。

---

## 第四步：半自动发布

个人订阅号无官方发布 API，发布流程半自动：

### 1. 生成公众号友好 HTML

```bash
python md_to_mphtml.py drafts/2026-09-11/article.md -o drafts/2026-09-11/mp_body.html
```

生成的 HTML 使用公众号编辑器兼容的内联样式，直接粘贴即可保留格式。

### 2. 登录 mp.weixin.qq.com

- 新建图文
- **正文区：** 全选 `mp_body.html` 内容，粘贴进编辑器
- **封面图：** 上传 `cover.jpg`
- **摘要：** 从 `meta.json` 的 `summary` 字段复制
- **原文链接：** 填写今日新闻中最有价值的一条原文

### 3. 发布

点击「保存并群发」→ 验证身份 → 发布

### 技巧：善用「专辑」

公众号后台创建「AI财经日报」专辑（合集），每天新文都归入此专辑。被关注回复和关键词回复里放这个专辑链接，用户一次点击就能看到所有历史日报。

---

## 第五步：自动回复配置

个人订阅号用**公众号后台**的「自动回复」功能，无需写代码。

### 规则文件：`auto_reply/rules.json`

包含：
- **被关注回复** — 用户关注后立即收到的文字
- **关键词规则** — 触发词 + 对应回复

### 后台配置步骤

1. 登录 mp.weixin.qq.com → 内容与互动 → 自动回复
2. 开启自动回复功能

**被关注回复：**
1. 点击「被关注回复」标签
2. 选择「文字」，粘贴 `rules.json` 中 `subscribe_reply.content`
3. 保存

**关键词自动回复：**
1. 点击「关键词」标签 → 添加规则
2. 对每条规则：
   - 规则名：任意（如"日报查询"）
   - 关键词：粘贴 `rules.json` 中的关键词
   - 匹配方式：全匹配或半匹配（看 `match` 字段）
   - 回复内容：选择文字/图文，粘贴对应内容
3. 保存

### 关键词设计建议

| 关键词 | 匹配 | 回复 | 说明 |
|--------|------|------|------|
| 日报/财经日报/今日财经 | 半匹配 | 专辑链接（图文消息） | 每天发布后确认专辑包含最新文 |
| AI/人工智能 | 半匹配 | 固定文字 + 最新 AI 专题文章链接 | — |
| 盘面/股市 | 半匹配 | 固定文字 + 最新市场分析文章链接 | — |
| 数据/指数 | 半匹配 | 文字 + 常用行情网址 | 长期不变 |

> 专辑链接获取：进入「专辑」→ 复制分享链接。专辑新增文章后链接自动更新。

---

## 完整每日操作清单

| 步骤 | 动作 | 命令/操作 | 耗时 |
|------|------|-----------|------|
| 1 | 等本地计划任务自动跑完（09:15；失败 13:00 / 20:00 自动补跑） | 无需操作 | — |
| 2 | 从 `drafts/` 取当天成品（正文/封面/HTML 都是自动生成的） | 无需操作 | — |
| 3 | （可选）AI 生图替换自动下载的封面 | 直接替换 `drafts/日期/cover.jpg` | 画图耗时 |
| 4 | 登录公众号，粘贴正文+上传封面，发布 | mp.weixin.qq.com 操作 | 5-10min |
| 5 | （首次）配置自动回复 | 按上文步骤，一次性完成 | — |
| 6 | （可选）确认专辑包含最新文章 | 手动添加 | 1min |

---

## 环境变量

配置写在项目根目录 `.env`（已被 git 忽略，不会泄露）：

| 变量 | 用途 | 是否必须 |
|------|------|----------|
| `DEEPSEEK_API_KEY` | DeepSeek 写稿 | 是（第二步） |
| `DEEPSEEK_BASE_URL` | LLM 接口地址（OpenAI 兼容） | 是，默认 `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | 模型名 | 否，默认 `deepseek-chat` |
| `PIXABAY_API_KEY` | 配图搜索 | 是（第三步） |
| `HTTP_PROXY` | 访问 Pixabay/GitHub 需要代理时填写 | 否 |

---

## 切换回 GitHub Actions（可选）

当前两个工作流（`.github/workflows/daily.yml`、`draft.yml`）的定时器**已注释停用**，只有本机在跑。若以后解决了 GitHub 账单问题（Settings → Billing and licensing 里更新支付方式）想切回云端：

1. 取消 `daily.yml` 和 `draft.yml` 中 `schedule:` 两行的注释
2. 在仓库 Settings → Secrets 中确认已有 `DEEPSEEK_API_KEY`、`PIXABAY_API_KEY`
3. 停用本机计划任务：
   ```powershell
   schtasks /Change /TN "FinanceNewsBot-Daily" /DISABLE
   schtasks /Change /TN "FinanceNewsBot-CatchUp-13" /DISABLE
   schtasks /Change /TN "FinanceNewsBot-CatchUp-20" /DISABLE
   # 反悔就改回 /ENABLE
   ```

> 就算忘了停本机任务也不会冲突：runner 发现远端出现当天 bot 提交时会自动让位跳过。

---

## 故障排查

| 现象 | 处理 |
|------|------|
| 当天没生成 `drafts/` | 看 `logs/daily_日期.log` 定位失败步骤；13:00 / 20:00 会自动补跑 |
| 写稿失败（LLM 502 等） | 已内置 3 次重试；仍失败就在补跑窗口自动重试，或手动 `python write_article.py --date 日期` |
| 推送失败（连接被重置） | 已内置 3 次重试；本地数据不丢，下一个补跑窗口自动重推 |
| 电脑上午没开机 | 09:15 漏跑由 13:00 / 20:00 补；整天没开就手动跑一次 `run_daily.ps1` |
| 强制本地跑（跳过 CI 检测） | 运行前设 `FORCE_LOCAL_RUN=1` |
| 日志乱码 | 用 VS Code / `Get-Content -Encoding utf8` 查看 |

---

## 合规提醒

- 所有稿件已标注"AI 基于公开新闻整理，不构成投资建议"
- 新闻引用均附原文链接，尊重版权
- 不建议全文照搬来源文章，当前稿件以摘要+点评为主
- 公众号发布前建议人工复核，避免 AI 幻觉导致事实错误
