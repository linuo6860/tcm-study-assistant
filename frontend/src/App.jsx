import { useState } from "react";

import KnowledgeTree from "./components/KnowledgeTree.jsx";
import ResultPage from "./components/ResultPage.jsx";
import UploadPage from "./components/UploadPage.jsx";

const tabs = [
  { id: "upload", label: "题图识别" },
  { id: "result", label: "讲解结果" },
  { id: "tree", label: "章节归档" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState("upload");
  const [ocrText, setOcrText] = useState("");
  const [explanation, setExplanation] = useState(null);

  function handleExplained(nextExplanation, nextOcrText) {
    setExplanation(nextExplanation);
    setOcrText(nextOcrText);
    setActiveTab("result");
  }

  return (
    <main className="app-shell">
      <section className="hero-card">
        <div>
          <p className="eyebrow">TCM Exam Companion</p>
          <h1>中医题目学习助手</h1>
          <p className="hero-copy">
            上传题目截图，自动识别、检索教材、生成解析，并按书本章节沉淀知识点。
          </p>
        </div>
        <div className="hero-seal">岐黄<br />题库</div>
      </section>

      <nav className="tabs" aria-label="功能导航">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={activeTab === tab.id ? "active" : ""}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "upload" && <UploadPage onExplained={handleExplained} />}
      {activeTab === "result" && (
        <ResultPage explanation={explanation} rawOcr={ocrText} onBack={() => setActiveTab("upload")} />
      )}
      {activeTab === "tree" && <KnowledgeTree />}
    </main>
  );
}

