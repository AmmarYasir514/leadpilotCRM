"""
Upwork login storage for LeadPilot.

Your Upwork email and password are saved in Windows Credential Manager
(Windows' own locked password vault), never in this file or any text file.

How to use:
  1. Double-click "Upwork_Login_Setup.bat" once.
  2. Type your Upwork email and password, then click Save.
  3. Done. LeadPilot can read them later with get_upwork_login().
"""

import tkinter as tk
from tkinter import messagebox

try:
    import keyring
except ImportError:
    keyring = None

SERVICE = "LeadPilot-Upwork"   # name shown in Windows Credential Manager
EMAIL_KEY = "__email__"


def save_upwork_login(email, password):
    keyring.set_password(SERVICE, EMAIL_KEY, email)
    keyring.set_password(SERVICE, email, password)


def get_upwork_login():
    """Returns (email, password), or (None, None) if nothing is saved yet."""
    if keyring is None:
        return None, None
    email = keyring.get_password(SERVICE, EMAIL_KEY)
    if not email:
        return None, None
    return email, keyring.get_password(SERVICE, email)


def clear_upwork_login():
    email = keyring.get_password(SERVICE, EMAIL_KEY)
    for key in (email, EMAIL_KEY):
        if key:
            try:
                keyring.delete_password(SERVICE, key)
            except Exception:
                pass


def open_login_window():
    root = tk.Tk()
    root.title("LeadPilot - Upwork Login")
    root.geometry("380x210")
    root.resizable(False, False)

    if keyring is None:
        messagebox.showerror("Missing part", "Run: python -m pip install keyring")
        root.destroy()
        return

    saved_email, _ = get_upwork_login()

    tk.Label(root, text="Upwork email").pack(anchor="w", padx=20, pady=(15, 0))
    email_box = tk.Entry(root, width=42)
    email_box.pack(padx=20)
    if saved_email:
        email_box.insert(0, saved_email)

    tk.Label(root, text="Upwork password").pack(anchor="w", padx=20, pady=(10, 0))
    pass_box = tk.Entry(root, width=42, show="*")   # hides what you type
    pass_box.pack(padx=20)

    status = tk.Label(root, text="Saved login found." if saved_email else "No login saved yet.", fg="gray")
    status.pack(pady=(8, 0))

    def on_save():
        email = email_box.get().strip()
        password = pass_box.get()
        if not email or not password:
            messagebox.showwarning("Missing info", "Please enter both email and password.")
            return
        save_upwork_login(email, password)
        pass_box.delete(0, tk.END)
        messagebox.showinfo("Saved", "Your Upwork login is saved securely in Windows.")
        root.destroy()

    def on_clear():
        clear_upwork_login()
        email_box.delete(0, tk.END)
        pass_box.delete(0, tk.END)
        status.config(text="Saved login removed.")

    buttons = tk.Frame(root)
    buttons.pack(pady=12)
    tk.Button(buttons, text="Save", width=12, command=on_save).pack(side="left", padx=5)
    tk.Button(buttons, text="Remove saved login", command=on_clear).pack(side="left", padx=5)

    root.mainloop()


if __name__ == "__main__":
    open_login_window()
