"""
SmartCampus AI - Face Recognition Engine V2
Completely rebuilt for reliability and accuracy
Uses OpenCV LBPH with aggressive detection and recognition
"""
import cv2
import numpy as np
import base64
import json
import pickle
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directories
FACE_DATA_DIR = Path("face_data")
FACE_DATA_DIR.mkdir(exist_ok=True)
UNKNOWN_FACES_DIR = FACE_DATA_DIR / "unknown_faces"
UNKNOWN_FACES_DIR.mkdir(exist_ok=True)

# Files
MODEL_FILE = FACE_DATA_DIR / "face_model_v2.pkl"
LABEL_MAP_FILE = FACE_DATA_DIR / "label_map_v2.json"
LBPH_MODEL_FILE = FACE_DATA_DIR / "lbph_model_v2.yml"

# Face detection
CASCADE_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
face_cascade = cv2.CascadeClassifier(CASCADE_PATH)

# LBPH recognizer - VERY LENIENT SETTINGS
recognizer = cv2.face.LBPHFaceRecognizer_create(
    radius=1,
    neighbors=8,
    grid_x=8,
    grid_y=8,
    threshold=150  # Very high threshold = accept more matches
)

# Global state
label_map = {}  # int -> reg_no
student_names = {}  # reg_no -> name

# VERY LENIENT THRESHOLDS - Will detect faces more easily
LBPH_DISTANCE_THRESHOLD = 100  # Accept distances up to 100 (very lenient)
MIN_MATCH_SCORE = 20  # Only need 20% match (very lenient)
MIN_DETECTION_RATE = 0.10  # Only need 10% of frames (very lenient)

logger.info("="*70)
logger.info("FACE RECOGNITION ENGINE V2 - INITIALIZED")
logger.info(f"LBPH Distance Threshold: {LBPH_DISTANCE_THRESHOLD} (VERY LENIENT)")
logger.info(f"Min Match Score: {MIN_MATCH_SCORE}% (VERY LENIENT)")
logger.info(f"Min Detection Rate: {MIN_DETECTION_RATE*100}% (VERY LENIENT)")
logger.info("="*70)


def base64_to_image(b64_str: str) -> Optional[np.ndarray]:
    """Convert base64 to OpenCV image"""
    try:
        if ',' in b64_str:
            b64_str = b64_str.split(',')[1]
        
        img_bytes = base64.b64decode(b64_str)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            logger.error("❌ Failed to decode image")
            return None
        
        return img
    except Exception as e:
        logger.error(f"❌ Base64 decode error: {e}")
        return None


def detect_faces_aggressive(img: np.ndarray) -> List[Tuple]:
    """
    AGGRESSIVE face detection - finds faces even in poor conditions
    Returns: [(face_gray, x, y, w, h), ...]
    """
    if img is None:
        return []
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Try multiple detection strategies
    all_faces = []
    
    # Strategy 1: Standard detection
    faces1 = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=3,
        minSize=(30, 30)
    )
    all_faces.extend(faces1)
    
    # Strategy 2: With histogram equalization
    gray_eq = cv2.equalizeHist(gray)
    faces2 = face_cascade.detectMultiScale(
        gray_eq,
        scaleFactor=1.05,
        minNeighbors=2,
        minSize=(25, 25)
    )
    all_faces.extend(faces2)
    
    # Strategy 3: Very aggressive (low neighbors)
    faces3 = face_cascade.detectMultiScale(
        gray_eq,
        scaleFactor=1.03,
        minNeighbors=1,
        minSize=(20, 20)
    )
    all_faces.extend(faces3)
    
    # Remove duplicates (faces detected multiple times)
    unique_faces = []
    for (x, y, w, h) in all_faces:
        is_duplicate = False
        for (x2, y2, w2, h2) in unique_faces:
            # Check if faces overlap significantly
            overlap_x = max(0, min(x+w, x2+w2) - max(x, x2))
            overlap_y = max(0, min(y+h, y2+h2) - max(y, y2))
            overlap_area = overlap_x * overlap_y
            area1 = w * h
            area2 = w2 * h2
            
            if overlap_area > 0.5 * min(area1, area2):
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_faces.append((x, y, w, h))
    
    logger.info(f"🔍 DETECTION: Found {len(unique_faces)} unique face(s) using aggressive detection")
    
    # Extract face regions
    results = []
    for idx, (x, y, w, h) in enumerate(unique_faces):
        face_roi = gray_eq[y:y+h, x:x+w]
        face_resized = cv2.resize(face_roi, (150, 150))
        results.append((face_resized, int(x), int(y), int(w), int(h)))
        logger.info(f"   Face {idx+1}: position=({x},{y}), size=({w}x{h})")
    
    return results


