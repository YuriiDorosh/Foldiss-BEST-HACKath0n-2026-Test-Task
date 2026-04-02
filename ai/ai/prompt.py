"""
Prompt construction for the UAV flight analysis LLM.

The prompt follows the Qwen2.5-Instruct chat template and is designed
for the LoRA fine-tune training data format in training_data.jsonl.
"""

SYSTEM_PROMPT = (
    "You are an expert UAV flight data analyst. "
    "Given numerical telemetry metrics from an ArduPilot flight log, "
    "produce a concise, structured flight analysis report. "
    "Use the following sections: Flight Summary, Performance Analysis, "
    "Safety Observations, and Recommendations. "
    "Be specific, reference the numbers, and keep the report under 400 words."
)


def build_prompt(metrics: dict) -> str:
    """
    Build the full chat-template prompt string for Qwen2.5-Instruct.

    The model is called with transformers pipeline("text-generation"),
    so we return the raw string including special tokens as required
    by the tokenizer's apply_chat_template with tokenize=False.

    Args:
        metrics: dict with keys total_distance, max_h_speed, max_v_speed,
                 max_acceleration, max_altitude_gain, flight_duration,
                 gps_count, imu_count, gps_sample_rate, imu_sample_rate.

    Returns:
        Formatted prompt string.
    """
    user_message = (
        f"Analyse the following UAV flight telemetry and write a structured report:\n\n"
        f"- Total distance flown:      {metrics.get('total_distance', 0):.1f} m\n"
        f"- Max horizontal speed:      {metrics.get('max_h_speed', 0):.2f} m/s\n"
        f"- Max vertical speed:        {metrics.get('max_v_speed', 0):.2f} m/s\n"
        f"- Max dynamic acceleration:  {metrics.get('max_acceleration', 0):.2f} m/s²\n"
        f"- Max altitude gain:         {metrics.get('max_altitude_gain', 0):.1f} m\n"
        f"- Flight duration:           {metrics.get('flight_duration', 0):.1f} s\n"
        f"- GPS records (3D fix):      {metrics.get('gps_count', 0)}\n"
        f"- IMU records:               {metrics.get('imu_count', 0)}\n"
        f"- GPS sample rate:           {metrics.get('gps_sample_rate', 0):.2f} Hz\n"
        f"- IMU sample rate:           {metrics.get('imu_sample_rate', 0):.2f} Hz\n"
    )

    # Qwen2.5-Instruct chat template (no tokenizer dependency at prompt-build time)
    prompt = (
        "<|im_start|>system\n"
        f"{SYSTEM_PROMPT}<|im_end|>\n"
        "<|im_start|>user\n"
        f"{user_message}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    return prompt
