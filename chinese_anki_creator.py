import os
import json
import base64
import urllib.request
import urllib.error
import argparse
import sys
import concurrent.futures
from google import genai
from google.genai import types
from google.cloud import texttospeech
from dotenv import load_dotenv
from usage_tracker import UsageTracker

# Load environment variables
load_dotenv()

# Try to import rich for better UI
try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
    from rich.table import Table
    from rich import print as rprint
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    print("Tip: Install 'rich' for a better experience: pip install rich")

# --- CONFIGURATION ---
PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
LOCATION = os.getenv("GOOGLE_LOCATION")

# Models
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-2.5-flash-preview-09-2025")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-2.5-flash-image")
AUDIO_MODEL = os.getenv("CHINESE_AUDIO_MODEL", "cmn-CN-Chirp3-HD-Achernar")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

# Anki Configuration
ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
DECK_NAME = os.getenv("CHINESE_DECK_NAME", "Chinese")
MODEL_NAME = os.getenv("CHINESE_MODEL_NAME", "Chinese Model")

# Initialize Google Client
try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
except Exception as e:
    print(f"Error initializing Google Client: {e}")
    sys.exit(1)

# --- ANKI CONNECT HELPERS ---

def request(action, **params):
    return {'action': action, 'params': params, 'version': 6}

def invoke(action, **params):
    requestJson = json.dumps(request(action, **params)).encode('utf-8')
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

def create_deck():
    if RICH_AVAILABLE:
        console.print(f"[dim]Checking deck '{DECK_NAME}'...[/dim]")
    else:
        print(f"Checking deck '{DECK_NAME}'...")
        
    decks = invoke('deckNames')
    if DECK_NAME not in decks:
        print(f"Creating deck '{DECK_NAME}'...")
        invoke('createDeck', deck=DECK_NAME)

