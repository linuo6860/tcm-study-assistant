import { useEffect, useState } from "react";

import { getKnowledgeTree } from "../api.js";

function TreeNode({ node }) {
  const hasChildren = node.children && node.children.length > 0;

  return (
    <li className={`tree-node ${node.type}`}>
      <details open={node.type !== "section"}>
        <summary>
          <span>{node.title}</span>
          <small>{node.type}</small>
        </summary>
        {node.key_points?.length > 0 && (
          <div className="keypoint-box">
            {node.key_points.map((point) => (
              <p key={point}>{point}</p>
            ))}
          </div>
        )}
        {node.keywords?.length > 0 && (
          <div className="keyword-row">
            {node.keywords.map((keyword) => (
              <span key={keyword}>{keyword}</span>
            ))}
          </div>
        )}
        {hasChildren && (
          <ul>
            {node.children.map((child) => (
              <TreeNode key={child.id} node={child} />
            ))}
          </ul>
        )}
      </details>
    </li>
  );
}

export default function KnowledgeTree() {
  const [tree, setTree] = useState([]);
  const [status, setStatus] = useState("正在读取教材章节...");

  useEffect(() => {
    let ignore = false;
    getKnowledgeTree()
      .then((data) => {
        if (!ignore) {
          setTree(data);
          setStatus("");
        }
      })
      .catch((error) => {
        if (!ignore) {
          setStatus(error.message);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <section className="panel tree-panel">
      <div className="panel-heading">
        <p className="eyebrow">Knowledge Archive</p>
        <h2>按书本章节展示知识点树</h2>
      </div>

      {status && <p className="status-text">{status}</p>}
      <ul className="knowledge-tree">
        {tree.map((node) => (
          <TreeNode key={node.id} node={node} />
        ))}
      </ul>
    </section>
  );
}

