#!/usr/bin/env python3
import argparse, json, re, sys
from pathlib import Path

STYLE_CONFIG = {
    "CINEMATIC": ("Điện ảnh (Live Action)", "photorealistic, cinematic lighting, 8k, highly detailed, shot on 35mm lens, shallow depth of field, blockbuster movie style"),
    "ANIME": ("Anime (Hoạt hình Nhật)", "anime style, studio ghibli, makoto shinkai style, vibrant colors, detailed background, high quality 2d animation"),
    "PAINTING": ("Tranh vẽ (Digital Art)", "digital painting, oil painting texture, artistic style, concept art, artstation, masterpiece, intricate details"),
    "RENDER_3D": ("3D Render", "3d render, unreal engine 5, octane render, global illumination, highly detailed, 8k resolution, ray tracing"),
    "COMIC_BOOK": ("Truyện tranh (Comic Book)", "comic book style, graphic novel, bold outlines, halftone patterns, high contrast, dynamic lighting, marvel comics style"),
    "PIXEL_ART": ("Pixel Art", "pixel art, 16-bit, retro gaming style, highly detailed pixel art, isometric perspective, vibrant colors"),
    "WATERCOLOR": ("Màu nước (Watercolor)", "watercolor painting, soft edges, color bleeding, traditional art, ethereal, dreamy, delicate brushstrokes"),
    "CYBERPUNK": ("Cyberpunk", "cyberpunk style, neon lights, futuristic city, high tech, sci-fi, dark atmosphere, holographic elements"),
    "STEAMPUNK": ("Steampunk", "steampunk style, brass gears, steam powered, victorian era, intricate machinery, sepia tones, retro-futuristic"),
    "NONE": ("Tự do", ""),
}
MODEL_CANDIDATES = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.0-flash"]


def get_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


def refine_prompt(client, raw_input: str, style: str, media_type: str) -> str:
    label, suffix = STYLE_CONFIG.get(style, STYLE_CONFIG["CINEMATIC"])
    system_instruction = f"""
Bạn là một chuyên gia kỹ sư prompt (Prompt Engineer) hàng đầu thế giới cho các mô hình AI tạo sinh như Gemini Image (Banana Pro) và Veo (Video).
Nhiệm vụ của bạn là nhận ý tưởng thô từ người dùng và viết lại thành một prompt tiếng Anh cực kỳ chi tiết, chất lượng cao để tạo ra kết quả tốt nhất.
YÊU CẦU:
1. Chỉ trả về nội dung prompt tiếng Anh đã tối ưu. Không giải thích, không thêm râu ria.
2. Tích hợp phong cách: {label}. ({suffix})
3. Loại media mục tiêu: {'Video (Veo 3.1) - Cần mô tả chuyển động, góc máy' if media_type == 'VIDEO' else 'Hình ảnh (Gemini Pro Image) - Cần mô tả bố cục, chi tiết tĩnh'}.
4. Nếu input là tiếng Việt, hãy dịch và phóng tác sang tiếng Anh thật hay.
"""
    last_err = None
    for model in MODEL_CANDIDATES:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=raw_input,
                config={"system_instruction": system_instruction, "temperature": 0.7},
            )
            return (resp.text or raw_input).strip()
        except Exception as e:
            last_err = e
            if not _is_retryable_model_error(e):
                raise
    raise last_err or RuntimeError("AI model failed")


def parse_duration_to_seconds(d: str) -> int:
    s = (d or "").lower()
    secs = 0
    m = re.search(r"(\d+)\s*(m|phút|minute)", s)
    if m: secs += int(m.group(1)) * 60
    m = re.search(r"(\d+)\s*(s|giây|second)", s)
    if m: secs += int(m.group(1))
    if secs == 0:
        m = re.search(r"^(\d+)$", s.strip())
        if m: secs = int(m.group(1)) * 60
    return secs or 60


def _is_retryable_model_error(e) -> bool:
    msg = str(e).lower()
    return any(x in msg for x in ["not found", "not supported", "404", "model", "publisher model"])


def _json_loads_loose(txt: str) -> dict:
    txt = (txt or "{}").strip()
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"```(?:json)?\s*(.*?)```", txt, re.S | re.I)
        if m:
            return json.loads(m.group(1).strip())
        start = txt.find("{")
        end = txt.rfind("}")
        if start >= 0 and end > start:
            return json.loads(txt[start:end+1])
        raise


def generate_video_script(client, topic: str, duration: str, style: str) -> dict:
    label, suffix = STYLE_CONFIG.get(style, STYLE_CONFIG["CINEMATIC"])
    total_seconds = parse_duration_to_seconds(duration)
    total_scenes = max(1, (total_seconds + 7) // 8)
    system_instruction = f"""
Bạn là một chuyên gia biên kịch và đạo diễn hình ảnh chuyên nghiệp.
Tạo kịch bản video chi tiết dựa trên chủ đề yêu cầu.
YÊU CẦU BẮT BUỘC:
1. Tạo chính xác {total_scenes} cảnh quay.
2. Mỗi cảnh quay thời lượng cố định 8s.
3. Tối ưu đồng nhất nhân vật: xác định character sheet chi tiết và lặp lại trong prompt từng cảnh.
4. Mỗi cảnh có sceneNumber, duration, description tiếng Việt, prompt tiếng Anh chi tiết cho Veo 3.1, phong cách {label} ({suffix}).
5. Chỉ trả JSON hợp lệ dạng: {{"title":"...","characterSheet":"...","scenes":[{{"sceneNumber":1,"duration":"8s","description":"...","prompt":"..."}}]}}
"""
    last_err = None
    for model in MODEL_CANDIDATES:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=f"Chủ đề: {topic}. Tổng cảnh: {total_scenes}.",
                config={"system_instruction": system_instruction, "response_mime_type": "application/json"},
            )
            obj = _json_loads_loose(resp.text or "{}")
            scenes = obj.get("scenes") or []
            if not scenes:
                raise RuntimeError("AI không trả về danh sách cảnh")
            return obj
        except Exception as e:
            last_err = e
            if not _is_retryable_model_error(e):
                raise
    raise last_err or RuntimeError("AI model failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["refine", "script"], required=True)
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--style", default="CINEMATIC")
    ap.add_argument("--media-type", default="IMAGE")
    ap.add_argument("--input-file", type=Path)
    ap.add_argument("--topic", default="")
    ap.add_argument("--duration", default="60 seconds")
    ap.add_argument("--output-file", type=Path, required=True)
    args = ap.parse_args()
    client = get_client(args.api_key)
    if args.mode == "refine":
        lines = [x.strip() for x in args.input_file.read_text(encoding="utf-8").splitlines() if x.strip()]
        results = []
        for i, line in enumerate(lines, 1):
            try:
                results.append({"index": i, "originalIdea": line, "prompt": refine_prompt(client, line, args.style, args.media_type), "ok": True})
            except Exception as e:
                results.append({"index": i, "originalIdea": line, "prompt": "", "ok": False, "error": str(e)})
        args.output_file.write_text(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        obj = generate_video_script(client, args.topic, args.duration, args.style)
        args.output_file.write_text(json.dumps({"ok": True, "script": obj}, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
