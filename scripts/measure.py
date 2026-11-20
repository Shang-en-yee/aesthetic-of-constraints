#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
measure.py — 逐帧测量脚本（本文所有数字的来源）

用法:
    python measure.py <video.mp4> [--fps-ratio 2.0]

输出:
    一份 JSON，含分辨率、帧率、时长、中位亮度、背景噪声、
    全局位移中位、调色板、切点时刻，以及可选的字幕墨量曲线。

依赖: opencv-python, numpy
"""
import sys, json, argparse
import numpy as np
import cv2


def to_hex(bgr):
    b, g, r = [int(v) for v in bgr]
    return "#%02X%02X%02X" % (r, g, b)


def luma(bgr):
    return 0.114 * bgr[0] + 0.587 * bgr[1] + 0.299 * bgr[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--fps-ratio", type=float, default=1.0,
                    help="播放倍速，例如 2 表示录屏以 2x 播放，用于把时长换算回原速")
    ap.add_argument("--ink-roi", type=str, default="0.30,0.85,0.86,0.93",
                    help="字幕行 ROI: x0,x1,y0,y1（相对比例）")
    ap.add_argument("--out", type=str, default=None)
    a = ap.parse_args()

    cap = cv2.VideoCapture(a.video)
    if not cap.isOpened():
        sys.exit(f"cannot open: {a.video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    x0, x1, y0, y1 = [float(v) for v in a.ink_roi.split(",")]
    ix0, ix1 = int(x0 * W), int(x1 * W)
    iy0, iy1 = int(y0 * H), int(y1 * H)

    # 用于相位相关的小图（速度快、精度够）
    SW = 640
    SH = int(SW * H / W)

    prev_small = None
    prev_big = None
    diffs, lums, inks, shifts = [], [], [], []
    palette_px = None
    flat_samples = []

    while True:
        ok, fr = cap.read()
        if not ok:
            break

        big = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        small = cv2.cvtColor(
            cv2.resize(fr, (SW, SH), interpolation=cv2.INTER_AREA),
            cv2.COLOR_BGR2GRAY).astype(np.float32)

        lums.append(float(small.mean()))

        row = big[iy0:iy1, ix0:ix1]
        inks.append(int((row > 150).sum()))

        if prev_small is None:
            diffs.append(0.0)
            shifts.append((0.0, 0.0))
        else:
            diffs.append(float(np.abs(small - prev_small).mean()))
            try:
                (dx, dy), _ = cv2.phaseCorrelate(
                    cv2.GaussianBlur(prev_small, (0, 0), 3),
                    cv2.GaussianBlur(small, (0, 0), 3))
                shifts.append((float(dx), float(dy)))
            except cv2.error:
                shifts.append((0.0, 0.0))

        prev_small = small
        if palette_px is None and len(lums) == 1:
            palette_px = fr[::10, ::10].reshape(-1, 3).astype(np.float32)

        # 每 2 秒采一帧，用于估计"最平坦区域"的噪声（颗粒/纸纹检测）
        if len(lums) % int(fps * 2) == 0:
            gg = big
            bank = []
            for gy in range(6):
                for gx in range(8):
                    py0, py1 = int(gy * H / 6), int((gy + 1) * H / 6)
                    px0, px1 = int(gx * W / 8), int((gx + 1) * W / 8)
                    bank.append(float(gg[py0:py1, px0:px1].std()))
            flat_samples.append(np.percentile(bank, 10))

        prev_big = big

    cap.release()

    lums = np.array(lums)
    diffs = np.array(diffs)
    inks = np.array(inks, dtype=float)
    shifts = np.array(shifts)

    # 调色板（k-means, k=5）
    k = 5
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(palette_px, k, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k)
    order = np.argsort(-counts)
    palette = [{"hex": to_hex(centers[i]), "share": round(100 * counts[i] / counts.sum(), 1)}
               for i in order]

    # 背景噪声：全片"最平坦 10% 区块"的标准差，逐 2 秒采样后取中位
    # 该指标对纯色背景（无颗粒）给出 1 以下，对纸纹/辉光给出数个单位。
    if flat_samples:
        bg_sigma = round(float(np.median(flat_samples)), 2)
    elif prev_big is not None:
        patch = prev_big[int(0.05 * H):int(0.13 * H), int(0.30 * W):int(0.42 * W)]
        bg_sigma = round(float(patch.std()), 2)
    else:
        bg_sigma = None

    # 切点：局部峰值
    med = np.median(diffs) + 1e-6
    thr = max(np.percentile(diffs, 92), med * 4)
    cuts = [round(i / fps, 2) for i in np.where(diffs > thr)[0]]

    # 合并相邻切点
    merged = []
    for c in cuts:
        if not merged or c - merged[-1] > 0.35:
            merged.append(c)

    result = {
        "video": a.video,
        "resolution": [W, H],
        "fps": round(fps, 3),
        "frames": n,
        "duration_recorded": round(n / fps, 2),
        "duration_original": round(n / fps * a.fps_ratio, 2),
        "luma_median": round(float(np.median(lums)), 1),
        "bg_sigma": bg_sigma,
        "shift_median_px": [round(float(np.median(shifts[:, 0])), 2),
                            round(float(np.median(shifts[:, 1])), 2)],
        "diff_median": round(float(np.median(diffs)), 2),
        "cuts": merged[:80],
        "cut_count": len(merged),
        "ink_curve": {
            "min": int(inks.min()),
            "max": int(inks.max()),
            "p10": int(np.percentile(inks, 10)),
            "p90": int(np.percentile(inks, 90)),
        },
        "palette": palette,
    }

    txt = json.dumps(result, ensure_ascii=False, indent=2)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(txt)
        print(f"written: {a.out}")
    else:
        print(txt)


if __name__ == "__main__":
    main()

