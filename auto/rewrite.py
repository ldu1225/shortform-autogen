"""기존 런의 소재·컷은 그대로 두고 대본만 현재 규칙으로 다시 써서 재렌더(10/19: 눈높이·속도 규칙 바꾼 뒤 포르쉐 릴스 재작업용).
사용: python3 -I auto/rewrite.py runs/2026-10-19g auto1
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "auto"))
import plan  # noqa: E402


def main():
    run_dir, name = Path(sys.argv[1]), sys.argv[2]
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(\w*)", run_dir.name)
    day = plan.Day(m.group(1), m.group(2))
    spec_p = run_dir / f"spec_{name}.json"
    spec = json.loads(spec_p.read_text())
    report = json.loads((run_dir / "auto_report.json").read_text())
    info = next((i for i in report["items"] if i["product"] == spec["product"]), None)
    if info is None:  # 렌더 실패로 보고서에 없던 편(10/19 리터로봇) → 새 항목으로 추가
        n = len(report["items"]) + 1
        info = {"product": spec["product"], "file": f"{n}_{re.sub(r'[^A-Za-z0-9]+', '_', spec['product']).strip('_')}.mp4", "videos": []}
        report["items"].append(info)
    picks = []
    for f in ("auto_pick_viral.json", "auto_pick.json"):
        if (run_dir / f).exists():
            picks += json.loads((run_dir / f).read_text())["items"]
    item = next(i for i in picks if f"{i['brand']} {i['product']}" == spec["product"])
    if info.get("kind") == "viral" or item.get("kind") == "viral":
        item["kind"] = "viral"
    info.setdefault("kind", item.get("kind", "product")); info.setdefault("category", item.get("category")); info.setdefault("facts", item.get("facts", [])); info.setdefault("korea", item.get("korea"))
    day.log(f"대본 재작성: {spec['product']} ({info.get('kind', 'product')})")
    vids = plan.viral_videos(day, item) if item.get("kind") == "viral" else plan.official_videos(day, item)
    w = plan.write_spec(day, item, [])
    n_body = len([c for c in str(w["props"].get("bodySubs", "")).split("/") if c.strip()]) or 5
    cuts = spec["cuts"]
    cuts.pop("훅", None)
    mid = cuts["중반부"]
    if len(mid) > n_body:
        cuts["중반부"] = mid[:n_body]
    while len(cuts["중반부"]) < n_body:  # 청크가 늘면 마지막 컷을 4초 뒤로 복제
        last = dict(cuts["중반부"][-1]); last["in"] = round(last["in"] + 4, 2); cuts["중반부"].append(last)
    for c in cuts["중반부"]:
        c.pop("dur", None)
    idx = int(re.sub(r"\D", "", name) or 1)
    new_spec = plan.make_spec(day, item, w, cuts, idx)
    preview, qa = plan.render(day, new_spec)
    caption = plan.fix_credit(plan.clean_caption(w["caption"]), vids, cuts, item)
    dst = day.out / info["file"]
    shutil.copy(preview, dst)
    dst.with_suffix(".txt").write_text(caption)
    title = (w.get("title") or "").strip()
    info.update({"layout": w["layout"], "qa": qa, "caption": caption, "title": title, "hook": None, "theme": plan.spec_theme(new_spec)})
    day.report = report
    day.save()
    day.log(f"재작성 완료 {dst.name} · {qa} · 제목: {title}")
    print(json.dumps({"title": title, "narration": w["narration"], "caption": caption, "qa": qa}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
