from healthvideo.workflows.runner import _execution_brief


def test_execution_brief_drops_diagnosis_only_limit_and_keeps_the_task():
    brief = (
        "Tạo storyboard/storyboard.yaml và assets/asset-manifest.yaml theo script đã duyệt. "
        "Lượt chẩn đoán này chỉ ghi báo cáo; chưa giao chạy agent, chưa sửa hoặc chạy test kỹ thuật. "
        "Nộp bằng healthvideo step storyboard."
    )
    result = _execution_brief(brief)
    assert "chỉ ghi báo cáo" not in result
    assert result.startswith("Tạo storyboard/storyboard.yaml")
    assert result.endswith("Nộp bằng healthvideo step storyboard.")
    assert "Trong vòng này chỉ đọc và ghi báo cáo" not in _execution_brief(
        "Sửa beat S02. Trong vòng này chỉ đọc và ghi báo cáo.")
