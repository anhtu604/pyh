---
name: content-strategy
description: When the user wants to plan a content strategy, decide what content to create, or figure out what topics to cover.
metadata:
  version: 2.1.5
---

# Content Strategy (PYH-Scoped)

## Ràng buộc PYH (bắt buộc)
- Chỉ áp dụng cho kênh giáo dục sức khỏe dự phòng tiếng Việt **Protect Your Health (PYH)**; bỏ toàn bộ phần SaaS/B2B, Buyer Stage (`pricing/demo/buy`), Scoring Template 40/30/20/10, Calendar Split 60/30/10, và link-building.
- Dùng thang điểm 100 điểm `THANG_DIEM` của PYH (`viral_engagement`, `urgency_prevention`, `evidence_readiness`, `short_feasibility`) trong `pyh-researcher`.
- Không tự bịa nhu cầu/xu hướng nếu không có tín hiệu hoặc nguồn xác minh; tín hiệu tìm kiếm không đồng nghĩa đang hot nếu thiếu số liệu thật.

## Searchable vs Shareable

Every piece of content must be searchable, shareable, or both.

**Searchable content** captures existing demand (people actively searching for answers):
- Target a specific question or misconception people actually ask.
- Match search intent directly with a clear, honest answer and verified sources.
- Use clear titles and headings that mirror real viewer questions.

**Shareable content** creates demand (spreads ideas and helps people understand):
- Lead with a counterintuitive mechanism, clinical nuance, or everyday habit check.
- Explain *why* a common belief misleads, backed by verified evidence.
- Keep framing empathetic and practical rather than fear-mongering.

## Content Pillars and Topic Clusters

Organize topics around repeatable pillars (e.g., everyday habits, lab-result literacy, common health myths, organ mechanisms) and connect related questions without repeating the exact same video angle.

## Content Ideation Sources

1. **Search & Question Data**: What real patients/viewers ask around symptoms, tests, supplements, and daily routines.
2. **Doctor & Channel Feedback**: Questions surfaced in doctor notes, comments (`top_comments`), and Google Sheet tabs (`THANG_DIEM`, `TRANH_CAI_MXH`, `Y_HOC_MOI`).
3. **Forum / Public Debate Signals**: Recurring misconceptions worth clarifying with evidence.
4. **Channel Insights**: Observed high-retention hooks and drop-off patterns from `topics/channel-insights.yaml` when available.

## Output Format

Follow the PYH schema and rubric required by the active step (`pyh-researcher` / `pyh-scout`); never invent unverified demand metrics or enqueue topics without authorization.
