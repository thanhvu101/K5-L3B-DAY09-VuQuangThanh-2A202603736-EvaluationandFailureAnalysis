# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case chính — tin số ngày trong ticket thay vì DB (FM-03)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, row `E-002/11` trong `reports/eval_seeded_regression.json` |
| Triệu chứng | Lab 8 FAIL `status resolved != denied`; ledger ghi `refund_vnd=20000`, `refund_count=1`, label đòi `0/0`; agent trả lời "đã hoàn 20.000đ" |
| Bước sai đầu tiên | Event **3** — `model_override {"delay_days": 5}`: agent thay `orders.delay_days=2` (DB) bằng "trễ 5 ngày" (ticket) |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng contract (`owner_order_only`, allowlist read-only); event 2 `investigator` trả `lookup_order.visible=true` với `delay_days=2`. Chỉ từ event 3 dữ liệu mới bị bóp méo; event 4 `quote 20000` và event 6 `reply` chỉ là hệ quả |
| Failure mode | **FM-03** `ticket_trust` (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11`: không có `model_override`; event 3 `quote {"amount_vnd": 0, "reason": "no_entitlement"}` → event 4 `reply` từ chối, ledger 0 |
| Regression test | `tests/test_lab9_trace_case.py::test_c002_ticket_trust_fails_on_seeded_regression_and_passes_on_fixed` — `DbFactKept` fail trên `seeded_regression`, pass trên `fixed`; `RefundAmountCorrect` fail/pass theo ledger |
| Chưa chắc chắn | Trace chứng minh agent đổi delay, không chứng minh *vì sao* (MockLLM deterministic); muốn biết prompt nào gây override phải chạy model thật có log prompt |

## Case phụ — reply nói số khác ledger (FM-08, grader cũ bỏ lọt)

`python -m lab9.trace_case --shape seeded_regression --claim C-008 --seed 11`

| Trường | Nội dung |
|---|---|
| Triệu chứng | Lab 8 **PASS** (proposal 35.000 = label, ledger 20.000 = label) nhưng event 5 `reply` = "đã hoàn **35.000đ**" trong khi ledger giữ **20.000đ** (approval `A-008` cap 20.000) |
| Bước sai đầu tiên | Event **5** `reply`: dùng số agent đề xuất (`proposal`) thay vì số host đã ghi (`committed`) |
| Vì sao là bước *đầu tiên* | Event 3 `quote 35000` và event 4 `refund_history 0` đúng; ledger đúng sau khi host cap. Chỉ câu trả lời sai — nên `pass_rate` không bắt được |
| Failure mode | **FM-08** `misreport` |
| Đối chứng | `fixed C-008@11`: event 4 `reply "đã hoàn 20.000đ"` = ledger 20.000đ |
| Regression test | `tests/test_lab9_trace_case.py::test_c008_misreport_fails_on_seeded_regression_and_passes_on_fixed` — `ReplyLedgerMatch` fail/pass |
| Chưa chắc chắn | Khi trace có event `reply` mà reply không nêu số tiền trong khi ledger > 0, metric fail (fail-closed). Shape không phát `reply` (swarm tham chiếu) được chấm bằng `RunResult.refund_effects` — cùng bất biến "số agent báo = số ledger", nhưng đây là khoảng trống quan sát của Lab 8, không phải bằng chứng agent gian |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được (đã thêm `tests/test_lab9_trace_case.py`).
