"""Green block detection + overlay drawing (shared with belt_vision tuning)."""
import cv2
import numpy as np

# Match belt_vision.py defaults
# Green through cyan/teal (OpenCV H 0-179). Widened so light cyan blocks register.
GREEN_LOWER = np.array([35, 40, 50])
GREEN_UPPER = np.array([110, 255, 255])
MIN_AREA = 500
MM_PER_PIXEL = 0.25
AXIS_FLIP_X = 1
AXIS_FLIP_Y = 1


def detect_green(frame_rgb):
    """
    Find the largest green blob in an RGB frame.

    Returns a dict with pixel/mm info, or None if nothing found.
    """
    hsv = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, GREEN_LOWER, GREEN_UPPER)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < MIN_AREA:
        return None

    x, y, w, h = cv2.boundingRect(largest)
    M = cv2.moments(largest)
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])

    img_h, img_w = frame_rgb.shape[:2]
    center_x, center_y = img_w // 2, img_h // 2
    dx_px = cx - center_x
    dy_px = cy - center_y
    arm_dx_mm = dy_px * MM_PER_PIXEL * AXIS_FLIP_X
    arm_dy_mm = dx_px * MM_PER_PIXEL * AXIS_FLIP_Y

    return {
        "detected": True,
        "cx": cx,
        "cy": cy,
        "bbox": (x, y, w, h),
        "area": int(area),
        "dx_px": dx_px,
        "dy_px": dy_px,
        "arm_dx_mm": round(arm_dx_mm, 1),
        "arm_dy_mm": round(arm_dy_mm, 1),
        "mask": mask,
    }


def annotate_frame(frame_rgb, detection=None):
    """Draw detection overlay. Returns BGR image ready for imencode."""
    out = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    img_h, img_w = out.shape[:2]
    cx0, cy0 = img_w // 2, img_h // 2

    # Faint center crosshair
    cv2.drawMarker(out, (cx0, cy0), (80, 80, 80), cv2.MARKER_CROSS, 24, 1)

    if detection:
        x, y, w, h = detection["bbox"]
        cx, cy = detection["cx"], detection["cy"]

        # Green mask tint where blob is
        tint = out.copy()
        tint[detection["mask"] > 0] = (0, 180, 0)
        cv2.addWeighted(tint, 0.25, out, 0.75, 0, out)

        # Bounding box + corners
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 120), 2)
        cv2.circle(out, (cx, cy), 8, (0, 255, 120), 2)
        cv2.line(out, (cx0, cy0), (cx, cy), (0, 255, 120), 2)

        label = "TARGET  dx={:.1f}mm dy={:.1f}mm  area={}".format(
            detection["arm_dx_mm"], detection["arm_dy_mm"], detection["area"]
        )
        cv2.rectangle(out, (8, 8), (min(img_w - 8, 8 + len(label) * 9 + 12), 36), (0, 40, 20), -1)
        cv2.putText(out, label, (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 120), 1, cv2.LINE_AA)
        cv2.putText(out, "DETECTED", (x, max(16, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 120), 2, cv2.LINE_AA)
    else:
        cv2.rectangle(out, (8, 8), (170, 36), (20, 20, 20), -1)
        cv2.putText(out, "SCANNING...", (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 80, 80), 1, cv2.LINE_AA)

    return out
