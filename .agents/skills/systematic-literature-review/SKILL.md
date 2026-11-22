---
name: systematic-literature-review
description: Standalone systematic literature review workflow (NOT assigned to PYH production roles).
---

# Systematic Literature Review (Non-PYH Standalone)

## Ràng buộc PYH (bắt buộc)
- Skill này **không** thuộc bất kỳ vai nào trong `profiles/company.yaml` (đã loại khỏi `researcher` và `medical_expert`).
- Tuyệt đối **không** dùng để săn đề tài (`topic_research`), phân tích kênh (`channel_analytics`), hay nghiên cứu bằng chứng y khoa (`research`) trong xưởng PYH.
- Xưởng PYH tra cứu bằng chứng y khoa qua CLI chính thức của Europe PMC / Elsevier / PubMed theo `pyh-medical-expert`; bỏ các đường dẫn không tồn tại như `/mnt/skills/...` hay `/mnt/user-data/...`.

## Overview

Standalone multi-paper literature survey helper for general research outside the PYH video factory pipeline:
1. Clarify topic scope, paper count (≤ 50), citation format (APA/IEEE/BibTeX), and local workspace output path.
2. Query real academic APIs available in the active environment; never fabricate paper metadata, DOIs, or abstracts.
3. Synthesize themes, methodology comparisons, and limitations faithfully with verifiable citations.
