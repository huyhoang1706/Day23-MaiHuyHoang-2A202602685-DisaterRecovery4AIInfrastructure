"""BƯỚC 3c — SINH VIÊN VIẾT. Tự động hoá runbook §4 "Runbook: Region Chính Down".

7 bước trên slide, mỗi bước 1 dòng log có ts. Log này CHÍNH LÀ timeline của postmortem.
  1 xac_nhan_outage          — probe cả 2 region, đừng tin 1 lần fail (dùng nhiều lần
                              hoặc gọi health_checker.probe nếu đã viết xong 3a)
  2 thong_bao_incident       — ts của dòng này là mốc "operator biết tin", LUÔN LUÔN
                              SAU t_outage trong chaos-events (không thể trùng — operator
                              không thể biết ngay giây outage xảy ra). Ghi cả 2 ts vào
                              log để postmortem tính được "độ trễ thông báo".
  3 scale_gpu_pool           — gọi HÀM `failover.failover(...)` MỘT LẦN DUY NHẤT. Hàm
                              đó tự làm đủ 5 bước con (verify/restore/scale/wait/cutover)
                              và tự ghi log riêng vào reports/failover-events.jsonl.
  4 verify_state_replica     — KHÔNG gọi lại failover — chỉ ĐỌC kết quả (vector count +
                              weights ở region phụ) từ dict mà bước 3 trả về, để log vào
                              runbook-run.jsonl cho postmortem đọc 1 chỗ duy nhất.
  5 dns_cutover              — cũng chỉ đọc lại: kết quả cutover có ok hay không.
  6 verify_golden_signals    — 10 request thật vào region phụ: p95 latency + error rate
  7 post_incident            — elapsed_s + lệnh đo RTO

BÁN TỰ ĐỘNG, KHÔNG FULL-AUTO (§4: "failover đầu tiên nên là bán tự động — alert +
1-click confirm — tránh flapping gây failover 2 chiều liên tục"). Mặc định phải hỏi
người vận hành confirm; --auto chỉ dùng trong CI/khi chấm điểm.

Chạy:  python dr/runbook.py --primary a --target b --backend fs
"""
import argparse
import json
import pathlib
import sys
import time

import httpx

sys.path.insert(0, ".")
from dr import failover as fo  # noqa: E402

LOG = pathlib.Path("reports/runbook-run.jsonl")
URL = {"a": "http://127.0.0.1:8001", "b": "http://127.0.0.1:8002"}


def step(n, name, **kw):
    """TODO: ghi 1 dòng {ts, iso, step, name, ...} vào LOG."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.time(), "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "step": n, "name": name, **kw}
    with LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))
    return rec


def confirm(auto: bool, msg: str) -> bool:
    """TODO: auto=True -> True; ngược lại hỏi y/N. Đừng bỏ hàm này đi."""
    return auto or input(f"{msg} [y/N] ").strip().lower() in {"y", "yes"}


def run(primary: str, target: str, backend: str, auto: bool) -> dict:
    """TODO: 7 bước ở trên."""
    started = time.time()
    failures, observations = 0, []
    for attempt in range(3):
        try:
            response = httpx.get(f"{URL[primary]}/readyz", timeout=2.0)
            ready = response.status_code == 200
        except httpx.HTTPError:
            ready = False
        observations.append(ready)
        failures += not ready
        if attempt < 2:
            time.sleep(5)
    # A short stability window lets the independently-running health checker record
    # its threshold transition before an operator cuts traffic over.
    time.sleep(5)
    outage = failures == 3
    step(1, "xac_nhan_outage", primary=primary, probes=observations, confirmed=outage)
    if not outage:
        return {"ok": False, "reason": "primary_not_confirmed_down"}
    announced = step(2, "thong_bao_incident", primary=primary, target=target,
                     outage_confirmed_at=time.time())
    if not confirm(auto, f"Fail over region-{primary} to region-{target}?"):
        step(7, "post_incident", ok=False, reason="operator_declined", elapsed_s=round(time.time() - started, 2))
        return {"ok": False, "reason": "operator_declined"}
    result = fo.failover(target, backend, wait=60.0)
    step(3, "scale_gpu_pool", failover_ok=result.get("ok"), result=result)
    if not result.get("ok"):
        step(7, "post_incident", ok=False, reason=result.get("reason"), elapsed_s=round(time.time() - started, 2))
        return result
    state = result.get("state", {})
    step(4, "verify_state_replica", target=target, weights=bool((state or {}).get("vectors") is not None), state=state)
    step(5, "dns_cutover", target=target, cutover=result.get("cutover", False))
    samples = []
    for _ in range(10):
        began = time.time()
        try:
            response = httpx.get(f"{URL[target]}/v1/infer", timeout=3.0)
            samples.append({"ok": response.status_code == 200, "latency_ms": round((time.time() - began) * 1000, 1)})
        except httpx.HTTPError:
            samples.append({"ok": False, "latency_ms": round((time.time() - began) * 1000, 1)})
    latencies = sorted(s["latency_ms"] for s in samples)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    error_rate = round(sum(not s["ok"] for s in samples) / len(samples), 3)
    step(6, "verify_golden_signals", requests=len(samples), p95_latency_ms=p95, error_rate=error_rate)
    step(7, "post_incident", ok=True, elapsed_s=round(time.time() - started, 2),
         measure_command="python3 tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl --target-rto 300")
    return {"ok": True, "announcement": announced, "failover": result, "p95_latency_ms": p95,
            "error_rate": error_rate}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--primary", default="a")
    p.add_argument("--target", default="b")
    p.add_argument("--backend", default="fs", choices=["fs", "minio"])
    p.add_argument("--auto", action="store_true")
    a = p.parse_args()
    print(json.dumps(run(a.primary, a.target, a.backend, a.auto), indent=2))
