import logging
from io import BytesIO
from pathlib import Path
import tempfile
import subprocess
import atexit

logger = logging.getLogger(__name__)

# Keep track of temp files to prevent deletion before playback completes
_temp_files = []

def _cleanup_temp_files():
    """Clean up any remaining temp files on exit."""
    for tmp_path in _temp_files:
        try:
            Path(tmp_path).unlink()
        except:
            pass

atexit.register(_cleanup_temp_files)


class TextToSpeech:
    """Text-to-speech player using Google TTS (gTTS) for real human female American voice (airport announcement style)."""

    def __init__(self, volume: int = 100, language: str = "en", tld: str = "com"):
        """
        Initialize TextToSpeech player.

        Args:
            volume: Volume level (0-100)
            language: Language code ('en' = English)
            tld: Top-level domain for regional accent ('com' = US, 'co.in' = India)
        """
        self.volume = volume
        self.language = language
        self.tld = tld
        self.tts_engine = self._detect_tts_engine()
        self._coqui_instance = None  # Lazy load the model only if needed
        logger.info(f"TTS Engine: {self.tts_engine} | Language: {language} | TLD: {tld} | Volume: {volume}%")

    def _detect_tts_engine(self) -> str:
        """Detect available TTS engine on system."""
        # Check for gTTS (high-quality Google voices - PRIORITY)
        try:
            from gtts import gTTS
            logger.info("✓ Using gTTS (Google Text-to-Speech - Real Human American Female Voice)")
            return "gtts"
        except ImportError:
            logger.warning("gTTS not available, install: pip3 install gTTS")

        # Fallback to Coqui TTS (High-quality offline synthesis)
        try:
            from TTS.api import TTS
            logger.info("⚠ Using Coqui TTS as fallback (High-quality offline voice)")
            return "coqui"
        except ImportError:
            pass

        logger.error("✗ No TTS engine available!")
        return None

    def _speak_message(self, text: str) -> bool:
        """
        Speak a message through the detected audio output.

        Args:
            text: The text message to speak

        Returns:
            True if successful, False otherwise
        """
        if not text or not self.tts_engine:
            return False

        try:
            if self.tts_engine == "gtts":
                return self._speak_with_gtts(text)
            elif self.tts_engine == "coqui":
                return self._speak_with_coqui(text)
        except Exception as exc:
            logger.error("Error speaking message: %s", exc)
            return False

        return False

    def _get_cardinal_direction(self, heading: float | None) -> str:
        """Convert heading degrees to cardinal direction string."""
        if heading is None: return ""
        directions = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
        idx = int((heading + 22.5) % 360 // 45)
        return directions[idx]

    def speak_flight_alert(
        self,
        airline_name: str,
        callsign: str,
        origin: str | None = None,
        destination: str | None = None,
        altitude: float | None = None,
        speed: float | None = None,
        heading: float | None = None,
    ) -> bool:
        """
        Speak a complete flight alert message.

        Args:
            airline_name: Airline name
            callsign: Aircraft callsign
            origin: Origin airport label or code
            destination: Destination airport label or code
            altitude: Altitude in meters
            speed: Speed in meters per second
            heading: Heading in degrees

        Returns:
            True if successful
        """
        # Start with airline name and callsign
        message = f"{airline_name} {callsign}"
        
        # Add route information
        route_parts = []
        if origin and destination:
            route_parts.append(origin)
            route_parts.append(destination)
        elif origin:
            route_parts.append(origin)
        elif destination:
            route_parts.append(destination)

        if route_parts:
            message += f" { ' -> '.join(route_parts) }"
        
        message += "." # Always end the route/callsign part with a period

        # Add live flight metrics
        details = []
        if altitude is not None:
            alt_feet = int(round(altitude * 3.28084))
            details.append(f"Cruising at {alt_feet:,} feet")
        if speed is not None:
            speed_mph = int(round(speed * 2.23694))
            details.append(f"{speed_mph} miles per hour")
        if heading is not None:
            direction = self._get_cardinal_direction(heading)
            details.append(f"heading {direction}")

        if details:
            message += " " + ", ".join(details) + "."

        return self._speak_message(message)

    def _speak_with_gtts(self, text: str) -> bool:
        """Use Google Text-to-Speech for high-quality real human American female voice (airport announcement style)."""
        try:
            from gtts import gTTS
            
            logger.info(f"🔊 Speaking via gTTS: {text}")
            
            # Create gTTS object with American English voice - normal speed
            tts = gTTS(text=text, lang=self.language, tld=self.tld, slow=False)
            
            # Save to temporary MP3 file
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tts.save(tmp.name)
                tmp_path = tmp.name
            
            # Track temp file for cleanup
            _temp_files.append(tmp_path)
            
            try:
                # Play using ffplay (blocking)
                subprocess.run(
                    ["ffplay", "-nodisp", "-autoexit", "-v", "0", tmp_path],
                    capture_output=True,
                )
                logger.info("✓ gTTS speech completed")
                return True
            except FileNotFoundError:
                # Fallback: try with paplay (PipeWire) - blocking
                logger.warning("ffplay not found, trying paplay...")
                subprocess.run(
                    ["paplay", tmp_path],
                    capture_output=True,
                )
                logger.info("✓ gTTS speech completed via paplay")
                return True
                
        except ImportError:
            logger.error("✗ gTTS not installed. Install: pip3 install gTTS")
            return False
        except Exception as exc:
            logger.error("✗ gTTS speech failed: %s", exc)
            return False

    def _speak_with_coqui(self, text: str) -> bool:
        """Use Coqui TTS as fallback (High-quality offline VITS model)."""
        try:
            from TTS.api import TTS
            
            if self._coqui_instance is None:
                logger.info("Initializing Coqui TTS model (ljspeech/vits)...")
                self._coqui_instance = TTS("tts_models/en/ljspeech/vits", gpu=False)
            
            logger.info(f"🔊 Speaking via Coqui TTS (Offline): {text}")
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            
            self._coqui_instance.tts_to_file(text=text, file_path=tmp_path)
            
            try:
                # Play using ffplay (blocking)
                subprocess.run(
                    ["ffplay", "-nodisp", "-autoexit", "-v", "0", tmp_path],
                    capture_output=True,
                )
                logger.info("✓ Coqui TTS speech completed")
                return True
            except FileNotFoundError:
                # Fallback: try with paplay
                logger.warning("ffplay not found, trying paplay...")
                subprocess.run(
                    ["paplay", tmp_path],
                    capture_output=True,
                )
                logger.info("✓ Coqui TTS speech completed via paplay")
                return True
            finally:
                # Clean up temp file
                try:
                    Path(tmp_path).unlink()
                except:
                    pass

        except ImportError:
            logger.error("✗ TTS (Coqui) not installed. Install: pip3 install TTS")
            return False
        except Exception as exc:
            logger.error("✗ Coqui TTS speech failed: %s", exc)
            return False