def register_face(reg_no: str, images_b64: List[str]) -> Dict:
    """
    Register student face from multiple images
    SIMPLIFIED - Just needs to work!
    """
    global recognizer, label_map
    
    logger.info("="*70)
    logger.info(f"📝 REGISTERING: {reg_no}")
    logger.info("="*70)
    
    # Collect face samples
    face_samples = []
    
    for idx, b64 in enumerate(images_b64):
        img = base64_to_image(b64)
        if img is None:
            logger.warning(f"⚠️  Image {idx+1}: Failed to decode")
            continue
        
        faces = detect_faces_aggressive(img)
        if not faces:
            logger.warning(f"⚠️  Image {idx+1}: No face detected")
            continue
        
        # Take first face
        face_gray, x, y, w, h = faces[0]
        face_samples.append(face_gray)
        logger.info(f"✅ Image {idx+1}: Face captured")
    
    if len(face_samples) < 2:
        error_msg = f"Only {len(face_samples)} valid faces detected. Need at least 2."
        logger.error(f"❌ REGISTRATION FAILED: {error_msg}")
        return {"success": False, "error": error_msg}
    
    # Load existing data
    existing_faces, existing_labels = _load_training_data()
    
    # Assign label
    if reg_no not in label_map.values():
        new_label = max(label_map.keys(), default=-1) + 1
        label_map[new_label] = reg_no
    else:
        # Re-registration - remove old samples
        new_label = [k for k, v in label_map.items() if v == reg_no][0]
        if existing_faces:
            keep_idx = [i for i, l in enumerate(existing_labels) if l != new_label]
            existing_faces = [existing_faces[i] for i in keep_idx]
            existing_labels = [existing_labels[i] for i in keep_idx]
    
    # Add new samples
    new_labels = [new_label] * len(face_samples)
    all_faces = existing_faces + face_samples
    all_labels = existing_labels + new_labels
    
    # Train model
    if len(all_faces) >= 2:
        recognizer.train(all_faces, np.array(all_labels))
        _save_model(all_faces, all_labels)
        _save_label_map()
        
        logger.info("="*70)
        logger.info(f"✅ REGISTRATION SUCCESS: {reg_no}")
        logger.info(f"   Samples: {len(face_samples)}")
        logger.info(f"   Total students: {len(label_map)}")
        logger.info("="*70)
        
        return {
            "success": True,
            "samples_captured": len(face_samples),
            "reg_no": reg_no,
            "total_students_trained": len(label_map)
        }
    else:
        logger.error("❌ REGISTRATION FAILED: Not enough samples")
        return {"success": False, "error": "Not enough samples"}


