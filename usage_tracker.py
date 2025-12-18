import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import fcntl

# Try to import rich for better UI
try:
    from rich.console import Console
    from rich.table import Table
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False

# --- PRICING CONSTANTS (USD) ---
# Gemini Flash 2.5
PRICE_GEMINI_FLASH_INPUT_1M = 0.30
PRICE_GEMINI_FLASH_OUTPUT_1M = 2.50

# Gemini Flash Lite 2.5 (For Comparison)
PRICE_GEMINI_FLASH_LITE_INPUT_1M = 0.10
PRICE_GEMINI_FLASH_LITE_OUTPUT_1M = 0.40

# Imagen (Nano Banana)
PRICE_IMAGEN_INPUT_1M = 0.30
PRICE_IMAGEN_PER_IMAGE = 0.039

# TTS (Chirp)
PRICE_TTS_CHIRP_1M_CHARS = 30.00

LOG_FILE = "usage_log.json"
LOCK_FILE = "usage_log.lock"

import threading
import time

class UsageTracker:
    def __init__(self):
        self.session_usage = []
        self.lock = threading.Lock()
        self._load_log()

    def _load_log(self):
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, 'r') as f:
                    self.all_usage = json.load(f)
            except json.JSONDecodeError:
                self.all_usage = []
        else:
            self.all_usage = []

    def log_word_usage(self, word: str, text_input_tokens: int = 0, text_output_tokens: int = 0, 
                      image_input_tokens: int = 0, audio_characters: int = 0, images_generated: int = 0):
        """
        Log usage stats for a single word.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "word": word,
            "text_input_tokens": text_input_tokens,
            "text_output_tokens": text_output_tokens,
            "image_input_tokens": image_input_tokens,
            "audio_characters": audio_characters,
            "images_generated": images_generated
        }
        
        with self.lock:
            # We must load the latest from disk and save immediately with a lock
            # to prevent multiple processes from overwriting each other.
            max_retries = 10
            retry_delay = 0.05
            
            for attempt in range(max_retries):
                try:
                    with open(LOCK_FILE, 'w') as lf:
                        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        try:
                            # Now we have the lock, read, append, write
                            data = []
                            if os.path.exists(LOG_FILE):
                                try:
                                    with open(LOG_FILE, 'r') as f:
                                        content = f.read()
                                        if content:
                                            data = json.loads(content)
                                except (json.JSONDecodeError, FileNotFoundError):
                                    data = []
                            
                            data.append(entry)
                            
                            with open(LOG_FILE, 'w') as f:
                                json.dump(data, f, indent=2)
                            
                            self.all_usage = data # Update in-memory cache
                            # Success!
                            break
                        finally:
                            fcntl.flock(lf, fcntl.LOCK_UN)
                except (OSError, IOError):
                    # Lock busy, wait and retry
                    if attempt == max_retries - 1:
                        print(f"Failed to acquire lock after {max_retries} attempts.")
                    else:
                        time.sleep(retry_delay)
                except Exception as e:
                    print(f"Error logging usage: {e}")
                    break
            
            self.session_usage.append(entry)

    def get_summary(self):
        """Returns a summary of all-time usage for the UI."""
        with self.lock:
            self._load_log() # Get latest
            
            total_cost_flash = self.calculate_cost(self.all_usage, "flash")
            words_processed = len(set(e['word'] for e in self.all_usage))
            
            # Aggregate counts
            total_text_input = sum(e.get("text_input_tokens", 0) for e in self.all_usage)
            total_text_output = sum(e.get("text_output_tokens", 0) for e in self.all_usage)
            total_image_input = sum(e.get("image_input_tokens", 0) for e in self.all_usage)
            total_audio_chars = sum(e.get("audio_characters", 0) for e in self.all_usage)
            total_images = sum(e.get("images_generated", 0) for e in self.all_usage)

            # Component costs
            text_cost = sum(((e.get("text_input_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_INPUT_1M + 
                            (e.get("text_output_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_OUTPUT_1M) for e in self.all_usage)
            image_cost = sum(((e.get("image_input_tokens", 0) / 1_000_000) * PRICE_IMAGEN_INPUT_1M + 
                             e.get("images_generated", 0) * PRICE_IMAGEN_PER_IMAGE) for e in self.all_usage)
            audio_cost = sum((e.get("audio_characters", 0) / 1_000_000) * PRICE_TTS_CHIRP_1M_CHARS for e in self.all_usage)

            return {
                "total_cost": round(total_cost_flash, 4),
                "words_processed": words_processed,
                "avg_cost_per_word": round(total_cost_flash / words_processed, 4) if words_processed > 0 else 0,
                "components": {
                    "text": {"total": total_text_input + total_text_output, "cost": round(text_cost, 4)},
                    "image": {"total": total_images, "cost": round(image_cost, 4)},
                    "audio": {"total": total_audio_chars, "cost": round(audio_cost, 4)}
                },
                "last_update": datetime.now().isoformat()
            }

    def calculate_cost(self, entries: List[Dict], model_type="flash") -> float:
        total_cost = 0.0
        for entry in entries:
            # Text Input/Output
            if model_type == "flash":
                total_cost += (entry.get("text_input_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_INPUT_1M
                total_cost += (entry.get("text_output_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_OUTPUT_1M
            elif model_type == "flash_lite":
                total_cost += (entry.get("text_input_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_LITE_INPUT_1M
                total_cost += (entry.get("text_output_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_LITE_OUTPUT_1M
            
            # Image Cost (Image generation is a separate service, so add to both)         
            image_cost = 0
            image_cost += (entry.get("image_input_tokens", 0) / 1_000_000) * PRICE_IMAGEN_INPUT_1M
            image_cost += entry.get("images_generated", 0) * PRICE_IMAGEN_PER_IMAGE
            
            total_cost += image_cost
            
            # Audio Cost (TTS is separate service, so add to both)
            audio_cost = (entry.get("audio_characters", 0) / 1_000_000) * PRICE_TTS_CHIRP_1M_CHARS
            total_cost += audio_cost
            
        return total_cost

    def print_report(self):
        """Prints a cost report for the current session and all-time stats."""
        if not self.session_usage:
            return

        # Session Costs
        session_cost_flash = self.calculate_cost(self.session_usage, "flash")
        session_cost_lite = self.calculate_cost(self.session_usage, "flash_lite")
        
        words_processed_session = len(set(e['word'] for e in self.session_usage))
        avg_cost_session = session_cost_flash / words_processed_session if words_processed_session > 0 else 0
        avg_cost_lite = session_cost_lite / words_processed_session if words_processed_session > 0 else 0

        # All-Time Costs
        all_time_cost_flash = self.calculate_cost(self.all_usage, "flash")
        words_processed_total = len(set(e['word'] for e in self.all_usage))
        avg_cost_total = all_time_cost_flash / words_processed_total if words_processed_total > 0 else 0

        # Aggregate counts (Session)
        total_text_input = sum(e.get("text_input_tokens", 0) for e in self.session_usage)
        total_text_output = sum(e.get("text_output_tokens", 0) for e in self.session_usage)
        total_image_input = sum(e.get("image_input_tokens", 0) for e in self.session_usage)
        total_audio_chars = sum(e.get("audio_characters", 0) for e in self.session_usage)
        total_images = sum(e.get("images_generated", 0) for e in self.session_usage)

        if RICH_AVAILABLE:
            table = Table(title="Session Usage & Cost Report")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="bold")
            table.add_column("Cost (Flash 2.5)", style="green")
            table.add_column("Cost (Flash Lite)", style="yellow")

            # Calculate component costs for Flash 2.5
            text_cost_flash = 0
            text_cost_lite = 0
            image_cost = 0
            audio_cost = 0
            
            for entry in self.session_usage:
                # Text
                text_cost_flash += (entry.get("text_input_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_INPUT_1M
                text_cost_flash += (entry.get("text_output_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_OUTPUT_1M
                
                text_cost_lite += (entry.get("text_input_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_LITE_INPUT_1M
                text_cost_lite += (entry.get("text_output_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_LITE_OUTPUT_1M
                
                # Image
                image_cost += (entry.get("image_input_tokens", 0) / 1_000_000) * PRICE_IMAGEN_INPUT_1M
                image_cost += entry.get("images_generated", 0) * PRICE_IMAGEN_PER_IMAGE
                
                # Audio
                audio_cost += (entry.get("audio_characters", 0) / 1_000_000) * PRICE_TTS_CHIRP_1M_CHARS

            table.add_row("Text Tokens (In/Out)", f"{total_text_input} / {total_text_output}", f"${text_cost_flash:.6f}", f"${text_cost_lite:.6f}")
            table.add_row("Image Tokens (In)", f"{total_image_input}", f"${(total_image_input/1_000_000)*PRICE_IMAGEN_INPUT_1M:.6f}", f"${(total_image_input/1_000_000)*PRICE_IMAGEN_INPUT_1M:.6f}")
            table.add_row("Images Generated", str(total_images), f"${total_images * PRICE_IMAGEN_PER_IMAGE:.6f}", f"${total_images * PRICE_IMAGEN_PER_IMAGE:.6f}")
            table.add_row("Audio Characters", str(total_audio_chars), f"${audio_cost:.6f}", f"${audio_cost:.6f}")

            # Total
            table.add_section()
            table.add_row("Total Session Cost", "", f"${session_cost_flash:.6f}", f"${session_cost_lite:.6f}")
            table.add_row("Avg Cost per Word", f"({words_processed_session} words)", f"${avg_cost_session:.6f}", f"${avg_cost_lite:.6f}")
            
            # All Time
            table.add_section()
            table.add_row("All-Time Avg Cost", f"({words_processed_total} words)", f"${avg_cost_total:.6f}", "-")

            console.print("\n")
            console.print(table)
        else:
            print("\n--- Session Usage & Cost Report ---")
            print(f"Total Cost (Flash 2.5): ${session_cost_flash:.6f}")
            print(f"Total Cost (Flash Lite): ${session_cost_lite:.6f}")
            print(f"Avg Cost/Word: ${avg_cost_session:.6f} ({words_processed_session} words)")
            print(f"All-Time Avg Cost: ${avg_cost_total:.6f} ({words_processed_total} words)")
    def print_full_report(self):
        """Prints a comprehensive report of all-time usage."""
        if not self.all_usage:
            print("No usage history found.")
            return

        # Calculate Costs
        total_cost_flash = self.calculate_cost(self.all_usage, "flash")
        total_cost_lite = self.calculate_cost(self.all_usage, "flash_lite")
        
        words_processed = len(set(e['word'] for e in self.all_usage))
        avg_cost = total_cost_flash / words_processed if words_processed > 0 else 0
        avg_cost_lite = total_cost_lite / words_processed if words_processed > 0 else 0

        # Aggregate counts
        total_text_input = sum(e.get("text_input_tokens", 0) for e in self.all_usage)
        total_text_output = sum(e.get("text_output_tokens", 0) for e in self.all_usage)
        total_image_input = sum(e.get("image_input_tokens", 0) for e in self.all_usage)
        total_audio_chars = sum(e.get("audio_characters", 0) for e in self.all_usage)
        total_images = sum(e.get("images_generated", 0) for e in self.all_usage)

        if RICH_AVAILABLE:
            table = Table(title="Comprehensive Usage & Cost Report (All-Time)")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="bold")
            table.add_column("Cost (Flash 2.5)", style="green")
            table.add_column("Cost (Flash Lite)", style="yellow")

            # Calculate component costs
            text_cost_flash = 0
            text_cost_lite = 0
            image_cost = 0
            audio_cost = 0
            
            for entry in self.all_usage:
                # Text
                text_cost_flash += (entry.get("text_input_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_INPUT_1M
                text_cost_flash += (entry.get("text_output_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_OUTPUT_1M
                
                text_cost_lite += (entry.get("text_input_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_LITE_INPUT_1M
                text_cost_lite += (entry.get("text_output_tokens", 0) / 1_000_000) * PRICE_GEMINI_FLASH_LITE_OUTPUT_1M
                
                # Image
                image_cost += (entry.get("image_input_tokens", 0) / 1_000_000) * PRICE_IMAGEN_INPUT_1M
                image_cost += entry.get("images_generated", 0) * PRICE_IMAGEN_PER_IMAGE
                
                # Audio
                audio_cost += (entry.get("audio_characters", 0) / 1_000_000) * PRICE_TTS_CHIRP_1M_CHARS

            table.add_row("Text Tokens (In/Out)", f"{total_text_input} / {total_text_output}", f"${text_cost_flash:.6f}", f"${text_cost_lite:.6f}")
            table.add_row("Image Tokens (In)", f"{total_image_input}", f"${(total_image_input/1_000_000)*PRICE_IMAGEN_INPUT_1M:.6f}", f"${(total_image_input/1_000_000)*PRICE_IMAGEN_INPUT_1M:.6f}")
            table.add_row("Images Generated", str(total_images), f"${total_images * PRICE_IMAGEN_PER_IMAGE:.6f}", f"${total_images * PRICE_IMAGEN_PER_IMAGE:.6f}")
            table.add_row("Audio Characters", str(total_audio_chars), f"${audio_cost:.6f}", f"${audio_cost:.6f}")

            # Total
            table.add_section()
            table.add_row("Total Cost", "", f"${total_cost_flash:.6f}", f"${total_cost_lite:.6f}")
            table.add_row("Avg Cost per Word", f"({words_processed} words)", f"${avg_cost:.6f}", f"${avg_cost_lite:.6f}")
            
            console.print("\n")
            console.print(table)
        else:
            print("\n--- Comprehensive Usage & Cost Report (All-Time) ---")
            print(f"Total Cost (Flash 2.5): ${total_cost_flash:.6f}")
            print(f"Total Cost (Flash Lite): ${total_cost_lite:.6f}")
            print(f"Avg Cost/Word: ${avg_cost:.6f} ({words_processed} words)")
            print(f"Text Tokens: {total_text_input} In / {total_text_output} Out")
            print(f"Image Tokens: {total_image_input}")
            print(f"Images: {total_images}")
            print(f"Audio Chars: {total_audio_chars}")

if __name__ == "__main__":
    tracker = UsageTracker()
    tracker.print_full_report()
