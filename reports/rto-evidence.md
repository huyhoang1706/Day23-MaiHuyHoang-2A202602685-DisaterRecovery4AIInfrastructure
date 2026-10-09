# RTO/RPO Evidence — Lab 23

Mọi số dưới đây lấy từ JSONL của lần drill này.

## 1. Drill 1 — không có DR

| Chỉ số | Giá trị | Cách đo | Evidence |
|---|---:|---|---|
| t_outage | 2026-10-09T05:04:41 | `action:kill` | `chaos/chaos-events.jsonl:2` |
| Request fail đầu tiên | +0.0s | `ok:false` đầu tiên sau outage | `reports/drill-1-nodr.jsonl:17` |
| Request thành công sau đó | không có | Không có `ok:true` sau outage | `reports/measure-drill-1.json:25` |
| RTO | NO_RECOVERY | measure tool | `reports/measure-drill-1.json:27` |

## 2. Drill 2 — có DR

| Mốc | +giây từ t_outage | Cách đo | Evidence |
|---|---:|---|---|
| t_outage | 0.0s | `action:kill` | `chaos/chaos-events.jsonl:4` |
| User thấy lỗi đầu tiên | 0.1s | `ok:false` đầu | `reports/drill-2-withdr.jsonl:45` |
| Health check phát hiện | 14.8s | `to:UNHEALTHY, region:a` | `reports/health-events.jsonl:2` |
| Snapshot restore xong | 26.8s | `2_restore_snapshot` | `reports/failover-events.jsonl:2` |
| Region phụ ready | 33.0s | `4_wait_ready` | `reports/failover-events.jsonl:4` |
| DNS cutover | 33.0s | `5_dns_cutover` | `reports/failover-events.jsonl:5` |
| **RTO đo được** | **34.4s** | `ok:true` đầu từ B | `reports/drill-2-withdr.jsonl:62` |

| Chỉ số | Đo được | Mục tiêu | Verdict |
|---|---:|---:|---|
| RTO — Inference API | 34.4s | 300s | PASS |
| RPO — Vector DB | 2.0s / 1 doc | 300s | PASS |

Measure tool xác nhận `valid:true`, `warnings:[]`, `recovered_by_region:"b"`, và `rto_verdict:"PASS"` trong `reports/measure-drill-2.json:2`.

## 3. RTO của tôi gồm những gì

| Thành phần | Giây | Nó đến từ đâu | Giảm được bằng cách nào |
|---|---:|---|---|
| Health-check detect floor | 14.85 | `interval_s=5.0`, `threshold=3`, floor 15s trong `reports/health-events.jsonl:2` | Giảm interval/threshold sau khi kiểm tra flap. |
| Operator confirm / handoff | 11.91 | alert đến verify target: `reports/health-events.jsonl:2`, `reports/failover-events.jsonl:1` | Alert trực tiếp và 1-click confirm. |
| Snapshot restore | 0.00 | `2_restore` đến `3_scale`: `reports/failover-events.jsonl:2`, `reports/failover-events.jsonl:3` | Kiểm tra replica định kỳ. |
| GPU pool warm-up | 6.24 | `waited_s` tại `reports/failover-events.jsonl:4` | Warm standby. |
| DNS/LB TTL cache | 1.46 | cutover đến request B: `reports/failover-events.jsonl:5`, `reports/drill-2-withdr.jsonl:62` | TTL thấp hơn/health-aware LB. |
| **Tổng (làm tròn)** | **34.4** | 14.85 + 11.91 + 0.00 + 6.24 + 1.46 | Khớp RTO loadgen. |
