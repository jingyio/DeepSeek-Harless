from src.adapters.final_response_integrity import supplemental_final


def test_intermediate_report_followed_by_short_addendum_needs_repair():
    events = [
        {"type": "assistant/message", "data": {"step": 8, "message": {"content": [
            {"type": "text", "text": "完整决定：" + "证据和建议。" * 180}]}}},
        {"type": "tool/call", "data": {"step": 8, "name": "read_pinned_pdf_pages"}},
    ]
    assert supplemental_final(events, "补充一项页码事实。" * 10)
    assert not supplemental_final(events, "完整独立交付。" * 150)


def test_long_intermediate_without_tool_is_not_mistaken_for_a_split_delivery():
    events = [{"type": "assistant/message", "data": {"step": 8, "message": {
        "content": [{"type": "text", "text": "分析。" * 300}]}}}]
    assert not supplemental_final(events, "最终决定。" * 10)
