"""Tracking session isolation, capacity and event cursor behavior."""
from pathlib import Path
import sys
import tempfile
from threading import RLock
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recognition_service.tracking.sessions import TrackingSessions


class TrackingTests(unittest.TestCase):
    def test_sessions_have_independent_tracker_state_and_cleanup(self):
        pipelines=[]
        states=[]
        def factory():
            pipeline=Mock()
            def process(frame,state):
                states.append(state)
                state.recognized_track_ids.add(len(states))
                return frame,[]
            pipeline.process_tracked_frame.side_effect=process
            pipelines.append(pipeline)
            return pipeline
        def capture_factory():
            capture=Mock()
            capture.isOpened.return_value=True
            capture.get.side_effect=lambda prop: 1000 if prop == cv2.CAP_PROP_FPS else 1
            capture.read.side_effect=[(True,np.zeros((20,20,3),dtype=np.uint8)),(False,None)]
            return capture
        manager=TrackingSessions(factory,RLock())
        try:
            with tempfile.TemporaryDirectory() as directory, patch('recognition_service.tracking.sessions.cv2.VideoCapture',side_effect=capture_factory):
                paths=[Path(directory)/f'{i}.mp4' for i in range(2)]
                for path in paths: path.write_bytes(b'test')
                sessions=[manager.create(path,path) for path in paths]
                for session in sessions: manager.start(session.session_id)
                for session in sessions: session.worker.join(5)
                self.assertEqual(len(pipelines),2)
                self.assertIsNot(pipelines[0],pipelines[1])
                self.assertIsNot(states[0],states[1])
                self.assertTrue(all(s.status=='completed' for s in sessions))
                self.assertFalse(any(p.exists() for p in paths))
                from fastapi import HTTPException
                with self.assertRaises(HTTPException) as error: manager.create('third')
                self.assertEqual(error.exception.status_code,429)
                for session in sessions: manager.delete(session.session_id)
                self.assertFalse(manager.sessions)
        finally: manager.close()

    def test_buffer_gap_is_reported_instead_of_silent_loss(self):
        manager=TrackingSessions(Mock(),RLock())
        try:
            session=manager.create('unused')
            session.status='completed'
            session.sequence=10
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as error:
                manager.events_after(session.session_id,0)
            self.assertEqual(error.exception.status_code,409)
        finally: manager.close()
