"""Real localhost HTTP integration; fake models keep it fast and deterministic."""
from dataclasses import replace
from pathlib import Path
import os
import socket
import sys
import tempfile
from threading import RLock, Thread
from time import monotonic, sleep
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
from fastapi import FastAPI
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'vehicle_recognition_service'))
with patch.dict(os.environ, {'API_PREFIX':'/api','API_KEY':'test','CORS_ORIGINS':'http://localhost:5173'}):
    from app.services.recognition.client import RecognitionClient
    from app.services.media import MediaService
    from app.services.recognition.results import RecognitionResults
from recognition_service.api import health, recognition as recognition_api, video as video_api, live
from recognition_service.config import settings as service_settings
from recognition_service.inference.pipeline import RecognitionPipeline
from recognition_service.tracking.sessions import TrackingSessions


class RecognitionHTTPTests(unittest.TestCase):
    def test_image_and_video_over_http_without_shared_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config=replace(service_settings, api_key='internal-test', runtime_dir=root/'remote')
            lock=RLock()
            classifier=Mock()
            classifier.label_groups={'model':['Toyota Prius'],'color':[],'type':['car'],'view':['rear_side']}
            classifier.classify.return_value={'model':{'label':'Toyota Prius','confidence':.98},
                                             'view':{'label':'rear_side','confidence':.99}}
            trackers=[]
            def factory():
                detector=Mock()
                box=SimpleNamespace(x1=8,y1=8,x2=48,y2=40,track_id=7,confidence=.99)
                detector.detect.return_value=[box]
                detector.track.return_value=[box]
                pipeline=RecognitionPipeline(detector,classifier)
                pipeline.roi_ratio=(0,0,1,1)
                trackers.append(detector)
                return pipeline
            sessions=TrackingSessions(factory,lock)
            service=FastAPI()
            service.state.classifier=classifier
            service.state.pipeline=factory()
            service.state.inference_lock=lock
            service.state.sessions=sessions
            for module in (health, recognition_api, video_api, live):
                service.include_router(module.router,prefix='/api/v1')
            sock=socket.socket(); sock.bind(('127.0.0.1',0)); sock.listen(128)
            port=sock.getsockname()[1]
            server=uvicorn.Server(uvicorn.Config(service,log_level='error',lifespan='off'))
            thread=Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
            patches=[patch('recognition_service.api.video.settings',config),patch('recognition_service.api.recognition.settings',config),patch('recognition_service.api.health.settings',config),patch('recognition_service.media.settings',config),
                     patch('recognition_service.tracking.sessions.settings',config),patch('recognition_service.api.security.settings',config)]
            for item in patches: item.start()
            try:
                thread.start()
                deadline=monotonic()+5
                while not server.started:
                    if monotonic()>deadline: self.fail('Local service did not start')
                    sleep(.01)
                local=MediaService(root/'backend-upload',root/'backend-crop',root/'backend-output')
                client=RecognitionClient(url=f'http://127.0.0.1:{port}/api/v1',api_key='internal-test')
                frame=np.zeros((48,64,3),np.uint8)
                recognition=RecognitionResults(local, client)
                results=recognition.process_image(frame)
                self.assertEqual(results[0].model.label,'Toyota Prius')
                self.assertTrue((local.crop_dir / f'{results[0].event_id}.jpg').exists())
                video=root/'source.avi'
                writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),10,(64,48))
                self.assertTrue(writer.isOpened())
                for _ in range(3): writer.write(frame)
                writer.release()
                session_id=client.create_video(video)
                self.assertTrue(video.exists())  # Service owns only its remote upload copy.
                events=[]; sequence=0; status='pending'
                deadline=monotonic()+5
                with patch('requests.post', side_effect=AssertionError('Unexpected seatbelt request')):
                    while status not in {'completed','error','stopped'}:
                        batch,status,error=recognition.tracking_events(f'/video/sessions/{session_id}/events',sequence)
                        events.extend(batch)
                        if batch: sequence=batch[-1][0]
                        if monotonic()>deadline: self.fail('Video did not finish')
                        sleep(.03)
                self.assertEqual(status,'completed',error)
                self.assertEqual(len(events),1)  # Same track across three frames is classified once.
                self.assertEqual(events[0][1].track_id,7)
                self.assertNotIn('seatbelt', events[0][1].model_dump(by_alias=True))
                self.assertFalse(list(config.runtime_dir.iterdir()))
                self.assertEqual(len(trackers),2)  # Image detector and isolated video detector.
                self.assertEqual(trackers[1].track.call_count,3)
                chunks,close=client.stream(f'/video/sessions/{session_id}/stream')
                self.assertIn(b'Content-Type: image/jpeg',b''.join(chunks))
                close()
                client.delete_video(session_id)
                self.assertFalse(sessions.sessions)
            finally:
                server.should_exit=True
                thread.join(5)
                sessions.close()
                sock.close()
                for item in reversed(patches): item.stop()
