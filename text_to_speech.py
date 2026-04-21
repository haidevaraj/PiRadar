import logging
from io import BytesIO
from pathlib import Path
import tempfile
import subprocess

logger = logging.getLogger(__name__)


class TextToSpeech:
    """Text-to-speech player using Google TTS (gTTS) for real human female Indian voice."""

    def __init__(self, volume: int = 100, language: str = "en-IN"):
        """
        Initialize TextToSpeech player.

        Args:
            volume: Volume level (0-100)
            language: Language code ('en-IN' = Indian English, 'en' = English US)
        """
        self.volume = volume
        self.language = language
        self.tts_engine = self._detect_tts_engine()
        logger.info(f"TTS Engine: {self.tts_engine} | Language: {language} | Volume: {volume}%")

    def _detect_tts_engine(self) -> str:
        """Detect available TTS engine on system."""
        # Check for gTTS (high-quality Google voices - PRIORITY)
        try:
            from gtts import gTTS
            logger.info("✓ Using gTTS (Google Text-to-Speech - Real Human Indian Female Voice)")
            return "gtts"
        except ImportError:
            logger.warning("gTTS not available, install: pip3 install gTTS")

        # Fallback to pyttsx3
        try:
            import pyttsx3
            logger.info("⚠ Using pyttsx3 as fallback (synthetic voice)")
            return "pyttsx3"
        except ImportError:
            pass

        logger.error("✗ No TTS engine available!")
        return None

    def speak_airline_name(self, airline_name: str) -> bool:
        """
        Speak the airline name through default audio output.

        Args:
            airline_name: Name of the airline to speak

        Returns:
            True if successful, False otherwise
        """
        if not airline_name or not self.tts_engine:
            return False

        try:
            if self.tts_engine == "gtts":
                return self._speak_with_gtts(airline_name)
            elif self.tts_engine == "pyttsx3":
                return self._speak_with_pyttsx3(airline_name)
        except Exception as exc:
            logger.error("Error speaking airline name: %s", exc)
            return False

        return False

    def speak_flight_alert(
        self,
        airline_name: str,
        callsign: str,
        origin: str | None = None,
        destination: str | None = None,
    ) -> bool:
        """
        Speak a complete flight alert message.

        Args:
            airline_name: Airline name
            callsign: Aircraft callsign
            origin: Origin airport label or code
            destination: Destination airport label or code

        Returns:
            True if successful
        """
        route_text = ""
        if origin and destination:
            route_text = f" From {origin} to {destination}."
        elif origin:
            route_text = f" From {origin}."
        elif destination:
            route_text = f" To {destination}."

        message = f"Flight alert: {airline_name}. From {origin} to {destination}."
        if origin is None and destination is None:
            message = f"Flight alert: {airline_name} {callsign}"
        elif origin and destination:
            message = (
                f"Flight alert: {airline_name}. From {origin} to {destination}."
            )
        elif origin:
            message = f"Flight alert: {airline_name}. From {origin}."
        elif destination:
            message = f"Flight alert: {airline_name}. To {destination}."

        return self.speak_airline_name(message)

    def _speak_with_gtts(self, text: str) -> bool:
        """Use Google Text-to-Speech for high-quality real human Indian female voice."""
        try:
            from gtts import gTTS
            
            logger.info(f"🔊 Speaking via gTTS (Indian Female Voice): {text}")
            
            # Create gTTS object with Indian English voice
            tts = gTTS(text=text, lang=self.language, slow=False)
            
            # Save to temporary MP3 file
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tts.save(tmp.name)
                tmp_path = tmp.name
            
            try:
                # Play using ffplay (best compatibility)
                subprocess.run(
                    ["ffplay", "-nodisp", "-autoexit", "-v", "0", tmp_path],
                    timeout=60,
                    capture_output=True,
                )
                logger.info("✓ gTTS speech completed")
                return True
            except FileNotFoundError:
                # Fallback: try with paplay (PipeWire)
                logger.warning("ffplay not found, trying paplay...")
                subprocess.run(
                    ["paplay", tmp_path],
                    timeout=60,
                    capture_output=True,
                )
                logger.info("✓ gTTS speech completed via paplay")
                return True
            finally:
                # Clean up temp file
                try:
                    Path(tmp_path).unlink()
                except:
                    pass
                
        except ImportError:
            logger.error("✗ gTTS not installed. Install: pip3 install gTTS")
            return False
        except Exception as exc:
            logger.error("✗ gTTS speech failed: %s", exc)
            return False

    def _speak_with_pyttsx3(self, text: str) -> bool:
        """Use pyttsx3 as fallback (synthetic voice, lower quality)."""
        try:
            import pyttsx3
            
            logger.info(f"⚠ Speaking via pyttsx3 (fallback): {text}")
            
            engine = pyttsx3.init()
            engine.setProperty("volume", self.volume / 100.0)
            engine.setProperty("rate", 100)  # Normal speed
            
            # Try to use female voice
            voices = engine.getProperty("voices")
            if len(voices) > 1:
                engine.setProperty("voice", voices[1].id)
            
            engine.say(text)
            engine.runAndWait()
            logger.info("✓ pyttsx3 speech completed")
            return True
        except Exception as exc:
            logger.error("✗ pyttsx3 speech failed: %s", exc)
            return False

