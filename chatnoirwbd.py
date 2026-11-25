"""Local AI assistant: desktop GUI (Tkinter). Fully offline."""
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext

from chatnoir_agent import ChatNoirAgent

BG, PANEL, FG, ACCENT, MUTED = "#14141c", "#1f1f2b", "#eaeaf2", "#7bdc65", "#888"
FONT = ("Segoe UI", 11)

try:  # crisp text on high-DPI Windows displays
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class TeachDialog(tk.Toplevel):
    """One window for both fields, with Enter/Esc shortcuts."""

    def __init__(self, parent, question=""):
        super().__init__(parent, bg=BG)
        self.title("Teach Chat Noir")
        self.transient(parent)
        self.resizable(False, False)
        self.result = None

        tk.Label(self, text="When the user says (keywords/phrase):", bg=BG, fg=FG, font=FONT).pack(anchor="w", padx=14, pady=(14, 2))
        self.q = tk.Entry(self, width=54, bg=PANEL, fg=FG, insertbackground=FG, bd=0, font=FONT)
        self.q.pack(padx=14, ipady=6)
        self.q.insert(0, question)
        tk.Label(self, text="The assistant should answer:", bg=BG, fg=FG, font=FONT).pack(anchor="w", padx=14, pady=(10, 2))
        self.a = tk.Text(self, width=54, height=5, wrap="word", bg=PANEL, fg=FG, insertbackground=FG, bd=0, font=FONT)
        self.a.pack(padx=14)

        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=14, pady=14)
        tk.Button(btns, text="Save", command=self.save, bg=ACCENT, fg="#000", bd=0, padx=14, pady=5).pack(side="right")
        tk.Button(btns, text="Cancel", command=self.destroy, bg=PANEL, fg=FG, bd=0, padx=14, pady=5).pack(side="right", padx=6)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-Return>", lambda _e: self.save())
        self.q.bind("<Return>", lambda _e: self.a.focus())
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + 80
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
    def __init__(self):
        super().__init__()
        self.title("Chat Noir AI")
        self.geometry("560x680")
        self.minsize(420, 480)
        self.configure(bg=BG)
        self.agent = ChatNoirAgent()
        self.history, self.hist_pos = [], 0
        self.last_unknown = ""

        tk.Label(self, text="Chat Noir AI", font=("Segoe UI", 20, "bold"), bg=BG, fg=ACCENT).pack(pady=(12, 0))
        self.subtitle = tk.Label(self, bg=BG, fg=MUTED)
        self.subtitle.pack()

        self.log = scrolledtext.ScrolledText(
            self, wrap="word", state="disabled", bg=PANEL, fg=FG, bd=0,
            font=FONT, padx=10, pady=10, cursor="arrow",
        )
        self.log.pack(fill="both", expand=True, padx=12, pady=10)
        self.log.tag_config("you", foreground="#8ab4ff", font=("Segoe UI", 11, "bold"))
        self.log.tag_config("bot", foreground=ACCENT, font=("Segoe UI", 11, "bold"))
        self.log.tag_config("time", foreground=MUTED, font=("Segoe UI", 8))
        self.log.tag_config("sys", foreground=MUTED, font=("Segoe UI", 10, "italic"))

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=12, pady=(0, 12))
        self.entry = tk.Entry(row, bg=PANEL, fg=FG, insertbackground=FG, bd=0, font=("Segoe UI", 12))
        self.entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        self.entry.bind("<Return>", lambda _e: self.send())
        self.entry.bind("<Up>", lambda _e: self.recall(-1))
        self.entry.bind("<Down>", lambda _e: self.recall(1))
        self.entry.focus()

        self.buttons = {}
        for text, cmd in (("Send", self.send), ("Teach", self.teach), ("Reload", self.reload), ("Clear", self.clear)):
            b = tk.Button(row, text=text, command=cmd, bg=ACCENT if text == "Send" else PANEL,
                          fg="#000" if text == "Send" else FG, bd=0, padx=10, pady=6,
                          activebackground="#a0eb8e" if text == "Send" else "#2b2b3b", cursor="hand2")
            b.pack(side="left", padx=2)
            self.buttons[text] = b

        self.bind("<Control-l>", lambda _e: self.clear())
        self.bind("<Control-t>", lambda _e: self.teach())
        self.refresh_subtitle()
        self.greet()

    # ---- helpers ----
    def refresh_subtitle(self):
        self.subtitle.config(text=f"Offline chatbot • {len(self.agent.rows)} answers in knowledge.csv")

    def greet(self):
        self.say("Assistant", "Hello! How can I help you today?", "bot")
        self.note("Tips: Up/Down recalls earlier messages • Ctrl+T teaches • Ctrl+L clears. I can also do maths.")

    def _write(self, *parts):
        self.log.config(state="normal")
        for text, tag in parts:
            self.log.insert("end", text, tag)
        self.log.config(state="disabled")
        self.log.see("end")

    def say(self, who, text, tag):
        stamp = datetime.now().strftime("%H:%M")
        self._write((f"{who}: ", tag), (f"{stamp}\n", "time"), (text + "\n\n", ""))

    def note(self, text):
        self._write((text + "\n\n", "sys"))

    # ---- actions ----
    def recall(self, step):
        if not self.history:
            return "break"
        self.hist_pos = max(0, min(len(self.history), self.hist_pos + step))
        self.entry.delete(0, "end")
        if self.hist_pos < len(self.history):
            self.entry.insert(0, self.history[self.hist_pos])
        return "break"

    def send(self):
        msg = self.entry.get().strip()
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
        self.say("Assistant", answer, "bot")
        if not known:
            self.last_unknown = msg
            self.note("Tip: press Teach (Ctrl+T) to add an answer for that.")

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
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        self.greet()


if __name__ == "__main__":
    App().mainloop()