def create_model():
    if RICH_AVAILABLE:
        console.print(f"[dim]Checking model '{MODEL_NAME}'...[/dim]")
    else:
        print(f"Checking model '{MODEL_NAME}'...")
        
    models = invoke('modelNames')
    
    css = """/* --- Global Container --- */
.card {
    font-family: "Segoe UI", "Microsoft YaHei", "SimHei", sans-serif;
    background-color: #fdfdfd;
    color: #333;
    font-size: 18px;
    text-align: center;
    line-height: 1.5;
    max-width: 600px;
    margin: 0 auto;
    padding: 20px;
}

/* --- Image Styling --- */
.image-container img {
    max-width: 100%;
    max-height: 250px;
    border-radius: 8px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    margin-bottom: 20px;
}

/* --- Sentence Display --- */
.sentence-hanzi {
    font-size: 32px;
    margin: 15px 0;
    font-family: "KaiTi", "SimSun", serif;
}

.cloze-blank {
    color: #3399ff;
    border-bottom: 2px solid #3399ff;
    padding: 0 10px;
    font-weight: bold;
}

/* --- Pinyin Styling --- */
.sentence-pinyin {
    font-family: "Arial", sans-serif;
    font-size: 20px;
    margin-bottom: 10px;
}
.tone1 { color: #FF6666; } /* Flat */
.tone2 { color: #FFCC66; } /* Rising */
.tone3 { color: #99CC66; } /* Dip */
.tone4 { color: #6699FF; } /* Falling */
.tone5 { color: #AAAAAA; } /* Neutral */

/* --- English Meaning --- */
.sentence-meaning {
    font-style: italic;
    color: #555;
    margin-bottom: 20px;
    border-top: 1px solid #eee;
    padding-top: 10px;
}

.target-meaning {
    font-weight: bold;
    color: #444;
    margin-bottom: 10px;
    font-size: 20px;
}

/* --- Word-for-Word Analysis --- */
.analysis-box {
    text-align: left;
    background: #f4f4f4;
    padding: 10px;
    border-radius: 5px;
    font-size: 16px;
    margin-top: 15px;
}

/* --- Writing Container --- */
.writing-container {
    display: flex;
    justify-content: center;
    margin-top: 20px;
}

/* --- Night Mode --- */
.card.nightMode { background-color: #2f2f31; color: #f0f0f0; }
.card.nightMode .sentence-meaning { color: #aaa; border-top-color: #444; }
.card.nightMode .target-meaning { color: #ddd; }
.card.nightMode .analysis-box { background: #3a3a3a; }
.card.nightMode .tone1 { color: #ff8080; }
.card.nightMode .tone2 { color: #ffd966; }
.card.nightMode .tone3 { color: #b3e699; }
.card.nightMode .tone4 { color: #8cb3ff; }
.card.nightMode .tone5 { color: #bbb; }

/* --- Target Spotlight Section --- */
.target-spotlight {
    background-color: #f0f7ff; /* Very light blue background */
    border: 1px solid #cce5ff;
    border-radius: 12px;
    padding: 20px;
    margin: 25px 0; /* Space it out from sentence and analysis */
    position: relative;
}

.target-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #88a;
    font-weight: bold;
    margin-bottom: 5px;
}

.target-word {
    font-family: "KaiTi", "SimSun", serif;
    font-size: 42px; /* Large and clear */
    color: #222;
    margin: 5px 0;
}

.target-def {
    font-size: 18px;
    color: #444;
    font-weight: 600;
    margin-bottom: 15px;
}

/* Update Writing Container to fit inside Spotlight */
.writing-container {
    display: flex;
    justify-content: center;
    margin-top: 10px;
    /* Remove top margin if it feels too spaced out */
}

/* --- NIGHT MODE UPDATES --- */
.card.nightMode .target-spotlight {
    background-color: #383e4a; /* Darker blue-grey */
    border-color: #4a5568;
}

.card.nightMode .target-label {
    color: #aab;
}

.card.nightMode .target-word {
    color: #fff;
}

.card.nightMode .target-def {
    color: #ddd;
}
    """

    # Templates
    front_cloze = """<div class="image-container">{{Image}}</div>

<div class="sentence-meaning">{{SentenceMeaning}}</div>

<script>
    // Logic: Find TargetWord in Sentence and replace with underscores
    var fullSentence = "{{SentenceHanzi}}";
    var target = "{{TargetWord}}";
    
    if(target && fullSentence.includes(target)) {
        var clozeStr = fullSentence.replace(target, "<span class='cloze-blank'>[ ___ ]</span>");
        document.getElementById('cloze-sentence').innerHTML = clozeStr;
    } else {
        document.getElementById('cloze-sentence').innerHTML = fullSentence;
    }
</script>
    """

    front_audio = """<div class="image-container">{{Image}}</div>

<div style="margin: 20px;">{{Audio}}</div>

<div style="font-size: 12px; color: #999; margin-top:50px;">
    (Listen and visualize the meaning)
</div>
    """

    front_recall = """<div class="image-container">{{Image}}</div>

<div class="sentence-hanzi">{{SentenceHanzi}}</div>
    """

    back_template = """<div class="image-container">{{Image}}</div>

<div class="sentence-hanzi">{{SentenceHanziColored}}</div>
<div class="sentence-pinyin">{{SentencePinyinColored}}</div>
<div style="margin: 10px 0;">{{Audio}}</div>
<div class="sentence-meaning">{{SentenceMeaning}}</div>

<div class="target-spotlight">
    <div class="target-label">FOCUS WORD</div>
    
    <div class="target-word">{{TargetWord}}</div>
    <div class="target-def">{{TargetWordMeaning}}</div>

    <div id="target-writing" class="writing-container"></div>
</div>

<div class="analysis-box">
    <b>Sentence Breakdown:</b><br>
    {{TargetAnalysis}}
</div>

<script>
// --- Script Helper: Load External Scripts ---
var injectScript = (src) => {
    return new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
        const script = document.createElement('script');
        script.src = src; script.async = true; script.onload = resolve; script.onerror = reject;
        document.head.appendChild(script);
    });
};

(async () => {
    // Hanzi Writer (Target Word Only)
    const targetWord = "{{TargetWord}}";
    if (targetWord && targetWord.trim() !== "") {
        await injectScript("https://cdn.jsdelivr.net/npm/hanzi-writer@3.6/dist/hanzi-writer.min.js");
        
        const writerDiv = document.getElementById('target-writing');
        writerDiv.innerHTML = ""; // clear loading
        const chars = targetWord.split('');
        
        chars.forEach((char, idx) => {
            let d = document.createElement('div');
            let id = 'hw-' + idx;
            d.id = id;
            d.style.margin = "5px";
            writerDiv.appendChild(d);
            
            try {
                HanziWriter.create(id, char, {
                    width: 100, height: 100, padding: 5,
                    showOutline: true,
                    strokeColor: '#555', // Slightly lighter stroke for better contrast
                    highlightColor: '#3399ff', // Blue highlight
                    drawingWidth: 20
                }).animateCharacter();
            } catch(e) { console.log(e); }
        });
    }
})();
</script>
    """

    # Fields list including the new TargetWordMeaning
    fields = ["TargetWord", "TargetWordMeaning", "SentenceHanzi", "SentencePinyin", "SentenceMeaning", "TargetAnalysis", "Image", "Audio", "SentenceHanziColored", "SentencePinyinColored"]

    if MODEL_NAME not in models:
        invoke('createModel', 
               modelName=MODEL_NAME,
               inOrderFields=fields,
               css=css,
               cardTemplates=[
                   {
                       "Name": "Cloze Card",
                       "Front": front_cloze,
                       "Back": back_template
                   },
                   {
                       "Name": "Audio Card",
                       "Front": front_audio,
                       "Back": back_template
                   },
                   {
                       "Name": "Recall Card",
                       "Front": front_recall,
                       "Back": back_template
                   }
               ]
        )
    else:
        # Check if fields exist and add if missing
        existing_fields = invoke('modelFieldNames', modelName=MODEL_NAME)
        for field in fields:
            if field not in existing_fields:
                if RICH_AVAILABLE:
                    console.print(f"[yellow]Adding missing field '{field}' to model '{MODEL_NAME}'...[/yellow]")
                else:
                    print(f"Adding missing field '{field}' to model '{MODEL_NAME}'...")
                invoke('modelAddField', model={
                    "name": MODEL_NAME,
                    "field": field,
                    "index": len(existing_fields)
                })
                existing_fields.append(field)

        invoke('updateModelStyling', model={
            "name": MODEL_NAME,
            "css": css
        })
        invoke('updateModelTemplates', model={
            "name": MODEL_NAME,
            "templates": {
                "Cloze Card": {
                    "Front": front_cloze,
                    "Back": back_template
                },
                "Audio Card": {
                    "Front": front_audio,
                    "Back": back_template
                },
                "Recall Card": {
                    "Front": front_recall,
                    "Back": back_template
                }
            }
        })

