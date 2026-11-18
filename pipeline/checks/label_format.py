"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from pathlib import Path


def run(ds, cfg):
    issues = []
    settings = cfg["label_format"]
    image_stems = {p.stem for p in ds.image_files()}
    previous = {}
    for path in ds.label_files():
        stem = path.stem
        for line_no, text in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not text.strip():
                continue
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError as exc:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, f"dòng nhãn không hợp lệ: {exc}", line_no))
                continue
            if not 0 <= cls < len(ds.classes):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {cls} ngoài phạm vi", line_no))
                continue
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, "chiều rộng hoặc cao không dương", line_no))
                continue

            edges = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            overflow = max(0.0, -edges[0], -edges[1], edges[2] - 1, edges[3] - 1)
            if overflow > settings["overflow_tol"]:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    f"box tràn ảnh {overflow:.6g}", line_no, {"overflow": overflow}))
            box = (cx, cy, w, h)
            if any(prev_cls == cls and iou_xywh(box, prev_box) > settings["dup_box_iou"]
                   for prev_cls, prev_box in previous.get(stem, [])):
                issues.append(Issue("label_format", ERROR, "DUP_BOX", stem, "box trùng với dòng trước cùng lớp", line_no))
            previous.setdefault(stem, []).append((cls, box))

            if stem in image_stems:
                size = ds.image_size(stem)
                if size:
                    width_px, height_px = size
                    if min(w * width_px, h * height_px) < settings["min_box_px"]:
                        issues.append(Issue("label_format", WARN, "BOX_TINY", stem, "cạnh ngắn của box nhỏ hơn ngưỡng px", line_no))
            if w * h > settings["max_box_frac"]:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem, "box chiếm diện tích quá lớn", line_no))
    return issues
