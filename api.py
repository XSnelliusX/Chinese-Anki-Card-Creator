import json
import uvicorn

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

import os
from dotenv import load_dotenv

# Import the creator scripts
import chinese_anki_creator

# Load environment variables
load_dotenv()

app = FastAPI(title="Anki Card Creator API")

# --- Configuration ---
ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

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
        # We pass None for progress and task_id as we are not using Rich here
        future_to_word = {executor.submit(processor_func, word, None, None): word for word in words}
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

# --- Endpoints ---
@app.post("/chinese/stream")
async def stream_chinese_cards(word_list: WordList):
    def event_generator():
        q = queue.Queue()
        
        def run_worker():
            try:
                chinese_anki_creator.create_deck()
                chinese_anki_creator.create_model()
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(chinese_anki_creator.process_word, word, ProgressProxy(q, word), None): word for word in word_list.words}
                    
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
def create_chinese_cards(word_list: WordList):
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

# Mount static files for PWA (Must be last to avoid shadowing API routes)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("api:app", host=API_HOST, port=API_PORT, reload=True)

