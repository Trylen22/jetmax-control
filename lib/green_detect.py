"""Green/cyan block detection + overlay drawing (shared with belt_vision tuning)."""
import cv2
import numpy as np

# Green through cyan/teal (OpenCV H 0-179).
# Saturation floor kept high enough to reject grey/white camera noise speckles.
GREEN_LOWER = np.array([35, 55, 55])
GREEN_UPPER = np.array([110, 255, 255])
MIN_AREA = 600
MM_PER_PIXEL = 0.25
AXIS_FLIP_X = 1
AXIS_FLIP_Y = 1

# Morphology kernel — kills single-pixel / speck noise better than default 3x3 None
_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


def _clean_mask(mask):
    """Open then close to drop speckles and fill small holes in the block."""
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _KERNEL, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _KERNEL, iterations=1)
    return mask


def detect_green(frame_rgb):
    """
    Find the largest green/cyan blob in an RGB frame.

    Returns a dict with pixel/mm info, or None if nothing found.
    The returned mask is clipped to the chosen contour only (no speckles).
    """
    hsv = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, GREEN_LOWER, GREEN_UPPER)
    mask = _clean_mask(mask)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < MIN_AREA:
        return None

    x, y, w, h = cv2.boundingRect(largest)
    M = cv2.moments(largest)
    if M["m00"] == 0:
        return None
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])

    # Overlay / diagnostics: only the accepted blob, not residual noise
    blob_mask = np.zeros_like(mask)
    cv2.drawContours(blob_mask, [largest], -1, 255, thickness=-1)

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
        "mask": blob_mask,
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

        # Tint only the accepted blob (not raw noisy mask)
        tint = out.copy()
        tint[detection["mask"] > 0] = (0, 180, 0)
        cv2.addWeighted(tint, 0.22, out, 0.78, 0, out)

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
