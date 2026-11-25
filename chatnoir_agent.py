"""Local Noir Intelligence chatbot. No network, no API keys, no third-party packages.

Knowledge lives in a CSV file with the columns: category, question, answer.
`question` holds keywords/phrases; the agent retrieves the best matching row
with a small TF-IDF cosine-similarity search, tolerating typos and plurals.
"""
import ast
import csv
import difflib
import math
import operator
import os
import random
import re
from collections import Counter
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(BASE_DIR, "knowledge.csv")
FIELDS = ["category", "question", "answer"]

STOPWORDS = {
    "a", "an", "the", "is", "are", "am", "to", "of", "and", "or", "it", "me",
    "my", "you", "your", "do", "does", "i", "in", "on", "for", "with", "that",
    "this", "be", "so", "can", "what", "us", "we", "today", "very", "really",
    "please", "tell", "about",
}

FALLBACKS = [
    "Sorry, I don't know the answer to that yet. You can teach me with the Teach button.",
    "I'm not sure about that one. Try rephrasing, or teach me the answer.",
    "I don't have an answer for that yet. Would you like to teach me?",
]

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def tokenize(text):
    words = re.findall(r"[a-z0-9']+", text.lower())
    return [w for w in words if w not in STOPWORDS]


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


def calculate(text):
    """Return a formatted result if `text` is a simple arithmetic question, else None."""
    expr = text.lower()
    expr = re.sub(r"\b(what is|what's|whats|calculate|compute|solve|equals?)\b|[=?]", " ", expr)
    expr = expr.replace("x", "*").replace("×", "*").replace("÷", "/").replace("^", "**")
    expr = re.sub(r"\bplus\b", "+", expr)
    expr = re.sub(r"\bminus\b", "-", expr)
    expr = re.sub(r"\b(times|multiplied by)\b", "*", expr)
    expr = re.sub(r"\b(divided by|over)\b", "/", expr).strip()
    if not re.fullmatch(r"[\d\s+\-*/().%]+", expr) or not re.search(r"\d\s*[+\-*/%]", expr):
        return None
    try:
        result = _safe_eval(ast.parse(expr, mode="eval"))
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
        return "I can't calculate that one."
    if isinstance(result, float):
        result = round(result, 10)
        if result == int(result) and abs(result) < 1e15:
            result = int(result)
    return f"{result}"


class ChatNoirAgent:
    def __init__(self, csv_path=DEFAULT_CSV, threshold=0.2):
        self.csv_path = csv_path
        self.threshold = threshold
        self.rows = []
        self.skipped = 0
        self.load()

    # ---- knowledge ----
    def load(self):
        """(Re)load the CSV. Bad/blank rows are skipped and counted in `self.skipped`."""
        self.rows = []
        self.skipped = 0
        if not os.path.exists(self.csv_path):
            self._write_all()
        with open(self.csv_path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                q = (r.get("question") or "").strip()
                a = (r.get("answer") or "").strip()
                if q and a:
                    self.rows.append(
                        {"category": (r.get("category") or "").strip(), "question": q, "answer": a}
                    )
                else:
                    self.skipped += 1
        self._index()

    def _write_all(self):
        tmp = self.csv_path + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(getattr(self, "rows", []))
        os.replace(tmp, self.csv_path)  # atomic: never leaves a half-written file

    def _index(self):
        docs = [Counter(self._stem(t) for t in tokenize(r["question"])) for r in self.rows]
        n = len(docs)
        df = Counter()
        for d in docs:
            df.update(d.keys())
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.vocab = list(df)
        self.vecs = [self._vec(d) for d in docs]

    @staticmethod
    def _stem(word):
        if len(word) > 3 and word.endswith("ies"):
            return word[:-3] + "y"
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
        return word

    def _query_counts(self, text):
        counts = Counter()
        for t in tokenize(text):
            t = self._stem(t)
            if t not in self.idf and len(t) > 3:  # likely a typo: snap to a known word
                close = difflib.get_close_matches(t, self.vocab, n=1, cutoff=0.8)
                if close:
                    t = close[0]
            counts[t] += 1
        return counts

    def _vec(self, counts):
        v = {t: c * self.idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def learn(self, question, answer, category="taught"):
        """Add a Q&A pair. If the question already exists its answer is replaced.
        Returns True if an existing entry was updated."""
        question, answer = question.strip(), answer.strip()
        if not question or not answer:
            raise ValueError("Both a question and an answer are required.")
        key = " ".join(re.findall(r"[a-z0-9']+", question.lower()))
        updated = False
        for row in self.rows:
            if " ".join(re.findall(r"[a-z0-9']+", row["question"].lower())) == key:
                row["answer"], updated = answer, True
                break
        if not updated:
            self.rows.append({"category": category, "question": question, "answer": answer})
        self._write_all()
        self._index()
        return updated

    # ---- responding ----
    def _score(self, text):
        q = self._vec(self._query_counts(text))
        scored = []
        for row, vec in zip(self.rows, self.vecs):
            s = sum(w * vec.get(t, 0.0) for t, w in q.items())
            if s > 0:
                scored.append((s, row))
        scored.sort(key=lambda x: -x[0])
        return scored

    def respond_ex(self, text):
        """Return (answer, known). `known` is False when the bot had no answer."""
        text = text.strip()
        if not text:
            return "Please type a message and I'll do my best to help.", True
        low = text.lower()
        if re.search(r"\b(what's|whats|what is|what) the time\b|\bwhat time\b", low):
            return f"It's {datetime.now().strftime('%H:%M')}.", True
        if re.search(r"\b(today's|todays|the) date\b|\bwhat day\b", low):
            return f"Today is {datetime.now().strftime('%A, %d %B %Y')}.", True
        if re.search(r"\bwhat year\b", low):
            return f"It's {datetime.now().year}.", True
        if re.search(r"\b(what's|whats|what is|what) the month\b|\bwhat month\b", low):
            return f"It's {datetime.now().strftime('%B')}.", True

        calc = calculate(text)
        if calc is not None:
            return calc, True

        norm = " ".join(re.findall(r"[a-z0-9']+", low))
        for row in self.rows:
            if row["question"].lower() == norm:
                return row["answer"], True

        scored = self._score(text)
        if scored and scored[0][0] >= self.threshold:
            return scored[0][1]["answer"], True

        msg = random.choice(FALLBACKS)
        hints = [r["question"] for s, r in scored[:3] if s >= self.threshold / 2]
        if hints:
            msg += "\n\nDid you mean:\n" + "\n".join(f"  - {h}" for h in hints)
        return msg, False

    def respond(self, text):
        return self.respond_ex(text)[0]
