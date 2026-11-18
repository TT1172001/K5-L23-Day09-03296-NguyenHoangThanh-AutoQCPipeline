"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    fixes = []
    removed = set()
    line_issues = defaultdict(dict)
    remove_codes = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}

    for issue in issues:
        if issue.severity != ERROR:
            continue
        code, stem = issue.code, issue.image
        if code in remove_codes and stem not in removed:
            image_path = ds.image_path(stem)
            if image_path:
                image_path.unlink(missing_ok=True)
            ds.label_path(stem).unlink(missing_ok=True)
            removed.add(stem)
            fixes.append({"image": stem, "line": issue.line, "action": "remove_image", "before": stem, "after": ""})
        elif code == "MISSING_LABEL_FILE":
            fixes.append({"image": stem, "line": issue.line, "action": "needs_label", "before": "(không có file)", "after": "chuyển người gán"})
        elif code == "BAD_CLASS_NAME":
            path = ds.yaml_path
            data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
            data = data or {}
            data["names"] = {i: name for i, name in enumerate(cfg["classes"])}
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            ds.classes = list(cfg["classes"])
            fixes.append({"image": stem, "line": issue.line, "action": "rename_classes", "before": "names hiện tại", "after": ", ".join(cfg["classes"])})
        elif issue.line is not None and (code in drop_codes or code == "BOX_OUT_OF_IMAGE") and stem not in removed:
            line_issues[stem].setdefault(issue.line, set()).add(code)

    for stem, by_line in line_issues.items():
        path = ds.label_path(stem)
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8", errors="replace").splitlines()
        changed = []
        lines_to_drop = {line_no for line_no, codes in by_line.items() if codes & drop_codes}
        for line_no, codes in by_line.items():
            if line_no <= len(original):
                changed.append((line_no, codes, original[line_no - 1]))
        for line_no, codes, before in sorted(changed):
            if codes & drop_codes:
                fixes.append({"image": stem, "line": line_no, "action": "drop_line", "before": before, "after": ""})
            else:
                try:
                    cls, cx, cy, w, h = parse_yolo_line(before)
                except ValueError:
                    fixes.append({"image": stem, "line": line_no, "action": "drop_line", "before": before, "after": ""})
                    continue
                x1, y1 = max(0.0, cx - w / 2), max(0.0, cy - h / 2)
                x2, y2 = min(1.0, cx + w / 2), min(1.0, cy + h / 2)
                if x2 <= x1 or y2 <= y1:
                    fixes.append({"image": stem, "line": line_no, "action": "drop_line", "before": before, "after": ""})
                    lines_to_drop.add(line_no)
                else:
                    after = f"{cls} {((x1+x2)/2):.8g} {((y1+y2)/2):.8g} {(x2-x1):.8g} {(y2-y1):.8g}"
                    original[line_no - 1] = after
                    fixes.append({"image": stem, "line": line_no, "action": "clip_box", "before": before, "after": after})
        for line_no in sorted(lines_to_drop, reverse=True):
            if line_no <= len(original):
                original.pop(line_no - 1)
        path.write_text("\n".join(original) + ("\n" if original else ""), encoding="utf-8")
    return fixes
