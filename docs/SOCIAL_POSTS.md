# Build-in-public posts

Selection weighs engagement on your nominated posts, so post progress weekly and save the big demo for the final week.
Always include **#GnaniAI #GreatIndianAIInternshipChallenge** and tag @Gnani AI.

---

## Week 1: announcement (LinkedIn)
I'm building **Kural (குரல்)** for the #GreatIndianAIInternshipChallenge by Gnani AI 🎙️

The problem: a farmer whose PM-KISAN money hasn't arrived shouldn't need an English website or an agent to find out why.

Kural is a Tamil voice helpline. You call, ask in Tamil or Tanglish, even from a noisy field, and it answers in Tamil
from verified government sources.

Stack, all from Gnani's own models:
🎧 Prisma v2.5 for speech-to-text
🧠 Evon v3.3 for grounded answers
🗣️ Timbre v2.5 for a natural Tamil voice

Building in public from Coimbatore. Updates every week 👇
#GnaniAI #GreatIndianAIInternshipChallenge #Tamil #VoiceAI #BuildInPublic

## Week 2: technical insight (LinkedIn)
Tamil broke my search engine 😅

"திட்டம்", "திட்டத்தில்", "திட்டத்திற்கு": one word, three forms. Plain keyword search treats them as different words.

The fix: I fused keyword ranking with character n-gram matching (Reciprocal Rank Fusion). Now Kural finds the right
scheme for Tamil, romanised Tanglish ("PM Kisan panam varala") and English questions: 20/20 on my test set.

Next week: making it work on noisy phone lines. 📞
#GnaniAI #GreatIndianAIInternshipChallenge #NLP #Tamil

## Week 3: noise benchmark (LinkedIn + short clip)
Real callers aren't in a studio. They're in markets, on buses, and on 8 kHz phone lines.

I built a phone-line simulator (8 kHz μ-law plus background noise) and benchmarked Gnani Prisma with my denoise
front-end at 20 → 0 dB SNR. Results with real Gnani Prisma calls:
📞 20 dB SNR: 0.8% character errors
📞 0 dB (noise as loud as the voice): 6.5% character errors
✅ Right scheme found 24/24 times, even at 0 dB

🎥 In the clip, my own voice is degraded to a terrible phone call, and Kural still understands it.
#GnaniAI #GreatIndianAIInternshipChallenge #SpeechAI

## Final week: the demo (LinkedIn native video, X video)
**Kural: a Tamil voice helpline that answers government scheme questions, even over a noisy phone call.** 🎙️

▶️ 60-second demo below.

✅ Speak in Tamil, Tanglish or English
✅ Works on noisy 8 kHz phone audio
✅ Answers only from verified sources, with citations
✅ Doesn't guess: escalates to a human with a ticket number
✅ Admin dashboard for knowledge gaps and callbacks

Built entirely on Gnani AI: Prisma (STT) · Evon (LLM) · Timbre (TTS).
Would love your feedback, and a 👍 helps it reach the right people!

#GnaniAI #GreatIndianAIInternshipChallenge #Tamil #VoiceAI #AIforBharat

## X thread (final week)
1/ I built Kural (குரல்): call it, ask in Tamil about any government scheme, and it answers in Tamil. Even on a noisy phone line. 🎙️ Demo 👇 #GnaniAI #GreatIndianAIInternshipChallenge
2/ Listen: Gnani Prisma v2.5, plus a denoise front-end tuned for 8 kHz calls
3/ Think: Gnani Evon v3.3, grounded only in official scheme docs, with citations
4/ Speak: Gnani Timbre v2.5, a natural Tamil voice
5/ If it doesn't know, it doesn't guess. It books a human callback. Built solo from Coimbatore.

---
**Engagement tips:** post Tue–Thu between 8 and 10 am IST. Reply to every comment in the first hour. Ask your
college's official page, your department and classmates to share. Pin the demo post to your profile.
