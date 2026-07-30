"""
问卷星自动填写工具的中文桌面启动界面。

该界面只负责读取配置、覆盖本次运行参数、展示题目规则和实时日志；
实际答案生成及浏览器操作仍由 wenjuanxing_auto.WJXSubmitter 完成。
"""

import copy
import logging
import os
import pprint
import queue
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    from wenjuanxing_auto import WJXSubmitter, load_config_from_py
except ImportError:
    from src.wenjuanxing_auto import WJXSubmitter, load_config_from_py


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.py"
DEFAULT_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
)

QUESTION_TYPE_OPTIONS = {
    "单选（范围随机）": "single_choice_random_int",
    "单选（定制比例）": "single_choice_probabilities",
    "多选（范围随机）": "Multiple_choices_random_int",
    "多选（独立概率）": "Multiple_choices_probabilities",
}
QUESTION_TYPE_NAMES = {value: key for key, value in QUESTION_TYPE_OPTIONS.items()}


class QueueLogHandler(logging.Handler):
    """把后台线程产生的日志转发给 Tkinter 主线程。"""

    def __init__(self, event_queue):
        super().__init__()
        self.event_queue = event_queue

    def emit(self, record):
        try:
            self.event_queue.put(("log", self.format(record)))
        except Exception:
            self.handleError(record)


def describe_question_type(question_type):
    """将内部题型名称转换为便于阅读的中文。"""

    return QUESTION_TYPE_NAMES.get(question_type, question_type or "未设置")


def describe_answer_rule(question):
    """生成题目规则的简短中文说明。"""

    question_type = question.get("type")
    logic = question.get("answer_logic") or {}
    if question_type in {"single_choice_random_int", "Multiple_choices_random_int"}:
        return f"选项 {logic.get('min', '?')}～{logic.get('max', '?')}"
    if question_type in {"single_choice_probabilities", "Multiple_choices_probabilities"}:
        probabilities = logic.get("probabilities") or []
        try:
            return " / ".join(f"{float(value):.0%}" for value in probabilities)
        except (TypeError, ValueError):
            return "概率配置无效"
    return "无法识别"


def parse_probability_text(text):
    """
    解析用户输入的概率。

    同时支持 0.2,0.5,0.3 和 20%,50%,30% 两种写法。
    """

    normalized = text.replace("，", ",").strip()
    if not normalized:
        raise ValueError("请填写每个选项的概率。")

    values = []
    for raw_value in normalized.split(","):
        raw_value = raw_value.strip()
        if not raw_value:
            raise ValueError("概率之间不能出现空值。")
        try:
            if raw_value.endswith("%"):
                value = float(raw_value[:-1].strip()) / 100
            else:
                value = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"无法识别概率：{raw_value}") from exc
        if not 0 <= value <= 1:
            raise ValueError(f"概率必须在 0%～100% 之间：{raw_value}")
        values.append(value)
    return values


def build_config_text(config):
    """将配置字典转换为可直接加载的 Python 配置文件内容。"""

    formatted = pprint.pformat(config, indent=2, width=120, sort_dicts=False)
    return "# 问卷星配置文件（由图形界面生成）\n\nconfig_data = " + formatted + "\n"


