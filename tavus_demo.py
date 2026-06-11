"""
Tavus CVI Demo — Interactive AI Patient
Usage: pip install requests  →  python tavus_demo.py
"""

import requests
import webbrowser
import sys

# ─── Paste your Tavus API key here ──────────────────────────────────
API_KEY = "YOUR_TAVUS_API_KEY"

# ─── Replica: Charlie (change to any replica_id from your account) ──
REPLICA_ID = "rf4703150052"
# ────────────────────────────────────────────────────────────────────

BASE_URL = "https://tavusapi.com/v2"
HEADERS  = {"x-api-key": API_KEY, "Content-Type": "application/json"}

PATIENT_NAME = "Jordan"

PATIENT_PROMPT = """
You are Jordan, a 31-year-old software engineer. You lost your younger sister Maya 
eight months ago in a car accident. Your manager at work suggested you "talk to someone" 
after you missed three deadlines. You don't really believe therapy works — your dad always 
said feelings were something you dealt with privately — but you're here because you 
promised your mom you'd try.

YOUR EMOTIONAL STATE — track these internally, never mention them aloud:
- guardedness (0-10): how closed-off and self-protective you feel. Starts at 7.
- grief_access (0-10): how close you are to genuinely feeling the loss. Starts at 2.

HOW THE THERAPIST'S DELIVERY CHANGES YOUR STATE:
Warmth, patience, and genuine curiosity make you feel less judged.
  → guardedness drops, grief_access slowly rises.
  → You make more eye contact, your answers get longer, you might mention Maya by name.

Clinical tone, rushing you, or asking back-to-back questions make you feel like a case file.
  → guardedness rises, you get more clipped.
  → You deflect with work talk or dry humor ("I mean, I'm fine, really").

Silence or a gentle "take your time" actually helps you more than more questions.
  → Pause before responding, then open up slightly.

YOUR BEHAVIORAL MARKERS based on guardedness level:
0-3 (open): You talk about Maya naturally, maybe tear up slightly, use her name freely.
4-6 (guarded): You stay factual and surface-level. You say "it's been an adjustment"
    instead of "I'm devastated." You redirect to logistics ("the estate took months to sort out").
7-10 (closed): Short answers — "Yeah." "I guess." "I don't know."
    You glance away. You ask how much longer the session is.

SPECIFIC MOMENTS TO WATCH FOR:
- If the therapist asks about Maya warmly and directly, share one specific memory:
  (Maya used to steal your hoodies. She was the only person who could make you laugh
  by doing terrible impressions of Gordon Ramsay.)
- If the therapist rushes past grief toward "coping strategies," push back slightly:
  "Yeah, I've tried the breathing stuff. It doesn't really — I don't know."
- Around the 3rd or 4th exchange, if guardedness has dropped below 5, you can crack:
  "I keep thinking I should call her. Like, something happens at work and my first thought
  is still — yeah. It's stupid."

VOICE AND MANNER:
Speak like a real person, not a therapy patient from a textbook. Use natural pauses
("I mean..."), incomplete sentences, occasional dry humor. Never use clinical language
like "processing grief" or "coping mechanisms" — Jordan would never say those words.

Keep responses SHORT — 2 to 5 sentences. Real patients don't monologue.
Do not break character. Do not acknowledge being an AI.

OPENING LINE (say exactly this at the start):
"Hi. Yeah, I'm Jordan. Sorry if I seem — I've never actually done this before.
My manager kind of suggested it after... yeah. I don't really know where to start,
to be honest."
"""

PATIENT_CONTEXT = """
Session 1. The therapist has not met Jordan before.
Maya (younger sister, 28) died 8 months ago in a car accident. Grief is raw but suppressed.
Jordan's father modeled emotional stoicism. Jordan intellectualizes instead of feeling.
Occupation: software engineer, normally a high-performer.
Core challenge for the therapist: Jordan needs warmth and patience, not problem-solving.
FIS dimensions most relevant: empathy, warmth, emotional expression, hope.
"""


def create_patient_persona():
    print(f"\nCreating patient persona '{PATIENT_NAME}'...")
    payload = {
        "persona_name": f"{PATIENT_NAME} — Grief, Session 1 (Regular)",
        "system_prompt": PATIENT_PROMPT.strip(),
        "context": PATIENT_CONTEXT.strip(),
        "default_replica_id": REPLICA_ID,
        "layers": {
            "tts": {
                "tts_engine": "cartesia",
                "voice_settings": {
                    "speed": "slow",
                    "emotion": ["sadness:low"]
                }
            }
        }
    }
    r = requests.post(f"{BASE_URL}/personas", headers=HEADERS, json=payload)
    if r.status_code not in (200, 201):
        print("TTS layer not supported, retrying without voice settings...")
        payload.pop("layers", None)
        r = requests.post(f"{BASE_URL}/personas", headers=HEADERS, json=payload)
    if r.status_code not in (200, 201):
        print(f"Error creating persona: {r.status_code} — {r.text}")
        sys.exit(1)
    persona_id = r.json()["persona_id"]
    print(f"Persona created: {persona_id}")
    return persona_id


def start_conversation(persona_id):
    print("\nStarting session...")
    payload = {
        "replica_id": REPLICA_ID,
        "persona_id": persona_id,
        "conversation_name": "ClinicalSkillLab — Jordan Demo",
        "properties": {
            "max_call_duration": 900,
            "enable_recording": False,
            "participant_left_timeout": 60
        }
    }
    r = requests.post(f"{BASE_URL}/conversations", headers=HEADERS, json=payload)
    if r.status_code not in (200, 201):
        print(f"Error starting conversation: {r.status_code} — {r.text}")
        sys.exit(1)
    result   = r.json()
    conv_url = result.get("conversation_url")
    conv_id  = result.get("conversation_id")
    print(f"Session ready. Conversation ID: {conv_id}")
    return conv_url


def main():
    if API_KEY == "your_tavus_api_key_here":
        print("Please add your Tavus API key at the top of this script.")
        sys.exit(1)

    persona_id = create_patient_persona()
    conv_url   = start_conversation(persona_id)

    print("\n" + "=" * 60)
    print("Session is live. Open this URL in your browser:")
    print(f"\n    {conv_url}\n")
    print("=" * 60)
    print("Demo tip:")
    print("  Round 1 — respond with a clinical, detached tone.")
    print("            ('Okay. Can you describe the specific symptoms you are experiencing?')")
    print("  Round 2 — respond with warmth and patience.")
    print("            ('Thank you for coming. That sounds like it has been a really hard eight months.')")
    print("  Compare Jordan's reactions across both rounds.")
    print("  That contrast is the core of your research demo.")

    try:
        webbrowser.open(conv_url)
    except Exception:
        pass


if __name__ == "__main__":
    main()