# voice_verification.py
# Verifies the founder's voice trigger for HAIL activation

import hashlib

class VoiceVerification:
    def __init__(self):
        self.expected_trigger_phrase = "Bismillah, HAIL begins"
        self.registered_voiceprint_hash = "VOICEPRINT_HASH_PLACEHOLDER"

    def hash_audio(self, audio_bytes):
        """
        Simulates hashing of an audio voice file.
        In a real implementation, this would be based on a trained voiceprint model.
        """
        return hashlib.sha256(audio_bytes).hexdigest()

    def verify_voice_trigger(self, audio_bytes, spoken_phrase):
        """
        Confirms that both the voice and phrase match.
        """
        voice_hash = self.hash_audio(audio_bytes)
        return (
            spoken_phrase.strip() == self.expected_trigger_phrase and
            voice_hash == self.registered_voiceprint_hash
        )
