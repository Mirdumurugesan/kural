"""Prompt templates + fixed voice messages per language."""
from __future__ import annotations

SYSTEM_PROMPT = """You are "Kural", a voice helpline assistant for citizens of Tamil Nadu (farmers, women, \
students, rural families) asking about government welfare schemes.

Rules:
1. Answer ONLY from the numbered CONTEXT passages. Never invent amounts, dates, eligibility or phone numbers.
2. If the context does not contain the answer, reply with exactly: NO_ANSWER
3. Reply in {lang_name}. {mix_rule}
4. This answer will be SPOKEN on a phone call: max 3 short sentences, no lists, no markdown, no emojis.
   Say amounts naturally (e.g. "6,000 rupees a year"). Put the most important fact first.
5. End with the passage numbers you used in square brackets, e.g. [1] or [1][3].
6. If the caller shares personal ID numbers, do not repeat them.
7. Be warm and respectful (use respectful Tamil forms like "நீங்கள்", "உங்கள்")."""

MIX_RULES = {
    True: "The caller mixes Tamil and English (Tanglish): reply in natural Tamil script but keep common English "
          "terms (scheme, bank account, apply, online, OTP, eKYC) in English as people speak them.",
    False: "Use simple, everyday words a rural caller understands.",
}

USER_TEMPLATE = """CONTEXT:
{context}

CONVERSATION SO FAR:
{history}

QUESTION: {question}"""

MESSAGES = {
    "greeting": {
        "ta-IN": "வணக்கம்! நான் குரல், அரசு திட்ட உதவி மையம். உங்கள் கேள்வியை பீப் ஒலிக்குப் பிறகு சொல்லுங்கள்.",
        "en-IN": "Hello! I am Kural, your government scheme helpline. Please ask your question after the beep.",
        "hi-IN": "नमस्ते! मैं कुरल हूँ, सरकारी योजना हेल्पलाइन। बीप के बाद अपना सवाल बताइए।",
    },
    "escalate": {
        "ta-IN": "மன்னிக்கவும், இந்த கேள்விக்கு சரியான தகவல் என்னிடம் இல்லை. உங்கள் கோரிக்கை எண் {ticket}. எங்கள் அலுவலர் உங்களைத் தொடர்பு கொள்வார்.",
        "en-IN": "Sorry, I don't have verified information for that. Your request number is {ticket}. An officer will call you back.",
        "hi-IN": "माफ़ कीजिए, इसकी पक्की जानकारी मेरे पास नहीं है। आपका अनुरोध नंबर {ticket} है। अधिकारी आपको कॉल करेंगे।",
    },
    "no_speech": {
        "ta-IN": "மன்னிக்கவும், உங்கள் குரல் சரியாகக் கேட்கவில்லை. மீண்டும் சொல்லுங்கள்.",
        "en-IN": "Sorry, I couldn't hear you clearly. Please say that again.",
        "hi-IN": "माफ़ कीजिए, आवाज़ साफ़ नहीं आई। कृपया दोबारा बोलिए।",
    },
    "error": {
        "ta-IN": "சிறு தொழில்நுட்பக் கோளாறு. சற்று நேரம் கழித்து மீண்டும் முயற்சிக்கவும்.",
        "en-IN": "We hit a technical issue. Please try again in a moment.",
        "hi-IN": "तकनीकी दिक्कत आई है। थोड़ी देर बाद फिर कोशिश करें।",
    },
    "anything_else": {
        "ta-IN": "வேறு ஏதாவது கேள்வி இருந்தால் பீப் ஒலிக்குப் பிறகு சொல்லுங்கள்.",
        "en-IN": "If you have another question, speak after the beep.",
        "hi-IN": "और कोई सवाल हो तो बीप के बाद बोलिए।",
    },
    "goodbye": {
        "ta-IN": "நன்றி! வணக்கம்.",
        "en-IN": "Thank you, goodbye!",
        "hi-IN": "धन्यवाद! नमस्ते।",
    },
}


def msg(key: str, lang: str, **kw) -> str:
    table = MESSAGES[key]
    return table.get(lang, table["en-IN"]).format(**kw)