# --- GENERATION FUNCTIONS ---

def generate_card_data(target_word):
    """
    1. TEXT GENERATION
    Generates the sentence, pinyin, meaning, and word-by-word analysis.
    """
    
    # Sanitize target_word for the prompt by escaping quotes
    safe_target_word = target_word.replace('"', '\\"')
    
    prompt = f"""
    Create a Traditional Chinese learning card for the target word: "{safe_target_word}".
    
    Return ONLY a raw JSON object (no markdown formatting) with this exact structure:
    {{
        "TargetWord": "{safe_target_word}",
        "TargetWordMeaning": "The English translation of the target word.",
        "SentenceHanzi": "A simple, natural sentence using the word.",
        "SentencePinyin": "The pinyin for the sentence with tone marks.",
        "SentenceMeaning": "The English translation of the sentence.",
        "TargetAnalysis": "A list of all words in the sentence with their pinyin and meaning. Format: 'Word (pinyin) - Meaning<br>Word (pinyin) - Meaning'",
        "SentenceWords": [
            {{
                "word": "我",
                "syllables": [{{"pinyin": "wǒ", "tone": 3}}]
            }},
            {{
                "word": "超市",
                "syllables": [{{"pinyin": "chāo", "tone": 1}}, {{"pinyin": "shì", "tone": 4}}]
            }}
        ]
    }}
    """

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part(text=prompt)
            ]
        )
    ]
    
    tools = [
        types.Tool(google_search=types.GoogleSearch()),
    ]

    generate_content_config = types.GenerateContentConfig(
        temperature = 1,
        top_p = 0.95,
        max_output_tokens = 65535,
        safety_settings = [
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
        ],
        tools = tools,
        thinking_config=types.ThinkingConfig(
            thinking_budget=1024, 
        ),
    )

    full_response = ""
    usage_metadata = None
    
    # Use non-streaming for easier usage metadata access
    try:
        response = client.models.generate_content(
            model=TEXT_MODEL,
            contents=contents,
            config=generate_content_config,
        )
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.text:
                    full_response += part.text
            
            if response.usage_metadata:
                usage_metadata = response.usage_metadata
    except Exception as e:
        print(f"Error generating text: {e}")
        return None, None

    # Attempt to parse JSON from the response
    try:
        start_idx = full_response.find('{')
        end_idx = full_response.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            json_str = full_response[start_idx:end_idx+1]
            data = json.loads(json_str)
            
            # Generate Colored HTML
            if "SentenceWords" in data:
                hanzi_colored = ""
                pinyin_colored = ""
                
                for word_item in data["SentenceWords"]:
                    word = word_item.get("word", "")
                    syllables = word_item.get("syllables", [])
                    
                    # 1. Pinyin
                    word_pinyin = ""
                    for syl in syllables:
                        p = syl.get("pinyin", "")
                        t = syl.get("tone", 5)
                        word_pinyin += f'<span class="tone{t}">{p}</span>'
                    pinyin_colored += word_pinyin + " "
                    
                    # 2. Hanzi
                    if len(word) == len(syllables):
                        for i, char in enumerate(word):
                            t = syllables[i].get("tone", 5)
                            hanzi_colored += f'<span class="tone{t}">{char}</span>'
                    else:
                        hanzi_colored += word 
                
                data["SentenceHanziColored"] = hanzi_colored
                data["SentencePinyinColored"] = pinyin_colored.strip()
            
            return data, usage_metadata
        else:
            return None, usage_metadata
    except json.JSONDecodeError:
        return None, usage_metadata

