import { useState } from "react";
import { apiFetch } from "../utils/api";

interface BoardSyncStatus {
  isBuilding: boolean;
  isVerifying: boolean;
  lastBuildTime: string | null;
  message: string;
}

export function BoardSyncButton() {
  const [status, setStatus] = useState<BoardSyncStatus>({
    isBuilding: false,
    isVerifying: false,
    lastBuildTime: null,
    message: ""
  });

  const buildMappings = async () => {
    setStatus(prev => ({
      ...prev,
      isBuilding: true,
      message: "构建板块映射中...(耗时较长，概念+行业)"
    }));

    try {
      const response = await apiFetch("/api/boards/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ board_types: ["industry", "concept"] })
      });

      const data = await response.json();

      if (response.ok) {
        setStatus({
          isBuilding: false,
          isVerifying: false,
          lastBuildTime: new Date().toLocaleString("zh-CN"),
          message: `✓ ${data.message}`
        });
      } else {
        throw new Error(data.detail || "构建失败");
      }
    } catch (error) {
      setStatus(prev => ({
        ...prev,
        isBuilding: false,
        message: `✗ 错误: ${error instanceof Error ? error.message : String(error)}`
      }));
    }
  };

  const verifyChanges = async () => {
    setStatus(prev => ({ ...prev, isVerifying: true, message: "验证板块变化中..." }));

    try {
      // 验证"银行"板块作为示例
      const response = await apiFetch("/api/boards/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          board_name: "银行",
          board_type: "industry"
        })
      });

      const data = await response.json();

      if (response.ok) {
        let message = "✓ 板块验证完成";
        if (data.has_changes) {
          message += ` | 变化: +${data.added.length} -${data.removed.length}`;
        } else {
          message += " | 无变化";
        }

        setStatus(prev => ({
          ...prev,
          isVerifying: false,
          message
        }));
      } else {
        throw new Error(data.detail || "验证失败");
      }
    } catch (error) {
      setStatus(prev => ({
        ...prev,
        isVerifying: false,
        message: `✗ 错误: ${error instanceof Error ? error.message : String(error)}`
      }));
    }
  };

  return (
    <div className="board-sync">
      <div className="board-sync__buttons">
        <button
          onClick={buildMappings}
          disabled={status.isBuilding || status.isVerifying}
          className={`board-sync__button board-sync__button--build ${status.isBuilding ? 'board-sync__button--loading' : ''}`}
        >
          {status.isBuilding ? "构建中..." : "构建板块映射"}
        </button>

        <button
          onClick={verifyChanges}
          disabled={status.isBuilding || status.isVerifying}
          className={`board-sync__button board-sync__button--verify ${status.isVerifying ? 'board-sync__button--loading' : ''}`}
        >
          {status.isVerifying ? "验证中..." : "验证变化"}
        </button>
      </div>

      {status.message && (
        <span className={`board-sync__message ${status.message.startsWith("✓") ? 'board-sync__message--success' : 'board-sync__message--error'}`}>
          {status.message}
        </span>
      )}

      {status.lastBuildTime && (
        <span className="board-sync__timestamp">
          上次构建: {status.lastBuildTime}
        </span>
      )}
    </div>
  );
}
