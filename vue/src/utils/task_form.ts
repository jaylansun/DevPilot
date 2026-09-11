import type {
  TaskCreateQO,
  TaskUpdateQO,
  TaskStatus,
  TaskVO,
} from "@/types/api";

export const TASK_COLUMNS: {
  status: TaskStatus;
  label: string;
  hint: string;
}[] = [
  { status: "todo", label: "待办", hint: "准备好后，从这里开始" },
  { status: "in_progress", label: "进行中", hint: "专注正在推进的工作" },
  { status: "done", label: "已完成", hint: "每一次完成，都算数" },
];

export const PRIORITIES = [
  { value: 1, label: "P1 · 最高" },
  { value: 2, label: "P2 · 较高" },
  { value: 3, label: "P3 · 普通" },
  { value: 4, label: "P4 · 较低" },
  { value: 5, label: "P5 · 最低" },
];

export type TaskForm = {
  title: string;
  description: string;
  status: TaskStatus;
  priority: number;
  acceptance_criteria: string;
};

export function newTaskForm(
  status: TaskStatus = "todo",
  priority = 3,
): TaskForm {
  return {
    title: "",
    description: "",
    status,
    priority,
    acceptance_criteria: "",
  };
}

export function taskToForm(task: TaskVO): TaskForm {
  const { title, description, status, priority, acceptance_criteria } = task;
  return { title, description, status, priority, acceptance_criteria };
}

export function toCreateQO(form: TaskForm): TaskCreateQO {
  return {
    ...form,
    title: form.title.trim(),
    description: form.description.trim(),
    acceptance_criteria: form.acceptance_criteria.trim(),
  };
}

export function toUpdateQO(
  original: TaskVO,
  form: TaskForm,
): TaskUpdateQO | null {
  const values = toCreateQO(form);
  // 保留用户开始编辑时的版本，只发送发生变化的字段。
  const changes = Object.fromEntries(
    Object.entries(values).filter(
      ([key, value]) => original[key as keyof TaskForm] !== value,
    ),
  );
  return Object.keys(changes).length
    ? { version: original.version, ...changes }
    : null;
}
