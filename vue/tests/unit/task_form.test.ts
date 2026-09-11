import { describe, expect, it } from "vitest";
import {
  newTaskForm,
  taskToForm,
  toCreateQO,
  toUpdateQO,
} from "@/utils/task_form";
import type { TaskVO } from "@/types/api";

const task: TaskVO = {
  id: "task-id",
  project_id: "project-id",
  title: "完成购物车",
  description: "支持修改数量",
  priority: 3,
  status: "todo",
  acceptance_criteria: "总价正确",
  source: "manual",
  version: 7,
  created_at: "2026-09-11T00:00:00Z",
  updated_at: "2026-09-11T00:00:00Z",
};

describe("任务表单与局部更新", () => {
  it("新建表单使用看板指定的初始状态和优先级", () => {
    expect(newTaskForm("in_progress", 1)).toMatchObject({
      status: "in_progress",
      priority: 1,
      title: "",
      acceptance_criteria: "",
    });
  });
  it("提交时清理文本首尾空白，不修改原始表单", () => {
    const form = {
      ...newTaskForm(),
      title: "  标题  ",
      description: " 内容\n",
      acceptance_criteria: " 标准 ",
    };
    expect(toCreateQO(form)).toMatchObject({
      title: "标题",
      description: "内容",
      acceptance_criteria: "标准",
    });
    expect(form.title).toBe("  标题  ");
  });
  it("没有变化时不发送只带版本的非法更新", () => {
    expect(toUpdateQO(task, taskToForm(task))).toBeNull();
    expect(
      toUpdateQO(task, { ...taskToForm(task), title: " 完成购物车 " }),
    ).toBeNull();
  });
  it("只提交修改字段并保留开始编辑时的版本", () => {
    expect(
      toUpdateQO(task, { ...taskToForm(task), priority: 1, status: "done" }),
    ).toEqual({ version: 7, priority: 1, status: "done" });
  });
  it("清空说明时仍发送空字符串，不遗漏用户的删除操作", () => {
    expect(
      toUpdateQO(task, {
        ...taskToForm(task),
        description: "",
        acceptance_criteria: "",
      }),
    ).toEqual({ version: 7, description: "", acceptance_criteria: "" });
  });
});