def generate_image_b64(card_data):
    """
    2. IMAGE GENERATION
    Generates a visual anchor for the sentence. Returns base64 string and usage metadata.
    """
    if not card_data:
        return None, None
        
    prompt = (
        f"A vibrant, premium 3D stylized animation style illustration representing the scene: '{card_data['SentenceMeaning']}'. "
        f"The primary goal is to clearly and unmistakably teach the concept of '{card_data['TargetWordMeaning']}'. "
        f"Style: Clean, smooth 3D render (Pixar-like) with soft rounded shapes, expressive characters, and a cheerful atmosphere. "
        f"Composition: High-contrast, iconic representation with a simple, uncluttered background to ensure the subject is the absolute focus. "
        f"Lighting: Cinematic, warm, and bright studio lighting that highlights textures and depth. "
        f"Constraint: ABSOLUTELY NO text, letters, symbols, or numbers in the image. "
        f"The image should feel like a high-quality asset from a modern educational game."
    )
    
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part(text=prompt)
            ]
        )
    ]

    generate_content_config = types.GenerateContentConfig(
        temperature = 1,
        top_p = 0.95,
        max_output_tokens = 32768,
        response_modalities = ["IMAGE"],
        safety_settings = [
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
        ],
        image_config=types.ImageConfig(
            aspect_ratio="16:9",
            image_size="1K",
            output_mime_type="image/png",
        ),
    )

    try:
        # Use non-streaming to get usage metadata easily
        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=contents,
            config=generate_content_config,
        )
        
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    return base64.b64encode(image_bytes).decode('utf-8'), response.usage_metadata
        return None, None
    except Exception as e:
        print(f"Image generation error: {e}")
        return None, None

