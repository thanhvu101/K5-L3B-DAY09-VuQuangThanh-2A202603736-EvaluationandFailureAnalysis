# Judge audit

Chạy (trong `src/`):

```bash
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5
```

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **có** | dùng (kèm sửa rubric bên dưới) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **không** (κ và R dưới sàn) | loại — không được làm gate |

Ma trận nhầm lẫn (FAIL là positive): tone `tp=24, fp=4, fn=6, tn=66`; helpful `tp=9, fp=0, fn=21, tn=70`.
Rogan-Gladen: tone quan sát 0.28 → hiệu chỉnh 0.300; helpful quan sát 0.09 → hiệu chỉnh 0.300
(helpful bỏ sót 70% lỗi nên báo sai tỉ lệ lỗi thật xuống còn 1/3 — đúng lý do không dùng làm cổng).

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | **Người** | Judge coi "nha/check giúp em" là thân thiện; rubric tone phải fail cách xưng "em" và từ đệm suồng sã với khách. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | **Người** | Xưng "bạn" với khách lớn tuổi; thêm luật cấm đại từ "bạn/em" khi chưa biết tuổi khách. |
| 3 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | **Người** | Judge chỉ thấy "Dạ, vui lòng"; rubric phải fail giọng ra lệnh ("không cần nhắn thêm") và thiếu thời hạn/next step. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người** | Judge phạt vì thiếu xin lỗi; rubric ghi rõ: ngắn nhưng đủ ý (số tiền + thời gian) là PASS, xin lỗi là tùy chọn. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | **Người** | Từ "refund" nằm trong từ vựng CS LogiX cho phép; thêm allowlist từ vựng trước khi chấm tone. |
| 6 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | **Người** | Judge helpful không đọc ledger nên không thấy sai tiền. Đây là lỗi FM-08, phải chấm bằng code (`reply_ledger_match`), không phải judge. |
| 7 | HL-016 reply xin lỗi + "đã hoàn 55.000đ" (ledger 35.000đ) | PASS | FAIL | **Người** | Cùng lỗi: judge chỉ chấm giọng điệu; rubric helpful phải đối chiếu số tiền với ledger — ngoài phạm vi của judge nên tiêu chí này bị loại khỏi gate. |

## Kết luận

- **Loại `helpful`**: κ=0.375 < 0.6 và recall=0.300 < 0.7. Judge bắt được 9/30 case fail, bỏ sót 21 case "sai tiền" —
  dùng làm gate sẽ cho qua gần như mọi câu trả lời sai về tiền. Hành động: chuyển kiểm tra số tiền sang code
  (`reply_ledger_match` trong M3), chỉ giữ helpful như tín hiệu tham khảo.
- **Dùng `tone_ok`**: κ=0.757, P=0.857, R=0.800 đạt sàn, nhưng phải sửa rubric theo 5 case trên (allowlist từ vựng,
  cấm đại từ suồng sã, cấm giọng ra lệnh, không bắt buộc xin lỗi) trước khi dùng cho PR sau.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (`judge_*_public.csv`); chưa có tập held-out mới,
  nên calibration này không chứng minh judge tổng quát hoá. Cần nhãn người mới trước khi dùng judge làm blocking gate.

