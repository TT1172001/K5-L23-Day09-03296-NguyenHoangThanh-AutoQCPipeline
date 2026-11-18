# Báo cáo Day 09 — Nguyễn Hoàng Thành / 202603296

## 1. Kết luận trước

Pipeline nhận 224 ảnh, loại 22 ảnh tại intake và đưa 202 ảnh vào QC. Sau mô phỏng duyệt 80 ảnh, còn 0 lỗi bắt buộc nhưng 38/202 ảnh (18,8%) vẫn có cảnh báo chưa được xử lý; ngưỡng Hold là 10%. Kết luận là **Hold**, vì hàng đợi 125 ảnh vượt ngân sách duyệt 80 ảnh. `clean_v1` được xuất ở trạng thái bản nháp, chưa được phát hành.

## 2. Lỗi và phân việc

Số dưới đây lấy từ `02_error_list_v1.csv`; số ảnh/dòng là số dòng lỗi, trừ khi ghi rõ số ảnh duy nhất. Máy sửa bằng các thao tác trong `03_fixes.csv`: 20 lần `drop_line`, 8 lần `clip_box`, 2 lần `rename_classes`; 6 ảnh thiếu nhãn được đẩy cho người gán (`needs_label`), không tạo nhãn rỗng.

| Mã lỗi | Số ảnh/dòng | Ai xử lý | Cách xử lý |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh | Máy | Loại ảnh hỏng khỏi tập |
| `BAD_SIZE` | 3 ảnh | Máy | Loại ảnh nhỏ hơn guideline |
| `LEAK_TEST` | 5 ảnh | Máy | Loại ảnh rò rỉ sang test/val |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy | Giữ một bản, loại bản trùng |
| `DUP_IMAGE_NEAR` | 4 ảnh | Máy | Loại ảnh gần trùng theo pHash |
| `MISSING_LABEL_FILE` | 6 ảnh | Người | Máy không bịa nhãn; ưu tiên cao trong hàng đợi |
| `BAD_CLASS_NAME` | 2 dòng, 1 ảnh | Máy | Ghi lại danh sách tên lớp chuẩn |
| `BAD_FORMAT` | 3 dòng | Máy | Xóa dòng không parse được |
| `BAD_CLASS_ID` | 6 dòng | Máy | Xóa dòng có ID ngoài phạm vi |
| `BOX_ZERO` | 4 dòng | Máy | Xóa box có cạnh không dương |
| `DUP_BOX` | 7 dòng | Máy | Xóa box lặp cùng lớp |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy | Cắt box vào ảnh; xóa nếu phần giao rỗng |
| `EMPTY_LABEL` | 12 ảnh | Người | Xác minh ảnh nền hay nhãn bị thiếu |
| `BOX_TINY` | 6 dòng, 4 ảnh | Người | Cảnh báo kích thước, không tự sửa |
| `BOX_HUGE` | 3 dòng | Người | Cảnh báo box chiếm diện tích lớn |
| `CLASS_RARE` | 4 cảnh báo dataset | Người | Theo dõi mất cân bằng lớp |
| `POSSIBLE_FALSE_POS` | 25 dòng, 24 ảnh | Người | Model không thấy vật được gán nhãn |
| `POSSIBLE_LOOSE_BOX` | 28 cảnh báo, 24 ảnh | Người | Đối chiếu box nhãn với model |
| `POSSIBLE_MISSING` | 53 cảnh báo, 52 ảnh | Người | Model thấy vật chưa có box |
| `POSSIBLE_WRONG_CLASS` | 18 cảnh báo | Người | Xác minh khác biệt lớp |

Hàng đợi có 125 ảnh; các mã `POSSIBLE_*` xuất hiện ở 103 ảnh. Mô phỏng duyệt 80 ảnh, trong đó 74 ảnh có cảnh báo ngữ nghĩa và 6 ảnh thiếu file nhãn. `NEEDS_LABEL` có trọng số 10, `POSSIBLE_WRONG_CLASS` trọng số 3 và `POSSIBLE_MISSING`/`POSSIBLE_FALSE_POS` trọng số 2, nên ảnh thiếu nhãn và ảnh có nhiều cảnh báo được đưa lên trước; ví dụ `img_0020` có ưu tiên 11,524.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do |
|---|---:|---:|---|---|
| `duplicates.phash_dist` | 2 | 14 | near duplicate: 1,00/0,50 → 1,00/0,67 | Tại 14 bắt thêm 1/6 cặp so với 2 mà vẫn không có FP trên 39 ảnh calib. Không chọn 16 vì kiểm tra ảnh raw cho thấy `img_0011` (người chơi tennis) bị ghép với `img_0008` (hai người trượt tuyết), pHash distance 16; đây là loại nhầm có thể loại oan ảnh tốt. |
| `second_opinion.conf` | 0,25 | 0,6 | wrong class: 0,56/0,83 → 0,62/0,83; missing: 0,50/1,00 → 0,57/1,00 | Ở ngưỡng 0,6, precision nhích lên mà không giảm recall của hai lỗi chính so với 0,25. Với các lỗi chèn khác, loose box đạt 0,20/0,20 và false positive 0,36/1,00; các cảnh báo này còn nhiều nhiễu, nên phải để người quyết định. |

Một điểm calib có thể đánh lừa là chỉ có 6 lỗi near-duplicate chèn sẵn: mỗi lỗi làm recall đổi 16,7 điểm phần trăm. Calib không có false positive ở pHash 16, nhưng cặp raw `img_0011`/`img_0008` xem bằng mắt lại rõ ràng không trùng. Vì vậy mình chọn ngưỡng thấp hơn 16, chấp nhận bỏ sót một phần recall để giảm rủi ro xóa nhầm. Ở ngưỡng cuối 14, intake loại 22/224 ảnh: 2 hỏng, 3 quá nhỏ, 5 rò rỉ test, 8 trùng byte và 4 gần trùng.

## 4. Cửa chặn và điều pipeline không bắt được

Đã chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`: còn 6 lỗi bắt buộc do thiếu nhãn, kết luận **Rework**, mã thoát **20**, log ghi không xuất dataset và `work/exp_nb/clean_v1` không tồn tại. Đây xác nhận ảnh thiếu nhãn không được biến thành ảnh nền, và gate chặn phát hành khi không có người gán.

Hai điểm mù có bằng chứng: (1) pHash 16 gây ghép nhầm hai cảnh khác nhau trên raw, dù sweep calib báo precision 1,00; (2) checker model cũng có thể bỏ sót hoặc dự đoán sai, vì các metric calib ở conf 0,6 chỉ có precision 0,57 cho missing và 0,63 cho wrong class. Nếu cả nhãn lẫn model cùng bỏ sót một vật hoặc cùng nhầm lớp, phép so sánh không phát hiện được. Calib chỉ có 39 ảnh và raw không có ground truth cho mọi cảnh báo, nên các số trên không chứng minh độ chính xác trên toàn bộ lô.

## 5. Train: raw vs clean

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.701 ± 0.025 | 0.487 ± 0.008 | 0.759 ± 0.003 | 0.625 ± 0.019 |

Chênh mAP50 (clean − raw) = **-0.025**.


## 6. Quyết định và ghi chú AI

a. Quyết định cuối: **Hold**. Để tiến tới Release, cần người duyệt xử lý toàn bộ cảnh báo còn lại (38/202 ảnh, cao hơn ngưỡng 10%) và gán nhãn còn thiếu trước khi chạy lại pipeline. 

b. 
Không dùng
