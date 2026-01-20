/**
 * 管理赛道对话框 - 允许添加新的赛道分类
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../utils/api";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export function ManageSectorsDialog({ isOpen, onClose }: Props) {
  const [newSectorName, setNewSectorName] = useState("");
  const [error, setError] = useState("");
  const queryClient = useQueryClient();

  const addSectorMutation = useMutation({
    mutationFn: async (name: string) => {
      const response = await apiFetch("/api/sectors/list/available", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "添加失败");
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["available-sectors"] });
      setNewSectorName("");
      setError("");
      alert("添加成功！");
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newSectorName.trim();
    if (!trimmed) {
      setError("赛道名称不能为空");
      return;
    }
    addSectorMutation.mutate(trimmed);
  };

  if (!isOpen) return null;

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-content" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h3 className="dialog-title">管理赛道</h3>
          <button className="dialog-close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="dialog-body">
          <form onSubmit={handleSubmit} className="sector-form">
            <div className="sector-form__group">
              <label className="sector-form__label">新增赛道：</label>
              <input
                type="text"
                className="sector-form__input"
                value={newSectorName}
                onChange={(e) => {
                  setNewSectorName(e.target.value);
                  setError("");
                }}
                placeholder="输入赛道名称"
                disabled={addSectorMutation.isPending}
              />
            </div>

            {error && (
              <div className="sector-form__error">{error}</div>
            )}

            <div className="sector-form__actions">
              <button
                type="submit"
                className="sector-form__btn sector-form__btn--primary"
                disabled={addSectorMutation.isPending}
              >
                {addSectorMutation.isPending ? "添加中..." : "添加"}
              </button>
              <button
                type="button"
                className="sector-form__btn sector-form__btn--secondary"
                onClick={onClose}
              >
                关闭
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
