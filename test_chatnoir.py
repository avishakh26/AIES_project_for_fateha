"""Tests for Chat Noir AI (agent + GUI). Run: python -m unittest -v test_chatnoir"""
import csv
import os
import shutil
import tempfile
import unittest
from datetime import datetime

from chatnoir_agent import DEFAULT_CSV, ChatNoirAgent, calculate, tokenize


class AgentBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "k.csv")
        shutil.copy(DEFAULT_CSV, self.path)
        self.a = ChatNoirAgent(self.path)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestLoading(AgentBase):
    def test_loads_rows(self):
        self.assertGreater(len(self.a.rows), 100)
        self.assertEqual(self.a.skipped, 0)

    def test_creates_missing_csv(self):
        p = os.path.join(self.dir, "new.csv")
        a = ChatNoirAgent(p)
        self.assertTrue(os.path.exists(p))
        self.assertEqual(a.rows, [])

    def test_skips_incomplete_rows(self):
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            f.write("x,onlyquestion,\nx,,onlyanswer\n")
        self.a.load()
        self.assertEqual(self.a.skipped, 2)

    def test_empty_kb_responds_with_fallback(self):
        a = ChatNoirAgent(os.path.join(self.dir, "e.csv"))
        ans, known = a.respond_ex("anything")
        self.assertFalse(known)


class TestMatching(AgentBase):
    def test_exact(self):
        self.assertEqual(self.a.respond("capital of france"), "Paris.")

    def test_case_and_punctuation(self):
        self.assertEqual(self.a.respond("Capital of FRANCE?!"), "Paris.")

    def test_keyword_match(self):
        self.assertIn("Eight", self.a.respond("how many planets"))

    def test_typos(self):
        self.assertEqual(self.a.respond("capitol of frnace"), "Paris.")

    def test_plurals(self):
        self.assertIn("Eight", self.a.respond("how many planet are in the solar system"))

    def test_unknown_returns_false(self):
        ans, known = self.a.respond_ex("blorp zzz qqq")
        self.assertFalse(known)

    def test_suggestions_on_unknown(self):
        ans, known = self.a.respond_ex("capital of narnia zorp")
        # either matched capital rows or gave suggestions; must never crash
        self.assertIsInstance(ans, str)

    def test_empty_input(self):
        ans, known = self.a.respond_ex("   ")
        self.assertTrue(known)
        self.assertIn("type a message", ans)

    def test_stopword_only_input(self):
        ans, known = self.a.respond_ex("the of a")
        self.assertFalse(known)

    def test_greeting(self):
        self.assertIn("Hello", self.a.respond("hello"))

    def test_joke(self):
        self.assertIn("cheetahs", self.a.respond("tell me a joke"))


class TestBuiltins(AgentBase):
    def test_time(self):
        for q in ("what time is it", "whats the time", "what's the time", "what is the time"):
            self.assertRegex(self.a.respond(q), r"It's \d\d:\d\d\.")

    def test_date(self):
        self.assertIn(str(datetime.now().year), self.a.respond("what is the date"))
        self.assertIn(str(datetime.now().year), self.a.respond("what day is it"))

    def test_year(self):
        self.assertEqual(self.a.respond("what year is it"), f"It's {datetime.now().year}.")

    def test_month(self):
        self.assertEqual(self.a.respond("what is the month"), f"It's {datetime.now().strftime('%B')}.")


class TestMaths(unittest.TestCase):
    def test_cases(self):
        cases = {
            "2+2": "4", "15*3": "45", "what is 15*3": "45", "2^10": "1024",
            "10/4": "2.5", "10 / 2": "5", "7 plus 5": "12", "9 minus 12": "-3",
            "6 times 7": "42", "20 divided by 5": "4", "(2+3)*4": "20",
            "3 x 4": "12", "10 % 3": "1", "what is 2 + 2 ?": "4", "-5+10": "5",
            "0.1+0.2": "0.3",
        }
        for q, want in cases.items():
            self.assertEqual(calculate(q), want, q)

    def test_div_zero(self):
        self.assertEqual(calculate("10/0"), "I can't calculate that one.")

    def test_huge_power_rejected(self):
        self.assertEqual(calculate("9**999"), "I can't calculate that one.")

    def test_non_math_returns_none(self):
        for q in ("hello", "what is pi", "capital of france", "what is 5", "", "1999"):
            self.assertIsNone(calculate(q), q)

    def test_no_code_execution(self):
        for q in ("__import__('os')", "2+__import__('os')", "open('x')"):
            self.assertIsNone(calculate(q), q)

    def test_agent_routes_maths(self):
        a = ChatNoirAgent(os.path.join(tempfile.mkdtemp(), "e.csv"))
        self.assertEqual(a.respond("what is 15*3"), "45")


