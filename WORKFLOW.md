# 工作流程

从新闻抓取到公众号发布的完整流水线。

---

## 整体流程

```
 ① 每日自动爬取  ②  AI 写稿  ③  生成封面  ④  半自动发布  ⑤  自动回复
 (GitHub Actions)   (DeepSeek)   (Pillow/生图API) (粘贴进后台)  (后台配置)
       │                 │              │                │               │
 data/finance_*.json   article.md   cover.jpg      mp.weixin.qq.com   后台自动回复
                       cover.jpg                       草稿箱 → 发布     rules.json
```

---

## 第一步：每日自动爬取（已就绪）

GitHub Actions 每天 UTC+8 09:00 自动运行 `finance_crawler.py`，产出：

- `data/finance_YYYY-MM-DD.json` — 原始结构化数据（约 1000+ 条）
- `daily/YYYY-MM-DD.md` — 分类 Markdown 日报

**数据字段：** `title` / `url` / `publish_time` / `category` / `source_site` / `intro`（摘要）/ `content`（正文）

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
├── article.md          # 观点点评文章 Markdown（含 [配图：xxx] 占位）
├── cover_prompt.txt    # 封面提示词（拿它去 AI 生图工具跑图）
└── meta.json           # 结构化元数据
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
| 1 | 等 GitHub Actions 自动跑完 | 无需操作 | — |
| 2 | AI 生成稿件 | `python write_article.py --date $(date -d yesterday +%F)` | ~10s |
| 3 | 用你的 AI 工具跑封面/插图 | 复制 `cover_prompt.txt` 到生图工具 | 画图耗时 |
| 4 | 登录公众号，粘贴正文+上传封面，发布 | mp.weixin.qq.com 操作 | 5-10min |
| 5 | （首次）配置自动回复 | 按上文步骤，一次性完成 | — |
| 6 | （可选）确认专辑包含最新文章 | 手动添加 | 1min |

---

## 环境变量

| 变量 | 用途 | 是否必须 |
|------|------|----------|
| `DEEPSEEK_API_KEY` | DeepSeek 写稿 | 是（第二步） |

---

## GitHub Actions 自动化草稿（可选）

`.github/workflows/draft.yml` 会在每天爬取后自动生成草稿并提交到 `drafts/` 目录，你只需登录公众号粘贴发布。

启用方法：在仓库 Settings → Secrets 中添加 `DEEPSEEK_API_KEY`。

---

## 合规提醒

- 所有稿件已标注"AI 基于公开新闻整理，不构成投资建议"
- 新闻引用均附原文链接，尊重版权
- 不建议全文照搬来源文章，当前稿件以摘要+点评为主
- 公众号发布前建议人工复核，避免 AI 幻觉导致事实错误
