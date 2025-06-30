#!/usr/bin/env python3
"""
graph_digitizer.py
依存: numpy, pillow (pip install numpy pillow)
使い方:
    python graph_digitizer.py                 # ダイアログで画像選択
    python graph_digitizer.py sample.png      # sample.png を直接読み込み
"""

from pathlib import Path
from datetime import datetime
import csv, sys, tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, ttk
import numpy as np
from PIL import Image, ImageTk

OUT_DIR = Path("./graph_value_output")

class GraphDigitizer(tk.Tk):
    def __init__(self, img_path=None):
        super().__init__()
        self.title("Graph Digitizer")
        self.calib_pairs, self.data_points = [], []
        self.transform = (1.0, 0.0, 1.0, 0.0)
        self.offset_x = 0
        self.offset_y = 0
        self.scale = 1.0              # zoom scale
        self.orig_img = None          # store original PIL image
        self.mode = "CALIB"
        self.image_id = None
        self._pan_start = None
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

        self.finish_btn = ttk.Button(self, text="データ取得を終了",
                                     state="disabled", command=self._finish)
        self.finish_btn.pack(fill="x")

        self.tree = ttk.Treeview(self, columns=("x","y"), show="headings", height=6)
        self.tree.heading("x", text="x")
        self.tree.heading("y", text="y")
        self.tree.pack(fill="x")

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
            img = Image.open(img_path)
        except Exception as e:
            messagebox.showerror("画像読み込み失敗", str(e))
            self.destroy(); return

        self.orig_img = img
        self.img = ImageTk.PhotoImage(img)
        self.image_id = self.canvas.create_image(0, 0, image=self.img, anchor="nw")
        self.geometry(f"{img.width}x{img.height+180}")

    # ---------- クリック処理 ----------
    def _on_click(self, ev):
        # adjust for pan offset
        xi = ev.x - self.offset_x
        yi = ev.y - self.offset_y
        if self.mode == "CALIB":
            self._ask_true_coords(xi, yi)
            return
        # データ取得モード
        x, y = self._apply_transform(xi, yi)
        self.data_points.append((x,y))
        self.tree.insert("", "end", values=(x,y))

    def _ask_true_coords(self, xi, yi):
        prompt = f"クリック位置 ({xi}, {yi}) の実際の座標を入力"
        xt = simpledialog.askfloat("キャリブレーション", prompt + "\nx 値:")
        yt = simpledialog.askfloat("キャリブレーション", prompt + "\ny 値:")
        if xt is None or yt is None:  # キャンセル
            return
        self.calib_pairs.append(((xi,yi), (xt,yt)))
        if messagebox.askyesno("続けますか？","キャリブレーションを続けますか？\nいいえ＝終了"):
            return
        self._solve_transform()

    # ---------- 線形変換推定 ----------
    def _solve_transform(self):
        if len(self.calib_pairs) < 2:
            messagebox.showerror("エラー","少なくとも 2 点必要です"); return
        xi, yi, xt, yt = zip(*( (p[0][0], p[0][1], p[1][0], p[1][1]) 
                                for p in self.calib_pairs ))
        ax,bx = np.polyfit(xi, xt, 1)
        ay,by = np.polyfit(yi, yt, 1)
        self.transform = (ax,bx, ay,by)
        self.mode = "DATA"
        self.finish_btn["state"] = "normal"
        messagebox.showinfo("キャリブレーション完了",
                            f"x = {ax:.4f}*x_img + {bx:.4f}\n"
                            f"y = {ay:.4f}*y_img + {by:.4f}\n"
                            "データ取得モードに移行しました。")

    def _apply_transform(self, xi, yi):
        ax,bx,ay,by = self.transform
        return ax*xi+bx, ay*yi+by

    # ---------- CSV 出力 ----------
    def _finish(self):
        if not self.data_points:
            messagebox.showwarning("注意","取得データがありません"); return
        # ユーザーに保存ファイル名を指定させる
        default_name = f"graph_value_{datetime.now():%Y%m%d_%H%M%S}"
        user_name = simpledialog.askstring("ファイル名指定", "CSVファイル名を入力してください（拡張子不要）", initialvalue=default_name)
        if user_name:
            fname = OUT_DIR / f"{user_name}.csv"
        else:
            fname = OUT_DIR / f"{default_name}.csv"
        OUT_DIR.mkdir(exist_ok=True)
        with fname.open("w", newline="") as f:
            csv.writer(f).writerows(self.data_points)
        messagebox.showinfo("完了", f"CSV を保存しました:\n{fname}")
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

if __name__ == "__main__":
    img_arg = sys.argv[1] if len(sys.argv) > 1 else None
    GraphDigitizer(img_arg).mainloop()
