#!/usr/bin/env python3
"""
graph_digitizer.py バージョン名: "v13_how_to_use"
依存: numpy, pillow (pip install numpy pillow)
使い方:
    python graph_digitizer.py                 # ダイアログで画像選択
    python graph_digitizer.py sample.png      # sample.png を直接読み込み
"""

from pathlib import Path
from datetime import datetime
from typing import Optional
import csv, logging, sys, tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, ttk
import numpy as np
from PIL import Image, ImageTk
from statistics import NormalDist

OUT_DIR = Path("./graph_value_output")
LOG_DIR = Path("./log")
LOG_FILE_PATH: Optional[Path] = None
IS_WINDOWS = sys.platform.startswith("win")


def _configure_logging() -> logging.Logger:
    """Set up a dedicated logger that writes to console and a timestamped file."""
    LOG_DIR.mkdir(exist_ok=True)
    global LOG_FILE_PATH
    log_file = LOG_DIR / f"graph_digitizer_{datetime.now():%Y%m%d_%H%M%S}.log"
    LOG_FILE_PATH = log_file
    logger = logging.getLogger("graph_digitizer")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    logger.propagate = False

    logger.info("ログ出力を %s に開始しました", log_file)
    return logger


LOGGER = _configure_logging()
NORMAL_DIST = NormalDist()

