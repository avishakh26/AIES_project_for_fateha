# Noir Intelligence

A fully local, offline chatbot. No API keys, no internet, no cloud.

## Features

- **Runs locally**: pure Python standard library, no dependencies
- **CSV knowledge base**: `knowledge.csv` (`category,question,answer`); edit it in Excel or any text editor
- **Retrieval**: TF-IDF matching picks the best row for what you type
- **Teach mode**: the GUI's *Teach* button appends new Q&A rows to the CSV
- **Typo tolerant**: "capitol of frnace" still finds the right answer; low-confidence replies suggest similar questions
- **Built-in helpers**: time, date and simple maths (`15*3`, `2^10`)
- **Smoother teaching**: one dialog, duplicate questions update the old answer, safe atomic saves
- **Desktop GUI** built with Tkinter: timestamps, message history (Up/Down), Clear (Ctrl+L), Teach (Ctrl+T)

## Run

```bash
python chatnoirwbd.py
```

## Extending knowledge

Add rows to `knowledge.csv`. The `question` column holds keywords or sample phrases; the `answer` column is the reply. Click **Reload CSV** after editing by hand.
