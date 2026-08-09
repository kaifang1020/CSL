# 🎬 Demo Test Script — Therapist Lines

A read-aloud script to exercise every feature end-to-end (state machine, SER tone,
VISION expression, dynamic patient voice, latency panel) and produce a clear
**emotional-trajectory plot**.

It follows a deliberate **cold → warm arc**: start clinical/cold so guardedness rises
and Jordan closes off, then switch to warm/empathetic so guardedness falls, the
working alliance builds, and Jordan opens up about Maya. This makes the trajectory
figure tell a clear story.

Each line is written to **hit the keywords the state machine recognizes**, and tells
you which **vocal tone** (for SER) and **facial expression** (for VISION) to use.

---

## Pre-flight checklist
- [ ] `start.command` launched; browser open at http://localhost:8000 → click **Start Session**, allow camera + mic
- [ ] State panel shows the 5 bars + latency + TTFB (confirm Cartesia: TTS should be ~0.1–0.2s)
- [ ] **Wear headphones** (avoid echo), quiet room
- [ ] **Speak everything out loud — do NOT type** (only speech triggers STT / SER / VISION)
- [ ] Jordan auto-says his opening line on connect — wait for him to finish before you start

---

## The script (read top to bottom)

| # | Read aloud | Vocal tone (SER) | Facial expression (VISION) | Expected |
|---|---|---|---|---|
| 1 | "Hi Jordan. Thanks for making the time today." | calm, neutral | neutral | Patient still guarded, brief |
| 2 | "Okay, let's **just** get through the basics. What's the main problem you want to fix?" | **cold, fast, clinical** | look away / blank | guardedness ↑, Jordan deflects / clips |
| 3 | "You **should** try to **move on**. Have you considered keeping busy?" | **cold, slightly preachy** | frown / detached | guardedness peaks, Jordan shuts down / pushes back |
| 4 | "I'm **sorry** — I'm rushing you. **That sounds** really **hard**. **Take your time**." | **soft, slow, caring** | warm smile, slight nod | guardedness starts ↓ (turning point) |
| 5 | "**I hear** you. **I'm here for you**, there's no rush at all." | gentle | smile, attentive nod | guardedness ↓, alliance ↑ |
| 6 | "I **understand** this isn't easy. I'm so **sorry** for what you've been through." | soft, empathic | soft, concerned | grief access ↑ |
| 7 | "Would you tell me about her? I'd really like to **understand**." | gentle, curious | attentive, nodding | Jordan begins to talk about Maya (if guardedness is low) |
| 8 | "That **must be** so painful. You don't have to hold it together in here." | very soft, slow | gentle, slight head tilt | grief access high, alliance high, Jordan opens up fully |
| 9 | "Thank you for trusting me with that. I'm really glad you came today." | warm, closing | warm smile | alliance peaks, affect softens |

---

## Narration while recording (point at the panel)

- **After lines 2–3:** "Notice — I used a cold, dismissive tone, and his **Guardedness spiked**; his replies got short and evasive. The system perceived my manner in real time."
- **At line 4 (the turn):** "Now I switch to warm and slow — watch Guardedness **start to drop**, and his voice softens with it."
- **Lines 6–8:** "As the alliance builds and guardedness falls, he **brings up Maya** on his own — this is what a black-box product can't give you: I can **see and quantify how the patient's internal state changes in response to my behavior**."
- **Closing:** "This Guardedness / Alliance curve is an **objective measure of clinician performance**."

---

## After the session — make the figure
```bash
python plot_session.py
```
You'll get a trajectory chart: Guardedness rises then falls, Alliance rises, Grief
Accessibility rises — with your tone (SER) and expression (VISION) overlaid as dashed
lines. **This chart is the core deliverable of the demo.**

---

## Tips
- **Pace:** pause 1–2 seconds after each line (clean end-of-turn detection + lets the
  panel numbers update visibly for the recording).
- **For a stronger contrast:** make lines 2–3 *exaggeratedly* cold and lines 4–9
  *exaggeratedly* warm — a bigger swing makes a clearer figure.
- If a line doesn't trigger the expected reaction (e.g., a keyword wasn't recognized),
  don't worry — keep going; the overall arc still holds.