class GraphDigitizer(tk.Tk):
    def __init__(self, img_path=None):
        super().__init__()
        self.title("Graph Digitizer")
        self.calib_pairs, self.data_points = [], []
        self.transform = {"x": (1.0, 0.0), "y": (1.0, 0.0)}
        self.offset_x = 0
        self.offset_y = 0
        self.scale = 1.0              # zoom scale
        self.orig_img = None          # store original PIL image
        self.mode = "CALIB"
        self.image_id = None
        self._pan_start = None
        self.x_scale_mode = None
        self.y_scale_mode = None
        self.image_path = None
        self._probability_is_percent = {"x": False, "y": False}
        LOGGER.info("GraphDigitizerを起動しました")
        if not self._select_scale_mode():
            self.after(0, self.destroy)
            return
        if not self._configure_probability_units():
            self.after(0, self.destroy)
            return
        self._build_ui()
        self._load_image(img_path)

    # ---------- UI ----------
    def _build_ui(self):
        self.canvas = tk.Canvas(self, bg="grey")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_click)
        # pan handlers
        self.canvas.bind("<ButtonPress-2>", self._on_middle_press)
        self.canvas.bind("<B2-Motion>", self._on_middle_drag)
        self.canvas.bind("<ButtonRelease-2>", self._on_middle_release)
        # zoom handlers
        self.canvas.bind("<MouseWheel>", self._on_zoom)
        self.canvas.bind("<Button-4>", self._on_zoom)
        self.canvas.bind("<Button-5>", self._on_zoom)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x")

        self.finish_btn = ttk.Button(btn_frame, text="データ取得を終了",
                                     state="disabled", command=self._finish)
        self.finish_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.help_btn = ttk.Button(btn_frame, text="操作方法",
                                   command=self._show_help)
        self.help_btn.pack(side="left", expand=True, fill="x")

        self.tree = ttk.Treeview(self, columns=("x","y"), show="headings", height=6)
        self.tree.heading("x", text="x")
        self.tree.heading("y", text="y")
        self.tree.pack(fill="x")

    # ---------- 軸スケール選択 ----------
    def _select_scale_mode(self):
        axis_modes = [("線形", "linear"), ("log", "log"), ("確率紙", "probability")]
        scale_options = {}
        labels = []
        for x_label, x_mode in axis_modes:
            for y_label, y_mode in axis_modes:
                label = f"{x_label}-{y_label}"
                scale_options[label] = (x_mode, y_mode)
                labels.append(label)

        class _ScaleDialog(simpledialog.Dialog):
            def __init__(self, parent):
                self._selection = tk.StringVar(value=labels[0])
                self.result = None
                super().__init__(parent, title="軸スケール選択")

            def body(self, master):
                ttk.Label(master, text="x軸-y軸のスケールを選択してください").grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 6))
                combo = ttk.Combobox(master, textvariable=self._selection,
                                      values=labels, state="readonly", width=12)
                combo.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 12))
                combo.current(0)
                return combo

            def buttonbox(self):
                box = ttk.Frame(self)
                box.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
                ttk.Button(box, text="OK", command=self.ok).pack(side="left", expand=True, fill="x", padx=(0, 4))
                ttk.Button(box, text="キャンセル", command=self.cancel).pack(side="left", expand=True, fill="x", padx=(4, 0))
                self.bind("<Return>", self.ok)
                self.bind("<Escape>", self.cancel)

            def apply(self):
                self.result = self._selection.get()

        dialog = _ScaleDialog(self)
        if dialog.result is None:
            return False
        self.x_scale_mode, self.y_scale_mode = scale_options[dialog.result]
        LOGGER.info("スケールモードを設定しました: x=%s, y=%s", self.x_scale_mode, self.y_scale_mode)
        return True

    def _configure_probability_units(self):
        for axis, mode in (("x", self.x_scale_mode), ("y", self.y_scale_mode)):
            if mode != "probability":
                continue

            unit = self._ask_probability_unit(axis)
            if unit is None:
                return False
            self._probability_is_percent[axis] = (unit == "percent")
        return True

    def _ask_probability_unit(self, axis):
        axis_label = "x軸" if axis == "x" else "y軸"
        options = {
            "0-1 (小数)": "fraction",
            "0-100 (百分率)": "percent",
        }

        class _UnitDialog(simpledialog.Dialog):
            def __init__(self, parent):
                self._selection = tk.StringVar(value=list(options.keys())[0])
                self.result = None
                super().__init__(parent, title=f"{axis_label}の確率単位")

            def body(self, master):
                ttk.Label(master, text=f"{axis_label} の入力単位を選択してください").grid(row=0, column=0, padx=12, pady=(12, 6))
                combo = ttk.Combobox(master, textvariable=self._selection,
                                      values=list(options.keys()), state="readonly", width=18)
                combo.grid(row=1, column=0, padx=12, pady=(0, 12))
                combo.current(0)
                return combo

            def buttonbox(self):
                box = ttk.Frame(self)
                box.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
                ttk.Button(box, text="OK", command=self.ok).pack(side="left", expand=True, fill="x", padx=(0, 4))
                ttk.Button(box, text="キャンセル", command=self.cancel).pack(side="left", expand=True, fill="x", padx=(4, 0))
                self.bind("<Return>", self.ok)
                self.bind("<Escape>", self.cancel)

            def apply(self):
                self.result = self._selection.get()

        dialog = _UnitDialog(self)
        if dialog.result is None:
            return None
        return options[dialog.result]

    # ---------- 画像ロード ----------
    def _load_image(self, img_path):
        # ask for path if not provided as argument
        if img_path is None:
            img_path = simpledialog.askstring(
                "画像ファイル指定", "画像のパスを指定してください")
            if not img_path:
                messagebox.showwarning("警告", "画像のパスが指定されませんでした")
                self.destroy(); return
        try:
            path_obj = Path(img_path)
            img = Image.open(path_obj)
        except Exception as e:
            messagebox.showerror("画像読み込み失敗", str(e))
            self.destroy(); return

        self.image_path = path_obj
        self.orig_img = img
        self.img = ImageTk.PhotoImage(img)
        self.image_id = self.canvas.create_image(0, 0, image=self.img, anchor="nw")
        self.geometry(f"{img.width}x{img.height+180}")
        LOGGER.info("画像を読み込みました: %s", path_obj)

    # ---------- クリック処理 ----------
    def _on_click(self, ev):
        xi, yi = self._screen_to_image(ev.x, ev.y)
        if self.mode == "CALIB":
            self._ask_true_coords(xi, yi)
            return
        # データ取得モード
        x, y = self._apply_transform(xi, yi)
        self.data_points.append((x, y))
        item = self.tree.insert("", "end", values=(x, y))
        self.tree.see(item)
        LOGGER.info("データ取得: x=%.6g, y=%.6g", x, y)

    def _ask_true_coords(self, xi, yi):
        result = self._prompt_calibration_values(xi, yi)
        if result is None:
            return
        xt, yt = result
        try:
            self._validate_calibration_value("x", xt)
            self._validate_calibration_value("y", yt)
        except ValueError as exc:
            messagebox.showerror("エラー", str(exc), parent=self)
            return
        LOGGER.info(
            "キャリブレーション入力: img=(%.2f, %.2f) -> actual=(%.6g, %.6g)",
            xi,
            yi,
            xt,
            yt,
        )
        self.calib_pairs.append(((xi,yi), (xt,yt)))
        if messagebox.askyesno("続けますか？","キャリブレーションを続けますか？\nいいえ＝終了", parent=self):
            return
        self._solve_transform()

    def _prompt_calibration_values(self, xi, yi):
        prompt = f"クリック位置 (画像座標: {xi:.2f}, {yi:.2f}) の実際の座標を入力"

        class _CoordinateDialog(simpledialog.Dialog):
            def __init__(self, parent, message):
                self._message = message
                self._x_var = tk.StringVar()
                self._y_var = tk.StringVar()
                self.result = None
                super().__init__(parent, title="キャリブレーション")

            def body(self, master):
                if IS_WINDOWS:
                    self.after(0, lambda: self.wm_attributes("-topmost", True))
                ttk.Label(master, text=self._message, justify="left").grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 6), sticky="w")
                ttk.Label(master, text="x 値:").grid(row=1, column=0, padx=(12, 6), pady=3, sticky="e")
                entry_x = ttk.Entry(master, textvariable=self._x_var, width=16)
                entry_x.grid(row=1, column=1, padx=(0, 12), pady=3, sticky="w")
                ttk.Label(master, text="y 値:").grid(row=2, column=0, padx=(12, 6), pady=(0, 12), sticky="e")
                entry_y = ttk.Entry(master, textvariable=self._y_var, width=16)
                entry_y.grid(row=2, column=1, padx=(0, 12), pady=(0, 12), sticky="w")
                return entry_x

            def validate(self):
                try:
                    self._x_value = float(self._x_var.get())
                    self._y_value = float(self._y_var.get())
                except ValueError:
                    messagebox.showerror("エラー", "数値を入力してください。", parent=self)
                    return False
                return True

            def apply(self):
                self.result = (self._x_value, self._y_value)

        dialog = _CoordinateDialog(self, prompt)
        return dialog.result

    # ---------- 線形変換推定 ----------
    def _solve_transform(self):
        if len(self.calib_pairs) < 2:
            messagebox.showerror("エラー","少なくとも 2 点必要です"); return
        xi, yi, xt, yt = zip(*( (p[0][0], p[0][1], p[1][0], p[1][1])
                                for p in self.calib_pairs ))
        try:
            ax, bx = self._fit_axis("x", xi, xt)
            ay, by = self._fit_axis("y", yi, yt)
        except ValueError as exc:
            messagebox.showerror("エラー", str(exc))
            return
        self.transform["x"] = (ax, bx)
        self.transform["y"] = (ay, by)
        self.mode = "DATA"
        self.finish_btn["state"] = "normal"
        eq_x = self._format_axis_message('x', ax, bx)
        eq_y = self._format_axis_message('y', ay, by)
        LOGGER.info("キャリブレーション完了: モードをDATAに変更しました")
        LOGGER.info("  %s", eq_x)
        LOGGER.info("  %s", eq_y)
        info = (
            f"{eq_x}\n"
            f"{eq_y}\n"
            "データ取得モードに移行しました。"
        )
        messagebox.showinfo("キャリブレーション完了", info)

    def _apply_transform(self, xi, yi):
        return self._apply_axis_value("x", xi), self._apply_axis_value("y", yi)

    def _screen_to_image(self, sx, sy):
        if self.scale == 0:
            return sx, sy
        xi = (sx - self.offset_x) / self.scale
        yi = (sy - self.offset_y) / self.scale
        return xi, yi

    def _fit_axis(self, axis, img_coords, actual_values):
        scale_mode = self.x_scale_mode if axis == "x" else self.y_scale_mode
        if scale_mode not in ("linear", "log", "probability"):
            raise ValueError("スケール設定が不正です。")
        img_arr = np.asarray(img_coords, dtype=float)
        act_arr = np.asarray(actual_values, dtype=float)
        if scale_mode == "log":
            if np.any(act_arr <= 0):
                raise ValueError("対数スケールには正の値が必要です。キャリブレーション点を確認してください。")
            target = np.log10(act_arr)
        elif scale_mode == "probability":
            probs = self._convert_probability_values(axis, act_arr)
            target = self._probability_forward_transform(probs)
        else:
            target = act_arr
        slope, intercept = np.polyfit(img_arr, target, 1)
        return float(slope), float(intercept)

    def _format_axis_message(self, axis, slope, intercept):
        axis_label = "x" if axis == "x" else "y"
        scale_mode = self.x_scale_mode if axis == "x" else self.y_scale_mode
        if scale_mode == "log":
            lhs = f"log10({axis_label})"
        elif scale_mode == "probability":
            lhs = f"probit({axis_label}/100)" if self._probability_is_percent[axis] else f"probit({axis_label})"
        else:
            lhs = axis_label
        return f"{lhs} = {slope:.4f}*{axis_label}_img + {intercept:.4f}"

    def _apply_axis_value(self, axis, coord):
        slope, intercept = self.transform[axis]
        scale_mode = self.x_scale_mode if axis == "x" else self.y_scale_mode
        value = slope * coord + intercept
        if scale_mode == "log":
            return 10 ** value
        if scale_mode == "probability":
            prob = self._probability_inverse_transform(value)
            if self._probability_is_percent[axis]:
                return prob * 100.0
            return prob
        return value

    def _validate_calibration_value(self, axis, value):
        scale_mode = self.x_scale_mode if axis == "x" else self.y_scale_mode
        if scale_mode == "log" and value <= 0:
            raise ValueError(f"{axis}軸をlogスケールにした場合、正の値のみ入力してください。")
        if scale_mode == "probability":
            is_percent = self._probability_is_percent[axis]
            lower, upper = (0, 100) if is_percent else (0, 1)
            if not (lower < value < upper):
                unit = "%" if is_percent else "0-1"
                raise ValueError(f"{axis}軸を確率紙スケールにした場合、{unit}の範囲内 (端点を除く) で入力してください。")

    def _convert_probability_values(self, axis, values):
        is_percent = self._probability_is_percent[axis]
        probs = np.asarray(values, dtype=float)
        if is_percent:
            probs = probs / 100.0
        if np.any((probs <= 0) | (probs >= 1)):
            raise ValueError("確率紙スケールでは0および1(0%および100%)を使用できません。キャリブレーション点を見直してください。")
        return probs

    def _probability_forward_transform(self, probs):
        return np.array([NORMAL_DIST.inv_cdf(float(p)) for p in probs], dtype=float)

    def _probability_inverse_transform(self, value):
        return NORMAL_DIST.cdf(value)

    # ---------- CSV 出力 ----------
    def _finish(self):
        if not self.data_points:
            messagebox.showwarning("注意","取得データがありません"); return
        # ユーザーに保存ファイル名を指定させる
        default_name = self.image_path.stem if self.image_path else f"graph_value_{datetime.now():%Y%m%d_%H%M%S}"
        user_name = simpledialog.askstring("ファイル名指定", "CSVファイル名を入力してください（拡張子不要）", initialvalue=default_name)
        if user_name:
            fname = OUT_DIR / f"{user_name}.csv"
        else:
            fname = OUT_DIR / f"{default_name}.csv"
        OUT_DIR.mkdir(exist_ok=True)
        with fname.open("w", newline="") as f:
            csv.writer(f).writerows(self.data_points)
        messagebox.showinfo("完了", f"CSV を保存しました:\n{fname}")
        LOGGER.info("CSVを保存しました: %s", fname)
        self.destroy()

    # ---------- middle-click pan handlers ----------
    def _on_middle_press(self, ev):
        # start panning
        self._pan_start = (ev.x, ev.y)

    def _on_middle_drag(self, ev):
        # perform panning by moving image
        if self._pan_start is None or self.image_id is None:
            return
        dx = ev.x - self._pan_start[0]
        dy = ev.y - self._pan_start[1]
        self.canvas.move(self.image_id, dx, dy)
        # update offsets
        self.offset_x += dx
        self.offset_y += dy
        self._pan_start = (ev.x, ev.y)

    def _on_middle_release(self, ev):
        # end panning
        self._pan_start = None

    # ---------- zoom handlers ----------
    def _on_zoom(self, ev):
        # guard if image not loaded
        if self.orig_img is None or self.image_id is None:
            return
        # record old scale and determine zoom factor based on event
        old_scale = self.scale
        factor = 1.1
        # use button numbers on Linux (4=up, 5=down)
        if hasattr(ev, 'num') and ev.num in (4,5):
            zoom_dir = factor if ev.num == 4 else 1/factor
        # use delta on Windows/macOS
        elif hasattr(ev, 'delta'):
            zoom_dir = factor if ev.delta > 0 else 1/factor
        else:
            return
        # compute new scale with limits
        new_scale = max(0.1, min(old_scale * zoom_dir, 10))
        actual_zoom = new_scale / old_scale
        self.scale = new_scale
        # get mouse position
        cx, cy = ev.x, ev.y
        # adjust offset so that zoom is centered at cursor
        ox, oy = self.offset_x, self.offset_y
        new_ox = cx - (cx - ox) * actual_zoom
        new_oy = cy - (cy - oy) * actual_zoom
        self.offset_x, self.offset_y = new_ox, new_oy
        # resize image
        orig_w, orig_h = self.orig_img.size  # type: ignore
        w, h = int(orig_w * self.scale), int(orig_h * self.scale)
        resized = self.orig_img.resize((w, h), Image.LANCZOS)  # type: ignore
        self.img = ImageTk.PhotoImage(resized)
        # update canvas image and position
        self.canvas.itemconfig(self.image_id, image=self.img)
        self.canvas.coords(self.image_id, self.offset_x, self.offset_y)
        # adjust window size
        self.geometry(f"{w}x{h+180}")

    def _show_help(self):
        help_text = (
            "【操作手順】\n"
            "1. キャリブレーションモードでグラフ上の基準点をクリックし、実座標を入力します。\n"
            "2. 少なくとも 2 点登録後にキャリブレーションを完了するとデータ取得モードへ移行します。\n"
            "3. データ取得モードではデータを取得したい点をクリックすると座標が追加されます。\n\n"
            "【マウス操作】\n"
            "・左クリック: 現在のモードに応じてキャリブレーションまたはデータ取得。\n"
            "・中ボタンドラッグ: 画像のパン移動。\n"
            "・ホイール: マウス位置を中心にズーム。\n\n"
            "【確率紙スケール】\n"
            "・キャリブレーション入力時は 0 と 1（または 0% と 100%）を避けてください。"
        )
        messagebox.showinfo("操作方法", help_text, parent=self)
        LOGGER.info("操作方法ダイアログを表示しました")

if __name__ == "__main__":
    img_arg = sys.argv[1] if len(sys.argv) > 1 else None
    GraphDigitizer(img_arg).mainloop()
