import { useState } from "react";

import { explainQuestion, runOcr, uploadImage } from "../api.js";

function splitQuestionAndOptions(text) {
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  const options = [];
  const questionLines = [];
  const optionPattern = /^([A-EＡ-Ｅ])[\.\。．、:：]?\s*(.+)$/i;

  for (const line of lines) {
    const match = line.match(optionPattern);
    if (match) {
      const fullWidth = "ＡＢＣＤＥ";
      const ascii = "ABCDE";
      const rawLabel = match[1].toUpperCase();
      const label = fullWidth.includes(rawLabel) ? ascii[fullWidth.indexOf(rawLabel)] : rawLabel;
      options.push({ label, text: match[2].trim() });
    } else {
      questionLines.push(line);
    }
  }

  return {
    question: questionLines.join("\n") || text,
    options,
  };
}

export default function UploadPage({ onExplained }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [ocrText, setOcrText] = useState("");
  const [ocrEngine, setOcrEngine] = useState("");
  const [warning, setWarning] = useState("");
  const [status, setStatus] = useState("等待上传题目截图");
  const [loading, setLoading] = useState(false);

  function handleFileChange(event) {
    const nextFile = event.target.files?.[0];
    setFile(nextFile || null);
    setOcrText("");
    setOcrEngine("");
    setWarning("");
    setStatus(nextFile ? "已选择图片，可以开始 OCR" : "等待上传题目截图");
    setPreview(nextFile ? URL.createObjectURL(nextFile) : "");
  }

  async function handleOcr() {
    if (!file) {
      setStatus("请先选择一张题目截图");
      return;
    }

    setLoading(true);
    setStatus("正在上传图片并执行 OCR...");
    try {
      const uploaded = await uploadImage(file);
      const result = await runOcr(uploaded.upload_id);
      setOcrText(result.text);
      setOcrEngine(result.engine || "");
      setWarning(result.warning || "");
      setStatus(result.warning ? "OCR 返回了校对文本，请检查识别环境" : "真实 OCR 完成，请校对题干和选项后生成讲解");
    } catch (error) {
      setStatus(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleExplain() {
    if (!ocrText.trim()) {
      setStatus("请先完成 OCR，或直接粘贴题干和选项");
      return;
    }

    setLoading(true);
    setStatus("正在检索教材并生成解析...");
    try {
      const payload = splitQuestionAndOptions(ocrText);
      const result = await explainQuestion({ ...payload, top_k: 3 });
      onExplained(result, ocrText);
      setStatus("讲解已生成");
    } catch (error) {
      setStatus(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="workspace-grid">
      <div className="panel upload-panel">
        <div className="panel-heading">
          <p className="eyebrow">Step 01</p>
          <h2>上传题目截图</h2>
        </div>

        <label className="drop-zone">
          <input type="file" accept="image/*" onChange={handleFileChange} />
          {preview ? (
            <img src={preview} alt="题目截图预览" />
          ) : (
            <span>拖入或点击选择中医考试题截图</span>
          )}
        </label>

        <div className="upload-actions">
          <label className="secondary-button">
            手机拍照
            <input type="file" accept="image/*" capture="environment" onChange={handleFileChange} />
          </label>
          <label className="secondary-button">
            相册选择
            <input type="file" accept="image/*" onChange={handleFileChange} />
          </label>
        </div>

        <button className="primary-button" onClick={handleOcr} disabled={loading}>
          {loading ? "处理中..." : "上传并真实 OCR"}
        </button>

        <p className="status-text">{status}</p>
        {ocrEngine && <p className="status-text">OCR 引擎：{ocrEngine}</p>}
        {warning && <p className="warning-text">{warning}</p>}
        <p className="hint-text">手机建议竖屏拍题目，保持四边完整、文字清晰，拍完后仍可在右侧手动校正。</p>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <p className="eyebrow">Step 02</p>
          <h2>校对 OCR 文本</h2>
        </div>
        <textarea
          value={ocrText}
          onChange={(event) => setOcrText(event.target.value)}
          placeholder={"可直接粘贴题干和选项，例如：\n下列哪项最能体现阴阳互根关系？\nA. 阴阳对立\nB. 阴阳互根\nC. 阴阳消长\nD. 阴阳转化"}
        />
        <button className="accent-button" onClick={handleExplain} disabled={loading}>
          生成答案讲解
        </button>
      </div>
    </section>
  );
}
