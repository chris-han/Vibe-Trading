from src.adapters.feishu_visualization_adapter import FeishuVisualizationAdapter


def test_build_card_payload_downgrades_actions_to_markdown_for_schema_v2():
    adapter = FeishuVisualizationAdapter()

    payload = adapter.build_card_payload(
        "Test Card",
        "Body text",
        actions=[{"text": "Open details"}, {"label": "Retry"}],
    )

    assert '"tag": "action"' not in payload
    assert 'Available actions' in payload
    assert 'Open details' in payload
    assert 'Retry' in payload