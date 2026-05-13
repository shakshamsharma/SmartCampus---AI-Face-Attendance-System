"""
Production-Grade Real-Time Face Recognition Engine
Fixes all critical issues with face tracking, recognition, and state management
"""
import cv2
import numpy as np
import base64
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from collections import defaultdict, deque
from dataclasses import dataclass, field
import time

logger = logging.getLogger(__name__)

# Configuration
FACE_DATA_DIR = Path("face_data")
FACE_DATA_DIR.mkdir(exist_ok=True)
UNKNOWN_FACES_DIR = FACE_DATA_DIR / "unknown_faces"
UNKNOWN_FACES_DIR.mkdir(exist_ok=True)

# Face detection
CASCADE_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
face_cascade = cv2.CascadeClassifier(CASCADE_PATH)

# Recognition thresholds
RECOGNITION_THRESHOLD = 60  # LBPH distance threshold
MIN_CONFIDENCE_SCORE = 45   # Minimum match score percentage
UNKNOWN_THRESHOLD = 75      # Distance above this = unknown

# Temporal consistency settings
MIN_FRAMES_FOR_CONFIRMATION = 8  # Frames needed to confirm recognition
CONFIDENCE_SMOOTHING_WINDOW = 10  # Frames for rolling average
FACE_LOST_TIMEOUT = 2.0  # Seconds before removing lost face
MAX_FACE_DISTANCE_MOVEMENT = 100  # Max pixel movement between frames

# Face tracking
NEXT_TRACKING_ID = 1