class TestTeach(AgentBase):
    def test_learn_new(self):
        self.assertFalse(self.a.learn("favourite game", "Chess"))
        self.assertEqual(self.a.respond("favourite game"), "Chess")

    def test_persisted_to_disk(self):
        self.a.learn("favourite game", "Chess")
        b = ChatNoirAgent(self.path)
        self.assertEqual(b.respond("favourite game"), "Chess")

    def test_duplicate_updates(self):
        n = len(self.a.rows)
        self.a.learn("favourite game", "Chess")
        self.assertTrue(self.a.learn("Favourite game!", "Go"))
        self.assertEqual(len(self.a.rows), n + 1)
        self.assertEqual(self.a.respond("favourite game"), "Go")

    def test_commas_quotes_unicode(self):
        self.a.learn("what is café, \"special\"", "Yes, it's \"café\" — ünïcode")
        b = ChatNoirAgent(self.path)
        self.assertEqual(b.respond("what is café special"), "Yes, it's \"café\" — ünïcode")

    def test_empty_rejected(self):
        for q, ans in (("", "x"), ("x", ""), ("  ", "  ")):
            with self.assertRaises(ValueError):
                self.a.learn(q, ans)

    def test_no_tmp_file_left(self):
        self.a.learn("abc def", "ghi")
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_csv_stays_valid(self):
        self.a.learn("abc def", "ghi")
        with open(self.path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(list(rows[0].keys()), ["category", "question", "answer"])
        self.assertEqual(rows[-1]["question"], "abc def")

    def test_reload_picks_up_manual_edit(self):
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            f.write("t,secret word,Open sesame\n")
        self.a.load()
        self.assertEqual(self.a.respond("secret word"), "Open sesame")


class TestTokenize(unittest.TestCase):
    def test_removes_stopwords(self):
        self.assertEqual(tokenize("What is the capital of France?"), ["capital", "france"])


class TestGUI(AgentBase):
    @classmethod
    def setUpClass(cls):
        import tkinter
        try:
            r = tkinter.Tk(); r.destroy()
        except tkinter.TclError:
            raise unittest.SkipTest("no display")

    def setUp(self):
        super().setUp()
        import chatnoirwbd
        self.g = chatnoirwbd
        self.app = chatnoirwbd.App()
        self.app.agent = ChatNoirAgent(self.path)
        self.app.refresh_subtitle()

    def tearDown(self):
        self.app.destroy()
        super().tearDown()

    def text(self):
        return self.app.log.get("1.0", "end")

    def send(self, msg):
        self.app.entry.delete(0, "end")
        self.app.entry.insert(0, msg)
        self.app.send()
        self.app.update()

    def test_greeting_shown(self):
        self.assertIn("Hello! How can I help", self.text())

    def test_send_and_reply(self):
        self.send("capital of france")
        self.assertIn("You:", self.text())
        self.assertIn("Paris.", self.text())
        self.assertEqual(self.app.entry.get(), "")

    def test_send_maths(self):
        self.send("2+2")
        self.assertIn("\n4\n", self.text())

    def test_empty_send_ignored(self):
        before = self.text()
        self.send("   ")
        self.assertEqual(before, self.text())

    def test_timestamp(self):
        self.send("hello")
        self.assertRegex(self.text(), r"You: \d\d:\d\d")

    def test_history_recall(self):
        self.send("one"); self.send("two")
        self.app.recall(-1); self.assertEqual(self.app.entry.get(), "two")
        self.app.recall(-1); self.assertEqual(self.app.entry.get(), "one")
        self.app.recall(-1); self.assertEqual(self.app.entry.get(), "one")
        self.app.recall(1); self.assertEqual(self.app.entry.get(), "two")
        self.app.recall(1); self.assertEqual(self.app.entry.get(), "")

    def test_history_empty_safe(self):
        self.assertEqual(self.app.recall(-1), "break")

    def test_clear(self):
        self.send("hello")
        self.app.clear()
        self.assertNotIn("You:", self.text())
        self.assertIn("Hello! How can I help", self.text())

    def test_unknown_sets_teach_prefill_and_tip(self):
        self.send("blorp zzz qqq")
        self.assertEqual(self.app.last_unknown, "blorp zzz qqq")
        self.assertIn("Teach", self.text())

    def test_subtitle_count(self):
        self.assertIn(str(len(self.app.agent.rows)), self.app.subtitle.cget("text"))

    def test_reload(self):
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            f.write("t,secret word,Open sesame\n")
        self.app.reload()
        self.assertIn("Reloaded", self.text())
        self.send("secret word")
        self.assertIn("Open sesame", self.text())

    def test_teach_dialog_save_and_validation(self):
        d = self.g.TeachDialog(self.app, "prefilled q")
        self.assertEqual(d.q.get(), "prefilled q")
        d.a.insert("1.0", "  my answer ")
        d.save()
        self.assertEqual(d.result, ("prefilled q", "my answer"))

    def test_teach_dialog_cancel(self):
        d = self.g.TeachDialog(self.app)
        d.destroy()
        self.assertIsNone(d.result)

    def test_teach_flow(self):
        orig = self.g.TeachDialog

        class Fake:
            def __init__(s, parent, q=""):
                s.result = ("fav game", "Chess")
        self.g.TeachDialog = Fake
        self.app.wait_window = lambda _w: None
        try:
            self.app.teach()
        finally:
            self.g.TeachDialog = orig
        self.assertIn("Learned!", self.text())
        self.send("fav game")
        self.assertIn("Chess", self.text())

    def test_teach_cancel_flow(self):
        class Fake:
            def __init__(s, parent, q=""):
                s.result = None
        orig = self.g.TeachDialog
        self.g.TeachDialog = Fake
        self.app.wait_window = lambda _w: None
        n = len(self.app.agent.rows)
        try:
            self.app.teach()
        finally:
            self.g.TeachDialog = orig
        self.assertEqual(len(self.app.agent.rows), n)


if __name__ == "__main__":
    unittest.main()