class QuestionEditorDialog:
    """新增或编辑一道题目的弹窗。"""

    def __init__(self, parent, existing_ids, question=None):
        self.result = None
        self.original_id = str((question or {}).get("id", ""))
        self.existing_ids = {str(value) for value in existing_ids}

        self.window = tk.Toplevel(parent)
        self.window.title("编辑题目" if question else "添加题目")
        self.window.geometry("620x520")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        question = copy.deepcopy(question or {})
        answer_logic = question.get("answer_logic") or {}
        condition = question.get("condition") or {}

        self.id_var = tk.StringVar(value=str(question.get("id", "")))
        self.description_var = tk.StringVar(value=str(question.get("description", "")))
        self.type_var = tk.StringVar(
            value=describe_question_type(question.get("type"))
            if question.get("type")
            else "单选（定制比例）"
        )
        self.min_var = tk.StringVar(value=str(answer_logic.get("min", "1")))
        self.max_var = tk.StringVar(value=str(answer_logic.get("max", "2")))
        probabilities = answer_logic.get("probabilities") or []
        self.probabilities_var = tk.StringVar(
            value=", ".join(f"{float(value):g}" for value in probabilities)
        )
        self.conditional_var = tk.BooleanVar(value=bool(question.get("is_conditional", False)))
        self.condition_question_var = tk.StringVar(value=str(condition.get("on_question_id", "")))
        self.condition_answers_var = tk.StringVar(
            value=", ".join(str(value) for value in condition.get("is_one_of_answers", []))
        )

        self._build_ui()
        self._refresh_rule_fields()
        self._refresh_condition_fields()
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        self.window.wait_window()

    def _build_ui(self):
        """创建题目编辑表单。"""

        frame = ttk.Frame(self.window, padding=18)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="题号").grid(row=0, column=0, sticky=tk.W, pady=6)
        ttk.Entry(frame, textvariable=self.id_var).grid(row=0, column=1, sticky=tk.EW, pady=6)
        ttk.Label(frame, text="需与问卷页面题号一致，例如 1、2、3。").grid(
            row=0, column=2, sticky=tk.W, padx=(8, 0)
        )

        ttk.Label(frame, text="题目说明").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Entry(frame, textvariable=self.description_var).grid(
            row=1, column=1, columnspan=2, sticky=tk.EW, pady=6
        )

        ttk.Label(frame, text="题型").grid(row=2, column=0, sticky=tk.W, pady=6)
        type_box = ttk.Combobox(
            frame,
            textvariable=self.type_var,
            values=list(QUESTION_TYPE_OPTIONS),
            state="readonly",
        )
        type_box.grid(row=2, column=1, columnspan=2, sticky=tk.EW, pady=6)
        type_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_rule_fields())

        ttk.Separator(frame).grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=12)

        ttk.Label(frame, text="最小选项号").grid(row=4, column=0, sticky=tk.W, pady=6)
        self.min_entry = ttk.Entry(frame, textvariable=self.min_var)
        self.min_entry.grid(row=4, column=1, sticky=tk.EW, pady=6)

        ttk.Label(frame, text="最大选项号").grid(row=5, column=0, sticky=tk.W, pady=6)
        self.max_entry = ttk.Entry(frame, textvariable=self.max_var)
        self.max_entry.grid(row=5, column=1, sticky=tk.EW, pady=6)

        ttk.Label(frame, text="选项概率").grid(row=6, column=0, sticky=tk.W, pady=6)
        self.probabilities_entry = ttk.Entry(frame, textvariable=self.probabilities_var)
        self.probabilities_entry.grid(row=6, column=1, columnspan=2, sticky=tk.EW, pady=6)
        ttk.Label(
            frame,
            text="按选项顺序填写，例如：20%, 50%, 30% 或 0.2, 0.5, 0.3",
        ).grid(row=7, column=1, columnspan=2, sticky=tk.W)

        ttk.Separator(frame).grid(row=8, column=0, columnspan=3, sticky=tk.EW, pady=12)

        condition_check = ttk.Checkbutton(
            frame,
            text="这是条件题",
            variable=self.conditional_var,
            command=self._refresh_condition_fields,
        )
        condition_check.grid(row=9, column=0, columnspan=3, sticky=tk.W, pady=6)

        ttk.Label(frame, text="依赖题号").grid(row=10, column=0, sticky=tk.W, pady=6)
        self.condition_question_entry = ttk.Entry(frame, textvariable=self.condition_question_var)
        self.condition_question_entry.grid(row=10, column=1, sticky=tk.EW, pady=6)
        ttk.Label(frame, text="前置题的题号").grid(row=10, column=2, sticky=tk.W, padx=(8, 0))

        ttk.Label(frame, text="触发答案").grid(row=11, column=0, sticky=tk.W, pady=6)
        self.condition_answers_entry = ttk.Entry(frame, textvariable=self.condition_answers_var)
        self.condition_answers_entry.grid(row=11, column=1, sticky=tk.EW, pady=6)
        ttk.Label(frame, text="例如：1, 2").grid(row=11, column=2, sticky=tk.W, padx=(8, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=12, column=0, columnspan=3, sticky=tk.E, pady=(20, 0))
        ttk.Button(buttons, text="取消", command=self.window.destroy).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="保存题目", style="Primary.TButton", command=self._save).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

    def _refresh_rule_fields(self):
        """根据题型切换范围输入或概率输入。"""

        question_type = QUESTION_TYPE_OPTIONS.get(self.type_var.get())
        uses_range = question_type in {
            "single_choice_random_int",
            "Multiple_choices_random_int",
        }
        self.min_entry.configure(state=tk.NORMAL if uses_range else tk.DISABLED)
        self.max_entry.configure(state=tk.NORMAL if uses_range else tk.DISABLED)
        self.probabilities_entry.configure(state=tk.DISABLED if uses_range else tk.NORMAL)

    def _refresh_condition_fields(self):
        """启用或关闭条件题输入框。"""

        state = tk.NORMAL if self.conditional_var.get() else tk.DISABLED
        self.condition_question_entry.configure(state=state)
        self.condition_answers_entry.configure(state=state)

    def _save(self):
        """校验输入并生成一道题目的配置字典。"""

        question_id = self.id_var.get().strip()
        if not question_id:
            messagebox.showerror("题目配置错误", "题号不能为空。", parent=self.window)
            return
        if question_id != self.original_id and question_id in self.existing_ids:
            messagebox.showerror("题目配置错误", f"题号 {question_id} 已经存在。", parent=self.window)
            return

        question_type = QUESTION_TYPE_OPTIONS.get(self.type_var.get())
        if not question_type:
            messagebox.showerror("题目配置错误", "请选择有效题型。", parent=self.window)
            return

        answer_logic = {}
        if question_type in {"single_choice_random_int", "Multiple_choices_random_int"}:
            try:
                min_value = int(self.min_var.get())
                max_value = int(self.max_var.get())
            except ValueError:
                messagebox.showerror("题目配置错误", "最小和最大选项号必须为整数。", parent=self.window)
                return
            if min_value <= 0 or max_value < min_value:
                messagebox.showerror(
                    "题目配置错误",
                    "选项号必须大于 0，且最大选项号不能小于最小选项号。",
                    parent=self.window,
                )
                return
            answer_logic = {"min": min_value, "max": max_value}
        else:
            try:
                probabilities = parse_probability_text(self.probabilities_var.get())
            except ValueError as exc:
                messagebox.showerror("题目配置错误", str(exc), parent=self.window)
                return
            if question_type == "single_choice_probabilities" and abs(sum(probabilities) - 1) > 0.001:
                messagebox.showerror(
                    "题目配置错误",
                    f"单选题概率合计必须为 100%，当前为 {sum(probabilities):.2%}。",
                    parent=self.window,
                )
                return
            if question_type == "Multiple_choices_probabilities" and not any(probabilities):
                messagebox.showerror(
                    "题目配置错误",
                    "多选题至少要有一个选项的概率大于 0%。",
                    parent=self.window,
                )
                return
            answer_logic = {
                "options_count": len(probabilities),
                "probabilities": probabilities,
            }

        result = {
            "id": question_id,
            "description": self.description_var.get().strip(),
            "type": question_type,
            "answer_logic": answer_logic,
        }

        if self.conditional_var.get():
            condition_question = self.condition_question_var.get().strip()
            condition_answers = [
                value.strip()
                for value in self.condition_answers_var.get().replace("，", ",").split(",")
                if value.strip()
            ]
            if not condition_question or not condition_answers:
                messagebox.showerror(
                    "题目配置错误",
                    "条件题必须填写依赖题号和至少一个触发答案。",
                    parent=self.window,
                )
                return
            result["is_conditional"] = True
            result["condition"] = {
                "on_question_id": condition_question,
                "is_one_of_answers": condition_answers,
            }

        self.result = result
        self.window.destroy()


