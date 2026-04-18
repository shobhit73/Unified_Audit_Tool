import sys
import os
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path so 'utils' package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Inject a fake 'streamlit' module so tests don't need the real package installed
sys.modules['streamlit'] = MagicMock()

from utils import ui_components


def test_inject_premium_styles_calls_streamlit_markdown():
    with patch.object(ui_components.st, 'markdown') as mock_md:
        ui_components.inject_premium_styles()
        mock_md.assert_called_once()
        args, kwargs = mock_md.call_args
        assert isinstance(args[0], str)
        assert kwargs.get('unsafe_allow_html') is True


def test_render_premium_header_with_subtitle():
    with patch.object(ui_components.st, 'markdown') as mock_md:
        ui_components.render_premium_header('Title', 'Sub')
        # Should call markdown twice: title and subtitle
        assert mock_md.call_count == 2
        first_call = mock_md.call_args_list[0][0][0]
        assert '### Title' in first_call
        second_call_kwargs = mock_md.call_args_list[1][1]
        assert second_call_kwargs.get('unsafe_allow_html') is True


def test_render_premium_header_without_subtitle():
    with patch.object(ui_components.st, 'markdown') as mock_md:
        ui_components.render_premium_header('Only Title')
        mock_md.assert_called_once()
        assert '### Only Title' in mock_md.call_args[0][0]


def test_action_hub_container_returns_streamlit_container():
    with patch.object(ui_components.st, 'container') as mock_container:
        mock_container.return_value = 'container-object'
        result = ui_components.action_hub_container(type='warning')
        mock_container.assert_called_once()
        assert result == 'container-object'


def test_render_finding_card_renders_correct_html():
    with patch.object(ui_components.st, 'markdown') as mock_md:
        data = {'Label A': 'Value A', 'Label B': 'Value B'}
        ui_components.render_finding_card('My Title', data, type='warning')
        mock_md.assert_called_once()
        html = mock_md.call_args[0][0]
        # Basic assertions that the HTML includes provided content and colors for warning type
        assert 'My Title' in html
        assert 'Value A' in html and 'Value B' in html
        assert '#fffaf3' in html  # background for warning
        assert '#e8881f' in html  # border color for warning
        # unsafe flag should be set
        assert mock_md.call_args[1].get('unsafe_allow_html') is True


if __name__ == '__main__':
    # Run tests as simple functions when executed directly
    test_inject_premium_styles_calls_streamlit_markdown()
    test_render_premium_header_with_subtitle()
    test_render_premium_header_without_subtitle()
    test_action_hub_container_returns_streamlit_container()
    test_render_finding_card_renders_correct_html()
    print('All tests passed')