def recognize_faces_multi_frame(frames_b64: List[str], session_id: Optional[int] = None) -> Dict:
    """
    Process multiple frames and recognize faces
    SIMPLIFIED - Focus on making it work!
    """
    global label_map
    
    _load_model()
    
    if not label_map:
        logger.error("❌ No registered faces in database")
        return {
            "detected": [],
            "low_confidence": [],
            "not_detected": list(label_map.values()) if label_map else [],
            "unknown_faces": []
        }
    
    logger.info("="*70)
    logger.info(f"🎥 SCANNING: Processing {len(frames_b64)} frames")
    logger.info("="*70)
    
    # Track detections per student
    student_detections = {}  # reg_no -> [confidences]
    
    # Process each frame
    for frame_idx, b64_frame in enumerate(frames_b64):
        img = base64_to_image(b64_frame)
        if img is None:
            continue
        
        # Detect faces
        faces = detect_faces_aggressive(img)
        
        if not faces:
            logger.info(f"   Frame {frame_idx+1}/{len(frames_b64)}: No faces detected")
            continue
        
        logger.info(f"   Frame {frame_idx+1}/{len(frames_b64)}: {len(faces)} face(s) detected")
        
        # Recognize each face
        for face_idx, (face_gray, x, y, w, h) in enumerate(faces):
            try:
                label, distance = recognizer.predict(face_gray)
                
                # Convert distance to match score
                match_score = max(0, 100 - distance)
                
                reg_no = label_map.get(label)
                
                logger.info(f"      Face {face_idx+1}: Label={label}, Reg={reg_no}, "
                          f"Distance={distance:.1f}, Score={match_score:.1f}%")
                
                # VERY LENIENT - Accept almost anything
                if reg_no and distance <= LBPH_DISTANCE_THRESHOLD:
                    if reg_no not in student_detections:
                        student_detections[reg_no] = []
                    student_detections[reg_no].append(match_score)
                    logger.info(f"         ✅ MATCHED: {reg_no}")
                else:
                    logger.info(f"         ❌ NO MATCH (distance too high)")
            
            except Exception as e:
                logger.error(f"      ❌ Recognition error: {e}")
    
    # Determine final status
    all_registered = set(label_map.values())
    detected = []
    low_confidence = []
    not_detected = []
    
    logger.info("\n" + "="*70)
    logger.info("📊 FINAL RESULTS:")
    logger.info("="*70)
    
    for reg_no in all_registered:
        detections = student_detections.get(reg_no, [])
        
        if not detections:
            not_detected.append({"reg_no": reg_no})
            logger.info(f"❌ {reg_no}: ABSENT (not detected in any frame)")
            continue
        
        avg_score = sum(detections) / len(detections)
        max_score = max(detections)
        detection_rate = len(detections) / len(frames_b64)
        
        logger.info(f"📈 {reg_no}: Detected in {len(detections)}/{len(frames_b64)} frames "
                   f"(rate: {detection_rate*100:.1f}%, avg score: {avg_score:.1f}%)")
        
        # VERY LENIENT CRITERIA
        if avg_score >= MIN_MATCH_SCORE and detection_rate >= MIN_DETECTION_RATE:
            detected.append({
                "reg_no": reg_no,
                "confidence": round(max_score, 1),
                "avg_confidence": round(avg_score, 1),
                "detections": len(detections),
                "detection_rate": round(detection_rate * 100, 1)
            })
            logger.info(f"   ✅ PRESENT (avg: {avg_score:.1f}%, rate: {detection_rate*100:.1f}%)")
        elif avg_score >= 15 and detection_rate >= 0.05:
            low_confidence.append({
                "reg_no": reg_no,
                "confidence": round(max_score, 1),
                "avg_confidence": round(avg_score, 1),
                "detections": len(detections),
                "detection_rate": round(detection_rate * 100, 1)
            })
            logger.info(f"   ⚠️  NEEDS VERIFICATION (avg: {avg_score:.1f}%, rate: {detection_rate*100:.1f}%)")
        else:
            not_detected.append({"reg_no": reg_no})
            logger.info(f"   ❌ ABSENT (score/rate too low)")
    
    logger.info("="*70)
    logger.info(f"✅ PRESENT: {len(detected)}")
    logger.info(f"⚠️  VERIFY: {len(low_confidence)}")
    logger.info(f"❌ ABSENT: {len(not_detected)}")
    logger.info("="*70)
    
    return {
        "detected": detected,
        "low_confidence": low_confidence,
        "not_detected": not_detected,
        "unknown_faces": [],
        "frames_processed": len(frames_b64)
    }


