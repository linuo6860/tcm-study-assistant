# 中医题目学习助手

一个面向中医考试刷题复盘的学习助手原型。用户上传题目截图后，系统通过 OCR 识别题干和选项，从本地教材知识库检索相关章节，并生成答案、教材依据、选项解析、记忆口诀和归档章节。

## 项目目录

```text
tcm-study-assistant/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py
│   │   ├── data/
│   │   │   └── textbooks/
│   │   │       └── sample_tcm_textbook.json
│   │   ├── models/
│   │   │   └── schemas.py
│   │   ├── services/
│   │   │   ├── explainer.py
│   │   │   ├── knowledge_base.py
│   │   │   ├── ocr.py
│   │   │   └── storage.py
│   │   ├── uploads/
│   │   ├── db.py
│   │   └── main.py
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx
        ├── api.js
        ├── main.jsx
        ├── styles.css
        └── components/
            ├── KnowledgeTree.jsx
            ├── QuestionCard.jsx
            ├── ResultPage.jsx
            └── UploadPage.jsx
```

## 核心能力

- 图片上传接口：保存考试题截图并返回 `upload_id`。
- OCR 识别接口：使用 PaddleOCR 识别图片文字；未安装 PaddleOCR 时返回可编辑的占位文本，便于开发前端闭环。
- 教材知识库检索接口：从 JSON 教材知识库检索相关章节、段落和关键词。
- 答案讲解生成接口：基于检索结果生成固定格式讲解。
- 错题和知识点保存接口：用 SQLite 保存错题、OCR 文本、讲解结果和归档章节。
- React 页面：上传截图、编辑 OCR 文本、查看讲解结果、查看章节知识点树。

## 后端启动

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

接口文档启动后访问：

```text
http://127.0.0.1:8000/docs
```

> PaddleOCR 依赖较重。第一轮开发可以先不装或先用占位 OCR；需要真实识别时再安装 `paddleocr` 与对应运行环境。

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

默认请求后端：

```text
http://127.0.0.1:8000
```

如需修改后端地址：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/upload` | 上传题目截图 |
| `POST` | `/api/ocr` | 根据 `upload_id` 执行 OCR |
| `POST` | `/api/retrieve` | 检索教材知识库 |
| `POST` | `/api/explain` | 生成答案讲解 |
| `POST` | `/api/questions/save` | 保存错题与知识点 |
| `GET` | `/api/questions/saved` | 查看已保存题目 |
| `GET` | `/api/knowledge/tree` | 按教材章节查看知识点树 |

## 每题输出格式

```text
【题目】
【答案】
【教材依据】
【为什么选这个】
【为什么不选其他】
【一句话记忆】
【归档章节】
```

## 后续建议

1. 将 JSON 示例教材替换为正式教材切片，保留 `book -> chapter -> section` 层级。
2. 检索层从关键词匹配升级为 SQLite FTS5 或向量数据库。
3. 讲解生成层接入大模型时，保留当前结构化输出 schema，避免答案格式漂移。
4. OCR 结果建议增加人工校对步骤，因为考试截图常含表格、标点、省略号和多栏排版。

## 手机端云部署

手机浏览器访问需要公网地址，因此推荐：

- 前端：GitHub Pages，托管 React/Vite 构建后的静态网页。
- 后端：Render Web Service，托管 FastAPI API。
- 数据：第一版仍用 JSON + SQLite。Render 免费服务的文件系统适合测试；如果要长期保存错题，建议后续加 Render Disk、PostgreSQL 或同步到云盘。

### 1. 部署后端到 Render

把项目推送到 GitHub 后，在 Render 新建 Web Service，选择该仓库。如果 Render 识别到仓库根目录的 `render.yaml`，可以按 Blueprint 部署；也可以手动填写：

```text
Root Directory: backend
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health Check Path: /health
```

环境变量：

```text
CORS_ORIGINS=https://linuo6860.github.io
TCM_STORAGE_DIR=/tmp/tcm-study-assistant
TCM_UPLOAD_DIR=/tmp/tcm-study-assistant/uploads
```

部署成功后，Render 会给你一个类似下面的后端地址：

```text
https://tcm-study-assistant-api.onrender.com
```

### 2. 部署前端到 GitHub Pages

在 GitHub 仓库中进入 `Settings -> Pages`，把 `Build and deployment` 的 `Source` 设为 `GitHub Actions`。

然后进入 `Settings -> Secrets and variables -> Actions -> Variables`，新增变量：

```text
VITE_API_BASE_URL=https://你的-render-后端地址.onrender.com
```

推送到 `main` 分支后，`.github/workflows/deploy-frontend-pages.yml` 会自动构建 `frontend/` 并发布到 GitHub Pages。

如果仓库名是 `tcm-study-assistant`，前端地址通常是：

```text
https://linuo6860.github.io/tcm-study-assistant/
```

### 3. 关于云端 PaddleOCR

当前云部署默认使用轻量依赖，先保证网页、教材检索、讲解和保存接口能上线。PaddleOCR 已放在 `backend/requirements-ocr.txt` 作为可选依赖；云端真实 OCR 对内存、启动时间和系统库要求更高，建议后续单独做 Docker 镜像或换成云 OCR API。
