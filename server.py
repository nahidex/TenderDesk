#!/usr/bin/env python3
"""
Folder Explorer + PDF/Image Preview + Evaluation Checklist — server backend.

এই স্ক্রিপ্টটা index.html-এর পাশে রাখুন এবং চালান:

    python3 server.py

ডিফল্টে এটা সব নেটওয়ার্ক ইন্টারফেসে (0.0.0.0) পোর্ট 5000-এ চলবে, তাই
সার্ভারের IP দিয়ে যেকোনো ডিভাইস থেকে অ্যাক্সেস করা যাবে:

    http://<সার্ভারের-IP>:5000

পেজে "🌐 সার্ভার ফোল্ডার ব্রাউজ করুন" বাটনে ক্লিক করলে এই স্ক্রিপ্টের
পাশের ফোল্ডার থেকে সাব-ফোল্ডার/ফাইল ব্রাউজ করা যাবে। "🖥️ লোকাল ফোল্ডার
সিলেক্ট করুন" বাটনটা আগের মতোই কাজ করবে (ব্রাউজারের File System Access
API দিয়ে, শুধু Chrome/Edge, https:// বা localhost-এ)।

কনফিগারেশন (ঐচ্ছিক, environment variable দিয়ে):
    BROWSE_ROOT   কোন ফোল্ডারটা ব্রাউজ করা যাবে (ডিফল্ট: এই স্ক্রিপ্টের নিজের ফোল্ডার)
    HOST          ডিফল্ট 0.0.0.0
    PORT          ডিফল্ট 5000

নোট: /api/file এন্ডপয়েন্ট mimetypes.guess_type() দিয়ে যেকোনো ফাইলের
(PDF, JPG, PNG, GIF, WEBP, SVG ইত্যাদি) সঠিক mimetype বের করে পাঠায়,
তাই এই ফাইলে ইমেজ প্রিভিউর জন্য আলাদা কোনো পরিবর্তনের দরকার নেই —
ইমেজ প্রিভিউ যোগ করা হয়েছে index.html-এর ফ্রন্টএন্ড কোডে।
"""

import mimetypes
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, abort, Response

BASE_DIR = Path(os.environ.get("BROWSE_ROOT", Path(__file__).resolve().parent)).resolve()
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))

app = Flask(__name__, static_folder=None)

# Folder/file names to always hide from the folder-tree listing (dotfiles, this script, python noise, etc.)
# Note: this only hides them from /api/list — it is not a security boundary. Don't put secrets in this folder.
HIDDEN_PREFIXES = (".",)
HIDDEN_NAMES = {"__pycache__", "node_modules", Path(__file__).name}
HIDDEN_SUFFIXES = (".pyc", ".log")


def safe_resolve(rel_path: str) -> Path:
    """
    Resolve a user-supplied relative path against BASE_DIR, refusing anything
    that would escape BASE_DIR (path traversal via '..', absolute paths, etc.).
    """
    rel_path = (rel_path or "").strip().strip("/").strip("\\")
    candidate = (BASE_DIR / rel_path).resolve() if rel_path else BASE_DIR
    try:
        candidate.relative_to(BASE_DIR)
    except ValueError:
        abort(400, description="Invalid path")
    return candidate


def is_hidden(name: str) -> bool:
    return (
        name.startswith(HIDDEN_PREFIXES)
        or name in HIDDEN_NAMES
        or name.endswith(HIDDEN_SUFFIXES)
    )


@app.route("/")
def root_index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:filename>")
def static_passthrough(filename):
    """Serve any other static asset that lives next to index.html (css/js/images etc.)."""
    target = safe_resolve(filename)
    if not target.is_file():
        abort(404)
    return send_from_directory(BASE_DIR, filename)


@app.route("/api/list")
def api_list():
    rel_path = request.args.get("path", "")
    target = safe_resolve(rel_path)
    if not target.exists() or not target.is_dir():
        abort(404, description="Folder not found")

    folders, files = [], []
    try:
        with os.scandir(target) as it:
            for entry in it:
                if is_hidden(entry.name):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    folders.append(entry.name)
                elif entry.is_file(follow_symlinks=False):
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    files.append({"name": entry.name, "size": size})
    except PermissionError:
        abort(403, description="Permission denied")

    folders.sort(key=str.lower)
    files.sort(key=lambda f: f["name"].lower())
    return jsonify({"path": rel_path, "folders": folders, "files": files})


@app.route("/api/file")
def api_file():
    rel_path = request.args.get("path", "")
    if not rel_path:
        abort(400, description="Missing path")
    target = safe_resolve(rel_path)
    if not target.exists() or not target.is_file():
        abort(404, description="File not found")

    as_download = request.args.get("download") == "1"
    mimetype, _ = mimetypes.guess_type(target.name)
    mimetype = mimetype or "application/octet-stream"

    # conditional=True enables Range requests, which the browser's built-in
    # PDF viewer (and large image loading) relies on for seek/scroll performance.
    resp = send_from_directory(
        target.parent,
        target.name,
        mimetype=mimetype,
        as_attachment=as_download,
        conditional=True,
    )
    return resp


if __name__ == "__main__":
    print(f"📂 Browsing root : {BASE_DIR}")
    print(f"🌐 Serving on    : http://{HOST}:{PORT}  (and http://<এই-মেশিনের-IP>:{PORT})")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