def recognize_faces_in_frame(b64_image: str, session_id: Optional[int] = None) -> Dict:
    """Recognize faces in a single frame"""
    _load_model()
    
    if not label_map:
        return {"recognized": [], "unknown": [], "total_faces": 0}
    
    img = base64_to_image(b64_image)
    if img is None:
        return {"recognized": [], "unknown": [], "total_faces": 0}
    
    faces = detect_faces_aggressive(img)
    
    if not faces:
        return {"recognized": [], "unknown": [], "total_faces": 0}
    
    recognized = []
    
    for face_gray, x, y, w, h in faces:
        try:
            label, distance = recognizer.predict(face_gray)
            match_score = max(0, 100 - distance)
            reg_no = label_map.get(label)
            
            if reg_no and distance <= LBPH_DISTANCE_THRESHOLD:
                recognized.append({
                    "reg_no": reg_no,
                    "confidence": round(match_score, 1),
                    "distance": round(float(distance), 2),
                    "face_location": {"top": int(y), "right": int(x+w), "bottom": int(y+h), "left": int(x)}
                })
        except:
            pass
    
    return {
        "recognized": recognized,
        "unknown": [],
        "total_faces": len(faces)
    }


def delete_face(reg_no: str) -> bool:
    """Delete a student's face data"""
    global label_map, recognizer
    
    _load_model()
    
    label_to_remove = None
    for label, rn in label_map.items():
        if rn == reg_no:
            label_to_remove = label
            break
    
    if label_to_remove is None:
        return False
    
    del label_map[label_to_remove]
    
    # Retrain without this student
    faces, labels = _load_training_data()
    keep_idx = [i for i, l in enumerate(labels) if l != label_to_remove]
    faces = [faces[i] for i in keep_idx]
    labels = [labels[i] for i in keep_idx]
    
    if faces:
        recognizer.train(faces, np.array(labels))
        _save_model(faces, labels)
    
    _save_label_map()
    
    logger.info(f"✅ Deleted face data for {reg_no}")
    return True


def check_face_registered(reg_no: str) -> bool:
    """Check if student has registered face"""
    _load_label_map()
    return reg_no in label_map.values()


def get_registration_stats() -> Dict:
    """Get registration statistics"""
    _load_label_map()
    return {
        "total_registered": len(label_map),
        "registered_students": list(label_map.values()),
        "embeddings_file_exists": LBPH_MODEL_FILE.exists(),
        "embedding_dimensions": "LBPH",
        "recognition_threshold": LBPH_DISTANCE_THRESHOLD
    }


def _save_model(faces, labels):
    """Save training data and model"""
    with open(MODEL_FILE, 'wb') as f:
        pickle.dump({"faces": faces, "labels": labels}, f)
    recognizer.save(str(LBPH_MODEL_FILE))
    logger.info(f"💾 Model saved with {len(set(labels))} students")


def _load_training_data():
    """Load training data"""
    if MODEL_FILE.exists():
        try:
            with open(MODEL_FILE, 'rb') as f:
                data = pickle.load(f)
                return data.get("faces", []), data.get("labels", [])
        except:
            pass
    return [], []


def _save_label_map():
    """Save label map"""
    with open(LABEL_MAP_FILE, 'w') as f:
        json.dump({str(k): v for k, v in label_map.items()}, f)


def _load_label_map():
    """Load label map"""
    global label_map
    if LABEL_MAP_FILE.exists():
        try:
            with open(LABEL_MAP_FILE, 'r') as f:
                raw = json.load(f)
                label_map = {int(k): v for k, v in raw.items()}
                logger.info(f"📂 Loaded {len(label_map)} registered students")
        except:
            label_map = {}


def _load_model():
    """Load model and label map"""
    global recognizer, label_map
    _load_label_map()
    if LBPH_MODEL_FILE.exists() and label_map:
        try:
            recognizer.read(str(LBPH_MODEL_FILE))
            logger.info(f"📂 Loaded face model")
        except:
            pass


# Initialize on import
_load_model()
