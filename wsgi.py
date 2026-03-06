# wsgi.py - WSGI entry point for Vercel
from app import app

# This is the WSGI callable that Vercel expects
app = app
