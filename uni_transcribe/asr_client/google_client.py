from uni_transcribe.asr_client.asr_client import AsrClient
from uni_transcribe.messages import *
from uni_transcribe.exceptions.exceptions import ConfigurationException, AudioException
from uni_transcribe.utils import generate_random_str
from uni_transcribe.stream.stream_results import StreamResult, StreamResults
from uni_transcribe.stream.stream import Stream
from google.cloud import speech
from google.cloud import storage

AUDIO_DURATION_LIMIT = 480 * 60


class GoogleClient(AsrClient):
    def __init__(self, client, storage_client):
        self.client = client
        self.storage_client = storage_client

    def recognize(self, config: Config, audio: Audio):
        if audio.duration < 60:
            recog_audio = speech.RecognitionAudio(
                content=audio.byte_array_content
            )
            return self._async_recognize(config, audio, recog_audio)
        elif audio.duration < AUDIO_DURATION_LIMIT:
            if not config.google_storage_bucket:
                raise ConfigurationException("Please provide google_storage_bucket in the config for long file")
            blob = self._upload_to_google_storage(config.google_storage_bucket, audio)
            gs_url = "gs://{}/{}".format(blob.bucket.name, blob.name)
            recog_audio = speech.RecognitionAudio()
            recog_audio.uri = gs_url
            result = self._async_recognize(config, audio, recog_audio)
            blob.delete()
            return result
        else:
            raise AudioException("Google does not support audio longer than 480 minutes")

    def stream(self, stream: Stream, config: Config):

        recog_config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=config.language,
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=recog_config,
            interim_results=True
        )

        audio_generator = stream.generator()
        requests = (
            speech.StreamingRecognizeRequest(audio_content=content)
            for content in audio_generator
        )
        responses = self.client.streaming_recognize(streaming_config, requests)

        def parse_response():
            for response in responses:
                if not response.results:
                    continue
                result = response.results[0]
                if not result.alternatives:
                    continue
                transcript = result.alternatives[0].transcript
                if not result.is_final:
                    yield StreamResult(transcript, False)
                else:
                    yield StreamResult(transcript, True)

        return StreamResults(parse_response())

    def _async_recognize(self, config: Config, audio: Audio, recog_audio):
        config = speech.RecognitionConfig(
            encoding=audio.codec.name,
            sample_rate_hertz=audio.sample_rate,
            language_code=config.language,
            model="video",
            use_enhanced=True
        )

        operation = self.client.long_running_recognize(config=config, audio=recog_audio)
        response = operation.result()

        transcripts = []
        total_confidences = 0
        for result in response.results:
            transcripts.append(result.alternatives[0].transcript.strip())
            total_confidences += result.alternatives[0].confidence
        if not transcripts:
            confidence = 1
        else:
            confidence = total_confidences / len(transcripts)
        return Result(transcript=" ".join(transcripts), confidence=confidence)

    def _upload_to_google_storage(self, bucket_name, audio: Audio):
        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob("{}{}".format(generate_random_str(20), audio.file_extension))
        blob.upload_from_filename(audio.file)
        return blob

    @staticmethod
    def from_key_file(filename: str, *args, **kwargs):
        client = speech.SpeechClient.from_service_account_file(filename)
        storage_client = storage.Client.from_service_account_json(filename)
        return GoogleClient(client, storage_client)

    @staticmethod
    def from_key(key: str, *args, **kwargs):
        raise ConfigurationException("Google ASR: Use key file authentication")
