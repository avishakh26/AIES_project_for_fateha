"""Local AI assistant: premium dark desktop GUI (Tkinter). Fully offline."""
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime
from tkinter import messagebox, ttk

from chatnoir_agent import ChatNoirAgent

APP_NAME = "Noir Intelligence"

# Noir + champagne-gold palette
BG, SURFACE, SURFACE_2, BORDER = "#0a0a0f", "#13131b", "#1b1b26", "#262633"
FG, MUTED, FAINT = "#ececf3", "#8b8b9e", "#5a5a6c"
GOLD, GOLD_HOVER, ON_GOLD, ONLINE = "#e2b860", "#f0cc82", "#1a1405", "#4ade80"

F_BASE = ("Segoe UI", 11)
F_BOLD = ("Segoe UI Semibold", 11)
F_TITLE = ("Segoe UI Semibold", 15)
F_SMALL = ("Segoe UI", 9)

SUGGESTIONS = ["Tell me a joke", "Capital of France", "What is 15*3?", "Give me a fun fact"]

try:  # crisp text on high-DPI Windows displays
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


def rounded(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class Pill(tk.Canvas):
    """A rounded, hoverable button drawn on a canvas."""

    def __init__(self, parent, text, command, *, primary=False, width=None, height=34, bg=BG):
        w = width or (len(text) * 8 + 28)
        super().__init__(parent, width=w, height=height, bg=bg, highlightthickness=0, cursor="hand2")
        self.command, self.primary = command, primary
        self.base = GOLD if primary else SURFACE_2
        self.hover = GOLD_HOVER if primary else BORDER
        self.shape = rounded(self, 1, 1, w - 1, height - 1, height // 2 - 1, fill=self.base, outline="" if primary else BORDER)
        self.label = self.create_text(w // 2, height // 2, text=text, fill=ON_GOLD if primary else FG,
                                      font=F_BOLD if primary else ("Segoe UI", 10))
        self.bind("<Enter>", lambda _e: self.itemconfig(self.shape, fill=self.hover))
        self.bind("<Leave>", lambda _e: self.itemconfig(self.shape, fill=self.base))
        self.bind("<Button-1>", lambda _e: self.command())


class TeachDialog(tk.Toplevel):
    """One window for both fields, with Enter/Esc shortcuts."""

    def __init__(self, parent, question=""):
        super().__init__(parent, bg=BG)
        self.title(f"Teach {APP_NAME}")
        self.transient(parent)
        self.resizable(False, False)
        self.result = None

        tk.Label(self, text="Teach a new answer", bg=BG, fg=GOLD, font=F_TITLE).pack(anchor="w", padx=20, pady=(18, 0))
        tk.Label(self, text="Saved to knowledge.csv and used right away.", bg=BG, fg=MUTED, font=F_SMALL).pack(anchor="w", padx=20)

        tk.Label(self, text="When the user says (keywords or phrase)", bg=BG, fg=FG, font=F_BASE).pack(anchor="w", padx=20, pady=(14, 4))
        self.q = tk.Entry(self, width=52, bg=SURFACE, fg=FG, insertbackground=GOLD, bd=0, font=F_BASE,
                          highlightthickness=1, highlightbackground=BORDER, highlightcolor=GOLD)
        self.q.pack(padx=20, ipady=7)
        self.q.insert(0, question)

        tk.Label(self, text="The assistant should answer", bg=BG, fg=FG, font=F_BASE).pack(anchor="w", padx=20, pady=(12, 4))
        self.a = tk.Text(self, width=52, height=5, wrap="word", bg=SURFACE, fg=FG, insertbackground=GOLD, bd=0,
                         font=F_BASE, padx=8, pady=6, highlightthickness=1, highlightbackground=BORDER, highlightcolor=GOLD)
        self.a.pack(padx=20)

        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=20, pady=18)
        Pill(btns, "Save", self.save, primary=True, width=90).pack(side="right")
        Pill(btns, "Cancel", self.destroy, width=90).pack(side="right", padx=8)
        tk.Label(btns, text="Ctrl+Enter to save", bg=BG, fg=FAINT, font=F_SMALL).pack(side="left")

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-Return>", lambda _e: self.save())
        self.q.bind("<Return>", lambda _e: self.a.focus())
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + 90
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        (self.a if question else self.q).focus()

    def save(self):
        q, a = self.q.get().strip(), self.a.get("1.0", "end").strip()
        if not q or not a:
            messagebox.showwarning("Missing text", "Please fill in both the phrase and the answer.", parent=self)
            return
        self.result = (q, a)
        self.destroy()


class App(tk.Tk):
    reply_delay_ms = 450  # short "typing" pause so replies feel natural; 0 = instant

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("700x780")
        self.minsize(560, 520)
        self.configure(bg=BG)
        self.agent = ChatNoirAgent()
        self.history, self.hist_pos = [], 0
        self.last_unknown = ""
        self._pending = None

        self._build_header()
        self._build_input()  # bottom-packed first so they never get squeezed out
        self._build_chips()
        self._build_chat()

        self.bind("<Control-l>", lambda _e: self.clear())
        self.bind("<Control-t>", lambda _e: self.teach())
        self.refresh_subtitle()
        self.greet()

    # ---- layout ----
    def _build_header(self):
        head = tk.Frame(self, bg=SURFACE)
        head.pack(fill="x")
        av = tk.Canvas(head, width=44, height=44, bg=SURFACE, highlightthickness=0)
        av.pack(side="left", padx=(18, 12), pady=14)
        av.create_oval(2, 2, 42, 42, fill=GOLD, outline="")
        av.create_text(22, 22, text=APP_NAME[0], fill=ON_GOLD, font=("Segoe UI Semibold", 17))
        col = tk.Frame(head, bg=SURFACE)
        col.pack(side="left", pady=14)
        tk.Label(col, text=APP_NAME, bg=SURFACE, fg=FG, font=F_TITLE).pack(anchor="w")
        sub = tk.Frame(col, bg=SURFACE)
        sub.pack(anchor="w")
        dot = tk.Canvas(sub, width=10, height=10, bg=SURFACE, highlightthickness=0)
        dot.create_oval(1, 1, 9, 9, fill=ONLINE, outline="")
        dot.pack(side="left", padx=(0, 6))
        self.subtitle = tk.Label(sub, bg=SURFACE, fg=MUTED, font=F_SMALL)
        self.subtitle.pack(side="left")

        tools = tk.Frame(head, bg=SURFACE)
        tools.pack(side="right", padx=14)
        self.buttons = {}
        for text, cmd in (("Teach", self.teach), ("Reload", self.reload), ("Clear", self.clear)):
            b = Pill(tools, text, cmd, bg=SURFACE, height=30)
            b.pack(side="left", padx=3)
            self.buttons[text] = b
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

    def _build_chat(self):
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Noir.Vertical.TScrollbar", background=SURFACE_2, troughcolor=BG, bordercolor=BG,
                        lightcolor=SURFACE_2, darkcolor=SURFACE_2, arrowcolor=BG, relief="flat")
        style.map("Noir.Vertical.TScrollbar", background=[("active", BORDER)])
        sb = ttk.Scrollbar(wrap, style="Noir.Vertical.TScrollbar")
        sb.pack(side="right", fill="y")
        self.log = tk.Text(wrap, wrap="word", state="disabled", bg=BG, fg=FG, bd=0, highlightthickness=0,
                           font=F_BASE, padx=18, pady=14, cursor="arrow", spacing1=0, spacing3=0,
                           yscrollcommand=sb.set, selectbackground=BORDER)
        self.log.pack(side="left", fill="both", expand=True)
        sb.config(command=self.log.yview)

        t = self.log.tag_config
        t("meta_bot", foreground=FAINT, font=F_SMALL, lmargin1=18, lmargin2=18, spacing1=10)
        t("meta_you", foreground=FAINT, font=F_SMALL, justify="right", rmargin=18, lmargin1=90, spacing1=10)
        self._font_you = tkfont.Font(font=F_BOLD)
        t("bot", background=SURFACE_2, foreground=FG, lmargin1=18, lmargin2=18, rmargin=90,
          spacing1=3, spacing3=3, font=F_BASE)
        t("you", background=GOLD, foreground=ON_GOLD, justify="right", lmargin1=90, lmargin2=90,
          rmargin=18, spacing1=3, spacing3=3, font=F_BOLD)
        t("sys", foreground=FAINT, font=("Segoe UI", 9, "italic"), justify="center", spacing1=10)
        t("typing", foreground=MUTED, font=("Segoe UI", 10, "italic"), lmargin1=18, spacing1=10)
        t("meta_bot_nl")
        t("meta_you_nl")
        t("you_line", justify="right", rmargin=18, lmargin1=90, lmargin2=90)
        t("gap", font=("Segoe UI", 4))

    def _build_chips(self):
        self.chips = tk.Frame(self, bg=BG)
        self.chips.pack(side="bottom", fill="x", padx=16, pady=(4, 6))
        for s in SUGGESTIONS:
            Pill(self.chips, s, lambda s=s: self.send(s), height=28).pack(side="left", padx=3)

    def _build_input(self):
        bar = tk.Canvas(self, height=58, bg=BG, highlightthickness=0)
        bar.pack(side="bottom", fill="x", padx=16, pady=(0, 16))
        self.var = tk.StringVar()
        self.entry = tk.Entry(bar, textvariable=self.var, bg=SURFACE, fg=FG, insertbackground=GOLD, bd=0,
                              font=("Segoe UI", 12), highlightthickness=0)
        self.shape = None
        self.send_btn = Pill(bar, "Send", self.send, primary=True, width=84, height=38, bg=SURFACE)
        self.bar = bar
        self.entry_win = bar.create_window(0, 0, window=self.entry, anchor="w")
        self.btn_win = bar.create_window(0, 0, window=self.send_btn, anchor="e")
        bar.bind("<Configure>", self._layout_input)
        self.entry.bind("<Return>", lambda _e: self.send())
        self.entry.bind("<Up>", lambda _e: self.recall(-1))
        self.entry.bind("<Down>", lambda _e: self.recall(1))
        self.entry.bind("<FocusIn>", lambda _e: self._outline(GOLD))
        self.entry.bind("<FocusOut>", lambda _e: self._outline(BORDER))
        self.entry.focus()

    def _outline(self, color):
        if self.shape:
            self.bar.itemconfig(self.shape, outline=color)

    def _layout_input(self, e):
        w, h = e.width, e.height
        self.bar.delete("pill")
        self.shape = rounded(self.bar, 1, 4, w - 1, h - 4, (h - 8) // 2, fill=SURFACE, outline=BORDER, tags="pill")
        self.bar.tag_lower("pill")
        self.bar.coords(self.entry_win, 22, h // 2)
        self.bar.itemconfig(self.entry_win, width=w - 140)
        self.bar.coords(self.btn_win, w - 10, h // 2)

    # ---- helpers ----
    def refresh_subtitle(self):
        self.subtitle.config(text=f"Online locally • {len(self.agent.rows)} answers in knowledge.csv")

    def greet(self):
        self.say("Assistant", "Hello! How can I help you today?", "bot")
        self.note("Up/Down recalls messages  •  Ctrl+T teaches  •  Ctrl+L clears  •  I can do maths too")

    def _write(self, *parts):
        self.log.config(state="normal")
        for text, tag in parts:
            self.log.insert("end", text, tag)
        self.log.config(state="disabled")
        self.log.see("end")

    def say(self, who, text, tag):
        stamp = datetime.now().strftime("%H:%M")
        meta = "meta_you" if tag == "you" else "meta_bot"
        if tag == "you":  # right-aligned bubble: an embedded label sized to its text
            self._write((f"{who}  {stamp}\n", meta))
            self.log.config(state="normal")
            width = int(max(self.log.winfo_width(), 400) * 0.72)
            bubble = tk.Label(self.log, text=text, bg=GOLD, fg=ON_GOLD, font=F_BOLD, justify="left",
                              wraplength=width, padx=12, pady=6, anchor="w")
            self.log.insert("end", "\u200b", "you_line")
            self.log.window_create("end-1c", window=bubble)
            self.log.insert("end", "\n", "you_line")
            self.log.insert("end", "\n", "gap")
            self.log.config(state="disabled")
            self.log.see("end")
            return
        self._write((f"{who}  {stamp}\n", meta), (f"  {text}  ", tag), ("\n", meta + "_nl"), ("\n", "gap"))

    def note(self, text):
        self._write((text + "\n", "sys"))

    def _show_typing(self, on):
        self.log.config(state="normal")
        if on:
            self.log.insert("end", "Typing…\n", "typing")
        else:
            ranges = self.log.tag_ranges("typing")
            if ranges:
                self.log.delete(ranges[0], ranges[-1])
        self.log.config(state="disabled")
        self.log.see("end")

    # ---- actions ----
    def recall(self, step):
        if not self.history:
            return "break"
        self.hist_pos = max(0, min(len(self.history), self.hist_pos + step))
        self.entry.delete(0, "end")
        if self.hist_pos < len(self.history):
            self.entry.insert(0, self.history[self.hist_pos])
        self.entry.icursor("end")
        return "break"

    def send(self, text=None):
        msg = (text if text is not None else self.entry.get()).strip()
        if not msg:
            return
        self.entry.delete(0, "end")
        self.history.append(msg)
        self.hist_pos = len(self.history)
        self.say("You", msg, "you")
        try:
            answer, known = self.agent.respond_ex(msg)
        except Exception as exc:  # never let one bad reply crash the window
            answer, known = f"Something went wrong: {exc}", True
        if self.reply_delay_ms:
            self._show_typing(True)
            self._pending = self.after(self.reply_delay_ms, lambda: self._reply(msg, answer, known))
        else:
            self._reply(msg, answer, known)

    def _reply(self, msg, answer, known):
        self._pending = None
        self._show_typing(False)
        self.say("Assistant", answer, "bot")
        if not known:
            self.last_unknown = msg
            self.note("I don't know that yet — press Teach (Ctrl+T) to add an answer.")

    def teach(self):
        dlg = TeachDialog(self, self.last_unknown)
        self.wait_window(dlg)
        if not dlg.result:
            self.entry.focus()
            return
        try:
            updated = self.agent.learn(*dlg.result)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not save", f"{exc}", parent=self)
            return
        self.last_unknown = ""
        self.refresh_subtitle()
        self.note("Updated an existing answer." if updated else "Learned! Added to knowledge.csv.")
        self.entry.focus()

    def reload(self):
        try:
            self.agent.load()
        except (OSError, UnicodeDecodeError) as exc:
            messagebox.showerror("Could not reload", f"{exc}", parent=self)
            return
        self.refresh_subtitle()
        extra = f" ({self.agent.skipped} incomplete rows skipped)" if self.agent.skipped else ""
        self.note(f"Reloaded {len(self.agent.rows)} entries{extra}.")

    def clear(self):
        if self._pending:
            self.after_cancel(self._pending)
            self._pending = None
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        self.greet()


if __name__ == "__main__":
    App().mainloop()
