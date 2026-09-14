"""Playable Tk view. Importing the game engine never imports Tkinter."""

import tkinter as tk
from tkinter import ttk

from .forward_model import ForwardModelGriddle


class GridView:
    def __init__(self, model: ForwardModelGriddle, root: tk.Tk | None = None):
        self.model = model
        self.root = root if root is not None else tk.Tk()
        self.root.title("Griddle")
        self.root.geometry("560x650")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self.status = tk.StringVar(master=self.root)
        ttk.Label(self.root, textvariable=self.status, padding=12).grid(row=0, column=0)
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(row=1, column=0, sticky="nsew")
        self.buttons: list[tk.Button] = []
        for row in range(model.state.grid.size()):
            frame.rowconfigure(row, weight=1)
            frame.columnconfigure(row, weight=1)
            for col in range(model.state.grid.size()):
                index = model.state.grid.index(row, col)
                button = tk.Button(frame, font=("Helvetica", 24),
                                   command=lambda i=index: self.place(i))
                button.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)
                self.buttons.append(button)
        self.words = tk.Text(self.root, height=8, wrap="word", state="disabled")
        self.words.grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        self.refresh()

    def place(self, index: int) -> None:
        self.model.place_index(index)
        self.refresh()

    def refresh(self) -> None:
        matches = self.model.matches()
        score = sum(match.score for match in matches)
        if self.model.is_terminal():
            self.status.set(f"Game over — final score: {score}")
        else:
            self.status.set(f"Place {self.model.state.current_letter} in an empty cell.  Score: {score}")
        for button, letter in zip(self.buttons, self.model.state.grid.letters):
            button.configure(text=letter, state="normal" if letter == " " else "disabled")
        self.words.configure(state="normal")
        self.words.delete("1.0", tk.END)
        self.words.insert("1.0", "\n".join(
            f"{m.word}: {m.score} points ({m.row + 1}, {m.col + 1}, {m.direction})"
            for m in matches
        ) or "Words of two or more letters score across and down.")
        self.words.configure(state="disabled")

    def run(self) -> None:
        self.root.mainloop()
