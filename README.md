# AI-Powered Chinese (Traditional) Anki Card Creator

> **Revolutionize your vocabulary acquisition with context-rich, AI-generated flashcards.**

This project is designed to bridge the gap between encountering a new word and truly mastering it. By leveraging the power of Google's **Gemini 2.5 Flash** and **Cloud Text-to-Speech**, it automates the creation of high-quality, multi-modal Chinese Anki cards that provide the deep context necessary for effective language learning.

## Why This Exists

Traditional flashcards often lack context, leading to rote memorization that fades quickly. To truly acquire Chinese, you need:

1.  **Visual Anchors**: Images that link the word to a concept, not just a translation.
2.  **Native Audio**: High-fidelity speech to master pronunciation and listening.
3.  **Contextual Usage**: Sentences that show _how_ the word is actually used.
4.  **Active Recall**: Testing mechanisms that force your brain to work.

This tool automates the entire pipeline—from text generation to image synthesis to audio production—delivering a premium learning experience directly into your Anki deck.

## Key Capabilities

### 🧠 Intelligent Content Generation

- **Contextual Sentences**: Generates natural, practical sentences using the target word.
- **Deep Analysis**: Provides word-for-word breakdowns, Pinyin with tone marks, and traditional Chinese translations.
- **Smart Formatting**: Automatically highlights target words and color-codes tones for visual reinforcement.

### 🎨 Visual & Auditory Immersion

- **AI-Synthesized Imagery**: Uses **Google Nanobanana** to create unique, photorealistic images that visually represent the sentence's meaning, creating strong memory hooks.
- **Neural Text-to-Speech**: Utilizes Google's **Chirp 3 HD** models to generate realistic, native-sounding audio for every sentence.

### 🌐 Modern Web Interface (PWA)

- **Responsive Design**: A sleek, mobile-first interface built for both desktop and mobile use.
- **Progressive Web App**: Can be installed on your home screen for quick access, providing an app-like experience.
- **Real-time Feedback**: Interactive logs and progress indicators for batch processing.

### 🔌 REST API

- **FastAPI Powered**: A high-performance API backend that enables programmatic card creation.

### 🔄 Robust & Reliable

- **Automatic Retries**: Built-in resilience ensures that transient API errors don't stop your workflow. The system intelligently retries text, image, and audio generation up to 3 times (configurable).
- **Detailed Status Reporting**: Get a comprehensive summary table after every batch, showing exactly which steps succeeded or failed for each word.

### 📊 Usage & Cost Tracking

- **Granular Logging**: Tracks usage statistics for every single word processed, including token counts for text and images.
- **Cost Analysis**: Automatically calculates and reports the estimated cost of your session, comparing **Gemini Flash 2.5** vs. **Flash Lite** pricing.
- **Standalone Reporting**: Run the usage tracker independently to view your all-time usage history and average cost per word.

### 🃏 Triple-Card System

For every word, the tool generates three distinct card types to test different aspects of memory:

1.  **Cloze Card**: Fill in the blank based on context and audio.
2.  **Audio Card**: Pure listening practice—understand the meaning from sound alone.
3.  **Recall Card**: Produce the meaning from the German prompt (for Chinese learning).

## Prerequisites

- **Anki**: Installed and running on your machine.
- **AnkiConnect**: The essential Anki add-on (Code: `2055492159`) to allow external scripts to communicate with Anki.
- **Google Cloud Project**:
  - **Vertex AI API** enabled.
  - **Cloud Text-to-Speech API** enabled.
  - `gcloud` CLI installed and authenticated (`gcloud auth application-default login`).

## Installation

1.  **Clone the Repository**:

    ```bash
    git clone https://github.com/XSnelliusX/Chinese-Anki-Card-Creator.git
    cd Chinese-Anki-Card-Creator
    ```

2.  **Install Dependencies**:

    ```bash
    pip install -r requirements.txt
    ```

