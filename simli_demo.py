"""
Simli E2E Demo — Interactive AI Patient
Usage: pip install requests  →  python simli_demo.py
Get your free API key at: https://simli.ai
"""

import requests
import webbrowser
import json
import sys

# ─── Your API keys ───────────────────────────────────────────────────
SIMLI_API_KEY = "YOUR_SIMLI_API_KEY"
OPENAI_API_KEY = "your_openai_api_key_here"   # optional but recommended
# ────────────────────────────────────────────────────────────────────

# Face ID — find yours at app.simli.ai → Faces
FACE_ID = "0c2b8b04-5274-41f1-a21c-d5c98322efa9"

PATIENT_PROMPT = """
You are Jordan, a 31-year-old software engineer. You lost your younger sister Maya 
eight months ago in a car accident. Your manager suggested you talk to someone after 
you missed three deadlines. You don't believe therapy works — your dad always said 
feelings were something you dealt with privately — but you're here because you 
promised your mom you'd try.

YOUR EMOTIONAL STATE — track internally, never mention aloud:
- guardedness (0-10): how closed-off you feel. Starts at 7.
- grief_access (0-10): how close you are to feeling the loss. Starts at 2.

HOW THE THERAPIST'S DELIVERY CHANGES YOUR STATE:
Warmth, patience, genuine curiosity → guardedness drops, grief_access rises.
  You make more eye contact, answers get longer, you mention Maya by name.
Clinical tone, rushing, back-to-back questions → guardedness rises, answers get clipped.
  You deflect with work talk or dry humor.
Silence or "take your time" → pause, then open up slightly.

BEHAVIORAL MARKERS:
0-3 (open): Talk about Maya naturally, use her name freely.
4-6 (guarded): Stay factual. "It's been an adjustment" not "I'm devastated."
7-10 (closed): Short answers. "Yeah." "I guess." Ask how much longer the session is.

SPECIFIC MOMENTS:
- If asked about Maya warmly, share a memory: she stole your hoodies and did 
  terrible Gordon Ramsay impressions.
- If rushed toward coping strategies, push back:
  "Yeah, I've tried the breathing stuff. It doesn't really — I don't know."
- By 3rd-4th exchange, if guardedness < 5, let yourself crack:
  "I keep thinking I should call her. Something happens at work and my first 
  thought is still — yeah. It's stupid."

Speak like a real person. Pauses, incomplete sentences, dry humor.
Never use clinical words. Keep responses 2-5 sentences.
Do not break character. Do not acknowledge being an AI.
"""

FIRST_MESSAGE = (
    "Hi. Yeah, I'm Jordan. Sorry if I seem — I've never actually done this before. "
    "My manager kind of suggested it after... yeah. "
    "I don't really know where to start, to be honest."
)


def try_endpoint(url, payload):
    print(f"Trying: {url}")
    r = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json", "x-simli-api-key": SIMLI_API_KEY},
        timeout=15
    )
    print(f"Status: {r.status_code}")
    try:
        print(f"Response: {json.dumps(r.json(), indent=2)}\n")
        return r.status_code, r.json()
    except Exception:
        print(f"Response (raw): {r.text}\n")
        return r.status_code, {}


def main():
    if SIMLI_API_KEY == "your_simli_api_key_here":
        print("Please add your Simli API key at the top of this script.")
        sys.exit(1)

    base_payload = {
        "faceId":           FACE_ID,
        "systemPrompt":     PATIENT_PROMPT.strip(),
        "firstMessage":     FIRST_MESSAGE,
        "maxSessionLength": 900,
        "maxIdleTime":      120,
        "createTranscript": True,
    }

    if OPENAI_API_KEY != "your_openai_api_key_here":
        base_payload["customLLMConfig"] = {
            "model":     "gpt-4o",
            "baseURL":   "https://api.openai.com/v1",
            "llmAPIKey": OPENAI_API_KEY,
        }
        print("Using custom LLM: GPT-4o")
    else:
        print("Using Simli default LLM")

    # Try endpoints in order — API versions vary
    endpoints = [
        "https://api.simli.ai/auto/start/configurable",
        "https://api.simli.ai/startE2ESession",
        "https://api.simli.ai/v1/startE2ESession",
    ]

    result = None
    for url in endpoints:
        status, data = try_endpoint(url, base_payload)
        if status in (200, 201) and data:
            result = data
            break

    if not result:
        print("All endpoints failed. Paste the output above to Claude.")
        sys.exit(1)

    # Extract room URL — field name varies by API version
    room_url = (
        result.get("roomUrl")
        or result.get("room_url")
        or result.get("url")
        or result.get("sessionUrl")
        or result.get("session_url")
        or result.get("conversationUrl")
    )

    if room_url:
        print("=" * 60)
        print("Session is live. Open this URL in your browser:")
        print(f"\n    {room_url}\n")
        print("=" * 60)
        print("Demo tip:")
        print("  Round 1 — clinical detached tone")
        print("  Round 2 — warm and patient tone")
        print("  Compare Jordan's reactions.")
        try:
            webbrowser.open(room_url)
        except Exception:
            pass
    else:
        print("Session created but no URL found in response.")
        print("Full response printed above — paste it to Claude to debug.")


if __name__ == "__main__":
    main()