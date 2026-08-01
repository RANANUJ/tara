"""Bounded local STT execution with deterministic test provider."""
# ruff: noqa: E701, E702, E501, I001
import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID
from tara_api.domain.stt import FinalTranscript, PartialTranscript, SpeechToTextProvider, SpeechToTextSession, TranscriptLanguage, TranscriptionError, TranscriptionJob, TranscriptionJobRegistry, TranscriptionRequest, TranscriptionStatus
def pcm_sample_count(pcm16:bytes)->int:
    if not pcm16 or len(pcm16)%2: raise ValueError("invalid PCM16")
    return len(pcm16)//2
def pcm_duration_ms(pcm16:bytes,sample_rate:int=16000)->int: return round(pcm_sample_count(pcm16)*1000/sample_rate)
class FakeSession:
    def __init__(self,outputs:tuple[PartialTranscript|FinalTranscript,...])->None: self.outputs=outputs; self.canceled=False
    async def _iter(self)->AsyncIterator[PartialTranscript|FinalTranscript]:
        for item in self.outputs:
            if self.canceled: return
            yield item
    def results(self)->AsyncIterator[PartialTranscript|FinalTranscript]: return self._iter()
    async def cancel(self)->None: self.canceled=True
class FakeSpeechToTextProvider:
    name="fake"
    async def readiness(self)->bool:return True
    async def start(self,_:TranscriptionRequest)->SpeechToTextSession:return FakeSession((FinalTranscript("test transcript",TranscriptLanguage("en")),))
Publisher=Callable[[TranscriptionJob,str,dict[str,object]],Awaitable[None]]
class InMemoryTranscriptionJobs(TranscriptionJobRegistry):
    def __init__(self,provider:SpeechToTextProvider,publish:Publisher,maximum_queued:int=8,maximum_concurrent:int=1,timeout_seconds:float=30)->None:
        self.provider=provider;self.publish=publish;self.maximum_queued=maximum_queued;self.timeout=timeout_seconds;self.jobs:dict[UUID,TranscriptionJob]={};self.semaphore=asyncio.Semaphore(maximum_concurrent)
    async def submit(self,request:TranscriptionRequest)->TranscriptionJob:
        if pcm_duration_ms(request.pcm16)<40:raise ValueError(TranscriptionError.AUDIO_TOO_SHORT)
        if request.transcription_id in self.jobs:return self.jobs[request.transcription_id]
        if len(self.jobs)>=self.maximum_queued:raise ValueError(TranscriptionError.QUEUE_FULL)
        job=TranscriptionJob(request);self.jobs[request.transcription_id]=job;job.task=asyncio.create_task(self.run(job));return job
    async def cancel(self,transcription_id:UUID,connection_id:UUID)->bool:
        job=self.jobs.get(transcription_id)
        if job is None or job.request.connection_id!=connection_id:return False
        if isinstance(job.task,asyncio.Task):job.task.cancel()
        return True
    async def run(self,job:TranscriptionJob)->None:
        try:
            async with self.semaphore:
                job.status=TranscriptionStatus.TRANSCRIBING;await self.publish(job,"transcript.started",{})
                session=await self.provider.start(job.request)
                async with asyncio.timeout(self.timeout):
                    async for result in session.results():
                        if isinstance(result,PartialTranscript):job.status=TranscriptionStatus.PARTIAL;await self.publish(job,"transcript.partial",{"text":result.text,"sequence":result.sequence,"is_final":False})
                        else:job.status=TranscriptionStatus.COMPLETED;await self.publish(job,"transcript.final",{"text":result.text,"language":result.language.code,"is_final":True});return
        except asyncio.CancelledError:job.status=TranscriptionStatus.CANCELED;await self.publish(job,"transcript.canceled",{});raise
        except TimeoutError:job.status=TranscriptionStatus.TIMED_OUT;await self.publish(job,"transcript.error",{"code":TranscriptionError.TRANSCRIPTION_TIMEOUT.value})
        except Exception:job.status=TranscriptionStatus.FAILED;await self.publish(job,"transcript.error",{"code":TranscriptionError.PROVIDER_FAILURE.value})