3.  **Configuration**:
    Copy the example configuration and add your project details:
    ```bash
    cp .env.example .env
    ```
    Edit `.env` and set your `GOOGLE_PROJECT_ID`.
    You can also set the `API_HOST` and `API_PORT` if you want to change the default values.
    For more information about the configuration, see the [Configuration Reference](#configuration-reference).

4.  **Remote Access (Optional)**:
    If you plan to use this from your phone, follow the [Caddy Setup](#remote-access--https-caddy) to enable secure HTTPS access (Requires a domain name or Dynamic DNS service).

## Usage

### 🌐 Web Interface (Recommended)

The easiest way to use the tool is through the web interface. Start the API server and navigate to the local URL.

```bash
python api.py
```

Once running, open your browser to `http://<API_HOST>:<API_PORT>` (default: `http://127.0.0.1:8000`).

### 🖥️ CLI Mode

#### Interactive Mode

Simply run the script without arguments to enter interactive mode. You can paste a list of words (comma-separated), and the tool will process them one by one.

```bash
python chinese_anki_creator.py
```

#### Command Line Arguments

Pass words directly as arguments for quick batch processing:

```bash
python chinese_anki_creator.py 你好 謝謝 電腦
```

### 📊 Reports

To see a detailed report of your all-time usage and costs:

```bash
python usage_tracker.py
```

## API Reference

The project includes a FastAPI backend. Below is the primary endpoint:

### `POST /chinese`

Generate Chinese Anki cards.

- **Body**: `{"words": ["word1", "word2"]}`

## Configuration Reference

Customize the behavior via your `.env` file:

| Variable              | Description                             | Default                            |
| :-------------------- | :-------------------------------------- | :--------------------------------- |
| `GOOGLE_PROJECT_ID`   | **Required**. Your GCP Project ID.      | -                                  |
| `GOOGLE_LOCATION`     | GCP Region for Vertex AI.               | `global`                           |
| `ANKI_CONNECT_URL`    | URL for AnkiConnect.                    | `http://localhost:8765`            |
| `API_HOST`            | Host for the API server.                | `127.0.0.1`                        |
| `API_PORT`            | Port for the API server.                | `8000`                             |
| `API_KEY`             | Optional API Key for authentication.    | -                                  |
| `CHINESE_DECK_NAME`   | Name of the Anki deck to populate.      | `Chinese`                          |
| `CHINESE_MODEL_NAME`  | Name of the Note Type to create/use.    | `Chinese Model`                    |
| `TEXT_MODEL`          | Gemini model for text generation.       | `gemini-2.5-flash-preview-09-2025` |
| `IMAGE_MODEL`         | Gemini model for image generation.      | `gemini-2.5-flash-image`           |
| `CHINESE_AUDIO_MODEL` | TTS Voice model.                        | `cmn-CN-Chirp3-HD-Achernar`        |
| `MAX_RETRIES`         | Number of retries for failed API calls. | `3`                                |

## Security

This project includes several security measures:
- **API Key Authentication**: If `API_KEY` is set in your `.env`, the frontend and API will require this key.
- **Input Validation**: Prevents processing too many words or excessively long words.
- **XSS Protection**: Sanitizes user input before rendering in the UI.

To use the API Key in the web interface, click the **Settings (Gear)** icon in the header and enter your key. It will be saved in your browser's local storage.

## Remote Access & HTTPS (Caddy)

If you need to access this service from your phone or outside your home network, it is **highly recommended** to use a reverse proxy with HTTPS to protect your API Key.

### 1. Install Caddy
Caddy is a lightweight, secure web server that handles SSL automatically.
- **Linux**: `sudo apt install caddy` (or see [caddy.community](https://caddyserver.com/docs/install))

### 2. Configure Caddy
A `Caddyfile.example` has been provided. 
- Copy it to a new file named `Caddyfile`: `cp Caddyfile.example Caddyfile`
- Open `Caddyfile` and replace `your-domain.com` with your actual domain or a dynamic DNS like DuckDNS.
- Ensure your router is forwarding ports **80** and **443** to your server.

### 3. Run it
Simply run:
```bash
caddy run
```
Caddy will automatically fetch an SSL certificate and proxy all traffic to your Python backend on `localhost:8000`.

> [!IMPORTANT]
> When using Caddy, keep `API_HOST=127.0.0.1` in your `.env`. This ensures the backend only talks to Caddy and cannot be accessed directly via insecure HTTP.

---

_Built for serious learners who value efficiency and depth._
