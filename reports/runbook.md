# Runbook — Region chính down

Dùng `--auto` chỉ cho drill/CI. Vận hành bình thường cần xác nhận `y`.

| # | Bước | Lệnh | Biết là xong khi | Ai làm |
|---|---|---|---|---|
| 1 | Xác nhận outage | `python3 chaos/kill_region.py status` lặp 3 lần, cách 5s | `a.ready=false` ba lần, B `alive=true` | on-call |
| 2 | Mở incident + bấm giờ | `date -u +%FT%TZ` | timestamp ở `reports/runbook-run.jsonl` | incident commander |
| 3 | Restore và scale B | `python3 dr/runbook.py --primary a --target b --backend fs` | `2_restore_snapshot`, `3_scale_pool` trong `reports/failover-events.jsonl` | on-call |
| 4 | Chờ B ready | `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8002/readyz` | HTTP 200 và `4_wait_ready ready:true` | ML platform |
| 5 | DNS/LB cutover | `curl -s http://127.0.0.1:8080/edge/state` | `active_region=b`, log có `5_dns_cutover` | on-call |
| 6 | Verify golden signals | `python3 dr/runbook.py --primary a --target b --backend fs` sau khi outage được xác nhận | 10 request, error rate 0, p95 trong SLO | service owner |
| 7 | Đo RTO + postmortem | `python3 tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl --target-rto 300` | `valid:true`, `rto_verdict:PASS` | incident commander |

**Rollback:** chỉ trả traffic về A khi `/readyz` của A trả 200 ba lần liên tiếp, replica/model version đã đối chiếu, và incident commander phê duyệt. On-call thực hiện verify → restore/scale → wait ready → DNS cutover; không sửa `edge/active_region` thủ công. Nếu target chưa ready thì abort, không cutover.
