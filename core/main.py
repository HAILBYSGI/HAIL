# main.py
# Entry point for HAIL OS execution

from founder_identity import verify_founder
from voice_verification import verify_voice
from shariah_guard import check_shariah_compliance
from intent_classifier import classify_intent
from modules import *

def hail_start(trigger_text, voice_data, user_id):
    if not verify_founder(trigger_text, user_id):
        return "Founder identity could not be verified."

    if not verify_voice(voice_data, user_id):
        return "Voice verification failed."

    print("✅ Founder verified. HAIL OS execution beginning...")

    while True:
        user_input = input("\n>>> ")
        if not check_shariah_compliance(user_input):
            print("⚠️ Action blocked: Not compliant with Shari’ah.")
            continue

        intent = classify_intent(user_input)
        print(f"🔎 Detected intent: {intent}")

        if intent == "automation":
            engine = AutoAmanahEngine()
        elif intent == "ibadah":
            engine = IbadahTracker()
        elif intent == "dua":
            engine = DuaResponseEngine()
        elif intent == "zakat":
            engine = ZakatModule()
        elif intent == "investment":
            engine = HalalInvestmentSystem()
        elif intent == "family":
            engine = FamilyAlignmentCore()
        elif intent == "workflow":
            engine = IslamicWorkflowEngine()
        elif intent == "therapy":
            engine = QuranTherapyModule()
        elif intent == "wellness":
            engine = WellnessMonitor()
        elif intent == "daily":
            engine = HalalCompanion()
        else:
            print("🤖 No known system matched. Try again or refine your input.")
            continue

        result = engine.execute(user_input)
        print(f"✅ {result}")

if __name__ == "__main__":
    # Example trigger input - replace with actual voice/text verification data
    hail_start("Bismillah, HAIL begins", "founder_voice.m4a", "husnain_ali")