@dataclass
class FaceTrack:
    """Represents a tracked face across frames"""
    tracking_id: int
    reg_no: Optional[str] = None
    name: Optional[str] = None
    
    # Position tracking
    last_position: Tuple[int, int, int, int] = (0, 0, 0, 0)  # (x, y, w, h)
    centroid: Tuple[int, int] = (0, 0)
    
    # Recognition tracking
    recognition_history: deque = field(default_factory=lambda: deque(maxlen=CONFIDENCE_SMOOTHING_WINDOW))
    confidence_scores: deque = field(default_factory=lambda: deque(maxlen=CONFIDENCE_SMOOTHING_WINDOW))
    
    # State management
    state: str = "DETECTING"  # DETECTING, VERIFYING, CONFIRMED, UNKNOWN, LOST
    frames_detected: int = 0
    frames_since_seen: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    confirmed_at: Optional[float] = None
    
    # Recognition stability
    stable_recognition: Optional[str] = None
    recognition_changes: int = 0
    
    def update_position(self, x: int, y: int, w: int, h: int):
        """Update face position and centroid"""
        self.last_position = (x, y, w, h)
        self.centroid = (x + w // 2, y + h // 2)
        self.last_seen = time.time()
        self.frames_since_seen = 0
        self.frames_detected += 1
    
    def add_recognition(self, reg_no: Optional[str], confidence: float):
        """Add recognition result to history"""
        self.recognition_history.append(reg_no)
        self.confidence_scores.append(confidence)
        
        # Check for recognition stability
        if len(self.recognition_history) >= 3:
            recent = list(self.recognition_history)[-3:]
            if len(set(recent)) == 1 and recent[0] is not None:
                # Stable recognition
                if self.stable_recognition != recent[0]:
                    self.recognition_changes += 1
                    self.stable_recognition = recent[0]
            elif None in recent:
                self.stable_recognition = None
    
    def get_avg_confidence(self) -> float:
        """Get rolling average confidence"""
        if not self.confidence_scores:
            return 0.0
        return sum(self.confidence_scores) / len(self.confidence_scores)
    
    def is_confirmed(self) -> bool:
        """Check if recognition is confirmed"""
        return (
            self.state == "CONFIRMED" and
            self.frames_detected >= MIN_FRAMES_FOR_CONFIRMATION and
            self.stable_recognition is not None and
            self.get_avg_confidence() >= MIN_CONFIDENCE_SCORE
        )
    
    def should_confirm(self) -> bool:
        """Check if face should be confirmed"""
        if self.frames_detected < MIN_FRAMES_FOR_CONFIRMATION:
            return False
        
        if not self.stable_recognition:
            return False
        
        avg_conf = self.get_avg_confidence()
        if avg_conf < MIN_CONFIDENCE_SCORE:
            return False
        
        # Check consistency
        if len(self.recognition_history) >= MIN_FRAMES_FOR_CONFIRMATION:
            recent = list(self.recognition_history)[-MIN_FRAMES_FOR_CONFIRMATION:]
            same_count = sum(1 for r in recent if r == self.stable_recognition)
            consistency = same_count / len(recent)
            return consistency >= 0.75  # 75% consistency required
        
        return False
    
    def is_lost(self) -> bool:
        """Check if face tracking is lost"""
        time_since_seen = time.time() - self.last_seen
        return time_since_seen > FACE_LOST_TIMEOUT
    
    def distance_to(self, x: int, y: int, w: int, h: int) -> float:
        """Calculate distance to another face position"""
        other_centroid = (x + w // 2, y + h // 2)
        dx = self.centroid[0] - other_centroid[0]
        dy = self.centroid[1] - other_centroid[1]
        return np.sqrt(dx * dx + dy * dy)


class RealtimeFaceRecognitionEngine:
    """Production-grade real-time face recognition with proper tracking"""
    
    def __init__(self):
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=2, neighbors=8, grid_x=8, grid_y=8, threshold=100
        )
        self.label_map = {}  # label_int -> reg_no
        self.student_names = {}  # reg_no -> name
        
        # Active face tracking
        self.active_tracks: Dict[int, FaceTrack] = {}
        self.next_tracking_id = 1
        
        # Session state
        self.session_start = None
        self.confirmed_students = set()  # reg_nos confirmed present
        
        # Load model
        self._load_model()
        
        logger.info("Real-time face recognition engine initialized")
    
    def _load_model(self):
        """Load trained model and label map"""
        model_file = FACE_DATA_DIR / "face_model.pkl"
        label_map_file = FACE_DATA_DIR / "label_map.json"
        model_yml = FACE_DATA_DIR / "lbph_model.yml"
        
        if label_map_file.exists():
            try:
                with open(label_map_file, 'r') as f:
                    raw = json.load(f)
                    self.label_map = {int(k): v for k, v in raw.items()}
                logger.info(f"Loaded label map with {len(self.label_map)} students")
            except Exception as e:
                logger.error(f"Failed to load label map: {e}")
        
        if model_yml.exists() and self.label_map:
            try:
                self.recognizer.read(str(model_yml))
                logger.info("Loaded LBPH face model")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
    
    def start_session(self, student_names: Dict[str, str]):
        """Start a new recognition session"""
        self.session_start = time.time()
        self.student_names = student_names
        self.active_tracks.clear()
        self.confirmed_students.clear()
        self.next_tracking_id = 1
        logger.info(f"Started new session with {len(student_names)} students")
    
    def process_frame(self, frame_b64: str) -> Dict:
        """
        Process a single frame with real-time tracking
        Returns current recognition state
        """
        # Decode frame
        img = self._base64_to_image(frame_b64)
        if img is None:
            return self._empty_result()
        
        # Detect faces
        detected_faces = self._detect_faces(img)
        
        if not detected_faces:
            # No faces detected - update tracking
            self._update_lost_tracks()
            return self._build_result()
        
        # Match detected faces to existing tracks
        matched_tracks, unmatched_detections = self._match_faces_to_tracks(detected_faces)
        
        # Update matched tracks
        for track_id, (face_gray, x, y, w, h) in matched_tracks.items():
            track = self.active_tracks[track_id]
            track.update_position(x, y, w, h)
            
            # Recognize face
            reg_no, confidence = self._recognize_face(face_gray)
            track.add_recognition(reg_no, confidence)
            
            # Update state
            self._update_track_state(track)
        
        # Create new tracks for unmatched detections
        for face_gray, x, y, w, h in unmatched_detections:
            track = self._create_new_track(face_gray, x, y, w, h)
            self.active_tracks[track.tracking_id] = track
        
        # Remove lost tracks
        self._remove_lost_tracks()
        
        # Build and return result
        return self._build_result()
    
    def _detect_faces(self, img: np.ndarray) -> List[Tuple]:
        """Detect all faces in frame"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(40, 40),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        results = []
        for (x, y, w, h) in faces:
            face_roi = gray[y:y+h, x:x+w]
            face_resized = cv2.resize(face_roi, (150, 150))
            results.append((face_resized, int(x), int(y), int(w), int(h)))
        
        return results
    
    def _match_faces_to_tracks(self, detected_faces: List[Tuple]) -> Tuple[Dict, List]:
        """
        Match detected faces to existing tracks using position
        Returns: (matched_tracks, unmatched_detections)
        """
        matched = {}
        unmatched = []
        used_detections = set()
        
        # Try to match each active track
        for track_id, track in list(self.active_tracks.items()):
            if track.is_lost():
                continue
            
            best_match_idx = None
            best_distance = float('inf')
            
            # Find closest detection
            for idx, (_, x, y, w, h) in enumerate(detected_faces):
                if idx in used_detections:
                    continue
                
                distance = track.distance_to(x, y, w, h)
                
                if distance < MAX_FACE_DISTANCE_MOVEMENT and distance < best_distance:
                    best_distance = distance
                    best_match_idx = idx
            
            if best_match_idx is not None:
                matched[track_id] = detected_faces[best_match_idx]
                used_detections.add(best_match_idx)
            else:
                # Track not matched - increment lost counter
                track.frames_since_seen += 1
        
        # Unmatched detections become new tracks
        for idx, detection in enumerate(detected_faces):
            if idx not in used_detections:
                unmatched.append(detection)
        
        return matched, unmatched
    
    def _create_new_track(self, face_gray: np.ndarray, x: int, y: int, w: int, h: int) -> FaceTrack:
        """Create a new face track"""
        track = FaceTrack(tracking_id=self.next_tracking_id)
        self.next_tracking_id += 1
        
        track.update_position(x, y, w, h)
        
        # Initial recognition
        reg_no, confidence = self._recognize_face(face_gray)
        track.add_recognition(reg_no, confidence)
        
        logger.info(f"Created new track {track.tracking_id} at ({x},{y})")
        
        return track
    
    def _recognize_face(self, face_gray: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Recognize a face and return (reg_no, confidence_score)
        Returns (None, 0) for unknown faces
        """
        if not self.label_map:
            return None, 0.0
        
        try:
            label, distance = self.recognizer.predict(face_gray)
            
            # Convert LBPH distance to confidence score (0-100)
            confidence_score = max(0, 100 - distance)
            
            # Get student ID
            reg_no = self.label_map.get(label)
            
            # Validate recognition
            if distance > RECOGNITION_THRESHOLD:
                # Too far - unknown
                return None, confidence_score
            
            if confidence_score < MIN_CONFIDENCE_SCORE:
                # Too low confidence
                return None, confidence_score
            
            if reg_no and reg_no in self.student_names:
                return reg_no, confidence_score
            
            return None, confidence_score
            
        except Exception as e:
            logger.error(f"Recognition error: {e}")
            return None, 0.0
    
    def _update_track_state(self, track: FaceTrack):
        """Update track state based on recognition history"""
        if track.state == "CONFIRMED":
            # Already confirmed - just verify still present
            if track.is_lost():
                track.state = "LOST"
                logger.info(f"Track {track.tracking_id} ({track.reg_no}) lost")
            return
        
        # Check if should confirm
        if track.should_confirm():
            track.state = "CONFIRMED"
            track.confirmed_at = time.time()
            track.reg_no = track.stable_recognition
            track.name = self.student_names.get(track.reg_no, track.reg_no)
            
            # Add to confirmed students
            if track.reg_no:
                self.confirmed_students.add(track.reg_no)
            
            logger.info(f"Track {track.tracking_id} CONFIRMED as {track.reg_no} "
                       f"(avg conf: {track.get_avg_confidence():.1f}%)")
        
        elif track.frames_detected >= MIN_FRAMES_FOR_CONFIRMATION:
            # Enough frames but not confirmed - check why
            if track.stable_recognition is None:
                track.state = "UNKNOWN"
            elif track.get_avg_confidence() < MIN_CONFIDENCE_SCORE:
                track.state = "LOW_CONFIDENCE"
            else:
                track.state = "VERIFYING"
        else:
            track.state = "DETECTING"
    
    def _update_lost_tracks(self):
        """Update all tracks when no faces detected"""
        for track in self.active_tracks.values():
            track.frames_since_seen += 1
    
    def _remove_lost_tracks(self):
        """Remove tracks that are lost"""
        to_remove = []
        
        for track_id, track in self.active_tracks.items():
            if track.is_lost():
                # Only remove if not confirmed, or confirmed but lost for too long
                if track.state != "CONFIRMED" or track.frames_since_seen > 30:
                    to_remove.append(track_id)
                    logger.info(f"Removing lost track {track_id} (state: {track.state})")
        
        for track_id in to_remove:
            del self.active_tracks[track_id]
    
    def _build_result(self) -> Dict:
        """Build current recognition state result"""
        # Categorize tracks
        confirmed = []
        verifying = []
        unknown = []
        
        for track in self.active_tracks.values():
            if track.is_lost():
                continue
            
            track_info = {
                "tracking_id": track.tracking_id,
                "position": track.last_position,
                "centroid": track.centroid,
                "state": track.state,
                "frames_detected": track.frames_detected,
                "avg_confidence": round(track.get_avg_confidence(), 1),
                "time_tracked": round(time.time() - track.first_seen, 1)
            }
            
            if track.state == "CONFIRMED" and track.reg_no:
                track_info.update({
                    "reg_no": track.reg_no,
                    "name": track.name,
                    "confirmed_at": track.confirmed_at
                })
                confirmed.append(track_info)
            
            elif track.state in ("VERIFYING", "LOW_CONFIDENCE"):
                if track.stable_recognition:
                    track_info.update({
                        "reg_no": track.stable_recognition,
                        "name": self.student_names.get(track.stable_recognition, "Unknown")
                    })
                verifying.append(track_info)
            
            else:  # DETECTING, UNKNOWN
                unknown.append(track_info)
        
        # Get all students and their status
        all_students = []
        for reg_no, name in self.student_names.items():
            if reg_no in self.confirmed_students:
                # Find the track
                track = next((t for t in self.active_tracks.values() 
                            if t.reg_no == reg_no and t.state == "CONFIRMED"), None)
                
                if track and not track.is_lost():
                    status = "PRESENT"
                    confidence = track.get_avg_confidence()
                else:
                    # Was confirmed but now lost - still mark present
                    status = "PRESENT"
                    confidence = 0
            else:
                status = "ABSENT"
                confidence = 0
            
            all_students.append({
                "reg_no": reg_no,
                "name": name,
                "status": status,
                "confidence": round(confidence, 1)
            })
        
        return {
            "timestamp": datetime.now().isoformat(),
            "active_tracks": len(self.active_tracks),
            "confirmed": confirmed,
            "verifying": verifying,
            "unknown": unknown,
            "all_students": all_students,
            "confirmed_count": len(self.confirmed_students),
            "session_duration": round(time.time() - self.session_start, 1) if self.session_start else 0
        }
    
    def _empty_result(self) -> Dict:
        """Return empty result"""
        return {
            "timestamp": datetime.now().isoformat(),
            "active_tracks": 0,
            "confirmed": [],
            "verifying": [],
            "unknown": [],
            "all_students": [],
            "confirmed_count": 0,
            "session_duration": 0
        }
    
    def _base64_to_image(self, b64_str: str) -> Optional[np.ndarray]:
        """Convert base64 to OpenCV image"""
        try:
            if ',' in b64_str:
                b64_str = b64_str.split(',')[1]
            
            img_bytes = base64.b64decode(b64_str)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            return img
        except Exception as e:
            logger.error(f"Base64 decode error: {e}")
            return None
    
    def get_final_attendance(self) -> Dict:
        """Get final attendance summary for session end"""
        present = []
        absent = []
        
        for reg_no, name in self.student_names.items():
            if reg_no in self.confirmed_students:
                # Find best confidence from tracks
                best_conf = 0
                for track in self.active_tracks.values():
                    if track.reg_no == reg_no and track.state == "CONFIRMED":
                        best_conf = max(best_conf, track.get_avg_confidence())
                
                present.append({
                    "reg_no": reg_no,
                    "name": name,
                    "confidence": round(best_conf, 1),
                    "status": "present"
                })
            else:
                absent.append({
                    "reg_no": reg_no,
                    "name": name,
                    "reason": "not_detected",
                    "status": "absent"
                })
        
        return {
            "detected": present,
            "not_detected": absent,
            "total_confirmed": len(present),
            "total_absent": len(absent),
            "session_duration": round(time.time() - self.session_start, 1) if self.session_start else 0
        }


# Global engine instance
_engine = None

def get_engine() -> RealtimeFaceRecognitionEngine:
    """Get or create global engine instance"""
    global _engine
    if _engine is None:
        _engine = RealtimeFaceRecognitionEngine()
    return _engine
