"""
Prompt construction for the UAV flight analysis LLM.

Optimized for:
- Qwen/Qwen2.5-1.5B-Instruct
- CPU inference
- hard max output budget (~100 new tokens)
- HTML output for Odoo
"""


import json

SYSTEM_PROMPT = """
You are a UAV flight analyst.

Return ONLY valid HTML for Odoo.
No markdown. No backticks. No extra text.

Use exactly this structure:
<div class="flight-analysis">
  <p>...</p>
  <ul>
    <li>...</li>
    <li>...</li>
    <li>...</li>
  </ul>
</div>

Strict rules:
- Output must be between 65 and 90 words.
- Use exactly 1 paragraph and exactly 3 list items.
- First sentence must classify the flight and state overall risk as exactly one of: LOW, MEDIUM, HIGH.
- The paragraph must contain 2 sentences.
- Each list item must be a short analytical finding, not a raw metric dump.
- Interpret the data instead of repeating all values.
- If vibration_level is HIGH, it means high vibration severity, not low vibration.
- Keep all HTML tags closed.
"""


def build_prompt(metrics: dict, tokenizer) -> str:
    """Build a compact chat-template prompt for Qwen2.5-Instruct."""
    total_dist = metrics.get("total_distance", 0)
    duration = metrics.get("flight_duration", 0)
    max_h = metrics.get("max_h_speed", 0)
    max_acc = metrics.get("max_acceleration", 0)

    analytics_raw = metrics.get("analytics", "")
    if isinstance(analytics_raw, str):
        try:
            analytics = json.loads(analytics_raw) if analytics_raw else {}
        except (json.JSONDecodeError, TypeError):
            analytics = {}
    else:
        analytics = analytics_raw or {}

    avg_speed = total_dist / duration if duration > 0 else 0
    hover_ratio = analytics.get("hover_ratio", 0)
    path_efficiency = analytics.get("path_efficiency", 0)
    turn_count = analytics.get("turn_count", 0)
    vibration_level = analytics.get("vibration_level", "N/A")
    vibration_rms = analytics.get("vibration_rms", 0)
    gps_jumps = analytics.get("gps_jumps", 0)
    acceleration_spikes = analytics.get("acceleration_spikes", 0)

    user_message = f"""
Generate a short but complete HTML flight conclusion.

Available output budget: maximum 100 new tokens.
Try to use most of the budget and do not end after one sentence.

Flight data:
- avg_speed_mps: {avg_speed:.1f}
- max_speed_mps: {max_h:.1f}
- max_acceleration_mps2: {max_acc:.1f}
- hover_ratio_pct: {hover_ratio}
- path_efficiency_pct: {path_efficiency}
- turn_count: {turn_count}
- vibration_level: {vibration_level}
- vibration_rms_mps2: {vibration_rms}
- gps_jumps: {gps_jumps}
- acceleration_spikes: {acceleration_spikes}

Task:
- classify flight profile
- assign overall risk: LOW, MEDIUM, or HIGH
- provide exactly 3 analytical findings

Important:
- HIGH vibration_level means elevated vibration severity
- low anomaly counts support lower risk
- output only HTML
"""

    prompt = tokenizer.apply_chat_template(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )
    return prompt