class ConfigCreatorDialog:
    """通过图形界面创建一套新的问卷配置。"""

    def __init__(self, parent, on_saved):
        self.parent = parent
        self.on_saved = on_saved
        self.questions = []

        self.window = tk.Toplevel(parent)
        self.window.title("创建新问卷配置")
        self.window.geometry("940x680")
        self.window.minsize(820, 600)
        self.window.transient(parent)
        self.window.grab_set()

        self.url_var = tk.StringVar()
        self.submission_count_var = tk.StringVar(value="1")
        self.min_delay_var = tk.StringVar(value="70")
        self.max_delay_var = tk.StringVar(value="180")
        self.headless_var = tk.BooleanVar(value=False)

        self._build_ui()

    def _build_ui(self):
        """创建问卷基本信息、题目列表和保存按钮。"""

        outer = ttk.Frame(self.window, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.rowconfigure(3, weight=1)
        outer.columnconfigure(0, weight=1)

        ttk.Label(outer, text="创建新问卷配置", style="Title.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            outer,
            text="先填写问卷链接，再按页面顺序添加每一道题目。",
        ).grid(row=1, column=0, sticky=tk.W, pady=(2, 12))

        info = ttk.LabelFrame(outer, text="问卷基本信息", padding=10)
        info.grid(row=2, column=0, sticky=tk.EW)
        info.columnconfigure(1, weight=1)

        ttk.Label(info, text="问卷链接").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=5)
        ttk.Entry(info, textvariable=self.url_var).grid(
            row=0, column=1, columnspan=7, sticky=tk.EW, pady=5
        )
        ttk.Label(info, text="默认提交份数").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=5)
        ttk.Spinbox(info, from_=1, to=100000, width=9, textvariable=self.submission_count_var).grid(
            row=1, column=1, sticky=tk.W, pady=5
        )
        ttk.Label(info, text="最小延时（秒）").grid(row=1, column=2, sticky=tk.W, padx=(24, 8), pady=5)
        ttk.Entry(info, width=10, textvariable=self.min_delay_var).grid(row=1, column=3, sticky=tk.W, pady=5)
        ttk.Label(info, text="最大延时（秒）").grid(row=1, column=4, sticky=tk.W, padx=(24, 8), pady=5)
        ttk.Entry(info, width=10, textvariable=self.max_delay_var).grid(row=1, column=5, sticky=tk.W, pady=5)
        ttk.Checkbutton(info, text="无头模式", variable=self.headless_var).grid(
            row=1, column=6, columnspan=2, sticky=tk.W, padx=(24, 0), pady=5
        )

        question_frame = ttk.LabelFrame(outer, text="题目配置", padding=10)
        question_frame.grid(row=3, column=0, sticky=tk.NSEW, pady=(12, 0))
        question_frame.rowconfigure(0, weight=1)
        question_frame.columnconfigure(0, weight=1)

        columns = ("id", "description", "type", "rule", "condition")
        self.tree = ttk.Treeview(question_frame, columns=columns, show="headings")
        for column, title in (
            ("id", "题号"),
            ("description", "题目说明"),
            ("type", "题型"),
            ("rule", "选项比例 / 范围"),
            ("condition", "条件题"),
        ):
            self.tree.heading(column, text=title)
        self.tree.column("id", width=60, anchor=tk.CENTER, stretch=False)
        self.tree.column("description", width=220)
        self.tree.column("type", width=150, anchor=tk.CENTER)
        self.tree.column("rule", width=330)
        self.tree.column("condition", width=70, anchor=tk.CENTER, stretch=False)
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        tree_scroll = ttk.Scrollbar(question_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.tree.bind("<Double-1>", lambda _event: self.edit_question())

        question_buttons = ttk.Frame(question_frame)
        question_buttons.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))
        ttk.Button(question_buttons, text="添加题目", command=self.add_question).pack(side=tk.LEFT)
        ttk.Button(question_buttons, text="编辑题目", command=self.edit_question).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(question_buttons, text="删除题目", command=self.delete_question).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(question_buttons, text="上移", command=lambda: self.move_question(-1)).pack(
            side=tk.LEFT, padx=(24, 0)
        )
        ttk.Button(question_buttons, text="下移", command=lambda: self.move_question(1)).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        bottom = ttk.Frame(outer)
        bottom.grid(row=4, column=0, sticky=tk.EW, pady=(14, 0))
        ttk.Label(bottom, text="提示：双击题目可以编辑。").pack(side=tk.LEFT)
        ttk.Button(bottom, text="取消", command=self.window.destroy).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="保存配置", style="Primary.TButton", command=self.save_config).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

    def _selected_index(self):
        """返回当前选中题目的列表下标。"""

        selection = self.tree.selection()
        if not selection:
            return None
        return self.tree.index(selection[0])

    def _refresh_tree(self, selected_index=None):
        """刷新题目表格，并按需恢复选中行。"""

        for item in self.tree.get_children():
            self.tree.delete(item)
        for question in self.questions:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    question.get("id", ""),
                    question.get("description", ""),
                    describe_question_type(question.get("type")),
                    describe_answer_rule(question),
                    "是" if question.get("is_conditional", False) else "否",
                ),
            )
        if selected_index is not None and self.questions:
            selected_index = max(0, min(selected_index, len(self.questions) - 1))
            item = self.tree.get_children()[selected_index]
            self.tree.selection_set(item)
            self.tree.focus(item)

    def add_question(self):
        """打开新增题目弹窗。"""

        dialog = QuestionEditorDialog(
            self.window,
            existing_ids={question.get("id") for question in self.questions},
        )
        if dialog.result:
            self.questions.append(dialog.result)
            self._refresh_tree(len(self.questions) - 1)

    def edit_question(self):
        """编辑当前选中的题目。"""

        index = self._selected_index()
        if index is None:
            messagebox.showinfo("请选择题目", "请先在表格中选择一道题目。", parent=self.window)
            return
        dialog = QuestionEditorDialog(
            self.window,
            existing_ids={question.get("id") for question in self.questions},
            question=self.questions[index],
        )
        if dialog.result:
            self.questions[index] = dialog.result
            self._refresh_tree(index)

    def delete_question(self):
        """删除当前选中的题目。"""

        index = self._selected_index()
        if index is None:
            messagebox.showinfo("请选择题目", "请先在表格中选择一道题目。", parent=self.window)
            return
        question = self.questions[index]
        if messagebox.askyesno(
            "确认删除",
            f"确定删除题目 {question.get('id')} 吗？",
            parent=self.window,
        ):
            del self.questions[index]
            self._refresh_tree(index)

    def move_question(self, direction):
        """将选中的题目上移或下移。"""

        index = self._selected_index()
        if index is None:
            return
        new_index = index + direction
        if not 0 <= new_index < len(self.questions):
            return
        self.questions[index], self.questions[new_index] = self.questions[new_index], self.questions[index]
        self._refresh_tree(new_index)

    def save_config(self):
        """校验整份问卷并保存为新的 Python 配置文件。"""

        url = self.url_var.get().strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showerror("配置错误", "请输入以 http:// 或 https:// 开头的问卷链接。", parent=self.window)
            return
        if not self.questions:
            messagebox.showerror("配置错误", "请至少添加一道题目。", parent=self.window)
            return

        try:
            submission_count = int(self.submission_count_var.get())
            min_delay = float(self.min_delay_var.get())
            max_delay = float(self.max_delay_var.get())
        except ValueError:
            messagebox.showerror("配置错误", "提交份数必须为整数，延时必须为数字。", parent=self.window)
            return
        if submission_count <= 0:
            messagebox.showerror("配置错误", "提交份数必须大于 0。", parent=self.window)
            return
        if min_delay < 0 or max_delay < min_delay:
            messagebox.showerror("配置错误", "延时不能为负数，且最大延时不能小于最小延时。", parent=self.window)
            return

        previous_question_ids = set()
        for question in self.questions:
            if question.get("is_conditional"):
                parent_id = str((question.get("condition") or {}).get("on_question_id"))
                if parent_id not in previous_question_ids:
                    messagebox.showerror(
                        "配置错误",
                        f"题目 {question.get('id')} 依赖的题目 {parent_id} "
                        "必须存在，并排在当前题目之前。",
                        parent=self.window,
                    )
                    return
            previous_question_ids.add(str(question.get("id")))

        config = {
            "questionnaire_url": url,
            "number_of_submissions": submission_count,
            "min_delay_seconds": min_delay,
            "max_delay_seconds": max_delay,
            "headless": self.headless_var.get(),
            "mobile_user_agent": DEFAULT_MOBILE_UA,
            "questions": copy.deepcopy(self.questions),
        }

        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="保存新问卷配置",
            initialdir=str(PROJECT_ROOT / "config"),
            initialfile="新问卷配置.py",
            defaultextension=".py",
            filetypes=[("Python 配置文件", "*.py")],
        )
        if not path:
            return

        try:
            Path(path).write_text(build_config_text(config), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.window)
            return

        messagebox.showinfo(
            "保存成功",
            f"新配置已保存：\n{path}\n\n主窗口将自动加载该配置。",
            parent=self.window,
        )
        self.on_saved(path)
        self.window.destroy()