def generate_audio_b64(card_data):
    """
    3. AUDIO GENERATION (TTS)
    Generates the spoken audio for the sentence. Returns base64 string and char count.
    """
    if not card_data:
        return None, 0
        
    try:
        # Initialize Client
        tts_client = texttospeech.TextToSpeechClient()

        text_input = card_data['SentenceHanzi']
        # Input
        synthesis_input = texttospeech.SynthesisInput(
            text=text_input
        )

        # Voice
        voice = texttospeech.VoiceSelectionParams(
            language_code="cmn-CN",
            name="cmn-CN-Chirp3-HD-Achernar"
        )

        # Audio Config
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        # Request
        response = tts_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        return base64.b64encode(response.audio_content).decode('utf-8'), len(text_input)
            
    except Exception:
        return None, 0

# --- MAIN EXECUTION ---

def check_word_exists(word):
    """Check if the word already exists in the deck."""
    # Escape double quotes for Anki query
    safe_word = word.replace('"', '\\"')
    query = f'deck:"{DECK_NAME}" "TargetWord:{safe_word}"'
    notes = invoke('findNotes', query=query)
    return len(notes) > 0

def process_word(word, progress=None, task_id=None, tracker=None):
    """
    Process a single word: Text -> Image -> Audio -> Anki
    Returns a status dictionary.
    """
    # Usage Stats Accumulators
    text_input = 0
    text_output = 0
    image_input = 0
    images_gen = 0
    audio_chars = 0
    
    status = {
        "word": word,
        "text": "Skipped",
        "image": "Skipped",
        "audio": "Skipped",
        "final": "Failed"
    }

    try:
        # 0. Check for existence
        if check_word_exists(word):
            status["final"] = "Skipped (Exists)"
            if progress: progress.update(task_id, description=f"[yellow]Skipped '{word}' (Already exists)", completed=4)
            return status

        # 1. Text
        if progress: progress.update(task_id, description=f"[cyan]Generating text for '{word}'...")
        
        data = None
        usage = None
        text_attempts = 0
        for attempt in range(MAX_RETRIES):
            text_attempts += 1
            data, usage = generate_card_data(word)
            if data:
                break
            if progress: progress.update(task_id, description=f"[yellow]Retry {text_attempts}/{MAX_RETRIES} text for '{word}'...")
        
        if not data:
            status["text"] = f"Failed ({text_attempts})"
            return status
        
        status["text"] = f"Success ({text_attempts})"
        
        if usage:
            text_input += usage.prompt_token_count
            text_output += usage.candidates_token_count
            
        if progress: progress.advance(task_id, 1)

        # 2. Image
        if progress: progress.update(task_id, description=f"[cyan]Generating image for '{word}'...")
        
        image_b64 = None
        image_usage = None
        image_attempts = 0
        for attempt in range(MAX_RETRIES):
            image_attempts += 1
            image_b64, image_usage = generate_image_b64(data)
            if image_b64:
                break
            if progress: progress.update(task_id, description=f"[yellow]Retry {image_attempts}/{MAX_RETRIES} image for '{word}'...")
            
        if image_b64:
            status["image"] = f"Success ({image_attempts})"
            images_gen = 1
            if image_usage:
                image_input += image_usage.prompt_token_count
        else:
            status["image"] = f"Failed ({image_attempts})"
            if RICH_AVAILABLE:
                console.print(f"[yellow]Warning: Image generation failed for '{word}' after {MAX_RETRIES} attempts.[/yellow]")
            else:
                print(f"Warning: Image generation failed for '{word}' after {MAX_RETRIES} attempts.")
            
        if progress: progress.advance(task_id, 1)
        
        # 3. Audio
        if progress: progress.update(task_id, description=f"[cyan]Generating audio for '{word}'...")
        
        audio_b64 = None
        char_count = 0
        audio_attempts = 0
        for attempt in range(MAX_RETRIES):
            audio_attempts += 1
            audio_b64, char_count = generate_audio_b64(data)
            if audio_b64:
                break
            if progress: progress.update(task_id, description=f"[yellow]Retry {audio_attempts}/{MAX_RETRIES} audio for '{word}'...")
        
        if audio_b64:
            status["audio"] = f"Success ({audio_attempts})"
            audio_chars = char_count
        else:
            status["audio"] = f"Failed ({audio_attempts})"
            if RICH_AVAILABLE:
                console.print(f"[yellow]Warning: Audio generation failed for '{word}' after {MAX_RETRIES} attempts.[/yellow]")
            else:
                print(f"Warning: Audio generation failed for '{word}' after {MAX_RETRIES} attempts.")
            
        if progress: progress.advance(task_id, 1)
        
        # 4. Import to Anki
        if progress: progress.update(task_id, description=f"[cyan]Importing '{word}' to Anki...")
        
        note_payload = {
            "deckName": DECK_NAME,
            "modelName": MODEL_NAME,
            "fields": {
                "TargetWord": data['TargetWord'],
                "TargetWordMeaning": data.get('TargetWordMeaning', ''),
                "SentenceHanzi": data.get('SentenceHanzi', ''),
                "SentencePinyin": data.get('SentencePinyin', ''),
                "SentenceMeaning": data.get('SentenceMeaning', ''),
                "TargetAnalysis": data.get('TargetAnalysis', ''),
                "SentenceHanziColored": data.get('SentenceHanziColored', data.get('SentenceHanzi', '')),
                "SentencePinyinColored": data.get('SentencePinyinColored', data.get('SentencePinyin', '')),
                "Image": "", 
                "Audio": ""
            },
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck"
            },
            "tags": ["AI_Generated"],
            "audio": [],
            "picture": []
        }

        if audio_b64:
            note_payload["audio"].append({
                "data": audio_b64,
                "filename": f"ai_audio_{word}.mp3",
                "fields": ["Audio"]
            })
        
        if image_b64:
            note_payload["picture"].append({
                "data": image_b64,
                "filename": f"ai_image_{word}.png",
                "fields": ["Image"]
            })

        invoke('addNote', note=note_payload)
        
        status["final"] = "Success"
        
        # Log Usage if successful (or partial success)
        if tracker:
            tracker.log_word_usage(
                word=word,
                text_input_tokens=text_input,
                text_output_tokens=text_output,
                image_input_tokens=image_input,
                audio_characters=audio_chars,
                images_generated=images_gen
            )

        if progress: progress.advance(task_id, 1)
        return status

    except Exception as e:
        # Log partial usage if failed? 
        if tracker and (text_input > 0 or image_input > 0):
             tracker.log_word_usage(
                word=word,
                text_input_tokens=text_input,
                text_output_tokens=text_output,
                image_input_tokens=image_input,
                audio_characters=audio_chars,
                images_generated=images_gen
            )

        if "duplicate" in str(e):
            status["final"] = "Duplicate"
            return status
            
        status["final"] = f"Error: {str(e)}"
        return status

