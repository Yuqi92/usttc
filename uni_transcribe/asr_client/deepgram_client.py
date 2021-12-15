from uni_transcribe.asr_client.asr_client import AsrClient
from uni_transcribe.config import Config
from uni_transcribe.audio.audio_file import AudioFile
from uni_transcribe.result.recognize_result import RecognizeResult
from uni_transcribe.result.word import Word
from uni_transcribe.exceptions.exceptions import ConfigurationException, AudioException
from deepgram import Deepgram
import asyncio


class DeepgramClient(AsrClient):
    def __init__(self, client):
        self.client = client

    def recognize(self, config: Config, audio: AudioFile):
        response = asyncio.run(self.async_recognize(config, audio))
        word_list = []
        results = response["results"]
        channels = results.get("channels")
        if channels:
            for (M, channel) in enumerate(channels):
                alternatives = channel["alternatives"]
                words = alternatives[0]["words"]
                for word in words:
                    if len(channels) > 1:
                        speaker = M
                    else:
                        speaker = word.get("speaker")
                    word_list.append(
                        Word(
                            text=word["punctuated_word"], confidence=word["confidence"],
                            start=word["start"] * 1000,
                            end=word["end"] * 1000,
                            speaker=speaker
                        )
                    )

        return RecognizeResult(words=word_list)

    async def async_recognize(self, config: Config, audio: AudioFile):
        with open(audio.file, 'rb') as audio_file:
            # Replace mimetype as appropriate
            source = {'buffer': audio_file, 'mimetype': 'audio/*'}
            response = await self.client.transcription.prerecorded(
                source,
                {
                    'punctuate': True,
                    "diarize": (config.diarization is not None),
                    "multichannel": config.separate_speaker_per_channel and (audio.channels > 1)
                }
            )
            return response

    def stream(self):
        pass

    @staticmethod
    def from_key_file(filename: str, *args, **kwargs):
        raise ConfigurationException("Deepgram ASR: Use key authentication")

    @staticmethod
    def from_key(key: str, *args, **kwargs):
        client = Deepgram(key)
        return DeepgramClient(client)