class WJXLauncher:
    """问卷任务的可视化启动器。"""

    def __init__(self, root):
        self.root = root
        self.root.title("问卷星自动填写工具")
        self.root.geometry("1040x760")
        self.root.minsize(900, 650)

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.submitter = None
        self.current_config = None
        self.close_when_finished = False

        self.config_path_var = tk.StringVar(value=str(DEFAULT_CONFIG_PATH))
        self.url_var = tk.StringVar(value="尚未加载配置")
        self.question_count_var = tk.StringVar(value="0")
        self.submission_count_var = tk.StringVar(value="1")
        self.min_delay_var = tk.StringVar(value="60")
        self.max_delay_var = tk.StringVar(value="180")
        self.headless_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="准备就绪")
        self.progress_text_var = tk.StringVar(value="0 / 0，成功 0")
        self.config_controls = []

        self._configure_style()
        self._build_ui()
        self._install_log_handler()
        self.root.report_callback_exception = self._report_callback_exception
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_events)
        self.load_config(show_success=False)

    def _configure_style(self):
        """设置简洁的中文界面样式。"""

        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Subtitle.TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(16, 8))
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(10, 6))
        style.configure("TLabel", font=("Microsoft YaHei UI", 9))
        style.configure("TCheckbutton", font=("Microsoft YaHei UI", 9))
        style.configure("Treeview", font=("Microsoft YaHei UI", 9), rowheight=26)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

    def _build_ui(self):
        """创建窗口中的配置、题目、运行状态和日志区域。"""

        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="问卷星自动填写工具", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text="加载现有配置，确认本次运行参数后即可启动。",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(2, 12))

        config_frame = ttk.LabelFrame(outer, text="配置文件", padding=10)
        config_frame.pack(fill=tk.X)
        config_frame.columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="文件路径").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        self.config_entry = ttk.Entry(config_frame, textvariable=self.config_path_var)
        self.config_entry.grid(row=0, column=1, sticky=tk.EW)
        choose_button = ttk.Button(config_frame, text="选择…", command=self.choose_config)
        choose_button.grid(row=0, column=2, padx=(8, 0))
        reload_button = ttk.Button(config_frame, text="重新加载", command=self.load_config)
        reload_button.grid(row=0, column=3, padx=(8, 0))
        create_button = ttk.Button(config_frame, text="新建配置", command=self.create_config)
        create_button.grid(row=0, column=4, padx=(8, 0))
        open_button = ttk.Button(config_frame, text="打开文件", command=self.open_config_file)
        open_button.grid(row=0, column=5, padx=(8, 0))

        ttk.Label(config_frame, text="问卷地址").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=(10, 0))
        ttk.Entry(config_frame, textvariable=self.url_var, state="readonly").grid(
            row=1, column=1, columnspan=5, sticky=tk.EW, pady=(10, 0)
        )

        controls = ttk.LabelFrame(outer, text="本次运行参数", padding=10)
        controls.pack(fill=tk.X, pady=(12, 0))

        ttk.Label(controls, text="题目数量").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(controls, textvariable=self.question_count_var, style="Status.TLabel").grid(
            row=0, column=1, sticky=tk.W, padx=(8, 28)
        )
        ttk.Label(controls, text="提交份数").grid(row=0, column=2, sticky=tk.W)
        submission_spinbox = ttk.Spinbox(
            controls,
            from_=1,
            to=100000,
            width=9,
            textvariable=self.submission_count_var,
        )
        submission_spinbox.grid(row=0, column=3, sticky=tk.W, padx=(8, 28))
        ttk.Label(controls, text="最小延时（秒）").grid(row=0, column=4, sticky=tk.W)
        min_delay_entry = ttk.Entry(controls, width=10, textvariable=self.min_delay_var)
        min_delay_entry.grid(row=0, column=5, sticky=tk.W, padx=(8, 28))
        ttk.Label(controls, text="最大延时（秒）").grid(row=0, column=6, sticky=tk.W)
        max_delay_entry = ttk.Entry(controls, width=10, textvariable=self.max_delay_var)
        max_delay_entry.grid(row=0, column=7, sticky=tk.W, padx=(8, 20))
        headless_checkbutton = ttk.Checkbutton(controls, text="无头模式", variable=self.headless_var)
        headless_checkbutton.grid(row=0, column=8, sticky=tk.W)

        self.config_controls.extend(
            [
                self.config_entry,
                choose_button,
                reload_button,
                create_button,
                open_button,
                submission_spinbox,
                min_delay_entry,
                max_delay_entry,
                headless_checkbutton,
            ]
        )

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        question_tab = ttk.Frame(notebook, padding=8)
        log_tab = ttk.Frame(notebook, padding=8)
        notebook.add(question_tab, text="题目与比例")
        notebook.add(log_tab, text="运行日志")

        question_tab.rowconfigure(0, weight=1)
        question_tab.columnconfigure(0, weight=1)
        columns = ("id", "description", "type", "rule", "condition")
        self.question_tree = ttk.Treeview(question_tab, columns=columns, show="headings")
        self.question_tree.heading("id", text="题号")
        self.question_tree.heading("description", text="题目说明")
        self.question_tree.heading("type", text="题型")
        self.question_tree.heading("rule", text="选项比例 / 范围")
        self.question_tree.heading("condition", text="条件题")
        self.question_tree.column("id", width=60, anchor=tk.CENTER, stretch=False)
        self.question_tree.column("description", width=240)
        self.question_tree.column("type", width=150, anchor=tk.CENTER)
        self.question_tree.column("rule", width=360)
        self.question_tree.column("condition", width=80, anchor=tk.CENTER, stretch=False)
        tree_scroll = ttk.Scrollbar(question_tab, orient=tk.VERTICAL, command=self.question_tree.yview)
        self.question_tree.configure(yscrollcommand=tree_scroll.set)
        self.question_tree.grid(row=0, column=0, sticky=tk.NSEW)
        tree_scroll.grid(row=0, column=1, sticky=tk.NS)

        log_tab.rowconfigure(0, weight=1)
        log_tab.columnconfigure(0, weight=1)
        self.log_text = ScrolledText(
            log_tab,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9),
            background="#111827",
            foreground="#e5e7eb",
            insertbackground="#e5e7eb",
        )
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)
        ttk.Button(log_tab, text="清空日志", command=self.clear_log).grid(
            row=1, column=0, sticky=tk.E, pady=(8, 0)
        )

        action_frame = ttk.Frame(outer)
        action_frame.pack(fill=tk.X, pady=(12, 0))
        action_frame.columnconfigure(1, weight=1)

        self.start_button = ttk.Button(
            action_frame,
            text="开始运行",
            style="Primary.TButton",
            command=self.start_run,
        )
        self.start_button.grid(row=0, column=0, rowspan=2, sticky=tk.W)
        self.progress_bar = ttk.Progressbar(action_frame, mode="determinate", maximum=1)
        self.progress_bar.grid(row=0, column=1, sticky=tk.EW, padx=12)
        ttk.Label(action_frame, textvariable=self.progress_text_var).grid(row=1, column=1, sticky=tk.W, padx=12)
        self.stop_button = ttk.Button(
            action_frame,
            text="停止（当前步骤后）",
            command=self.request_stop,
            state=tk.DISABLED,
        )
        self.stop_button.grid(row=0, column=2, rowspan=2, sticky=tk.E)
        ttk.Label(action_frame, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=3, rowspan=2, sticky=tk.E, padx=(16, 0)
        )

    def _install_log_handler(self):
        """把 logging 输出接入界面的运行日志页。"""

        handler = QueueLogHandler(self.event_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        self.log_handler = handler

    def _report_callback_exception(self, exception_type, exception, exception_traceback):
        """显示 Tkinter 回调异常，避免界面静默停在空白状态。"""

        detail = "".join(traceback.format_exception(exception_type, exception, exception_traceback))
        logging.getLogger(__name__).error("界面操作发生异常：\n%s", detail)
        messagebox.showerror("界面操作失败", f"{exception_type.__name__}: {exception}")

    def choose_config(self):
        """选择另一个 Python 配置文件。"""

        selected = filedialog.askopenfilename(
            title="选择问卷配置文件",
            initialdir=str(PROJECT_ROOT / "config"),
            filetypes=[("Python 配置文件", "*.py"), ("所有文件", "*.*")],
        )
        if selected:
            self.config_path_var.set(selected)
            self.load_config()

    def create_config(self):
        """打开新问卷配置创建窗口。"""

        ConfigCreatorDialog(self.root, self._load_created_config)

    def _load_created_config(self, path):
        """新配置保存成功后，在主窗口中自动加载。"""

        self.config_path_var.set(path)
        self.load_config(show_success=False)

    def load_config(self, show_success=True):
        """加载配置并刷新题目比例预览。"""

        path = Path(self.config_path_var.get().strip())
        if not path.is_file():
            messagebox.showerror("配置错误", f"找不到配置文件：\n{path}")
            return

        config = load_config_from_py(str(path))
        if not isinstance(config, dict):
            messagebox.showerror("配置错误", "没有读取到有效的 config_data 字典。")
            return

        self.current_config = config
        questions = config.get("questions") or []
        self.url_var.set(str(config.get("questionnaire_url") or "未配置"))
        self.question_count_var.set(str(len(questions)))
        self.submission_count_var.set(str(config.get("number_of_submissions", 1)))
        self.min_delay_var.set(str(config.get("min_delay_seconds", 60)))
        self.max_delay_var.set(str(config.get("max_delay_seconds", 180)))
        self.headless_var.set(bool(config.get("headless", False)))

        for item in self.question_tree.get_children():
            self.question_tree.delete(item)
        for question in questions:
            self.question_tree.insert(
                "",
                tk.END,
                values=(
                    question.get("id", ""),
                    question.get("description", ""),
                    describe_question_type(question.get("type")),
                    describe_answer_rule(question),
                    "是" if question.get("is_conditional", False) else "否",
                ),
            )

        self.status_var.set("配置已加载")
        logging.getLogger(__name__).info("已加载配置：%s，共 %s 道题。", path, len(questions))
        if show_success:
            messagebox.showinfo("加载成功", f"配置已加载，共 {len(questions)} 道题。")

    def open_config_file(self):
        """使用系统默认编辑器打开当前配置文件。"""

        path = Path(self.config_path_var.get().strip())
        if not path.is_file():
            messagebox.showerror("打开失败", f"找不到配置文件：\n{path}")
            return
        try:
            os.startfile(str(path))
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc))

    def _build_runtime_config(self):
        """校验界面输入，并生成只用于本次运行的配置副本。"""

        if not isinstance(self.current_config, dict):
            raise ValueError("请先加载有效配置。")

        try:
            submissions = int(self.submission_count_var.get())
            min_delay = float(self.min_delay_var.get())
            max_delay = float(self.max_delay_var.get())
        except ValueError as exc:
            raise ValueError("提交份数必须为整数，延时必须为数字。") from exc

        if submissions <= 0:
            raise ValueError("提交份数必须大于 0。")
        if min_delay < 0 or max_delay < 0:
            raise ValueError("延时不能为负数。")
        if max_delay < min_delay:
            raise ValueError("最大延时不能小于最小延时。")
        if not self.current_config.get("questionnaire_url"):
            raise ValueError("配置中缺少 questionnaire_url。")
        if not self.current_config.get("questions"):
            raise ValueError("配置中没有题目。")

        runtime_config = copy.deepcopy(self.current_config)
        runtime_config["number_of_submissions"] = submissions
        runtime_config["min_delay_seconds"] = min_delay
        runtime_config["max_delay_seconds"] = max_delay
        runtime_config["headless"] = self.headless_var.get()
        return runtime_config

    def start_run(self):
        """校验参数并在后台线程启动浏览器任务。"""

        if self.worker and self.worker.is_alive():
            return
        try:
            runtime_config = self._build_runtime_config()
        except ValueError as exc:
            messagebox.showerror("无法启动", str(exc))
            return

        total = runtime_config["number_of_submissions"]
        self.stop_event.clear()
        self.progress_bar.configure(maximum=total, value=0)
        self.progress_text_var.set(f"0 / {total}，成功 0")
        self.status_var.set("正在启动浏览器…")
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self._set_config_controls_state(tk.DISABLED)

        self.worker = threading.Thread(
            target=self._run_worker,
            args=(runtime_config,),
            name="wjx-worker",
            daemon=True,
        )
        self.worker.start()

    def _run_worker(self, runtime_config):
        """后台执行任务，避免 Selenium 阻塞界面。"""

        success_count = 0
        error = None
        try:
            self.event_queue.put(("status", "正在运行"))
            self.submitter = WJXSubmitter(runtime_config)
            success_count = self.submitter.run_loop(
                stop_event=self.stop_event,
                progress_callback=self._report_progress,
            )
        except Exception as exc:
            logging.getLogger(__name__).exception("任务运行失败")
            error = str(exc)
        finally:
            if self.submitter is not None:
                self.submitter.close_driver()
            self.submitter = None
            self.event_queue.put(("finished", success_count, error))

    def _report_progress(self, completed, total, successful):
        """从工作线程向界面报告进度。"""

        self.event_queue.put(("progress", completed, total, successful))

    def request_stop(self):
        """请求在当前浏览器步骤结束后停止任务。"""

        self.stop_event.set()
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("正在等待安全停止…")
        logging.getLogger(__name__).info("用户请求停止任务。")

    def _poll_events(self):
        """在主线程处理后台日志和进度事件。"""

        try:
            while True:
                event = self.event_queue.get_nowait()
                event_type = event[0]
                if event_type == "log":
                    self._append_log(event[1])
                elif event_type == "status":
                    self.status_var.set(event[1])
                elif event_type == "progress":
                    _, completed, total, successful = event
                    self.progress_bar.configure(maximum=max(total, 1), value=completed)
                    self.progress_text_var.set(f"{completed} / {total}，成功 {successful}")
                elif event_type == "finished":
                    _, successful, error = event
                    self._finish_run(successful, error)
        except queue.Empty:
            pass

        try:
            if self.root.winfo_exists():
                self.root.after(100, self._poll_events)
        except tk.TclError:
            pass

    def _finish_run(self, successful, error):
        """恢复界面状态并显示任务结果。"""

        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self._set_config_controls_state(tk.NORMAL)
        if error:
            self.status_var.set("运行失败")
            messagebox.showerror("运行失败", error)
        elif self.stop_event.is_set():
            self.status_var.set(f"已停止，成功 {successful} 份")
        else:
            self.status_var.set(f"运行完成，成功 {successful} 份")

        if self.close_when_finished:
            self.root.destroy()

    def _set_config_controls_state(self, state):
        """运行期间锁定配置入口，避免中途修改。"""

        for widget in self.config_controls:
            widget.configure(state=state)

    def _append_log(self, message):
        """追加一行日志并自动滚动到底部。"""

        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def clear_log(self):
        """清空界面日志。"""

        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _on_close(self):
        """关闭窗口；任务运行时先请求安全停止。"""

        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("任务仍在运行", "是否停止任务并在安全结束后关闭窗口？"):
                return
            self.close_when_finished = True
            self.request_stop()
            return

        logging.getLogger().removeHandler(self.log_handler)
        self.root.destroy()


def main():
    """启动中文图形界面。"""

    root = tk.Tk()
    WJXLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
