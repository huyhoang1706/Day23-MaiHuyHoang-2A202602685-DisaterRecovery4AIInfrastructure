# Postmortem — DR Drill Lab 23

Blameless: drill kiểm tra hệ thống và runbook, không quy lỗi cho cá nhân.

## 1. Timeline

| ISO time | Sự kiện | Evidence |
|---|---|---|
| 2026-10-09T05:06:02 | outage Region A bắt đầu | `chaos/chaos-events.jsonl:4` |
| 2026-10-09T05:06:02 | user đầu tiên bị ảnh hưởng | `reports/drill-2-withdr.jsonl:45` |
| 2026-10-09T05:06:17 | health check alert A UNHEALTHY | `reports/health-events.jsonl:2` |
| 2026-10-09T05:06:29 | operator confirm cutover | `reports/runbook-run.jsonl:2` |
| 2026-10-09T05:06:37 | request đầu tiên OK từ B, resolved | `reports/drill-2-withdr.jsonl:62` |

## 2. RTO/RPO đo được vs mục tiêu — gap ở bước nào?

- RTO mục tiêu 300s; đo được **34.4s**; gap **265.6s dưới mục tiêu** (`reports/measure-drill-2.json:24`).
- RPO mục tiêu 300s; đo được **2.0s / 1 document**; gap **298.0s dưới mục tiêu** (`reports/failover-events.jsonl:2`).
- Bước tốn nhiều giây nhất là health-check detection: 14.85s thực tế (floor cấu hình 15s); kế tiếp là operator handoff 11.91s và GPU warm-up 6.24s.

## 3. Root cause (5 whys)

1. User lỗi vì edge vẫn route tới Region A bị netblock.
2. Edge không đổi ngay vì DNS chỉ đổi sau khi target ready.
3. Alert cần ba lỗi liên tiếp mỗi 5s để chống flapping.
4. Failover cần operator confirm vì runbook là semi-automated.
5. Outage thật có thể làm restore fail nếu thiếu snapshot/model version; do đó runbook log version và abort nếu target không ready.

## 4. Action items

| # | Action item | Owner | Deadline | Giảm RTO/RPO bao nhiêu giây |
|---|---|---|---|---:|
| 1 | On-call alert và 1-click confirm có audit log | SRE | 2026-10-23 | ~10s RTO |
| 2 | Test interval 3s với false-positive budget | Platform SRE | 2026-10-30 | tối đa ~6s RTO |
| 3 | Warm standby và kiểm tra manifest replica | ML Platform | 2026-10-30 | ~6s RTO |

## 5. Ba câu hỏi bắt buộc

1. `interval × threshold = 5 × 3 = 15s`; detection 14.8s, khoảng **43.0%** RTO (`reports/health-events.jsonl:2`, `reports/measure-drill-2.json:24`).
2. Interval 1s với threshold 3 giảm floor 15s xuống 3s, tối đa **12s**, đổi lại là 5 lần probe và nguy cơ flap cao hơn.
3. Nếu A mất vĩnh viễn 6 giờ, `docs_lost=1` là một document ingest sau snapshot chưa có ở B; cần xác định và khôi phục từ source of truth.
