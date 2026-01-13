import json
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response

import urllib.request
import urllib.error
import concurrent.futures
from typing import List
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import queue
import threading
import re
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import time
from collections import defaultdict

import os
from dotenv import load_dotenv

# Import the creator scripts
import chinese_anki_creator
from usage_tracker import UsageTracker

# Load environment variables
load_dotenv()

# Initialize global usage tracker
tracker = UsageTracker()

# --- Configuration ---
ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_KEY = os.getenv("API_KEY") # Optional: Set in .env to enable authentication

# --- Constants ---
MAX_WORDS_PER_REQUEST = 50
MAX_WORD_LENGTH = 100

# --- Security Global State ---
# Very simple in-memory rate limiting: {ip: [timestamps]}
rate_limit_store = defaultdict(list)
RATE_LIMIT_WINDOW = 60 # 1 minute
RATE_LIMIT_MAX_REQUESTS = 30 # Limit to 30 requests per minute per IP

# --- Security Middlewares ---

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Adjusted CSP to allow Google Fonts and the Hanzi Writer from CDN
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self';"
        )
        return response

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/static") or request.url.path == "/favicon.ico":
             return await call_next(request)
             
        # Use X-Forwarded-For if behind a proxy, else fallback to direct client IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
            
        now = time.time()
        
        # Clean old entries
        rate_limit_store[client_ip] = [t for t in rate_limit_store[client_ip] if now - t < RATE_LIMIT_WINDOW]
        
        if len(rate_limit_store[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
            return Response(content="Too Many Requests", status_code=429)
            
        rate_limit_store[client_ip].append(now)
        return await call_next(request)

class BotBlockerMiddleware(BaseHTTPMiddleware):
    BLOCKED_PATHS = {".env", ".git", ".php", "wp-admin", "boaform", "powershell", "config"}
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path.lower()
        if any(bp in path for bp in self.BLOCKED_PATHS):
             return Response(content="Not Found", status_code=404)
        return await call_next(request)

app = FastAPI(title="Anki Card Creator API")

# Add Middlewares in order
app.add_middleware(BotBlockerMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Helpers ---
class ProgressProxy:
    def __init__(self, q, word):
        self.q = q
        self.word = word

    def update(self, task_id, description, **kwargs):
        # Extract plain text from rich tags
        clean_desc = re.sub(r'\[.*?\]', '', description)
        self.q.put({"word": self.word, "type": "progress", "message": clean_desc})

    def advance(self, task_id, amount):
        pass

def invoke(action, **params):
    requestJson = json.dumps({'action': action, 'params': params, 'version': 6}).encode('utf-8')
    try:
        response = json.load(urllib.request.urlopen(urllib.request.Request(ANKI_CONNECT_URL, requestJson)))
    except urllib.error.URLError as e:
        raise Exception(f"Failed to connect to Anki: {e}. Is Anki running?")

    if len(response) != 2:
        raise Exception('response has an unexpected number of fields')
    if 'error' not in response:
        raise Exception('response is missing required error field')
    if 'result' not in response:
        raise Exception('response is missing required result field')
    if response['error'] is not None:
        raise Exception(response['error'])
    return response['result']

def sync_anki():
    try:
        invoke('sync')
        return True
    except Exception as e:
        print(f"Sync failed: {e}")
        return False

def process_words_parallel(words: List[str], processor_func):
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # We pass None for progress and task_id as we are not using Rich here, but we pass the tracker
        future_to_word = {executor.submit(processor_func, word, None, None, tracker): word for word in words}
        for future in concurrent.futures.as_completed(future_to_word):
            word = future_to_word[future]
            try:
                status = future.result()
                # We return the full status dictionary so the frontend can see sub-step details
                # But we ensure it has word, success and message for backward compatibility or ease of use
                status["success"] = status.get("final") == "Success"
                status["message"] = status.get("final", "Unknown Error")
                results.append(status)
            except Exception as e:
                results.append({"word": word, "success": False, "message": str(e), "final": f"Error: {e}"})
    return results

# --- Models ---
class WordList(BaseModel):
    words: List[str]

def check_auth(request: Request):
    if API_KEY:
        auth_header = request.headers.get("X-API-Key")
        if auth_header != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API Key")

def validate_word_list(words: List[str]):
    if not words:
        raise HTTPException(status_code=400, detail="Word list cannot be empty")
    if len(words) > MAX_WORDS_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"Too many words. Maximum is {MAX_WORDS_PER_REQUEST}")
    for word in words:
        if len(word) > MAX_WORD_LENGTH:
            raise HTTPException(status_code=400, detail=f"Word too long: {word[:20]}...")

# --- Endpoints ---
@app.post("/chinese/stream")
async def stream_chinese_cards(word_list: WordList, request: Request):
    check_auth(request)
    validate_word_list(word_list.words)
    def event_generator():
        q = queue.Queue()
        
        def run_worker():
            try:
                chinese_anki_creator.create_deck()
                chinese_anki_creator.create_model()
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(chinese_anki_creator.process_word, word, ProgressProxy(q, word), None, tracker): word for word in word_list.words}
                    
                    for future in concurrent.futures.as_completed(futures):
                        word = futures[future]
                        try:
                            status = future.result()
                            status["success"] = status.get("final") == "Success"
                            status["message"] = status.get("final", "Success")
                            status["type"] = "done"
                            status["word"] = word
                            q.put(status)
                        except Exception as e:
                            q.put({"word": word, "type": "done", "success": False, "message": str(e)})
                
                # Sync at the end
                sync_success = sync_anki()
                q.put({"type": "sync", "success": sync_success})
                
            except Exception as e:
                q.put({"type": "error", "message": f"Global error: {e}"})
            finally:
                q.put(None) # Sentinel

        thread = threading.Thread(target=run_worker)
        thread.start()

        while True:
            try:
                item = q.get(timeout=30) # 30s timeout just in case
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/chinese")
def create_chinese_cards(word_list: WordList, request: Request):
    check_auth(request)
    validate_word_list(word_list.words)
    """
    Generate Chinese Anki cards for the provided list of words.
    """
    if not word_list.words:
        raise HTTPException(status_code=400, detail="Word list cannot be empty")

    # Ensure deck/model exist (using the script's functions)
    try:
        chinese_anki_creator.create_deck()
        chinese_anki_creator.create_model()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize Anki environment: {e}")

    # Process words
    results = process_words_parallel(word_list.words, chinese_anki_creator.process_word)
    
    # Sync Anki
    sync_success = sync_anki()

    return {
        "results": results,
        "anki_sync": "success" if sync_success else "failed"
    }

@app.get("/usage")
def get_usage(request: Request):
    check_auth(request)
    """
    Get the comprehensive usage summary.
    """
    try:
        return tracker.get_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

# Mount static files for PWA (Must be last to avoid shadowing API routes)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    # When using a reverse proxy like Caddy, the app should bind to 127.0.0.1
    # so that it is not accessible directly from the outside.
    uvicorn.run(
        "api:app", 
        host=API_HOST, 
        port=API_PORT, 
        reload=False,   # Disable reload in production for stability
        proxy_headers=True, 
        forwarded_allow_ips="*" # Trust the reverse proxy headers
    )

