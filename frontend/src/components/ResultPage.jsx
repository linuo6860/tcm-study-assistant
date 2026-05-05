import { useState } from "react";

import { saveQuestion } from "../api.js";
import QuestionCard from "./QuestionCard.jsx";

export default function ResultPage({ explanation, rawOcr, onBack }) {
  const [saveStatus, setSaveStatus] = useState("");

  async function handleSave() {
    if (!explanation) {
      return;
    }
    setSaveStatus("正在保存...");
    try {
      const result = await saveQuestion({
        raw_ocr: rawOcr,
        explanation,
        is_wrong: true,
        note: "前端上传页面保存",
      });
      setSaveStatus(`${result.message} ID: ${result.id}`);
    } catch (error) {
      setSaveStatus(error.message);
    }
  }

  if (!explanation) {
    return (
      <section className="panel empty-state">
        <h2>还没有讲解结果</h2>
        <p>先去“题图识别”上传截图，或粘贴题干和选项生成解析。</p>
        <button className="primary-button" onClick={onBack}>返回上传</button>
      </section>
    );
  }

  return (
    <section className="panel result-panel">
      <div className="result-toolbar">
        <div>
          <p className="eyebrow">Structured Answer</p>
          <h2>本题讲解</h2>
        </div>
        <button className="primary-button" onClick={handleSave}>保存为错题</button>
      </div>

      <QuestionCard explanation={explanation} />
      {saveStatus && <p className="status-text">{saveStatus}</p>}
    </section>
  );
}