def main():
    parser = argparse.ArgumentParser(description="Generate Anki cards for Chinese learning.")
    parser.add_argument("words", nargs="*", help="List of words to generate cards for")
    args = parser.parse_args()

    words_to_learn = args.words

    # Interactive mode if no args
    if not words_to_learn:
        if RICH_AVAILABLE:
            console.print("[bold green]Welcome to Anki Card Creator![/bold green]")
            words_input = console.input("[bold yellow]Enter words to learn (comma separated): [/bold yellow]")
        else:
            print("Welcome to Anki Card Creator!")
            words_input = input("Enter words to learn (comma separated): ")
        
        if words_input.strip():
            words_to_learn = [w.strip() for w in words_input.split(",") if w.strip()]
        else:
            print("No words entered. Exiting.")
            return

    try:
        # Check connection
        invoke('version')
        if RICH_AVAILABLE:
            console.print("[green]Connected to AnkiConnect.[/green]")
        else:
            print("Connected to AnkiConnect.")
        
        # Ensure Deck and Model exist
        create_deck()
        create_model()
        
        tracker = UsageTracker()
        results = []

        if RICH_AVAILABLE:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None, style="black", complete_style="green", finished_style="green"),
                TimeRemainingColumn(),
                transient=False,
            ) as progress:
                
                # Create a task for each word
                futures = {}
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    for word in words_to_learn:
                        # Total=4 steps: Text, Image, Audio, Import
                        task_id = progress.add_task(f"[cyan]Waiting '{word}'...", total=4)
                        future = executor.submit(process_word, word, progress, task_id, tracker)
                        futures[future] = (word, task_id)
                    
                    for future in concurrent.futures.as_completed(futures):
                        word, task_id = futures[future]
                        try:
                            status = future.result()
                            results.append(status)
                            
                            final_msg = status['final']
                            if "Success" in final_msg or "Duplicate" in final_msg:
                                progress.update(task_id, description=f"[green]Done: {word} ({final_msg})", completed=4)
                            else:
                                progress.update(task_id, description=f"[red]Failed: {word} ({final_msg})", completed=4)
                        except Exception as e:
                            results.append({
                                "word": word,
                                "text": "Error",
                                "image": "Error",
                                "audio": "Error",
                                "final": str(e)
                            })
                            progress.update(task_id, description=f"[red]Error: {word} ({e})", completed=4)
            
            # Summary Table
            table = Table(title="Generation Summary")
            table.add_column("Word", style="cyan")
            table.add_column("Text Status", style="blue")
            table.add_column("Image Status", style="magenta")
            table.add_column("Audio Status", style="yellow")
            table.add_column("Final Status", style="bold")

            for res in results:
                final_style = "green" if "Success" in res['final'] else "red"
                if "Duplicate" in res['final']: final_style = "yellow"
                
                table.add_row(
                    res['word'], 
                    res['text'], 
                    res['image'], 
                    res['audio'], 
                    f"[{final_style}]{res['final']}[/{final_style}]"
                )
            
            console.print("\n")
            console.print(table)
            
            # Print Usage Report
            tracker.print_report()

        else:
            # Fallback for no Rich (Sequential)
            print("Running in sequential mode (install 'rich' for parallel processing UI)...")
            for word in words_to_learn:
                print(f"\n--- Processing {word} ---")
                status = process_word(word, tracker=tracker)
                print(f"Final Status: {status['final']}")
                print(f"Details: Text={status['text']}, Image={status['image']}, Audio={status['audio']}")
            
            tracker.print_report()
        
        # Sync Anki
        if RICH_AVAILABLE:
            console.print("[bold cyan]Syncing Anki...[/bold cyan]")
        else:
            print("Syncing Anki...")
        invoke('sync')
        
    except Exception as e:
        if RICH_AVAILABLE:
            console.print(f"[bold red]Error: {e}[/bold red]")
            console.print("[yellow]Make sure Anki is running and the AnkiConnect add-on is installed.[/yellow]")
        else:
            print(f"\nError: {e}")
            print("Make sure Anki is running and the AnkiConnect add-on is installed.")

if __name__ == "__main__":
    main()
    